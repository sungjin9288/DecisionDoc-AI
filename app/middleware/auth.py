"""app/middleware/auth.py — JWT-based authentication middleware.

Injects authenticated user info into request.state before routing.
Public paths bypass auth. Viewer role is blocked from write methods
except for an allowlist of paths.
"""
from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.auth.api_key import has_valid_api_key_header
from app.auth.ops_key import has_valid_ops_key_header
from app.services.auth_service import get_current_user_from_request

# Paths that don't require a valid JWT
PUBLIC_PATHS: frozenset[str] = frozenset({
    # App shell — served before JS auth runs
    "/",
    "/favicon.ico",
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
    "/version",
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

    def _attach_user_state(user_payload: dict) -> None:
        request.state.user_id = user_payload["sub"]
        request.state.username = user_payload["username"]
        request.state.user_role = user_payload["role"]

    # Static files, explicit public endpoints, invite acceptance pages, and
    # shared document views must be reachable before a JWT session exists.
    if (
        path in PUBLIC_PATHS
        or path.startswith("/static")
        or path.startswith("/shared/")
        or path.startswith("/invite/")
    ):
        user = get_current_user_from_request(request)
        if user:
            _attach_user_state(user)
        return await call_next(request)

    user = get_current_user_from_request(request)

    if not user:
        if has_valid_api_key_header(request) or has_valid_ops_key_header(request):
            return await call_next(request)

        # Allow anonymous access on fresh installs (no registered users yet).
        # This preserves backward compatibility with deployments that haven't
        # set up user accounts, and ensures existing tests continue to work
        # without JWT tokens.
        tenant_id = request.headers.get("X-Tenant-ID", "system") or "system"
        _users_exist = False
        try:
            from app.storage.user_store import get_user_store

            _users_exist = get_user_store(tenant_id).has_any_users()
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
    _attach_user_state(user)

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
