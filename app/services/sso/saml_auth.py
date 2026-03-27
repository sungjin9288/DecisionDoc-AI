"""SAML 2.0 authentication helpers.

Tries onelogin/python3-saml first; falls back to basic XML parsing if unavailable.
"""
from __future__ import annotations

import base64
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone

from app.storage.sso_store import SAMLConfig


@dataclass
class SAMLUser:
    username: str
    display_name: str
    email: str
    role: str


def build_authn_request(config: SAMLConfig) -> tuple[str, str]:
    """Build SAML SP-initiated AuthnRequest.

    Returns (redirect_url, relay_state).
    Uses onelogin if available, else builds minimal XML.
    """
    relay_state = str(uuid.uuid4())

    try:
        return _build_with_onelogin(config, relay_state)
    except ImportError:
        return _build_basic_authn_request(config, relay_state)


def parse_saml_response(config: SAMLConfig, saml_response_b64: str) -> SAMLUser | None:
    """Parse and validate SAML response. Returns SAMLUser or None."""
    try:
        return _parse_with_onelogin(config, saml_response_b64)
    except ImportError:
        return _parse_basic(config, saml_response_b64)


def build_sp_metadata(config: SAMLConfig) -> str:
    """Generate SP metadata XML."""
    try:
        return _sp_metadata_onelogin(config)
    except ImportError:
        return _sp_metadata_basic(config)


# ── onelogin implementation ────────────────────────────────────────────────────

def _build_with_onelogin(config: SAMLConfig, relay_state: str) -> tuple[str, str]:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    settings = _onelogin_settings(config)
    req = {"https": "on", "http_host": "", "script_name": "/saml/acs",
           "server_port": "443", "get_data": {}, "post_data": {}}
    auth = OneLogin_Saml2_Auth(req, settings)
    redirect_url = auth.login(return_to=relay_state)
    return redirect_url, relay_state


def _parse_with_onelogin(config: SAMLConfig, saml_response_b64: str) -> SAMLUser | None:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    settings = _onelogin_settings(config)
    req = {"https": "on", "http_host": "", "script_name": "/saml/acs",
           "server_port": "443", "get_data": {},
           "post_data": {"SAMLResponse": saml_response_b64}}
    auth = OneLogin_Saml2_Auth(req, settings)
    auth.process_response()
    if not auth.is_authenticated():
        return None
    attrs = auth.get_attributes()
    username = _first_attr(attrs, config.attribute_username) or auth.get_nameid()
    display_name = _first_attr(attrs, config.attribute_display_name) or username
    email = _first_attr(attrs, "email") or username
    role = _first_attr(attrs, config.attribute_role) or "member"
    return SAMLUser(username=username, display_name=display_name, email=email, role=role)


def _sp_metadata_onelogin(config: SAMLConfig) -> str:
    from onelogin.saml2.metadata import OneLogin_Saml2_Metadata
    settings = _onelogin_settings(config)
    metadata = OneLogin_Saml2_Metadata.builder(settings["sp"])
    return metadata


def _onelogin_settings(config: SAMLConfig) -> dict:
    return {
        "strict": False,
        "debug": False,
        "sp": {
            "entityId": config.sp_entity_id,
            "assertionConsumerService": {
                "url": config.sp_acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "privateKey": config.sp_private_key.replace("-----BEGIN RSA PRIVATE KEY-----", "")
                         .replace("-----END RSA PRIVATE KEY-----", "").replace("\n", "") if config.sp_private_key else "",
            "x509cert": config.sp_certificate.replace("-----BEGIN CERTIFICATE-----", "")
                       .replace("-----END CERTIFICATE-----", "").replace("\n", "") if config.sp_certificate else "",
        },
        "idp": {
            "entityId": config.idp_entity_id,
            "singleSignOnService": {
                "url": config.idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": config.idp_certificate.replace("-----BEGIN CERTIFICATE-----", "")
                       .replace("-----END CERTIFICATE-----", "").replace("\n", "") if config.idp_certificate else "",
        },
    }


# ── Basic XML fallback ─────────────────────────────────────────────────────────

def _build_basic_authn_request(config: SAMLConfig, relay_state: str) -> tuple[str, str]:
    import urllib.parse
    import zlib

    request_id = "_" + uuid.uuid4().hex
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    xml = (
        f'<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        f'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{request_id}" Version="2.0" IssueInstant="{now}" '
        f'Destination="{config.idp_sso_url}" '
        f'AssertionConsumerServiceURL="{config.sp_acs_url}" '
        f'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">'
        f'<saml:Issuer>{config.sp_entity_id}</saml:Issuer>'
        f'</samlp:AuthnRequest>'
    )
    deflated = zlib.compress(xml.encode("utf-8"))[2:-4]
    encoded = base64.b64encode(deflated).decode("utf-8")
    params = urllib.parse.urlencode({
        "SAMLRequest": encoded,
        "RelayState": relay_state,
    })
    redirect_url = f"{config.idp_sso_url}?{params}"
    return redirect_url, relay_state


def _parse_basic(config: SAMLConfig, saml_response_b64: str) -> SAMLUser | None:
    try:
        xml_bytes = base64.b64decode(saml_response_b64)
        root = ET.fromstring(xml_bytes)
        ns = {
            "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
            "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
        }
        # Check status
        status_code = root.find(".//samlp:StatusCode", ns)
        if status_code is not None:
            val = status_code.get("Value", "")
            if "Success" not in val:
                return None

        # Get NameID
        name_id = root.find(".//saml:NameID", ns)
        username = name_id.text if name_id is not None else ""

        # Get attributes
        attrs: dict[str, str] = {}
        for attr in root.findall(".//saml:Attribute", ns):
            name = attr.get("Name", "")
            val_el = attr.find("saml:AttributeValue", ns)
            if val_el is not None and val_el.text:
                attrs[name] = val_el.text

        display_name = attrs.get(config.attribute_display_name) or attrs.get("displayName") or username
        email = attrs.get(config.attribute_username) or attrs.get("email") or username
        role = attrs.get(config.attribute_role) or "member"
        return SAMLUser(username=username or email, display_name=display_name, email=email, role=role)
    except Exception:
        return None


def _sp_metadata_basic(config: SAMLConfig) -> str:
    return (
        f'<?xml version="1.0"?>'
        f'<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
        f'entityID="{config.sp_entity_id}">'
        f'<md:SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true" '
        f'protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
        f'<md:AssertionConsumerService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{config.sp_acs_url}" index="1"/>'
        f'</md:SPSSODescriptor>'
        f'</md:EntityDescriptor>'
    )


def _first_attr(attrs: dict, key: str) -> str:
    val = attrs.get(key, [])
    if isinstance(val, list):
        return val[0] if val else ""
    return str(val)
