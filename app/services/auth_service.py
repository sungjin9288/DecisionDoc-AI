"""app/services/auth_service.py — JWT token creation and verification.

Tokens:
  access  — 8 hours, carries user_id/tenant_id/role/username
  refresh — 30 days, carries user_id/tenant_id only
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


def create_access_token(user_id: str, tenant_id: str, role: str, username: str) -> str:
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "username": username,
        "type": "access",
        "exp": _utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, get_jwt_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(user_id: str, tenant_id: str) -> str:
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
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
    if not persisted_user or not persisted_user.is_active:
        return None, True

    return {
        **token_user,
        "username": persisted_user.username,
        "role": persisted_user.role.value,
    }, True
