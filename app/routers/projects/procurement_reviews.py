"""Project-scoped procurement review packet and receipt endpoints."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.dependencies import (
    get_tenant_id,
    require_session_bound_procurement_reviewer,
)
from app.routers.projects.procurement import (
    _apply_procurement_observability,
    _ensure_procurement_copilot_enabled,
)
from app.routers.projects.procurement_review_shared import (
    ensure_project_exists,
    require_packet_sha256,
)
from app.schemas import (
    CompleteProjectProcurementReviewRequest,
    ExportProjectProcurementReviewPacketRequest,
)
from app.services.auth_service import get_request_user_store
from app.services.procurement_review_access import (
    authorized_review_records,
    get_procurement_review_access,
    require_assignment_access,
    require_assignment_request_access,
    require_project_review_access,
    require_reviewer_filter_access,
    require_reviewed_package_access,
    review_summary,
)


router = APIRouter()


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


@router.get(
    "/procurement/reviews",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def list_procurement_review_inbox_endpoint(
    request: Request,
    review_status: Literal["all", "pending", "completed"] = "all",
    reviewer: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List the current tenant's review queue with lightweight project context."""
    _ensure_procurement_copilot_enabled(request)
    request.state.procurement_action = "review_inbox"
    tenant_id = get_tenant_id(request)
    access = get_procurement_review_access(request)
    request.state.procurement_review_access_scope = access.scope
    require_reviewer_filter_access(access, reviewer)

    records = request.app.state.procurement_review_store.list_by_tenant(
        tenant_id=tenant_id,
        reviewer_user_id=None if access.is_admin else access.user_id,
    )
    records = authorized_review_records(records, access)
    summary = {
        "total": len(records),
        "pending": sum(record.review_status == "pending" for record in records),
        "completed": sum(record.review_status == "completed" for record in records),
    }
    filtered = records
    if review_status != "all":
        filtered = [record for record in filtered if record.review_status == review_status]
    normalized_reviewer = (reviewer or "").strip().casefold()
    if normalized_reviewer:
        filtered = [
            record
            for record in filtered
            if record.reviewer.casefold() == normalized_reviewer
        ]

    project_by_id = {
        project.project_id: project
        for project in request.app.state.project_store.list_by_tenant(tenant_id)
    }
    total = len(filtered)
    page = filtered[offset: offset + limit]
    reviews = []
    for record in page:
        project = project_by_id.get(record.project_id)
        item = review_summary(record, access)
        item["project"] = (
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
        reviews.append(item)

    request.state.procurement_review_status = review_status
    request.state.procurement_review_total = summary["total"]
    request.state.procurement_review_pending_count = summary["pending"]
    request.state.procurement_review_completed_count = summary["completed"]
    request.state.procurement_review_authorized_count = len(records)
    return {
        "reviews": reviews,
        "summary": summary,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + limit < total,
        "operational_approval": False,
    }


@router.post(
    "/projects/{project_id}/procurement/review-packet",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
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
    access = get_procurement_review_access(request)
    request.state.procurement_review_access_scope = access.scope
    ensure_project_exists(request, project_id=project_id, tenant_id=tenant_id)

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
    require_assignment_request_access(access, payload.reviewer)
    reviewer_assignment = _resolve_reviewer_assignment(
        request,
        tenant_id=tenant_id,
        reviewer_username=payload.reviewer,
    )
    require_assignment_access(access, reviewer_assignment)

    try:
        packet = build_project_procurement_review_packet(
            record,
            reviewer_owner=reviewer_assignment["username"],
        )
        receipt = build_pending_procurement_review_receipt(packet.content)
        validate_procurement_review_receipt(receipt, packet.content)
        review_record, review_created = request.app.state.procurement_review_store.prepare(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_content=packet.content,
            receipt=receipt,
            prepared_at=_utc_now(),
            reviewer_assignment=reviewer_assignment,
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
            "X-DecisionDoc-Reviewer-Identity-Bound": str(
                review_record.reviewer_identity_bound
            ).lower(),
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


@router.get(
    "/projects/{project_id}/procurement/reviews",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
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
    access = get_procurement_review_access(request)
    request.state.procurement_review_access_scope = access.scope
    ensure_project_exists(request, project_id=project_id, tenant_id=tenant_id)

    review_store = request.app.state.procurement_review_store
    has_records = (
        review_store.has_records_by_project(
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if not access.is_admin
        else False
    )
    records = review_store.list_by_project(
        tenant_id=tenant_id,
        project_id=project_id,
        reviewer_user_id=None if access.is_admin else access.user_id,
    )
    authorized = authorized_review_records(records, access)
    require_project_review_access(
        has_records=has_records,
        authorized=authorized,
        access=access,
    )
    request.state.procurement_review_total = len(authorized)
    request.state.procurement_review_pending_count = sum(
        record.review_status == "pending" for record in authorized
    )
    request.state.procurement_review_completed_count = sum(
        record.review_status == "completed" for record in authorized
    )
    request.state.procurement_review_authorized_count = len(authorized)
    return {
        "project_id": project_id,
        "reviews": [review_summary(record, access) for record in authorized],
        "operational_approval": False,
    }


@router.post(
    "/projects/{project_id}/procurement/reviews/{packet_sha256}/complete",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
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
    from app.services.procurement_decision_package.reviewer_attestation import (
        build_procurement_reviewer_attestation,
    )

    _ensure_procurement_copilot_enabled(request)
    packet_sha256 = require_packet_sha256(packet_sha256)
    _apply_procurement_observability(
        request,
        action="review_complete",
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    tenant_id = get_tenant_id(request)
    ensure_project_exists(request, project_id=project_id, tenant_id=tenant_id)

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

    if review_record.review_status == "completed":
        if (
            review_record.decision != payload.decision
            or review_record.receipt["rationale"] != payload.rationale
        ):
            request.state.error_code = "procurement_review_already_completed"
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "procurement_review_already_completed",
                    "message": "완료된 검토에는 동일한 요청만 재전송할 수 있습니다.",
                },
            )
        reviewed_package = review_store.read_reviewed_package(
            review_record,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        verification = verify_procurement_reviewed_package(
            reviewed_package,
            expected_tenant_id=tenant_id,
            expected_project_id=project_id,
            expected_reviewer_user_id=request.state.user_id,
        )
        _apply_procurement_observability(
            request,
            action="review_completed",
            project_id=project_id,
            operation="replayed",
            packet_sha256=packet_sha256,
            review_status=review_record.review_status,
            review_decision=review_record.decision,
        )
        request.state.procurement_review_packet_sha256 = packet_sha256
        request.state.procurement_review_decision = review_record.decision
        request.state.procurement_review_identity_bound = True
        request.state.procurement_reviewed_package_sha256 = (
            review_record.reviewed_package_sha256
        )
        return _reviewed_package_response(
            packet_sha256=packet_sha256,
            reviewed_package=reviewed_package,
            reviewed_package_sha256=(
                review_record.reviewed_package_sha256 or ""
            ),
            verification=verification,
            reviewer_identity_bound=True,
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
        packet_content = review_store.read_packet(
            review_record,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
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
            reviewer=review_record.reviewer,
            decision=payload.decision,
            rationale=payload.rationale,
            reviewed_at=_utc_now(),
        )
        receipt_content = _canonical_json_bytes(completed_receipt)
        reviewer_attestation = build_procurement_reviewer_attestation(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
            completed_receipt_sha256=hashlib.sha256(
                receipt_content
            ).hexdigest(),
            decision=payload.decision,
            reviewed_at=completed_receipt["reviewed_at"],
            reviewer_user_id=request.state.user_id,
            reviewer_username=request.state.username,
            reviewer_role=request.state.user_role,
        )
        reviewed_package, _manifest = build_procurement_reviewed_package(
            packet_content,
            completed_receipt,
            receipt_content=receipt_content,
            reviewer_attestation=reviewer_attestation,
            expected_tenant_id=tenant_id,
            expected_project_id=project_id,
            expected_reviewer_user_id=request.state.user_id,
        )
        verification = verify_procurement_reviewed_package(
            reviewed_package,
            expected_tenant_id=tenant_id,
            expected_project_id=project_id,
            expected_reviewer_user_id=request.state.user_id,
        )
        completed_record = review_store.complete(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
            current=review_record,
            completed_receipt=completed_receipt,
            reviewed_package_content=reviewed_package,
            reviewer_attestation=reviewer_attestation,
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
    request.state.procurement_review_packet_sha256 = packet_sha256
    request.state.procurement_review_decision = completed_record.decision
    request.state.procurement_review_identity_bound = (
        completed_record.reviewer_identity_bound
    )
    request.state.procurement_reviewed_package_sha256 = (
        completed_record.reviewed_package_sha256
    )
    return _reviewed_package_response(
        packet_sha256=packet_sha256,
        reviewed_package=reviewed_package,
        reviewed_package_sha256=completed_record.reviewed_package_sha256 or "",
        verification=verification,
        reviewer_identity_bound=completed_record.reviewer_identity_bound,
    )


@router.get(
    "/projects/{project_id}/procurement/reviews/{packet_sha256}/reviewed-package",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
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
    packet_sha256 = require_packet_sha256(packet_sha256)
    _apply_procurement_observability(
        request,
        action="reviewed_package_download",
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    tenant_id = get_tenant_id(request)
    access = get_procurement_review_access(request)
    request.state.procurement_review_access_scope = access.scope
    ensure_project_exists(request, project_id=project_id, tenant_id=tenant_id)

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
    require_reviewed_package_access(review_record, access)
    if review_record.review_status != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_review_pending",
                "message": "검토가 완료된 뒤 reviewed package를 내려받을 수 있습니다.",
            },
        )

    try:
        reviewed_package = review_store.read_reviewed_package(
            review_record,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        verification = verify_procurement_reviewed_package(
            reviewed_package,
            expected_tenant_id=tenant_id,
            expected_project_id=project_id,
            expected_reviewer_user_id=(
                review_record.reviewer_assignment["user_id"]
                if review_record.reviewer_assignment is not None
                else None
            ),
        )
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
            "X-DecisionDoc-Reviewer-Identity-Bound": str(
                review_record.reviewer_identity_bound
            ).lower(),
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )
