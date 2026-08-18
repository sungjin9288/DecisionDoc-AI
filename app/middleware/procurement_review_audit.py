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
    if _is_procurement_review_action(action):
        return user_id, username, user_role, ""
    return user_id, username, user_role, session_id


def procurement_review_audit_network(
    action: str,
    ip_address: str,
    user_agent: str,
) -> tuple[str, str]:
    """Exclude request network metadata from procurement review evidence."""
    if _is_procurement_review_action(action):
        return "", ""
    return ip_address, user_agent


def _is_procurement_review_action(action: str) -> bool:
    return (
        action.startswith("procurement.review")
        or action
        in {
            "procurement.guided_review_handoff_download",
            "procurement.guided_review_handoff_recheck",
            "procurement.guided_review_disposition",
            "procurement.guided_review_registry_create",
            "procurement.guided_review_registry_list",
            "procurement.guided_review_registry_read",
            "procurement.guided_review_registry_download",
        }
    )


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
        "decision_evidence_projection_fingerprint": "projection_fingerprint",
        "guided_review_handoff_sha256": "handoff_sha256",
        "guided_review_source_handoff_sha256": "source_handoff_sha256",
        "guided_review_current_handoff_sha256": "current_handoff_sha256",
        "guided_review_source_state_fingerprint_sha256": (
            "source_review_state_fingerprint_sha256"
        ),
        "guided_review_current_state_fingerprint_sha256": (
            "current_review_state_fingerprint_sha256"
        ),
        "guided_review_state_status": "review_state_status",
        "guided_review_disposition": "review_disposition",
        "guided_review_source_recheck_receipt_sha256": (
            "source_recheck_receipt_sha256"
        ),
        "guided_review_disposition_binding_sha256": (
            "disposition_binding_sha256"
        ),
        "guided_review_disposition_receipt_sha256": (
            "disposition_receipt_sha256"
        ),
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
        "guided_review_read_only": "read_only",
        "guided_review_snapshot_atomic": "snapshot_atomic",
        "guided_review_handoff_persisted": "handoff_persisted",
        "guided_review_requires_recheck_before_reliance": (
            "requires_recheck_before_reliance"
        ),
        "guided_review_recheck_persisted": "recheck_persisted",
        "guided_review_reviewer_identity_bound": "reviewer_identity_bound",
        "guided_review_disposition_receipt_persisted": (
            "disposition_receipt_persisted"
        ),
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
    registry_detail = getattr(request.state, "guided_review_registry_detail", None)
    if isinstance(registry_detail, dict):
        allowed_registry_fields = {
            "operation_id",
            "record_sha256",
            "source_disposition_receipt_sha256",
            "source_recheck_receipt_sha256",
            "current_handoff_sha256",
            "current_review_state_fingerprint_sha256",
            "review_state_status",
            "review_disposition",
            "disposition_binding_sha256",
            "replay",
            "review_state_only",
            "review_only",
            "read_only",
            "reviewer_identity_bound",
            "registry_record_persisted",
            "snapshot_atomic",
            "requires_recheck_before_reliance",
            "mutation",
            "approval",
            "export_execution",
            "provider_call",
            "bid_submission",
            "legal_contractual_commitment",
        }
        detail.update(
            {
                field: registry_detail[field]
                for field in allowed_registry_fields
                if field in registry_detail
            }
        )
    return detail
