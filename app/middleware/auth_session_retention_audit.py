"""Audit projection for the read-only auth-session retention evidence chain."""

from __future__ import annotations

from typing import Any

from fastapi import Request


def auth_session_retention_audit_detail(request: Request) -> dict[str, Any]:
    """Return the narrow H118 audit fields after contract verification succeeds."""
    detail = getattr(request.state, "auth_session_retention_review_disposition", None)
    if isinstance(detail, dict):
        return {
            "selected_policy_days": detail["selected_policy_days"],
            "aggregate_status": detail["aggregate_status"],
            "review_disposition": detail["review_disposition"],
            "source_recheck_receipt_sha256": detail[
                "source_recheck_receipt_sha256"
            ],
            "receipt_sha256": detail["receipt_sha256"],
            "review_only": detail["review_only"],
        }
    registry = getattr(request.state, "auth_session_retention_registry", None)
    if not isinstance(registry, dict):
        return {}
    return {
        "operation_id": registry["operation_id"],
        "record_sha256": registry["record_sha256"],
        "source_disposition_receipt_sha256": registry[
            "source_disposition_receipt_sha256"
        ],
        "selected_policy_days": registry["selected_policy_days"],
        "aggregate_status": registry["aggregate_status"],
        "review_disposition": registry["review_disposition"],
        "replay": registry["replay"],
    }


def auth_session_retention_audit_principal(
    action: str,
    user_id: str,
    username: str,
    user_role: str,
    session_id: str,
) -> tuple[str, str, str, str]:
    """Keep H119 reviewer identity, while historic aggregate evidence remains anonymous."""
    if action.startswith("auth_session.retention_registry_"):
        return user_id, username, user_role, ""
    if action.startswith("auth_session.retention_"):
        return "", "", "", ""
    return user_id, username, user_role, session_id


def auth_session_retention_audit_network(
    action: str,
    ip_address: str,
    user_agent: str,
) -> tuple[str, str]:
    """Remove request identity from aggregate-only retention audit events."""
    if action.startswith("auth_session.retention_"):
        return "", ""
    return ip_address, user_agent
