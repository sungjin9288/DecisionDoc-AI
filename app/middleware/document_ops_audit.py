"""Redacted audit context for DocumentOps review operations."""

from __future__ import annotations

from typing import Any

from fastapi import Request


_GOVERNANCE_VIEW_ACTION = "document_ops.governance_view"
_GOVERNANCE_DOWNLOAD_ACTION = "document_ops.governance_handoff_download"


def prepare_governance_audit(
    request: Request,
    *,
    surface: str,
    download: bool = False,
) -> None:
    request.state.audit_action = (
        _GOVERNANCE_DOWNLOAD_ACTION if download else _GOVERNANCE_VIEW_ACTION
    )
    request.state.document_ops_governance_surface = surface


def record_governance_audit_result(
    request: Request,
    payload: dict[str, Any],
) -> None:
    summary = payload.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    status = (
        payload.get("status")
        or payload.get("overall_status")
        or summary.get("status")
        or summary.get("overall_status")
    )
    if isinstance(status, str) and status:
        request.state.document_ops_governance_status = status

    read_only = payload.get("read_only")
    if isinstance(read_only, bool):
        request.state.document_ops_governance_read_only = read_only

    recheck = payload.get("recheck_evidence")
    if isinstance(recheck, dict) and isinstance(recheck.get("persisted"), bool):
        request.state.document_ops_governance_fingerprint_persisted = recheck[
            "persisted"
        ]


def _add_if_present(detail: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value != "":
        detail[key] = value


def document_ops_audit_detail(request: Request) -> dict[str, Any]:
    state = request.state
    detail: dict[str, Any] = {}
    _add_if_present(
        detail,
        "trajectory_id",
        getattr(state, "document_ops_trajectory_id", ""),
    )
    _add_if_present(
        detail,
        "review_status",
        getattr(state, "document_ops_review_status", ""),
    )
    _add_if_present(
        detail,
        "review_decision",
        getattr(state, "document_ops_review_decision", ""),
    )
    _add_if_present(detail, "reviewer", getattr(state, "document_ops_reviewer", ""))
    _add_if_present(
        detail,
        "review_version",
        getattr(state, "document_ops_review_version", None),
    )
    _add_if_present(
        detail,
        "expected_review_version",
        getattr(state, "document_ops_expected_review_version", None),
    )
    _add_if_present(
        detail,
        "current_review_version",
        getattr(state, "document_ops_current_review_version", None),
    )
    _add_if_present(
        detail,
        "quality_score",
        getattr(state, "document_ops_quality_score", None),
    )
    _add_if_present(
        detail,
        "governance_surface",
        getattr(state, "document_ops_governance_surface", ""),
    )
    _add_if_present(
        detail,
        "governance_status",
        getattr(state, "document_ops_governance_status", ""),
    )
    _add_if_present(
        detail,
        "read_only",
        getattr(state, "document_ops_governance_read_only", None),
    )
    _add_if_present(
        detail,
        "state_fingerprint_persisted",
        getattr(state, "document_ops_governance_fingerprint_persisted", None),
    )
    _add_if_present(
        detail,
        "operation_id",
        getattr(state, "document_ops_operation_id", ""),
    )
    _add_if_present(
        detail,
        "operation_status",
        getattr(state, "document_ops_operation_status", ""),
    )
    _add_if_present(
        detail,
        "replay_available",
        getattr(state, "document_ops_operation_replay_available", None),
    )
    return detail


def document_ops_resource_identity(
    request: Request,
    action: str,
) -> tuple[str, str] | None:
    if not action.startswith("document_ops."):
        return None
    surface = getattr(request.state, "document_ops_governance_surface", "")
    if isinstance(surface, str) and surface:
        return "document_ops_governance", surface
    operation_id = getattr(request.state, "document_ops_operation_id", "")
    if isinstance(operation_id, str) and operation_id:
        return "document_ops_agent_operation", operation_id
    trajectory_id = getattr(request.state, "document_ops_trajectory_id", "")
    return "document_ops_trajectory", str(trajectory_id or "")
