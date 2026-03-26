"""SSO-related endpoints extracted from app/main.py."""

from __future__ import annotations

import dataclasses
import secrets as _secrets
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import get_jwt_secret_key
from app.dependencies import get_tenant_id, require_admin, require_auth

router = APIRouter(tags=["sso"])


# ── Helper functions ──────────────────────────────────────────────────────────


def _mask_sso_secrets(d: dict) -> None:
    """Replace secret fields with '***' for safe client response."""
    SECRET_FIELDS = {"bind_password", "client_secret", "sp_private_key"}
    for k, v in list(d.items()):
        if k in SECRET_FIELDS and v:
            d[k] = "***"
        elif isinstance(v, dict):
            _mask_sso_secrets(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    _mask_sso_secrets(item)


def _update_ldap_config(cfg, payload: dict, store) -> None:
    for k, v in payload.items():
        if k == "bind_password" and v and v != "***":
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


def _update_saml_config(cfg, payload: dict, store) -> None:
    for k, v in payload.items():
        if k == "sp_private_key" and v and v != "***":
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


def _update_gcloud_config(cfg, payload: dict, store) -> None:
    for k, v in payload.items():
        if k == "client_secret" and v and v != "***":
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


def _provision_sso_user(tenant_id: str, username: str, display_name: str, email: str, role: str):
    """Create or update SSO user on first login."""
    from app.storage.user_store import UserRole, get_user_store

    usr_store = get_user_store(tenant_id)
    user = usr_store.get_by_username(tenant_id, username)
    if user is None:
        random_pw = _secrets.token_urlsafe(32)
        try:
            user_role = UserRole(role) if role in ("admin", "member", "viewer") else UserRole.MEMBER
        except ValueError:
            user_role = UserRole.MEMBER
        user = usr_store.create(
            tenant_id=tenant_id,
            username=username,
            display_name=display_name or username,
            email=email,
            password=random_pw,
            role=user_role,
        )
    return user


def _create_jwt_for_user(user) -> str:
    """Create JWT token for a provisioned user."""
    payload = {
        "sub": user.user_id,
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "tenant_id": user.tenant_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return pyjwt.encode(payload, get_jwt_secret_key(), algorithm="HS256")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/admin/sso/config")
def get_sso_config(request: Request):
    """Get SSO configuration for the tenant (admin only)."""
    require_admin(request)
    tenant_id = get_tenant_id(request)
    from app.storage.sso_store import get_sso_store

    store = get_sso_store(tenant_id)
    cfg = store.get()
    d = dataclasses.asdict(cfg)
    # Serialize provider enum value
    d["provider"] = cfg.provider.value
    _mask_sso_secrets(d)
    return d


@router.put("/admin/sso/config")
async def update_sso_config(request: Request):
    """Update SSO configuration for the tenant (admin only)."""
    require_admin(request)
    tenant_id = get_tenant_id(request)
    payload = await request.json()
    from app.storage.sso_store import SSOProvider, get_sso_store

    store = get_sso_store(tenant_id)
    cfg = store.get()
    # Update provider
    if "provider" in payload:
        cfg.provider = SSOProvider(payload["provider"])
    # Update sub-configs (only provided fields, encrypt secrets)
    _update_ldap_config(cfg.ldap, payload.get("ldap", {}), store)
    _update_saml_config(cfg.saml, payload.get("saml", {}), store)
    _update_gcloud_config(cfg.gcloud, payload.get("gcloud", {}), store)
    cfg.updated_at = datetime.now(timezone.utc).isoformat()
    store.save(cfg)
    return {"ok": True}


@router.post("/admin/sso/test-ldap")
def test_ldap(request: Request):
    """Test LDAP connection with current service-account config (admin only)."""
    require_admin(request)
    tenant_id = get_tenant_id(request)
    from app.services.sso.ldap_auth import test_ldap_connection
    from app.storage.sso_store import get_sso_store

    store = get_sso_store(tenant_id)
    cfg = store.get()
    ldap = cfg.ldap
    # Decrypt bind password for the test
    if ldap.bind_password:
        ldap.bind_password = store.decrypt_secret(ldap.bind_password)
    result = test_ldap_connection(ldap)
    return result


@router.get("/saml/metadata")
def saml_metadata(request: Request):
    """Return SP metadata XML for IdP configuration."""
    tenant_id = get_tenant_id(request)
    from app.services.sso.saml_auth import build_sp_metadata
    from app.storage.sso_store import get_sso_store

    store = get_sso_store(tenant_id)
    cfg = store.get()
    xml = build_sp_metadata(cfg.saml)
    return Response(content=xml, media_type="application/xml")


@router.get("/saml/login")
def saml_login(request: Request):
    """Initiate SAML SP-initiated login flow."""
    tenant_id = get_tenant_id(request)
    from app.services.sso.saml_auth import build_authn_request
    from app.storage.sso_store import get_sso_store

    store = get_sso_store(tenant_id)
    cfg = store.get()
    redirect_url, relay_state = build_authn_request(cfg.saml)
    return RedirectResponse(redirect_url)


@router.post("/saml/acs")
async def saml_acs(request: Request):
    """SAML Assertion Consumer Service -- receives IdP POST-back."""
    tenant_id = get_tenant_id(request)
    from app.services.sso.saml_auth import parse_saml_response
    from app.storage.sso_store import get_sso_store

    store = get_sso_store(tenant_id)
    cfg = store.get()
    form = await request.form()
    saml_response_b64 = form.get("SAMLResponse", "")
    user = parse_saml_response(cfg.saml, saml_response_b64)
    if not user:
        raise HTTPException(status_code=401, detail="SAML authentication failed")
    provisioned = _provision_sso_user(tenant_id, user.username, user.display_name, user.email, user.role)
    token = _create_jwt_for_user(provisioned)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("dd_token", token, httponly=True, samesite="lax")
    return resp


@router.post("/auth/ldap-login")
async def ldap_login(request: Request):
    """Authenticate via LDAP and return a JWT token."""
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")
    tenant_id = get_tenant_id(request)
    from app.services.sso.ldap_auth import authenticate_ldap
    from app.storage.sso_store import get_sso_store

    store = get_sso_store(tenant_id)
    cfg = store.get()
    if cfg.provider.value != "ldap":
        raise HTTPException(status_code=400, detail="LDAP SSO가 활성화되어 있지 않습니다.")
    ldap = cfg.ldap
    if ldap.bind_password:
        ldap.bind_password = store.decrypt_secret(ldap.bind_password)
    try:
        user = authenticate_ldap(ldap, username, password)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid LDAP credentials")
    provisioned = _provision_sso_user(tenant_id, user.username, user.display_name, user.email, user.role)
    token = _create_jwt_for_user(provisioned)
    return {
        "token": token,
        "user": {
            "username": provisioned.username,
            "display_name": provisioned.display_name,
            "role": provisioned.role.value if hasattr(provisioned.role, "value") else provisioned.role,
        },
    }


@router.get("/sso/gcloud")
def sso_gcloud(request: Request):
    """Initiate Google Cloud / Workspace OAuth2 login flow."""
    tenant_id = get_tenant_id(request)
    from app.services.sso.gcloud_auth import build_gcloud_auth_url
    from app.storage.sso_store import get_sso_store

    store = get_sso_store(tenant_id)
    cfg = store.get()
    if cfg.gcloud.client_secret:
        cfg.gcloud.client_secret = store.decrypt_secret(cfg.gcloud.client_secret)
    redirect_uri = str(request.base_url).rstrip("/") + "/sso/gcloud/callback"
    auth_url, state = build_gcloud_auth_url(cfg.gcloud, redirect_uri)
    resp = RedirectResponse(auth_url)
    resp.set_cookie("gcloud_state", state, httponly=True, samesite="lax", max_age=600)
    return resp


@router.get("/sso/gcloud/callback")
async def sso_gcloud_callback(request: Request, code: str = "", state: str = ""):
    """Handle Google OAuth2 callback and provision user session."""
    tenant_id = get_tenant_id(request)
    from app.services.sso.gcloud_auth import exchange_gcloud_code
    from app.storage.sso_store import get_sso_store

    # Validate state cookie
    stored_state = request.cookies.get("gcloud_state", "")
    if stored_state and state and stored_state != state:
        raise HTTPException(status_code=400, detail="잘못된 state 파라미터입니다.")
    store = get_sso_store(tenant_id)
    cfg = store.get()
    if cfg.gcloud.client_secret:
        cfg.gcloud.client_secret = store.decrypt_secret(cfg.gcloud.client_secret)
    redirect_uri = str(request.base_url).rstrip("/") + "/sso/gcloud/callback"
    user_info = exchange_gcloud_code(cfg.gcloud, code, redirect_uri)
    if not user_info:
        raise HTTPException(status_code=401, detail="Google authentication failed")
    provisioned = _provision_sso_user(
        tenant_id, user_info["username"], user_info["display_name"],
        user_info["email"], user_info["role"],
    )
    token = _create_jwt_for_user(provisioned)
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("dd_token", token, httponly=True, samesite="lax")
    resp.delete_cookie("gcloud_state")
    return resp
