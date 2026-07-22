"""SSO-related endpoints extracted from app/main.py."""

from __future__ import annotations

import dataclasses
import logging
import secrets as _secrets
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.config import get_jwt_secret_key
from app.dependencies import get_tenant_id, require_admin
from app.schemas import LDAPLoginRequest, UpdateSSOConfigRequest
from app.services.auth_service import get_request_user_store

router = APIRouter(tags=["sso"])
_MAX_SAML_RESPONSE_CHARACTERS = 1_500_000
_logger = logging.getLogger("decisiondoc.sso")


# ── Helper functions ──────────────────────────────────────────────────────────


def _get_sso_store(request: Request):
    from app.storage.sso_store import get_sso_store

    return get_sso_store(
        get_tenant_id(request),
        data_dir=request.app.state.data_dir,
        backend=request.app.state.state_backend,
    )


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
        if k == "bind_password":
            if v == "***":
                continue
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


def _update_saml_config(cfg, payload: dict, store) -> None:
    for k, v in payload.items():
        if k == "sp_private_key":
            if v == "***":
                continue
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


def _update_gcloud_config(cfg, payload: dict, store) -> None:
    for k, v in payload.items():
        if k == "client_secret":
            if v == "***":
                continue
            setattr(cfg, k, store.encrypt_secret(v))
        elif hasattr(cfg, k):
            setattr(cfg, k, v)


def _update_oauth2_config(cfg, payload: dict, store) -> None:
    for key, value in payload.items():
        if key == "client_secret":
            if value == "***":
                continue
            setattr(cfg, key, store.encrypt_secret(value))
        elif hasattr(cfg, key):
            setattr(cfg, key, value)


def _saml_config_with_secret(cfg, store):
    saml = dataclasses.replace(cfg.saml)
    if saml.sp_private_key:
        saml.sp_private_key = store.decrypt_secret(saml.sp_private_key)
    return saml


def _require_provider(cfg, provider: str) -> None:
    if cfg.provider.value != provider:
        raise HTTPException(
            status_code=400, detail=f"{provider} SSO가 활성화되어 있지 않습니다."
        )


def _apply_config_update(cfg, payload: dict, store) -> None:
    from app.storage.sso_store import SSOProvider

    if payload.get("provider") is not None:
        cfg.provider = SSOProvider(payload["provider"])
    _update_ldap_config(cfg.ldap, payload.get("ldap") or {}, store)
    _update_saml_config(cfg.saml, payload.get("saml") or {}, store)
    _update_gcloud_config(cfg.gcloud, payload.get("gcloud") or {}, store)
    _update_oauth2_config(cfg.oauth2, payload.get("oauth2") or {}, store)
    cfg.updated_at = datetime.now(timezone.utc).isoformat()


def _provision_sso_user(
    request: Request,
    tenant_id: str,
    username: str,
    display_name: str,
    email: str,
    role: str,
):
    """Create or update SSO user on first login."""
    from app.storage.user_store import UserRole

    usr_store = get_request_user_store(request, tenant_id)
    user = usr_store.get_by_username(username)
    if user is None:
        random_pw = _secrets.token_urlsafe(32)
        try:
            user_role = (
                UserRole(role)
                if role in ("admin", "member", "viewer")
                else UserRole.MEMBER
            )
        except ValueError:
            user_role = UserRole.MEMBER
        user = usr_store.create(
            username=username,
            display_name=display_name or username,
            email=email,
            password=random_pw,
            role=user_role,
        )
    return user


def _create_jwt_for_user(user, *, session_id: str) -> str:
    """Create JWT token for a provisioned user."""
    payload = {
        "sub": user.user_id,
        "username": user.username,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "tenant_id": user.tenant_id,
        "credential_version": user.credential_version,
        "session_id": session_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return pyjwt.encode(payload, get_jwt_secret_key(), algorithm="HS256")


def _issue_sso_tokens(request: Request, user) -> dict[str, str]:
    from app.services.auth_service import create_refresh_token
    from app.storage.auth_session_store import (
        AuthSessionStoreError,
        get_auth_session_store,
    )

    try:
        session_id = get_auth_session_store(
            user.tenant_id,
            data_dir=getattr(request.app.state, "data_dir", None),
            backend=getattr(request.app.state, "state_backend", None),
        ).create(
            user_id=user.user_id,
            credential_version=user.credential_version,
        )
    except AuthSessionStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail="인증 세션을 일시적으로 생성할 수 없습니다.",
        ) from exc

    return {
        "access_token": _create_jwt_for_user(user, session_id=session_id),
        "refresh_token": create_refresh_token(
            user.user_id,
            user.tenant_id,
            credential_version=user.credential_version,
            session_id=session_id,
        ),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/auth/sso-status")
def get_sso_status(request: Request):
    """Return only the public provider state needed by the login screen."""
    provider = _get_sso_store(request).get().provider.value
    return {
        "provider": provider,
        "enabled": provider in {"ldap", "saml", "gcloud"},
    }


@router.get("/admin/sso/config")
def get_sso_config(request: Request):
    """Get SSO configuration for the tenant (admin only)."""
    require_admin(request)
    store = _get_sso_store(request)
    cfg = store.get()
    d = dataclasses.asdict(cfg)
    # Serialize provider enum value
    d["provider"] = cfg.provider.value
    _mask_sso_secrets(d)
    return d


@router.put("/admin/sso/config")
async def update_sso_config(request: Request, body: UpdateSSOConfigRequest):
    """Update SSO configuration for the tenant (admin only)."""
    require_admin(request)
    payload = body.model_dump(exclude_unset=True)
    store = _get_sso_store(request)
    try:
        store.update(lambda cfg: _apply_config_update(cfg, payload, store))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/admin/sso/test-ldap")
def test_ldap(request: Request):
    """Test LDAP connection with current service-account config (admin only)."""
    require_admin(request)
    from app.services.sso.ldap_auth import test_ldap_connection

    store = _get_sso_store(request)
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
    from app.services.sso.saml_auth import build_sp_metadata

    store = _get_sso_store(request)
    cfg = store.get()
    xml = build_sp_metadata(_saml_config_with_secret(cfg, store))
    return Response(content=xml, media_type="application/xml")


@router.get("/saml/login")
def saml_login(request: Request):
    """Initiate SAML SP-initiated login flow."""
    from app.services.sso.saml_auth import build_authn_request

    store = _get_sso_store(request)
    cfg = store.get()
    _require_provider(cfg, "saml")
    redirect_url, relay_state = build_authn_request(
        _saml_config_with_secret(cfg, store)
    )
    response = RedirectResponse(redirect_url)
    response.set_cookie(
        "saml_relay_state",
        relay_state,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=600,
    )
    return response


@router.post("/saml/acs")
async def saml_acs(request: Request):
    """SAML Assertion Consumer Service -- receives IdP POST-back."""
    tenant_id = get_tenant_id(request)
    from app.services.sso.saml_auth import parse_saml_response

    store = _get_sso_store(request)
    cfg = store.get()
    _require_provider(cfg, "saml")
    form = await request.form()
    saml_response_b64 = form.get("SAMLResponse", "")
    relay_state = form.get("RelayState", "")
    stored_relay_state = request.cookies.get("saml_relay_state", "")
    if (
        not isinstance(relay_state, str)
        or not relay_state
        or not stored_relay_state
        or not _secrets.compare_digest(stored_relay_state, relay_state)
    ):
        raise HTTPException(status_code=400, detail="잘못된 RelayState입니다.")
    if (
        not isinstance(saml_response_b64, str)
        or not saml_response_b64
        or len(saml_response_b64) > _MAX_SAML_RESPONSE_CHARACTERS
    ):
        raise HTTPException(status_code=400, detail="잘못된 SAML 응답입니다.")
    user = parse_saml_response(
        _saml_config_with_secret(cfg, store),
        saml_response_b64,
    )
    if not user:
        raise HTTPException(status_code=401, detail="SAML authentication failed")
    provisioned = _provision_sso_user(
        request,
        tenant_id, user.username, user.display_name, user.email, user.role
    )
    token = _issue_sso_tokens(request, provisioned)["access_token"]
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("dd_token", token, httponly=True, samesite="lax")
    resp.delete_cookie("saml_relay_state")
    return resp


@router.post("/auth/ldap-login")
async def ldap_login(request: Request, body: LDAPLoginRequest):
    """Authenticate via LDAP and return a JWT token."""
    tenant_id = get_tenant_id(request)
    from app.services.sso.ldap_auth import authenticate_ldap

    store = _get_sso_store(request)
    cfg = store.get()
    if cfg.provider.value != "ldap":
        raise HTTPException(
            status_code=400, detail="LDAP SSO가 활성화되어 있지 않습니다."
        )
    ldap = cfg.ldap
    if ldap.bind_password:
        ldap.bind_password = store.decrypt_secret(ldap.bind_password)
    try:
        user = authenticate_ldap(ldap, body.username, body.password)
    except Exception as exc:
        _logger.warning(
            "LDAP authentication service unavailable tenant_id=%s",
            tenant_id,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=502,
            detail="LDAP authentication service unavailable",
        ) from exc
    if not user:
        raise HTTPException(status_code=401, detail="Invalid LDAP credentials")
    provisioned = _provision_sso_user(
        request,
        tenant_id, user.username, user.display_name, user.email, user.role
    )
    tokens = _issue_sso_tokens(request, provisioned)
    token = tokens["access_token"]

    return {
        "token": token,
        "access_token": token,
        "refresh_token": tokens["refresh_token"],
        "user": {
            "username": provisioned.username,
            "display_name": provisioned.display_name,
            "role": provisioned.role.value
            if hasattr(provisioned.role, "value")
            else provisioned.role,
        },
    }


@router.get("/sso/gcloud")
def sso_gcloud(request: Request):
    """Initiate Google Cloud / Workspace OAuth2 login flow."""
    from app.services.sso.gcloud_auth import build_gcloud_auth_url

    store = _get_sso_store(request)
    cfg = store.get()
    _require_provider(cfg, "gcloud")
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

    stored_state = request.cookies.get("gcloud_state", "")
    if (
        not code
        or not state
        or not stored_state
        or not _secrets.compare_digest(stored_state, state)
    ):
        raise HTTPException(status_code=400, detail="잘못된 state 파라미터입니다.")
    store = _get_sso_store(request)
    cfg = store.get()
    _require_provider(cfg, "gcloud")
    if cfg.gcloud.client_secret:
        cfg.gcloud.client_secret = store.decrypt_secret(cfg.gcloud.client_secret)
    redirect_uri = str(request.base_url).rstrip("/") + "/sso/gcloud/callback"
    user_info = exchange_gcloud_code(cfg.gcloud, code, redirect_uri)
    if not user_info:
        raise HTTPException(status_code=401, detail="Google authentication failed")
    provisioned = _provision_sso_user(
        request,
        tenant_id,
        user_info["username"],
        user_info["display_name"],
        user_info["email"],
        user_info["role"],
    )
    token = _issue_sso_tokens(request, provisioned)["access_token"]
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie("dd_token", token, httponly=True, samesite="lax")
    resp.delete_cookie("gcloud_state")
    return resp
