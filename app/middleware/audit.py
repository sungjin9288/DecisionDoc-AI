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
    ("POST", "/projects/{id}/decision-council/run"): "decision_council.run",
    ("POST", "/projects/{id}/procurement/override-reason"): "procurement.override_reason",
    ("POST", "/projects/{id}/procurement/remediation-link-copy"): "procurement.remediation_link_copied",
    ("POST", "/projects/{id}/procurement/remediation-link-open"): "procurement.remediation_link_opened",
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
    error_code = getattr(request.state, "error_code", "")
    procurement_error_code = getattr(request.state, "procurement_error_code", "") or error_code
    procurement_action = getattr(request.state, "procurement_action", "")
    decision_council_handoff_used = bool(
        getattr(request.state, "decision_council_handoff_used", False)
    )
    action = _resolve_action(
        request.method,
        path,
        status_code,
        error_code=error_code,
        procurement_action=procurement_action,
        decision_council_handoff_used=decision_council_handoff_used,
    )

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

    if _should_defer_stream_audit(request.method, path, status_code, action, response):
        original_iterator = response.body_iterator

        async def _audited_body_iterator():
            try:
                async for chunk in original_iterator:
                    yield chunk
            finally:
                _append_audit_entries(
                    request,
                    session_id=session_id,
                    start_time=start_time,
                    path=path,
                    status_code=status_code,
                )

        response.body_iterator = _audited_body_iterator()
        return response

    _append_audit_entries(
        request,
        session_id=session_id,
        start_time=start_time,
        path=path,
        status_code=status_code,
    )
    return response


# ── Helpers ────────────────────────────────────────────────────────────────────


def _get_client_ip(request: Request) -> str:
    from app.middleware.rate_limit import _get_client_ip as _rl_get_ip
    return _rl_get_ip(request)


def _resolve_action(
    method: str,
    path: str,
    status_code: int,
    *,
    error_code: str | None = None,
    procurement_action: str | None = None,
    decision_council_handoff_used: bool = False,
) -> str:
    """Determine the semantic action type for this request."""
    if (
        status_code == 409
        and error_code == "procurement_override_reason_required"
        and path.startswith("/generate")
    ):
        return "procurement.downstream_blocked"

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


def _resolve_supplemental_actions(
    method: str,
    path: str,
    status_code: int,
    *,
    procurement_action: str | None = None,
    decision_council_handoff_used: bool = False,
) -> list[str]:
    if method != "POST" or status_code >= 400 or not path.startswith("/generate"):
        return []
    actions: list[str] = []
    if procurement_action == "downstream_resolved":
        actions.append("procurement.downstream_resolved")
    if decision_council_handoff_used:
        actions.append("decision_council.handoff_used")
    return actions


def _should_defer_stream_audit(
    method: str,
    path: str,
    status_code: int,
    action: str,
    response,
) -> bool:
    return (
        method == "POST"
        and path == "/generate/stream"
        and status_code < 400
        and action == "doc.generate"
        and hasattr(response, "body_iterator")
    )


