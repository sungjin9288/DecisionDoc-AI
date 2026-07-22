"""app/services/auth_service.py — JWT token creation and verification.

Tokens:
  access  — 8 hours, carries user/tenant/role and credential version
  refresh — 30 days, carries user/tenant and credential version
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import jwt

from app.config import get_jwt_secret_key
from app.tenant import require_tenant_id

if TYPE_CHECKING:
    from app.storage.state_backend import StateBackend

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8   # 8 hours
REFRESH_TOKEN_EXPIRE_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_credential_version(credential_version: int) -> int:
    if type(credential_version) is not int or credential_version < 0:
        raise ValueError("credential_version must be a non-negative integer")
    return credential_version


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: str,
    username: str,
    *,
    credential_version: int = 0,
) -> str:
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "username": username,
        "credential_version": _require_credential_version(credential_version),
        "type": "access",
        "exp": _utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, get_jwt_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(
    user_id: str,
    tenant_id: str,
    *,
    credential_version: int = 0,
) -> str:
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "credential_version": _require_credential_version(credential_version),
        "type": "refresh",
        "exp": _utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, get_jwt_secret_key(), algorithm=ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Returns the decoded payload dict, or None if invalid/expired."""
    try:
        return jwt.decode(token, get_jwt_secret_key(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_current_user_from_request(request) -> dict | None:
    """Extract and verify Bearer token from Authorization header.

    Returns the payload dict (with 'sub', 'tenant_id', 'role', 'username')
    or None if missing/invalid.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    payload = verify_token(token)
    if not payload or payload.get("type") != "access":
        return None
    return payload


def get_request_user_store(request, tenant_id: str):
    """Return the user store selected when the application was created."""
    from app.storage.user_store import get_user_store

    return get_user_store(
        tenant_id,
        data_dir=getattr(request.app.state, "data_dir", None),
        backend=getattr(request.app.state, "state_backend", None),
    )


def credentials_are_current(token_payload: dict, persisted_user) -> bool:
    """Accept legacy versionless tokens only while credentials remain at version 0."""
    token_version = token_payload.get("credential_version", 0)
    return (
        type(token_version) is int
        and token_version >= 0
        and token_version == persisted_user.credential_version
    )


def resolve_persisted_user(
    token_user: dict,
    *,
    data_dir: str | Path | None = None,
    backend: StateBackend | None = None,
) -> tuple[dict | None, bool]:
    """Resolve current user authority from tenant state.

    The returned boolean indicates whether the tenant already has persisted
    users. Fresh installs keep the legacy token-only compatibility path.
    """
    from app.storage.user_store import get_user_store

    user_id = str(token_user.get("sub") or "").strip()
    try:
        tenant_id = require_tenant_id(token_user.get("tenant_id"))
    except ValueError:
        return None, True
    if not user_id:
        return None, True

    user_store = get_user_store(
        tenant_id,
        data_dir=data_dir,
        backend=backend,
    )
    users_exist = user_store.has_any_users()
    if not users_exist:
        return token_user, False

    persisted_user = user_store.get_by_id(user_id)
    if (
        not persisted_user
        or not persisted_user.is_active
        or not credentials_are_current(token_user, persisted_user)
    ):
        return None, True

    return {
        **token_user,
        "username": persisted_user.username,
        "role": persisted_user.role.value,
    }, True
