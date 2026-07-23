"""Verified re-download of immutable original procurement review packets."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

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
from app.services.procurement_review_access import (
    get_procurement_review_access,
    require_review_packet_access,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/procurement/reviews/{packet_sha256}/packet",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def download_project_procurement_review_packet_endpoint(
    project_id: str,
    packet_sha256: str,
    request: Request,
) -> Response:
    """Return a reverified persisted packet after authorization succeeds."""
    from app.services.procurement_decision_package.review_packet import (
        verify_procurement_review_packet,
    )

    _ensure_procurement_copilot_enabled(request)
    packet_sha256 = require_packet_sha256(packet_sha256)
    _apply_procurement_observability(
        request,
        action="review_packet_download",
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    tenant_id = get_tenant_id(request)
    access = get_procurement_review_access(request)
    request.state.procurement_review_access_scope = access.scope
    ensure_project_exists(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
    )

    store = request.app.state.procurement_review_store
    record = store.get(
        tenant_id=tenant_id,
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "procurement_review_not_found",
                "message": "검토 기록을 찾을 수 없습니다.",
            },
        )

    # The artifact must not be read until the stable assignment is authorized.
    require_review_packet_access(record, access)
    request.state.procurement_review_packet_sha256 = packet_sha256
    request.state.procurement_review_status = record.review_status
    request.state.procurement_review_identity_bound = record.reviewer_identity_bound
    request.state.procurement_review_operational_approval = False

    try:
        content = store.read_packet(
            record,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        verification = verify_procurement_review_packet(content)
        if (
            verification["package_id"] != record.package_id
            or verification["recommendation"] != record.recommendation
        ):
            raise ValueError("procurement review packet record binding changed")
    except (KeyError, ValueError) as exc:
        request.state.error_code = "procurement_review_packet_invalid"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_review_packet_invalid",
                "message": "저장된 원본 검토 패킷 증빙을 검증할 수 없습니다.",
            },
        ) from exc

    _apply_procurement_observability(
        request,
        action="review_packet_download",
        project_id=project_id,
        operation="downloaded",
        packet_sha256=packet_sha256,
        review_status=record.review_status,
    )
    filename = f"procurement_review_packet_{packet_sha256[:12]}.zip"
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-DecisionDoc-Packet-SHA256": packet_sha256,
            "X-DecisionDoc-Package-Id": verification["package_id"],
            "X-DecisionDoc-Artifact-Count": str(
                verification["artifact_count"]
            ),
            "X-DecisionDoc-Review-Status": record.review_status,
            "X-DecisionDoc-Reviewer-Identity-Bound": str(
                record.reviewer_identity_bound
            ).lower(),
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )
