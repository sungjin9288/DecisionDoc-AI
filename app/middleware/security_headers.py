"""app/middleware/security_headers.py — HTTP security headers for all responses."""
from __future__ import annotations

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
    """Add security headers to all responses."""
    response = await call_next(request)

    csp = (
        "default-src 'self'; "
        # The current single-file web UI still relies on inline event handlers
        # and inline script blocks. Keep this policy aligned with the shipped UI
        # until those handlers are fully refactored away.
        "script-src 'self' 'unsafe-inline'; "
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