def _append_audit_entries(
    request: Request,
    *,
    session_id: str,
    start_time: float,
    path: str,
    status_code: int,
) -> None:
    error_code = getattr(request.state, "error_code", "")
    procurement_error_code = getattr(request.state, "procurement_error_code", "") or error_code
    procurement_action = getattr(request.state, "procurement_action", "")
    decision_council_handoff_used = bool(
        getattr(request.state, "decision_council_handoff_used", False)
    )
    action = _resolve_action(
        request.method,
        path,
        status_code,
        error_code=error_code,
        procurement_action=procurement_action,
        decision_council_handoff_used=decision_council_handoff_used,
    )
    if not action:
        return

    result = _resolve_result(status_code)

    try:
        from app.storage.audit_store import AuditStore

        tenant_id = getattr(request.state, "tenant_id", "system") or "system"
        user_id = getattr(request.state, "user_id", "anonymous") or "anonymous"
        username = getattr(request.state, "username", "anonymous") or "anonymous"
        user_role = getattr(request.state, "user_role", "unknown") or "unknown"

        procurement_project_id = getattr(request.state, "procurement_project_id", "") or ""
        decision_council_project_id = getattr(request.state, "decision_council_project_id", "") or ""
        bundle_type = getattr(request.state, "bundle_type", "") or ""
        procurement_operation = getattr(request.state, "procurement_operation", "") or ""
        procurement_context_kind = getattr(request.state, "procurement_context_kind", "") or ""
        procurement_recommendation = getattr(request.state, "procurement_recommendation", "") or ""
        decision_council_session_id = getattr(request.state, "decision_council_session_id", "") or ""
        decision_council_session_revision = getattr(
            request.state, "decision_council_session_revision", None
        )
        decision_council_handoff_skipped_reason = (
            getattr(request.state, "decision_council_handoff_skipped_reason", "") or ""
        )
        decision_council_use_case = getattr(request.state, "decision_council_use_case", "") or ""
        decision_council_target_bundle = getattr(
            request.state, "decision_council_target_bundle", ""
        ) or ""
        decision_council_applied_bundle = getattr(
            request.state, "decision_council_applied_bundle", ""
        ) or ""
        decision_council_direction = getattr(request.state, "decision_council_direction", "") or ""
        share_decision_council_document_status = (
            getattr(request.state, "share_decision_council_document_status", "") or ""
        )
        share_decision_council_document_status_tone = (
            getattr(request.state, "share_decision_council_document_status_tone", "") or ""
        )
        share_decision_council_document_status_copy = (
            getattr(request.state, "share_decision_council_document_status_copy", "") or ""
        )
        share_decision_council_document_status_summary = (
            getattr(request.state, "share_decision_council_document_status_summary", "") or ""
        )
        share_project_document_id = getattr(request.state, "share_project_document_id", "") or ""
        detail = {
            "method": request.method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round((time.time() - start_time) * 1000),
        }
        if procurement_error_code:
            detail["error_code"] = procurement_error_code
        if procurement_project_id:
            detail["project_id"] = procurement_project_id
        if bundle_type:
            detail["bundle_type"] = bundle_type
        if procurement_operation:
            detail["procurement_operation"] = procurement_operation
        if procurement_context_kind:
            detail["procurement_context_kind"] = procurement_context_kind
        if procurement_recommendation:
            detail["recommendation"] = procurement_recommendation
        if decision_council_project_id:
            detail["project_id"] = decision_council_project_id
        if decision_council_session_id:
            detail["decision_council_session_id"] = decision_council_session_id
        if decision_council_session_revision is not None:
            detail["decision_council_session_revision"] = decision_council_session_revision
        if decision_council_handoff_skipped_reason:
            detail["decision_council_handoff_skipped_reason"] = decision_council_handoff_skipped_reason
        if decision_council_use_case:
            detail["decision_council_use_case"] = decision_council_use_case
        if decision_council_target_bundle:
            detail["decision_council_target_bundle"] = decision_council_target_bundle
        if decision_council_applied_bundle:
            detail["decision_council_applied_bundle"] = decision_council_applied_bundle
        if decision_council_direction:
            detail["decision_council_direction"] = decision_council_direction
        if decision_council_handoff_used:
            detail["decision_council_handoff_used"] = True
        if share_decision_council_document_status:
            detail["share_decision_council_document_status"] = share_decision_council_document_status
        if share_decision_council_document_status_tone:
            detail["share_decision_council_document_status_tone"] = share_decision_council_document_status_tone
        if share_decision_council_document_status_copy:
            detail["share_decision_council_document_status_copy"] = share_decision_council_document_status_copy
        if share_decision_council_document_status_summary:
            detail["share_decision_council_document_status_summary"] = share_decision_council_document_status_summary
        if share_project_document_id:
            detail["share_project_document_id"] = share_project_document_id

        store = AuditStore(tenant_id)
        timestamp = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        store.append(
            _build_audit_log(
                tenant_id=tenant_id,
                user_id=user_id,
                username=username,
                user_role=user_role,
                request=request,
                session_id=session_id,
                result=result,
                detail=detail,
                action=action,
                procurement_project_id=procurement_project_id,
                decision_council_project_id=decision_council_project_id,
                decision_council_session_id=decision_council_session_id,
                timestamp=timestamp,
            )
        )
        for supplemental_action in _resolve_supplemental_actions(
            request.method,
            path,
            status_code,
            procurement_action=procurement_action,
            decision_council_handoff_used=decision_council_handoff_used,
        ):
            store.append(
                _build_audit_log(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    username=username,
                    user_role=user_role,
                    request=request,
                    session_id=session_id,
                    result=result,
                    detail=detail,
                    action=supplemental_action,
                    procurement_project_id=procurement_project_id,
                    decision_council_project_id=decision_council_project_id,
                    decision_council_session_id=decision_council_session_id,
                    timestamp=timestamp,
                )
            )

    except Exception as exc:
        _log.error("[Audit] Failed to log request %s %s: %s", request.method, path, exc)


def _resolve_resource_identity(
    action: str,
    path: str,
    *,
    procurement_project_id: str,
    decision_council_project_id: str,
    decision_council_session_id: str,
) -> tuple[str, str]:
    resource_id = (
        decision_council_session_id
        if action.startswith("decision_council.") and decision_council_session_id
        else _extract_resource_id(path) or decision_council_project_id or procurement_project_id
    )
    resource_type = (
        "decision_council"
        if action.startswith("decision_council.")
        else
        "procurement"
        if action.startswith("procurement.") and procurement_project_id
        else _infer_resource_type(path)
    )
    return resource_type, resource_id


def _build_audit_log(
    *,
    tenant_id: str,
    user_id: str,
    username: str,
    user_role: str,
    request: Request,
    session_id: str,
    result: str,
    detail: dict,
    action: str,
    procurement_project_id: str,
    decision_council_project_id: str,
    decision_council_session_id: str,
    timestamp: str,
):
    from app.storage.audit_store import AuditLog

    resource_type, resource_id = _resolve_resource_identity(
        action,
        request.url.path,
        procurement_project_id=procurement_project_id,
        decision_council_project_id=decision_council_project_id,
        decision_council_session_id=decision_council_session_id,
    )
    return AuditLog(
        log_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        timestamp=timestamp,
        user_id=user_id,
        username=username,
        user_role=user_role,
        ip_address=_get_client_ip(request),
        user_agent=request.headers.get("user-agent", "")[:200],
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name="",
        result=result,
        detail=dict(detail),
        session_id=session_id,
    )


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
    if "/decision-council" in path:
        return "decision_council"
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
