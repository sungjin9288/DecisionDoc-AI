"""Project-scoped procurement review packet and receipt endpoints."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id
from app.routers.projects.procurement import (
    _apply_procurement_observability,
    _ensure_procurement_copilot_enabled,
)
from app.schemas import (
    CompleteProjectProcurementReviewRequest,
    ExportProjectProcurementReviewPacketRequest,
)


router = APIRouter()
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _require_packet_sha256(packet_sha256: str) -> str:
    if not _SHA256_PATTERN.fullmatch(packet_sha256):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_procurement_review_packet_sha256",
                "message": "검토 패킷 SHA256 형식이 올바르지 않습니다.",
            },
        )
    return packet_sha256


def _ensure_project_exists(request: Request, *, project_id: str, tenant_id: str) -> None:
    project = request.app.state.project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")


@router.post(
    "/projects/{project_id}/procurement/review-packet",
    dependencies=[Depends(require_api_key)],
)
def export_project_procurement_review_packet_endpoint(
    project_id: str,
    payload: ExportProjectProcurementReviewPacketRequest,
    request: Request,
) -> Response:
    """Export a verified packet and prepare its packet-bound review record."""
    from app.services.procurement_decision_package.review_packet import (
        build_project_procurement_review_packet,
    )
    from app.services.procurement_decision_package.review_receipt import (
        build_pending_procurement_review_receipt,
        validate_procurement_review_receipt,
    )

    _ensure_procurement_copilot_enabled(request)
    _apply_procurement_observability(
        request,
        action="review_packet_export",
        project_id=project_id,
    )
    tenant_id = get_tenant_id(request)
    _ensure_project_exists(request, project_id=project_id, tenant_id=tenant_id)

    record = request.app.state.procurement_store.get(project_id, tenant_id=tenant_id)
    if record is None or record.opportunity is None or record.recommendation is None:
        request.state.error_code = "procurement_review_packet_context_required"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_review_packet_context_required",
                "message": (
                    "검토 패킷은 procurement opportunity 연결과 recommendation 생성이 완료된 "
                    "project에서만 내보낼 수 있습니다."
                ),
                "project_id": project_id,
                "required_steps": [
                    "imports/g2b-opportunity",
                    "procurement/evaluate",
                    "procurement/recommend",
                ],
            },
        )

    try:
        packet = build_project_procurement_review_packet(
            record,
            reviewer_owner=payload.reviewer,
        )
        receipt = build_pending_procurement_review_receipt(packet.content)
        validate_procurement_review_receipt(receipt, packet.content)
        review_record, review_created = request.app.state.procurement_review_store.prepare(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_content=packet.content,
            receipt=receipt,
            prepared_at=_utc_now(),
        )
    except ValueError as exc:
        request.state.error_code = "procurement_review_packet_not_ready"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_review_packet_not_ready",
                "message": "현재 procurement decision을 검토 패킷으로 검증할 수 없습니다.",
                "project_id": project_id,
            },
        ) from exc

    _apply_procurement_observability(
        request,
        action="review_started",
        project_id=project_id,
        operation="exported",
        record=record,
        packet_sha256=packet.sha256,
        review_status=review_record.review_status,
    )
    request.state.procurement_review_started = review_created
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
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


@router.get(
    "/projects/{project_id}/procurement/reviews",
    dependencies=[Depends(require_api_key)],
)
def list_project_procurement_reviews_endpoint(project_id: str, request: Request) -> dict:
    """List packet-bound procurement review history for the current tenant."""
    _ensure_procurement_copilot_enabled(request)
    _apply_procurement_observability(
        request,
        action="review_list",
        project_id=project_id,
    )
    tenant_id = get_tenant_id(request)
    _ensure_project_exists(request, project_id=project_id, tenant_id=tenant_id)

    records = request.app.state.procurement_review_store.list_by_project(
        tenant_id=tenant_id,
        project_id=project_id,
    )
    return {
        "project_id": project_id,
        "reviews": [record.to_public_dict() for record in records],
        "operational_approval": False,
    }


@router.post(
    "/projects/{project_id}/procurement/reviews/{packet_sha256}/complete",
    dependencies=[Depends(require_api_key)],
)
def complete_project_procurement_review_endpoint(
    project_id: str,
    packet_sha256: str,
    payload: CompleteProjectProcurementReviewRequest,
    request: Request,
) -> Response:
    """Complete one review and return its independently verified audit package."""
    from app.services.procurement_decision_package.review_packet import (
        build_project_procurement_review_packet,
    )
    from app.services.procurement_decision_package.review_receipt import (
        record_procurement_review_decision,
        validate_procurement_review_receipt,
    )
    from app.services.procurement_decision_package.reviewed_package import (
        build_procurement_reviewed_package,
        verify_procurement_reviewed_package,
    )

    _ensure_procurement_copilot_enabled(request)
    packet_sha256 = _require_packet_sha256(packet_sha256)
    _apply_procurement_observability(
        request,
        action="review_complete",
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    tenant_id = get_tenant_id(request)
    _ensure_project_exists(request, project_id=project_id, tenant_id=tenant_id)

    review_store = request.app.state.procurement_review_store
    review_record = review_store.get(
        tenant_id=tenant_id,
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    if review_record is None:
        request.state.error_code = "procurement_review_not_found"
        raise HTTPException(
            status_code=404,
            detail={
                "code": "procurement_review_not_found",
                "message": "검토 기록을 찾을 수 없습니다.",
            },
        )
    if review_record.review_status != "pending":
        request.state.error_code = "procurement_review_already_completed"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_review_already_completed",
                "message": "이미 완료된 검토 기록은 다시 변경할 수 없습니다.",
            },
        )

    decision_record = request.app.state.procurement_store.get(project_id, tenant_id=tenant_id)
    if decision_record is None:
        request.state.error_code = "procurement_review_source_missing"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_review_source_missing",
                "message": "검토의 원본 procurement decision을 찾을 수 없습니다.",
            },
        )

    try:
        packet_content = review_store.read_packet(review_record)
        validate_procurement_review_receipt(review_record.receipt, packet_content)
        current_packet = build_project_procurement_review_packet(
            decision_record,
            reviewer_owner=review_record.reviewer,
        )
        if current_packet.sha256 != packet_sha256:
            request.state.error_code = "procurement_review_source_changed"
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "procurement_review_source_changed",
                    "message": (
                        "검토 패킷을 만든 뒤 procurement decision이 변경되었습니다. "
                        "새 검토 패킷을 내려받아 다시 검토해주세요."
                    ),
                },
            )

        completed_receipt = record_procurement_review_decision(
            review_record.receipt,
            packet_content,
            reviewer=payload.reviewer,
            decision=payload.decision,
            rationale=payload.rationale,
            reviewed_at=_utc_now(),
        )
        receipt_content = _canonical_json_bytes(completed_receipt)
        reviewed_package, _manifest = build_procurement_reviewed_package(
            packet_content,
            completed_receipt,
            receipt_content=receipt_content,
        )
        verification = verify_procurement_reviewed_package(reviewed_package)
        completed_record = review_store.complete(
            current=review_record,
            completed_receipt=completed_receipt,
            reviewed_package_content=reviewed_package,
        )
    except HTTPException:
        raise
    except (KeyError, ValueError) as exc:
        request.state.error_code = "procurement_review_completion_rejected"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_review_completion_rejected",
                "message": "검토 기록을 완료할 수 없습니다. 담당자와 패킷 상태를 확인해주세요.",
            },
        ) from exc

    _apply_procurement_observability(
        request,
        action="review_completed",
        project_id=project_id,
        operation="completed",
        record=decision_record,
        packet_sha256=packet_sha256,
        review_status=completed_record.review_status,
        review_decision=completed_record.decision,
    )
    filename = f"procurement_reviewed_package_{packet_sha256[:12]}.zip"
    return Response(
        content=reviewed_package,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "X-DecisionDoc-Packet-SHA256": packet_sha256,
            "X-DecisionDoc-Reviewed-Package-SHA256": completed_record.reviewed_package_sha256 or "",
            "X-DecisionDoc-Review-Status": verification["reviewed_package_status"],
            "X-DecisionDoc-Review-Decision": verification["decision"],
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


@router.get(
    "/projects/{project_id}/procurement/reviews/{packet_sha256}/reviewed-package",
    dependencies=[Depends(require_api_key)],
)
def download_project_procurement_reviewed_package_endpoint(
    project_id: str,
    packet_sha256: str,
    request: Request,
) -> Response:
    """Return a previously completed and reverified procurement review package."""
    from app.services.procurement_decision_package.reviewed_package import (
        verify_procurement_reviewed_package,
    )

    _ensure_procurement_copilot_enabled(request)
    packet_sha256 = _require_packet_sha256(packet_sha256)
    _apply_procurement_observability(
        request,
        action="reviewed_package_download",
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    tenant_id = get_tenant_id(request)
    _ensure_project_exists(request, project_id=project_id, tenant_id=tenant_id)

    review_store = request.app.state.procurement_review_store
    review_record = review_store.get(
        tenant_id=tenant_id,
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    if review_record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "procurement_review_not_found",
                "message": "검토 기록을 찾을 수 없습니다.",
            },
        )
    if review_record.review_status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_review_pending",
                "message": "검토가 완료된 뒤 reviewed package를 내려받을 수 있습니다.",
            },
        )

    try:
        reviewed_package = review_store.read_reviewed_package(review_record)
        verification = verify_procurement_reviewed_package(reviewed_package)
    except (KeyError, ValueError) as exc:
        request.state.error_code = "procurement_reviewed_package_invalid"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_reviewed_package_invalid",
                "message": "저장된 reviewed package 증빙을 검증할 수 없습니다.",
            },
        ) from exc

    _apply_procurement_observability(
        request,
        action="reviewed_package_download",
        project_id=project_id,
        operation="downloaded",
        packet_sha256=packet_sha256,
        review_status=review_record.review_status,
        review_decision=review_record.decision,
    )
    filename = f"procurement_reviewed_package_{packet_sha256[:12]}.zip"
    return Response(
        content=reviewed_package,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "X-DecisionDoc-Packet-SHA256": packet_sha256,
            "X-DecisionDoc-Reviewed-Package-SHA256": review_record.reviewed_package_sha256 or "",
            "X-DecisionDoc-Review-Status": verification["reviewed_package_status"],
            "X-DecisionDoc-Review-Decision": verification["decision"],
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )
