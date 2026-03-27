"""app/middleware/audit.py — Request-level audit logging for ISMS compliance.

Runs AFTER auth middleware so user context (user_id, role) is available.
Appends structured audit entries to the per-tenant JSONL audit log.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import Request

_log = logging.getLogger("decisiondoc.audit")

# ── Audit rules — (HTTP method, path pattern) → action type ────────────────────

AUDIT_RULES: dict[tuple[str, str], str] = {
    ("POST", "/auth/login"): "user.login",
    ("POST", "/auth/logout"): "user.logout",
    ("POST", "/generate/stream"): "doc.generate",
    ("POST", "/generate/with-attachments"): "doc.generate",
    ("POST", "/projects/{id}/imports/g2b-opportunity"): "procurement.import",
    ("POST", "/projects/{id}/procurement/evaluate"): "procurement.evaluate",
    ("POST", "/projects/{id}/procurement/recommend"): "procurement.recommend",
    ("GET", "/approvals/{id}/download/{fmt}"): "doc.download",
    ("GET", "/projects/{id}/documents/{id}/download"): "doc.download",
    ("POST", "/approvals"): "approval.create",
    ("POST", "/approvals/{id}/submit"): "approval.submit",
    ("POST", "/approvals/{id}/review/approve"): "approval.review",
    ("POST", "/approvals/{id}/review/request-changes"): "approval.review",
    ("POST", "/approvals/{id}/approve"): "approval.approve",
    ("POST", "/approvals/{id}/reject"): "approval.reject",
    ("POST", "/share"): "share.create",
    ("DELETE", "/share/{id}"): "share.revoke",
    ("POST", "/admin/users"): "user.create",
    ("PATCH", "/admin/users/{id}"): "user.update",
    ("POST", "/auth/change-password"): "user.password_change",
    ("POST", "/finetune/export"): "system.export",
}

# Paths that must always be audited
ALWAYS_AUDIT_PREFIXES: tuple[str, ...] = (
    "/admin/",
    "/auth/",
    "/approvals/",
    "/finetune/export",
)


# ── Middleware ─────────────────────────────────────────────────────────────────


async def audit_middleware(request: Request, call_next):
    """ASGI middleware: capture request metadata + append audit log entry."""
    start_time = time.time()

    # Derive session ID from cookie or header, or generate a short one
    session_id = (
        request.cookies.get("dd_session")
        or request.headers.get("X-Session-ID")
        or str(uuid.uuid4())[:8]
    )

    response = await call_next(request)

    path = request.url.path
    status_code = response.status_code
    action = _resolve_action(request.method, path, status_code)

    # Decide whether to audit this request
    should_audit = (
        bool(action)
        or
        any(path.startswith(p) for p in ALWAYS_AUDIT_PREFIXES)
        or status_code in (401, 403)
    )
    if not should_audit:
        return response

    if not action:
        return response

    result = _resolve_result(status_code)

    try:
        from app.storage.audit_store import AuditLog, AuditStore

        tenant_id = getattr(request.state, "tenant_id", "system") or "system"
        user_id = getattr(request.state, "user_id", "anonymous") or "anonymous"
        username = getattr(request.state, "username", "anonymous") or "anonymous"
        user_role = getattr(request.state, "user_role", "unknown") or "unknown"

        log = AuditLog(
            log_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            user_id=user_id,
            username=username,
            user_role=user_role,
            ip_address=_get_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:200],
            action=action,
            resource_type=_infer_resource_type(path),
            resource_id=_extract_resource_id(path),
            resource_name="",
            result=result,
            detail={
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round((time.time() - start_time) * 1000),
            },
            session_id=session_id,
        )

        AuditStore(tenant_id).append(log)

    except Exception as exc:
        _log.error("[Audit] Failed to log request %s %s: %s", request.method, path, exc)

    return response


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_client_ip(request: Request) -> str:
    from app.middleware.rate_limit import _get_client_ip as _rl_get_ip
    return _rl_get_ip(request)


def _resolve_action(method: str, path: str, status_code: int) -> str:
    """Determine the semantic action type for this request."""
    # Special handling for auth failures
    if status_code == 401:
        if "/login" in path:
            return "user.login_fail"
        return "access.unauthorized"
    if status_code == 403:
        return "access.blocked"

    # Match against rule table
    for (m, pattern), action in AUDIT_RULES.items():
        if method == m and _path_matches(path, pattern):
            return action

    # Fallback: admin mutations
    if method in ("DELETE", "PATCH") and "/admin/" in path:
        return "user.update"

    # Fallback: any admin read → audit it generically
    if "/admin/" in path:
        return "doc.view"

    return ""


def _resolve_result(status_code: int) -> str:
    if status_code < 400:
        return "success"
    if status_code in (401, 403):
        return "blocked"
    return "failure"


def _path_matches(actual: str, pattern: str) -> bool:
    """Check whether *actual* path matches a pattern with {id} placeholders."""
    # Escape everything except {id} placeholders, then replace placeholders
    parts = re.split(r"(\{[^}]+\})", pattern)
    regex = "".join(
        "[^/]+" if p.startswith("{") else re.escape(p) for p in parts
    )
    return bool(re.fullmatch(regex, actual))


def _infer_resource_type(path: str) -> str:
    if "/approvals" in path:
        return "approval"
    if "/procurement" in path:
        return "procurement"
    if "/share" in path:
        return "share"
    if "/projects" in path:
        return "project"
    if "/admin/users" in path:
        return "user"
    if "/generate" in path:
        return "document"
    if "/auth" in path:
        return "user"
    if "/styles" in path:
        return "style"
    return "system"


def _extract_resource_id(path: str) -> str:
    """Extract the last UUID-like segment from the path."""
    parts = path.strip("/").split("/")
    for part in reversed(parts):
        if re.match(r"[0-9a-f\-]{8,}", part):
            return part
    return ""


def install_audit_middleware(app) -> None:
    """Register the audit middleware with a FastAPI app."""
    from starlette.middleware.base import BaseHTTPMiddleware
    app.add_middleware(BaseHTTPMiddleware, dispatch=audit_middleware)
