"""app/services/auth_service.py — JWT token creation and verification.

Tokens:
  access  — 8 hours, carries user_id/tenant_id/role/username
  refresh — 30 days, carries user_id/tenant_id only
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.config import get_jwt_secret_key

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
