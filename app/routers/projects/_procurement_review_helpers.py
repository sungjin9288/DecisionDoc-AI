"""Private helpers for app/routers/projects/procurement_reviews.py.

Moved from procurement_reviews.py to keep the router module within the
800-line guide; names stay importable from procurement_reviews.py. Store
artifact reads (read_packet / complete / read_reviewed_package) stay in the
router so their resource-scope binding remains visible there.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException, Request, Response

from app.services.auth_service import get_request_user_store
from app.services.generation.procurement_source import ProcurementGenerationError
from app.services.procurement_applicability_service import (
    ProcurementApplicabilityConflict, ProcurementApplicabilityNotFound,
)
from app.storage.procurement_store import ProcurementDecisionStoreError


def _capture_requirement_context(request: Request, source):
    service = getattr(request.app.state, "procurement_applicability_service", None)
    if service is None:
        raise ProcurementGenerationError("procurement_source_unavailable", status_code=503)
    try:
        captured = service.capture(
            source.binding.project_id, tenant_id=source.binding.tenant_id,
            decision_id=source.binding.decision_id,
            expected_revision=source.binding.decision_revision,
        )
        if captured.binding != source.binding:
            raise ProcurementApplicabilityConflict("Procurement source changed")
        return captured
    except (ProcurementApplicabilityConflict, ProcurementApplicabilityNotFound) as exc:
        raise ProcurementGenerationError("procurement_context_changed") from exc
    except ProcurementDecisionStoreError as exc:
        raise ProcurementGenerationError("procurement_source_unavailable", status_code=503) from exc


def _assert_requirements_current(request: Request, captured) -> None:
    try:
        request.app.state.procurement_applicability_service.assert_current(captured)
    except (ProcurementApplicabilityConflict, ProcurementApplicabilityNotFound) as exc:
        raise ProcurementGenerationError("procurement_context_changed") from exc
    except ProcurementDecisionStoreError as exc:
        raise ProcurementGenerationError("procurement_source_unavailable", status_code=503) from exc


def _canonical_json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _reviewed_package_response(
    *,
    packet_sha256: str,
    reviewed_package: bytes,
    reviewed_package_sha256: str,
    verification: dict,
    reviewer_identity_bound: bool,
) -> Response:
    filename = f"procurement_reviewed_package_{packet_sha256[:12]}.zip"
    return Response(
        content=reviewed_package,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "X-DecisionDoc-Packet-SHA256": packet_sha256,
            "X-DecisionDoc-Reviewed-Package-SHA256": reviewed_package_sha256,
            "X-DecisionDoc-Review-Status": verification["reviewed_package_status"],
            "X-DecisionDoc-Review-Decision": verification["decision"],
            "X-DecisionDoc-Reviewer-Identity-Bound": str(
                reviewer_identity_bound
            ).lower(),
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


def _resolve_reviewer_assignment(
    request: Request,
    *,
    tenant_id: str,
    reviewer_username: str,
) -> dict[str, str]:
    """Resolve one active tenant reviewer to its stable account identity."""
    user = get_request_user_store(
        request,
        tenant_id,
    ).get_by_username(reviewer_username)
    if (
        user is None
        or not user.is_active
        or user.role.value not in {"admin", "member"}
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "procurement_reviewer_assignment_invalid",
                "message": (
                    "검토 담당자는 현재 tenant의 활성 관리자 또는 "
                    "멤버여야 합니다."
                ),
            },
        )
    return {
        "user_id": user.user_id,
        "username": user.username,
    }


def _review_project_summary(project) -> dict | None:
    """Shape the lightweight project context attached to inbox items."""
    return (
        {
            "project_id": project.project_id,
            "name": project.name,
            "client": project.client,
            "fiscal_year": project.fiscal_year,
            "status": project.status,
        }
        if project is not None
        else None
    )


def _require_bound_reviewer(request: Request, review_record) -> None:
    """Allow only the identity-bound assigned reviewer to complete a review."""
    assignment = review_record.reviewer_assignment
    if (
        not review_record.reviewer_identity_bound
        or not isinstance(assignment, dict)
    ):
        request.state.error_code = "procurement_reviewer_identity_required"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_reviewer_identity_required",
                "message": (
                    "기존 검토 기록은 담당자를 다시 지정한 뒤 "
                    "완료할 수 있습니다."
                ),
            },
        )
    if assignment["user_id"] != request.state.user_id:
        request.state.error_code = "procurement_reviewer_mismatch"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_reviewer_mismatch",
                "message": (
                    "지정된 검토 담당자만 이 패킷을 완료할 수 있습니다."
                ),
            },
        )


def _review_packet_response(*, packet, review_record) -> Response:
    filename = f"procurement_review_packet_{packet.sha256[:12]}.zip"
    return Response(
        content=packet.content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "X-DecisionDoc-Packet-SHA256": packet.sha256,
            "X-DecisionDoc-Package-Id": packet.verification["package_id"],
            "X-DecisionDoc-Artifact-Count": str(packet.verification["artifact_count"]),
            "X-DecisionDoc-Review-Status": review_record.review_status,
            "X-DecisionDoc-Reviewer-Identity-Bound": str(
                review_record.reviewer_identity_bound
            ).lower(),
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )
