"""Read-only Decision Evidence Map for one tenant-owned project."""
from __future__ import annotations

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
from app.schemas.decision_evidence import DecisionEvidenceMapResponse
from app.services.procurement_review_access import (
    authorized_review_records,
    get_procurement_review_access,
    review_summary,
)
from app.storage.knowledge_store import KnowledgeStore


router = APIRouter()

DecisionEvidenceBundleType = Literal[
    "bid_decision_kr",
    "rfp_analysis_kr",
    "proposal_kr",
    "performance_plan_kr",
]


@router.get(
    "/projects/{project_id}/decision-evidence-map",
    response_model=DecisionEvidenceMapResponse,
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def get_project_decision_evidence_map(
    project_id: str,
    request: Request,
    response: Response,
    bundle_type: DecisionEvidenceBundleType = Query(default="proposal_kr"),
) -> DecisionEvidenceMapResponse:
    """Project current evidence without creating approval or export authority."""
    _ensure_procurement_copilot_enabled(request)
    _apply_procurement_observability(
        request,
        action="review_evidence_map",
        project_id=project_id,
    )
    request.state.audit_action = "procurement.review_evidence_map_view"
    request.state.bundle_type = bundle_type

    tenant_id = get_tenant_id(request)
    access = get_procurement_review_access(request)
    request.state.procurement_review_access_scope = access.scope
    review_store = request.app.state.procurement_review_store
    review_records = review_store.list_by_project(
        tenant_id=tenant_id,
        project_id=project_id,
        reviewer_user_id=None if access.is_admin else access.user_id,
    )
    authorized_reviews = authorized_review_records(review_records, access)
    if not access.is_admin and not authorized_reviews:
        raise HTTPException(
            status_code=404,
            detail="Decision evidence is not available for this project.",
        )

    project = request.app.state.project_store.get(
        project_id,
        tenant_id=tenant_id,
    )
    if project is None:
        raise HTTPException(
            status_code=404,
            detail=f"프로젝트를 찾을 수 없습니다: {project_id}",
        )

    request.state.procurement_review_total = len(authorized_reviews)
    request.state.procurement_review_authorized_count = len(authorized_reviews)
    request.state.procurement_review_operational_approval = False

    procurement_record = request.app.state.procurement_store.get(
        project_id,
        tenant_id=tenant_id,
    )
    council_session = request.app.state.decision_council_service.get_latest_procurement_council(
        tenant_id=tenant_id,
        project_id=project_id,
    )
    if council_session is not None:
        council_session = request.app.state.decision_council_service.attach_procurement_binding(
            session=council_session,
            procurement_record=procurement_record,
        )

    approvals = [
        record
        for record in request.app.state.approval_store.list_by_tenant(tenant_id)
        if record.project_id == project_id
    ]
    report_workflows = request.app.state.report_workflow_store.list_by_tenant(
        tenant_id,
    )
    knowledge_metadata = KnowledgeStore(
        project_id,
        str(request.app.state.data_dir),
        tenant_id=tenant_id,
        backend=request.app.state.state_backend,
    ).list_documents()

    projection = request.app.state.decision_evidence_service.build(
        project_id=project_id,
        bundle_type=bundle_type,
        procurement_record=procurement_record,
        review_summaries=[
            review_summary(record, access)
            for record in authorized_reviews
        ],
        council_session=council_session,
        project_documents=project.documents,
        approval_records=approvals,
        report_workflows=report_workflows,
        knowledge_metadata=knowledge_metadata,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-DecisionDoc-Projection-Fingerprint"] = (
        projection.projection_fingerprint
    )
    response.headers["X-DecisionDoc-Operational-Approval"] = "false"
    return projection
