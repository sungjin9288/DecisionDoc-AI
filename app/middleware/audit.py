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

from app.middleware.document_ops_audit import (
    document_ops_audit_detail,
    document_ops_resource_identity,
)

_log = logging.getLogger("decisiondoc.audit")

# ── Audit rules — (HTTP method, path pattern) → action type ────────────────────

AUDIT_RULES: dict[tuple[str, str], str] = {
    ("POST", "/auth/login"): "user.login",
    ("POST", "/auth/logout"): "user.logout",
    ("POST", "/generate/stream"): "doc.generate",
    ("POST", "/generate/with-attachments"): "doc.generate",
    ("POST", "/generate/from-documents"): "doc.generate",
    ("POST", "/projects/{id}/imports/g2b-opportunity"): "procurement.import",
    ("POST", "/projects/{id}/procurement/evaluate"): "procurement.evaluate",
    ("POST", "/projects/{id}/procurement/recommend"): "procurement.recommend",
    ("POST", "/projects/{id}/procurement/review-packet"): "procurement.review_packet_export",
    ("GET", "/procurement/reviews"): "procurement.review_inbox_view",
    ("POST", "/projects/{id}/procurement/reviews/{id}/complete"): "procurement.review_completed",
    ("GET", "/projects/{id}/procurement/reviews/{id}/reviewed-package"): "procurement.reviewed_package_download",
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
    ("GET", "/shared/{id}"): "share.view",
    ("DELETE", "/share/{id}"): "share.revoke",
    ("POST", "/admin/users"): "user.create",
    ("PATCH", "/admin/users/{id}"): "user.update",
    ("POST", "/auth/change-password"): "user.password_change",
    ("POST", "/finetune/export"): "system.export",
    (
        "POST",
        "/report-workflows/learning/correction-artifacts/pilot-export/preview",
    ): "report_quality.pilot_preview",
    (
        "POST",
        "/report-workflows/learning/correction-artifacts/pilot-export/package",
    ): "report_quality.pilot_package",
    (
        "POST",
        "/report-workflows/learning/correction-artifacts/pilot-package/verify",
    ): "report_quality.pilot_package_verify",
    (
        "POST",
        "/report-workflows/learning/correction-artifacts/pilot-export",
    ): "report_quality.pilot_export",
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
    procurement_action = getattr(request.state, "procurement_action", "")
    explicit_action = getattr(request.state, "audit_action", "")
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
        explicit_action=explicit_action,
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
    explicit_action: str | None = None,
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
    if explicit_action:
        return explicit_action

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
    procurement_review_started: bool = False,
    procurement_review_handoff_used: bool = False,
    decision_council_handoff_used: bool = False,
) -> list[str]:
    if status_code >= 400:
        return []
    actions: list[str] = []
    if method == "POST" and path.endswith("/procurement/review-packet"):
        if procurement_review_started:
            actions.append("procurement.review_started")
    if method == "POST" and path.startswith("/generate"):
        if procurement_action == "downstream_resolved":
            actions.append("procurement.downstream_resolved")
        if procurement_review_handoff_used:
            actions.append("procurement.review_handoff_used")
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
    explicit_action = getattr(request.state, "audit_action", "")
    procurement_review_started = bool(
        getattr(request.state, "procurement_review_started", False)
    )
    procurement_review_handoff_used = bool(
        getattr(request.state, "procurement_review_handoff_used", False)
    )
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
        explicit_action=explicit_action,
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
        procurement_packet_sha256 = getattr(
            request.state, "procurement_packet_sha256", ""
        ) or ""
        procurement_review_status = getattr(
            request.state, "procurement_review_status", ""
        ) or ""
        procurement_review_decision = getattr(
            request.state, "procurement_review_decision", ""
        ) or ""
        procurement_review_handoff_skipped_reason = getattr(
            request.state, "procurement_review_handoff_skipped_reason", ""
        ) or ""
        procurement_review_packet_sha256 = getattr(
            request.state, "procurement_review_packet_sha256", ""
        ) or ""
        procurement_reviewed_at = getattr(
            request.state, "procurement_reviewed_at", ""
        ) or ""
        procurement_review_operational_approval = getattr(
            request.state, "procurement_review_operational_approval", None
        )
        procurement_review_total = getattr(request.state, "procurement_review_total", None)
        procurement_review_pending_count = getattr(
            request.state, "procurement_review_pending_count", None
        )
        procurement_review_completed_count = getattr(
            request.state, "procurement_review_completed_count", None
        )
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
        share_procurement_review_document_status = (
            getattr(request.state, "share_procurement_review_document_status", "") or ""
        )
        share_procurement_review_document_status_tone = (
            getattr(request.state, "share_procurement_review_document_status_tone", "") or ""
        )
        share_procurement_review_document_status_copy = (
            getattr(request.state, "share_procurement_review_document_status_copy", "") or ""
        )
        share_procurement_review_document_status_summary = (
            getattr(request.state, "share_procurement_review_document_status_summary", "") or ""
        )
        share_project_document_id = getattr(request.state, "share_project_document_id", "") or ""
        share_id = getattr(request.state, "share_id", "") or ""
        share_source_binding_status = (
            getattr(request.state, "share_source_binding_status", "") or ""
        )
        share_post_share_source_changed = getattr(
            request.state, "share_post_share_source_changed", None
        )
        share_revoked_at = getattr(request.state, "share_revoked_at", "") or ""
        share_revoked_by = getattr(request.state, "share_revoked_by", "") or ""
        share_revoked_by_username = (
            getattr(request.state, "share_revoked_by_username", "") or ""
        )
        approval_project_id = getattr(request.state, "approval_project_id", "") or ""
        approval_project_document_id = (
            getattr(request.state, "approval_project_document_id", "") or ""
        )
        approval_document_binding_status = (
            getattr(request.state, "approval_document_binding_status", "") or ""
        )
        approval_decision_council_document_status = (
            getattr(request.state, "approval_decision_council_document_status", "") or ""
        )
        approval_procurement_review_document_status = (
            getattr(request.state, "approval_procurement_review_document_status", "") or ""
        )
        approval_freshness_acknowledged = getattr(
            request.state, "approval_freshness_acknowledged", None
        )
        approval_post_approval_source_changed = getattr(
            request.state, "approval_post_approval_source_changed", None
        )
        approval_source_change_acknowledged = getattr(
            request.state, "approval_source_change_acknowledged", None
        )
        report_quality_pilot_sha256 = (
            getattr(request.state, "report_quality_pilot_sha256", "") or ""
        )
        report_quality_pilot_artifact_count = getattr(
            request.state, "report_quality_pilot_artifact_count", None
        )
        report_quality_pilot_package_sha256 = (
            getattr(request.state, "report_quality_pilot_package_sha256", "") or ""
        )
        report_quality_pilot_artifact_semantics_verified = getattr(
            request.state,
            "report_quality_pilot_artifact_semantics_verified",
            None,
        )
        report_quality_pilot_preview_verified = getattr(
            request.state, "report_quality_pilot_preview_verified", None
        )
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
        if procurement_packet_sha256:
            detail["packet_sha256"] = procurement_packet_sha256
        if procurement_review_status:
            detail["review_status"] = procurement_review_status
        if procurement_review_decision:
            detail["review_decision"] = procurement_review_decision
        if procurement_review_handoff_used:
            detail["procurement_review_handoff_used"] = True
        if procurement_review_handoff_skipped_reason:
            detail["procurement_review_handoff_skipped_reason"] = (
                procurement_review_handoff_skipped_reason
            )
        if procurement_review_packet_sha256:
            detail["procurement_review_packet_sha256"] = procurement_review_packet_sha256
        if procurement_reviewed_at:
            detail["procurement_reviewed_at"] = procurement_reviewed_at
        if procurement_review_operational_approval is not None:
            detail["procurement_review_operational_approval"] = (
                procurement_review_operational_approval
            )
        if procurement_review_total is not None:
            detail["review_total"] = procurement_review_total
        if procurement_review_pending_count is not None:
            detail["review_pending_count"] = procurement_review_pending_count
        if procurement_review_completed_count is not None:
            detail["review_completed_count"] = procurement_review_completed_count
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
        if share_procurement_review_document_status:
            detail["share_procurement_review_document_status"] = share_procurement_review_document_status
        if share_procurement_review_document_status_tone:
            detail["share_procurement_review_document_status_tone"] = share_procurement_review_document_status_tone
        if share_procurement_review_document_status_copy:
            detail["share_procurement_review_document_status_copy"] = share_procurement_review_document_status_copy
        if share_procurement_review_document_status_summary:
            detail["share_procurement_review_document_status_summary"] = share_procurement_review_document_status_summary
        if share_project_document_id:
            detail["share_project_document_id"] = share_project_document_id
        if share_id:
            detail["share_id"] = share_id
        if share_source_binding_status:
            detail["share_source_binding_status"] = share_source_binding_status
        if share_post_share_source_changed is not None:
            detail["share_post_share_source_changed"] = share_post_share_source_changed
        if share_revoked_at:
            detail["share_revoked_at"] = share_revoked_at
        if share_revoked_by:
            detail["share_revoked_by"] = share_revoked_by
        if share_revoked_by_username:
            detail["share_revoked_by_username"] = share_revoked_by_username
        if approval_project_id:
            detail["project_id"] = approval_project_id
        if approval_project_document_id:
            detail["approval_project_document_id"] = approval_project_document_id
        if approval_document_binding_status:
            detail["approval_document_binding_status"] = approval_document_binding_status
        if approval_decision_council_document_status:
            detail["approval_decision_council_document_status"] = (
                approval_decision_council_document_status
            )
        if approval_procurement_review_document_status:
            detail["approval_procurement_review_document_status"] = (
                approval_procurement_review_document_status
            )
        if approval_freshness_acknowledged is not None:
            detail["approval_freshness_acknowledged"] = approval_freshness_acknowledged
        if approval_post_approval_source_changed is not None:
            detail["approval_post_approval_source_changed"] = (
                approval_post_approval_source_changed
            )
        if approval_source_change_acknowledged is not None:
            detail["approval_source_change_acknowledged"] = (
                approval_source_change_acknowledged
            )
        if report_quality_pilot_sha256:
            detail["pilot_sha256"] = report_quality_pilot_sha256
            detail["request_id"] = str(getattr(request.state, "request_id", "") or "")
        if report_quality_pilot_artifact_count is not None:
            detail["pilot_artifact_count"] = report_quality_pilot_artifact_count
        if report_quality_pilot_package_sha256:
            detail["pilot_package_sha256"] = report_quality_pilot_package_sha256
        if report_quality_pilot_artifact_semantics_verified is not None:
            detail["pilot_artifact_semantics_verified"] = (
                report_quality_pilot_artifact_semantics_verified
            )
        if report_quality_pilot_preview_verified is not None:
            detail["pilot_preview_verified"] = report_quality_pilot_preview_verified
        detail.update(document_ops_audit_detail(request))

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
            procurement_review_started=procurement_review_started,
            procurement_review_handoff_used=procurement_review_handoff_used,
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
    share_id = getattr(request.state, "share_id", "") or ""
    if action.startswith("share.") and share_id:
        resource_type = "share"
        resource_id = share_id
    document_ops_identity = document_ops_resource_identity(request, action)
    if document_ops_identity is not None:
        resource_type, resource_id = document_ops_identity
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
