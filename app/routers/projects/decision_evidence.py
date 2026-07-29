"""Read-only Decision Evidence Map for one tenant-owned project."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.dependencies import (
    get_tenant_id,
    require_session_bound_procurement_reviewer,
)
from app.routers.projects.procurement import (
    _apply_procurement_observability,
    _ensure_procurement_copilot_enabled,
)
from app.routers.projects._shared import _serialize_project_documents
from app.schemas.decision_evidence import (
    DecisionEvidenceBundleType,
    DecisionEvidenceMapResponse,
    GuidedDecisionReviewDispositionRequest,
    GuidedDecisionReviewHandoffResponse,
    GuidedDecisionReviewRecheckRequest,
)
from app.services.procurement_review_access import (
    authorized_review_records,
    get_procurement_review_access,
    review_summary,
)
from app.storage.knowledge_store import KnowledgeStore


router = APIRouter()

@dataclass(frozen=True)
class _DecisionEvidenceContext:
    projection: DecisionEvidenceMapResponse
    procurement_record: object | None
    review_summaries: tuple[dict, ...]
    council_session: object | None
    project: object


def _load_decision_evidence_context(
    project_id: str,
    request: Request,
    *,
    bundle_type: DecisionEvidenceBundleType,
) -> _DecisionEvidenceContext:
    _ensure_procurement_copilot_enabled(request)

    tenant_id = get_tenant_id(request)
    project, review_summaries = _load_authorized_decision_evidence_project(
        project_id,
        request,
    )
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
        review_summaries=review_summaries,
        council_session=council_session,
        project_documents=project.documents,
        approval_records=approvals,
        report_workflows=report_workflows,
        knowledge_metadata=knowledge_metadata,
    )
    return _DecisionEvidenceContext(
        projection=projection,
        procurement_record=procurement_record,
        review_summaries=review_summaries,
        council_session=council_session,
        project=project,
    )


def _load_authorized_decision_evidence_project(
    project_id: str,
    request: Request,
) -> tuple[object, tuple[dict, ...]]:
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

    review_summaries = tuple(
        review_summary(record, access)
        for record in authorized_reviews
    )
    return project, review_summaries


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
    _apply_procurement_observability(
        request,
        action="review_evidence_map",
        project_id=project_id,
    )
    request.state.audit_action = "procurement.review_evidence_map_view"
    request.state.bundle_type = bundle_type
    context = _load_decision_evidence_context(
        project_id,
        request,
        bundle_type=bundle_type,
    )
    projection = context.projection
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-DecisionDoc-Projection-Fingerprint"] = (
        projection.projection_fingerprint
    )
    response.headers["X-DecisionDoc-Operational-Approval"] = "false"
    return projection


@router.get(
    "/projects/{project_id}/guided-decision-review-handoff",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def download_guided_decision_review_handoff(
    project_id: str,
    request: Request,
    bundle_type: DecisionEvidenceBundleType = Query(default="proposal_kr"),
) -> Response:
    """Download a review-only snapshot without persisting or approving it."""
    _apply_procurement_observability(
        request,
        action="guided_review_handoff",
        project_id=project_id,
    )
    request.state.audit_action = "procurement.guided_review_handoff_download"
    request.state.bundle_type = bundle_type
    context = _load_decision_evidence_context(
        project_id,
        request,
        bundle_type=bundle_type,
    )
    handoff = _build_current_guided_review_handoff(request, context)
    body = request.app.state.guided_decision_review_service.serialize(handoff)
    body_sha256 = hashlib.sha256(body).hexdigest()

    request.state.decision_evidence_projection_fingerprint = (
        context.projection.projection_fingerprint
    )
    request.state.guided_review_handoff_sha256 = body_sha256
    request.state.guided_review_read_only = True
    request.state.guided_review_snapshot_atomic = False
    request.state.guided_review_handoff_persisted = False
    request.state.guided_review_requires_recheck_before_reliance = True
    filename = (
        "guided-decision-review-handoff-"
        f"{context.projection.projection_fingerprint[:12]}.json"
    )
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-DecisionDoc-Guided-Review-Handoff-SHA256": body_sha256,
            "X-DecisionDoc-Projection-Fingerprint": (
                context.projection.projection_fingerprint
            ),
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


@router.post(
    "/projects/{project_id}/guided-decision-review-handoff/recheck",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def recheck_guided_decision_review_handoff(
    project_id: str,
    payload: GuidedDecisionReviewRecheckRequest,
    request: Request,
) -> Response:
    """Compare one browser-held handoff with a fresh review-only observation."""
    _apply_procurement_observability(
        request,
        action="guided_review_handoff_recheck",
        project_id=project_id,
    )
    request.state.audit_action = "procurement.guided_review_handoff_recheck"
    request.state.bundle_type = payload.source_handoff.bundle_type
    context = _load_decision_evidence_context(
        project_id,
        request,
        bundle_type=payload.source_handoff.bundle_type,
    )
    current_handoff = _build_current_guided_review_handoff(request, context)
    try:
        receipt = request.app.state.guided_decision_review_service.recheck(
            source_handoff=payload.source_handoff,
            source_handoff_sha256=payload.source_handoff_sha256,
            current_handoff=current_handoff,
            expected_project_id=project_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Guided Decision Review handoff를 재확인하지 못했습니다.",
        ) from exc

    body = request.app.state.guided_decision_review_service.serialize_recheck(
        receipt
    )
    body_sha256 = hashlib.sha256(body).hexdigest()
    request.state.decision_evidence_projection_fingerprint = (
        current_handoff.projection_fingerprint
    )
    request.state.guided_review_source_handoff_sha256 = (
        receipt.source_handoff_sha256
    )
    request.state.guided_review_current_handoff_sha256 = (
        receipt.current_handoff_sha256
    )
    request.state.guided_review_source_state_fingerprint_sha256 = (
        receipt.source_review_state_fingerprint_sha256
    )
    request.state.guided_review_current_state_fingerprint_sha256 = (
        receipt.current_review_state_fingerprint_sha256
    )
    request.state.guided_review_state_status = receipt.review_state_status
    request.state.guided_review_read_only = True
    request.state.guided_review_snapshot_atomic = False
    request.state.guided_review_requires_recheck_before_reliance = True
    request.state.guided_review_recheck_persisted = False
    filename = (
        "guided-decision-review-recheck-receipt-"
        f"{current_handoff.projection_fingerprint[:12]}.json"
    )
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-DecisionDoc-Guided-Review-Recheck-Receipt-SHA256": body_sha256,
            "X-DecisionDoc-Projection-Fingerprint": (
                current_handoff.projection_fingerprint
            ),
            "X-DecisionDoc-Review-State-Status": receipt.review_state_status,
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


@router.post(
    "/projects/{project_id}/guided-decision-review-handoff/review-disposition",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def download_guided_decision_review_disposition(
    project_id: str,
    payload: GuidedDecisionReviewDispositionRequest,
    request: Request,
) -> Response:
    """Issue a non-persistent disposition for one exact H127 receipt."""
    _apply_procurement_observability(
        request,
        action="guided_review_disposition",
        project_id=project_id,
    )
    request.state.audit_action = "procurement.guided_review_disposition"
    current_handoff = payload.source_recheck_receipt.current_handoff
    request.state.bundle_type = current_handoff.bundle_type
    _ensure_procurement_copilot_enabled(request)
    _load_authorized_decision_evidence_project(project_id, request)
    try:
        receipt = request.app.state.guided_decision_review_service.issue_disposition(
            source_recheck_receipt=payload.source_recheck_receipt,
            source_recheck_receipt_sha256=(
                payload.source_recheck_receipt_sha256
            ),
            review_disposition=payload.review_disposition,
            expected_project_id=project_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="Guided Decision Review 재확인 영수증을 검증하지 못했습니다.",
        ) from exc

    body = request.app.state.guided_decision_review_service.serialize_disposition(
        receipt
    )
    body_sha256 = hashlib.sha256(body).hexdigest()
    request.state.decision_evidence_projection_fingerprint = (
        current_handoff.projection_fingerprint
    )
    request.state.guided_review_source_recheck_receipt_sha256 = (
        receipt.source_recheck_receipt_sha256
    )
    request.state.guided_review_current_handoff_sha256 = (
        receipt.current_handoff_sha256
    )
    request.state.guided_review_current_state_fingerprint_sha256 = (
        receipt.current_review_state_fingerprint_sha256
    )
    request.state.guided_review_state_status = receipt.review_state_status
    request.state.guided_review_disposition = receipt.review_disposition
    request.state.guided_review_disposition_binding_sha256 = (
        receipt.disposition_binding_sha256
    )
    request.state.guided_review_disposition_receipt_sha256 = body_sha256
    request.state.guided_review_read_only = True
    request.state.guided_review_snapshot_atomic = False
    request.state.guided_review_requires_recheck_before_reliance = True
    request.state.guided_review_reviewer_identity_bound = False
    request.state.guided_review_disposition_receipt_persisted = False
    filename = (
        "guided-decision-review-disposition-receipt-"
        f"{current_handoff.projection_fingerprint[:12]}.json"
    )
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-DecisionDoc-Guided-Review-Disposition-Receipt-SHA256": (
                body_sha256
            ),
            "X-DecisionDoc-Projection-Fingerprint": (
                current_handoff.projection_fingerprint
            ),
            "X-DecisionDoc-Review-State-Status": receipt.review_state_status,
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


def _build_current_guided_review_handoff(
    request: Request,
    context: _DecisionEvidenceContext,
) -> GuidedDecisionReviewHandoffResponse:
    project_documents = _serialize_project_documents(
        request,
        tenant_id=get_tenant_id(request),
        project=context.project,
    )
    return request.app.state.guided_decision_review_service.build(
        projection=context.projection,
        procurement_record=context.procurement_record,
        review_summaries=context.review_summaries,
        council_session=context.council_session,
        project_documents=project_documents,
    )
