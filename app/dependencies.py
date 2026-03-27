"""app/dependencies.py — Shared FastAPI dependency functions.

Extracted from main.py to be reusable across APIRouter modules.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Request


def require_auth(request: Request) -> None:
    """Raise 401 if the request has no authenticated user."""
    if not getattr(request.state, "user_id", None):
        raise HTTPException(status_code=401, detail="인증이 필요합니다.")


def require_admin(request: Request) -> None:
    """Raise 401/403 if the user is not an authenticated admin.

    Accepts either a valid JWT admin role OR the ops key header so that
    CI/CD scripts and admin CLI tools can also reach these endpoints.
    """
    ops_key_env = os.getenv("DECISIONDOC_OPS_KEY", "")
    if ops_key_env and request.headers.get("X-DecisionDoc-Ops-Key") == ops_key_env:
        return
    require_auth(request)
    if getattr(request.state, "user_role", "") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")


def get_tenant_id(request: Request) -> str:
    """Extract the current tenant ID from request state, defaulting to 'system'."""
    return getattr(request.state, "tenant_id", "system") or "system"


def get_user_id(request: Request) -> str:
    """Extract the authenticated user ID from request state."""
    return getattr(request.state, "user_id", "anonymous") or "anonymous"


def get_username(request: Request) -> str:
    """Extract the authenticated username from request state."""
    return getattr(request.state, "username", "anonymous") or "anonymous"
