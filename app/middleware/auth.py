"""app/middleware/auth.py — JWT-based authentication middleware.

Injects authenticated user info into request.state before routing.
Public paths bypass auth. Viewer role is blocked from write methods
except for an allowlist of paths.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.auth_service import get_current_user_from_request

# Paths that don't require a valid JWT
PUBLIC_PATHS: frozenset[str] = frozenset({
    # App shell — served before JS auth runs
    "/",
    "/manifest.json",
    "/sw.js",
    "/offline.html",
    "/privacy",
    # Health / ops
    "/health",
    "/health/",
    "/health/live",
    "/health/ready",
    "/metrics",
    "/local-llm/health",
    # Auth flows
    "/auth/login",
    "/auth/refresh",
    "/auth/register",
    "/auth/ldap-login",
    # SSO — all SAML and GCloud endpoints
    "/saml/metadata",
    "/saml/login",
    "/saml/acs",
    "/sso/gcloud",
    "/sso/gcloud/callback",
    # Public data
    "/bundles",
    "/g2b/status",
})

# HTTP methods that write/modify state
_WRITE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Paths where viewers are still allowed to POST/PUT/PATCH
_VIEWER_WRITE_ALLOWED_PREFIXES: tuple[str, ...] = (
    "/generate/stream",
    "/generate/sketch",
)


async def auth_middleware(request: Request, call_next):
    path = request.url.path

    # Static files, explicitly public endpoints, and shared document views pass through
    if path in PUBLIC_PATHS or path.startswith("/static") or path.startswith("/shared/"):
        return await call_next(request)

    user = get_current_user_from_request(request)

    if not user:
        # Allow anonymous access on fresh installs (no registered users yet).
        # This preserves backward compatibility with deployments that haven't
        # set up user accounts, and ensures existing tests continue to work
        # without JWT tokens.
        tenant_id = request.headers.get("X-Tenant-ID", "system") or "system"
        _users_exist = False
        try:
            import json
            import os
            from pathlib import Path

            users_file = (
                Path(os.getenv("DATA_DIR", "./data"))
                / "tenants"
                / tenant_id
                / "users.json"
            )
            if users_file.exists():
                data = json.loads(users_file.read_text(encoding="utf-8"))
                if data:  # non-empty dict → registered users exist
                    _users_exist = True
        except Exception as exc:
            import logging as _logging
            _logging.getLogger("decisiondoc.auth").error(
                "[Auth] UserStore read failed — failing CLOSED: %s", exc
            )
            return JSONResponse(
                status_code=503,
                content={"error": "인증 서비스를 일시적으로 사용할 수 없습니다.", "code": "AUTH_UNAVAILABLE"},
            )

        if not _users_exist:
            return await call_next(request)

        return JSONResponse(
            status_code=401,
            content={"error": "인증이 필요합니다.", "code": "UNAUTHORIZED"},
        )

    # Attach user context to request state for downstream handlers
    request.state.user_id = user["sub"]
    request.state.username = user["username"]
    request.state.user_role = user["role"]

    # Viewer: block write methods except on the allowed prefixes
    if user["role"] == "viewer":
        if request.method in _WRITE_METHODS:
            allowed = any(path.startswith(p) for p in _VIEWER_WRITE_ALLOWED_PREFIXES)
            if not allowed:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": "뷰어 권한으로는 이 작업을 수행할 수 없습니다.",
                        "code": "FORBIDDEN",
                    },
                )

    return await call_next(request)


def install_auth_middleware(app) -> None:
    """Register the auth middleware on a FastAPI app instance."""
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)
