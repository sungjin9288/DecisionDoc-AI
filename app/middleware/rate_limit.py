"""app/middleware/rate_limit.py — IP-based rate limiting for auth endpoints."""
from __future__ import annotations

import ipaddress
import os
import time
import threading
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

_login_attempts: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()

LOGIN_WINDOW_SECONDS = 900   # 15 minutes
LOGIN_MAX_ATTEMPTS = 10      # per IP per window
LOCKOUT_DURATION_SECONDS = 900

_RATE_LIMITED_PATHS = {"/auth/login", "/auth/ldap-login"}

# Only trust X-Forwarded-For from known reverse-proxy IPs.
# Set TRUSTED_PROXIES="10.0.0.1,172.16.0.0/12" to enable.
_TRUSTED_PROXIES: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()
_raw = os.getenv("TRUSTED_PROXIES", "")
for _cidr in (s.strip() for s in _raw.split(",") if s.strip()):
    try:
        _TRUSTED_PROXIES.add(ipaddress.ip_network(_cidr, strict=False))
    except ValueError:
        pass


def _get_client_ip(request: Request) -> str:
    """Return the real client IP, only trusting XFF from configured proxies."""
    peer_ip = request.client.host if request.client else "unknown"
    if peer_ip == "unknown":
        return peer_ip

    forwarded = request.headers.get("X-Forwarded-For", "")
    if not forwarded or not _TRUSTED_PROXIES:
        return peer_ip

    try:
        peer_addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return peer_ip

    if any(peer_addr in net for net in _TRUSTED_PROXIES):
        return forwarded.split(",")[0].strip()
    return peer_ip


async def rate_limit_middleware(request: Request, call_next):
    """Rate-limit login endpoints to prevent brute-force attacks."""
    if request.url.path not in _RATE_LIMITED_PATHS:
        return await call_next(request)

    ip = _get_client_ip(request)

    now = time.time()

    with _lock:
        # Expire old attempts
        _login_attempts[ip] = [
            t for t in _login_attempts[ip] if now - t < LOGIN_WINDOW_SECONDS
        ]
        if len(_login_attempts[ip]) >= LOGIN_MAX_ATTEMPTS:
            oldest = _login_attempts[ip][0]
            retry_after = max(1, int(LOCKOUT_DURATION_SECONDS - (now - oldest)))
            return JSONResponse(
                status_code=429,
                content={
                    "error": f"너무 많은 로그인 시도. {retry_after}초 후 다시 시도하세요.",
                    "code": "TOO_MANY_REQUESTS",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )
        _login_attempts[ip].append(now)

    response = await call_next(request)

    # Clear attempts on successful login
    if response.status_code == 200:
        with _lock:
            _login_attempts.pop(ip, None)

    return response


def install_rate_limit_middleware(app) -> None:
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=rate_limit_middleware)


def clear_attempts_for_test() -> None:
    """Clear all rate limit state — for use in tests only."""
    with _lock:
        _login_attempts.clear()
