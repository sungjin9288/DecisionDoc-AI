"""app/middleware/security_headers.py — HTTP security headers for all responses."""
from __future__ import annotations

import secrets

from fastapi import Request

_STATIC_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


async def security_headers_middleware(request: Request, call_next):
    """Add security headers (with per-request nonce for CSP) to all responses."""
    nonce = secrets.token_urlsafe(16)
    request.state.csp_nonce = nonce

    response = await call_next(request)

    csp = (
        "default-src 'self'; "
        f"script-src 'self' 'nonce-{nonce}' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "frame-ancestors 'none';"
    )

    for header, value in _STATIC_HEADERS.items():
        response.headers.setdefault(header, value)
    response.headers["Content-Security-Policy"] = csp

    return response


def install_security_headers_middleware(app) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers_middleware)
