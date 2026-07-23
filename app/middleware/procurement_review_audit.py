"""Redacted audit projection for procurement review evidence."""
from __future__ import annotations

from typing import Any

from fastapi import Request


def procurement_review_audit_principal(
    action: str,
    user_id: str,
    username: str,
    user_role: str,
    session_id: str,
) -> tuple[str, str, str, str]:
    """Keep the reviewer identity without persisting its session identifier."""
    if action.startswith("procurement.review"):
        return user_id, username, user_role, ""
    return user_id, username, user_role, session_id


def procurement_review_audit_network(
    action: str,
    ip_address: str,
    user_agent: str,
) -> tuple[str, str]:
    """Exclude request network metadata from procurement review evidence."""
    if action.startswith("procurement.review"):
        return "", ""
    return ip_address, user_agent


def procurement_review_audit_detail(
    request: Request,
) -> dict[str, Any]:
    """Return review workflow fields that are safe for tenant audit history."""
    detail: dict[str, Any] = {}
    text_fields = {
        "procurement_review_status": "review_status",
        "procurement_review_decision": "review_decision",
        "procurement_review_handoff_skipped_reason": (
            "procurement_review_handoff_skipped_reason"
        ),
        "procurement_review_packet_sha256": (
            "procurement_review_packet_sha256"
        ),
        "procurement_reviewed_at": "procurement_reviewed_at",
        "procurement_reviewed_package_sha256": (
            "reviewed_package_sha256"
        ),
        "procurement_review_access_scope": "access_scope",
    }
    for state_field, detail_field in text_fields.items():
        value = getattr(request.state, state_field, "") or ""
        if value:
            detail[detail_field] = value

    optional_fields = {
        "procurement_review_operational_approval": (
            "procurement_review_operational_approval"
        ),
        "procurement_review_identity_bound": "reviewer_identity_bound",
        "procurement_review_total": "review_total",
        "procurement_review_pending_count": "review_pending_count",
        "procurement_review_completed_count": "review_completed_count",
        "procurement_review_authorized_count": "authorized_review_count",
    }
    for state_field, detail_field in optional_fields.items():
        value = getattr(request.state, state_field, None)
        if value is not None:
            detail[detail_field] = value

    if getattr(
        request.state,
        "procurement_review_handoff_used",
        False,
    ):
        detail["procurement_review_handoff_used"] = True
    return detail
