"""app/middleware/security_headers.py — HTTP security headers for all responses.

CSP nonce support
-----------------
HTML-serving route handlers (the SPA root ``/`` and ``/offline.html``) generate a
per-request nonce via :func:`generate_csp_nonce`, stamp it onto every inline
``<script>`` element they emit, and record it on ``request.state.csp_nonce``.
This middleware reads that value (if present) and builds the ``script-src``
directive with ``'nonce-<value>'`` so only the server-issued inline scripts run.

Inline event-handler attributes (``onclick=`` …) are NOT covered by nonces, so
the single-file UI keeps all actions behind delegated listeners instead of
``on*=`` attributes. With that boundary in place, HTML responses can emit a
nonce by default while still allowing ``DECISIONDOC_CSP_NONCE_ENFORCED=0`` as a
local diagnostic escape hatch. See ``docs/development-plan.md`` §4 (M4/G5).
"""
from __future__ import annotations

import os
import secrets

from fastapi import Request

_TRUTHY = {"1", "true", "yes", "on"}


def csp_nonce_enforced() -> bool:
    """Whether per-request CSP nonces should be emitted.

    On by default for HTML responses. Set ``DECISIONDOC_CSP_NONCE_ENFORCED=0``
    only when debugging legacy static HTML outside the normal app contract.
    """
    return os.getenv("DECISIONDOC_CSP_NONCE_ENFORCED", "1").strip().lower() in _TRUTHY

_STATIC_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

# Directives that never change between requests.
_CSP_TAIL = (
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-ancestors 'none';"
)


def generate_csp_nonce() -> str:
    """Return a fresh, URL-safe CSP nonce for a single response.

    Uses :func:`secrets.token_urlsafe` (cryptographically strong). Each call
    yields a distinct value, so callers must generate the nonce once per
    request and reuse it for every inline ``<script>`` in that response.
    """
    return secrets.token_urlsafe(16)


def _build_script_src(nonce: str | None) -> str:
    """Build the ``script-src`` directive.

    Without a nonce: ``'unsafe-inline'`` keeps the UI's inline handlers working.
    With a nonce (only when :func:`csp_nonce_enforced`): ``'unsafe-inline'`` is
    dropped because CSP Level 2+ browsers ignore it anyway once a nonce is
    present — keeping it would only mislead readers about what is enforced.
    """
    if nonce:
        return f"script-src 'self' 'nonce-{nonce}'; "
    return "script-src 'self' 'unsafe-inline'; "


def _build_csp(nonce: str | None) -> str:
    return "default-src 'self'; " + _build_script_src(nonce) + _CSP_TAIL


async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses."""
    response = await call_next(request)

    nonce = getattr(request.state, "csp_nonce", None)

    for header, value in _STATIC_HEADERS.items():
        response.headers.setdefault(header, value)
    response.headers["Content-Security-Policy"] = _build_csp(nonce)

    return response


def install_security_headers_middleware(app) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=security_headers_middleware)
