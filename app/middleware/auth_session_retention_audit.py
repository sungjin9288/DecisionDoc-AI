"""Audit projection for the read-only auth-session retention evidence chain."""

from __future__ import annotations

from typing import Any

from fastapi import Request


def auth_session_retention_audit_detail(request: Request) -> dict[str, Any]:
    """Return the narrow H118 audit fields after contract verification succeeds."""
    detail = getattr(request.state, "auth_session_retention_review_disposition", None)
    if not isinstance(detail, dict):
        return {}
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


def auth_session_retention_audit_identity(
    action: str,
    ip_address: str,
    user_agent: str,
) -> tuple[str, str]:
    """Remove request identity from aggregate-only retention audit events."""
    if action.startswith("auth_session.retention_"):
        return "", ""
    return ip_address, user_agent
