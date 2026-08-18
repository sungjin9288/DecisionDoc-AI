"""Read-only Decision Evidence Map for one tenant-owned project."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from uuid import UUID
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
    GuidedDecisionReviewDispositionRecordRequest,
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
from app.storage.guided_decision_review_disposition_registry import (
    GuidedDecisionReviewDispositionRegistryConflictError,
    GuidedDecisionReviewDispositionRegistryError,
    GuidedDecisionReviewDispositionRegistryValidationError,
    canonical_guided_review_registry_json_bytes,
    get_guided_decision_review_disposition_registry,
)


router = APIRouter()
logger = logging.getLogger("decisiondoc.procurement.guided_review")

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


def _guided_review_disposition_registry(
    request: Request,
    *,
    project_id: str,
    bundle_type: DecisionEvidenceBundleType,
):
    return get_guided_decision_review_disposition_registry(
        tenant_id=get_tenant_id(request),
        project_id=project_id,
        bundle_type=bundle_type,
        backend=request.app.state.state_backend,
    )


def _require_guided_review_registry_operation_id(operation_id: str) -> str:
    try:
        parsed = UUID(operation_id)
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=422,
            detail="operation ID 형식이 올바르지 않습니다.",
        ) from exc
    if parsed.version != 4 or str(parsed) != operation_id:
        raise HTTPException(
            status_code=422,
            detail="operation ID 형식이 올바르지 않습니다.",
        )
    return operation_id


def _guided_review_registry_owner(request: Request) -> str | None:
    access = get_procurement_review_access(request)
    return None if access.is_admin else access.user_id


def _guided_review_registry_record_response(
    record: dict,
    *,
    status_code: int,
    attachment: bool = False,
) -> Response:
    body = canonical_guided_review_registry_json_bytes(record)
    headers = {
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "X-DecisionDoc-Guided-Review-Disposition-Record-SHA256": (
            hashlib.sha256(body).hexdigest()
        ),
        "X-DecisionDoc-Operational-Approval": "false",
    }
    if attachment:
        headers["Content-Disposition"] = (
            'attachment; filename="guided-decision-review-disposition-record-'
            f'{record["operation_id"]}.json"'
        )
    return Response(
        content=body,
        status_code=status_code,
        media_type="application/json; charset=utf-8",
        headers=headers,
    )


def _set_guided_review_registry_audit(
    request: Request,
    record: dict,
    *,
    replay: bool,
) -> None:
    request.state.guided_review_registry_detail = {
        "operation_id": record["operation_id"],
        "record_sha256": hashlib.sha256(
            canonical_guided_review_registry_json_bytes(record)
        ).hexdigest(),
        "source_disposition_receipt_sha256": record[
            "source_disposition_receipt_sha256"
        ],
        "source_recheck_receipt_sha256": record[
            "source_recheck_receipt_sha256"
        ],
        "current_handoff_sha256": record["current_handoff_sha256"],
        "current_review_state_fingerprint_sha256": record[
            "current_review_state_fingerprint_sha256"
        ],
        "review_state_status": record["review_state_status"],
        "review_disposition": record["review_disposition"],
        "disposition_binding_sha256": record["disposition_binding_sha256"],
        "replay": replay,
        "review_state_only": True,
        "review_only": True,
        "read_only": True,
        "reviewer_identity_bound": True,
        "registry_record_persisted": True,
        "snapshot_atomic": False,
        "requires_recheck_before_reliance": True,
        **record["authority"],
    }


def _load_guided_review_registry_scope(
    request: Request,
    *,
    project_id: str,
    bundle_type: DecisionEvidenceBundleType,
) -> None:
    _apply_procurement_observability(
        request,
        action="guided_review_disposition_registry",
        project_id=project_id,
    )
    request.state.bundle_type = bundle_type
    _ensure_procurement_copilot_enabled(request)
    _load_authorized_decision_evidence_project(project_id, request)


@router.post(
    "/projects/{project_id}/guided-decision-review-dispositions",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def create_guided_decision_review_disposition_record(
    project_id: str,
    payload: GuidedDecisionReviewDispositionRecordRequest,
    request: Request,
    bundle_type: DecisionEvidenceBundleType = Query(...),
) -> Response:
    """Persist one immutable reviewer-bound H128 record without authority."""
    request.state.audit_action = "procurement.guided_review_registry_create"
    _load_guided_review_registry_scope(
        request,
        project_id=project_id,
        bundle_type=bundle_type,
    )
    try:
        record, created = _guided_review_disposition_registry(
            request,
            project_id=project_id,
            bundle_type=bundle_type,
        ).create(
            operation_id=payload.operation_id,
            reviewer_user_id=request.state.user_id,
            reviewer_username=request.state.username,
            reviewer_role=request.state.user_role,
            source_disposition_receipt=payload.source_disposition_receipt,
            source_disposition_receipt_sha256=(
                payload.source_disposition_receipt_sha256
            ),
        )
    except GuidedDecisionReviewDispositionRegistryValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail="Guided Decision Review 처리 영수증을 검증하지 못했습니다.",
        ) from exc
    except GuidedDecisionReviewDispositionRegistryConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="동일 operation ID가 다른 검토 처리 기록에 이미 사용되었습니다.",
        ) from exc
    except GuidedDecisionReviewDispositionRegistryError as exc:
        logger.error("Guided review registry create failed closed.", exc_info=exc)
        raise HTTPException(
            status_code=503,
            detail="Guided Decision Review 처리 이력을 기록할 수 없습니다.",
        ) from exc
    _set_guided_review_registry_audit(request, record, replay=not created)
    return _guided_review_registry_record_response(
        record,
        status_code=201 if created else 200,
    )


@router.get(
    "/projects/{project_id}/guided-decision-review-dispositions",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def list_guided_decision_review_disposition_records(
    project_id: str,
    request: Request,
    bundle_type: DecisionEvidenceBundleType = Query(...),
) -> Response:
    """List strict H129 summaries visible to the current stable reviewer."""
    request.state.audit_action = "procurement.guided_review_registry_list"
    _load_guided_review_registry_scope(
        request,
        project_id=project_id,
        bundle_type=bundle_type,
    )
    try:
        records = _guided_review_disposition_registry(
            request,
            project_id=project_id,
            bundle_type=bundle_type,
        ).list_summaries(
            reviewer_user_id=_guided_review_registry_owner(request),
        )
    except GuidedDecisionReviewDispositionRegistryError as exc:
        logger.error("Guided review registry list failed closed.", exc_info=exc)
        raise HTTPException(
            status_code=503,
            detail="Guided Decision Review 처리 이력을 조회할 수 없습니다.",
        ) from exc
    body = canonical_guided_review_registry_json_bytes({"records": records})
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-DecisionDoc-Guided-Review-Disposition-Registry-SHA256": (
                hashlib.sha256(body).hexdigest()
            ),
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


def _read_guided_review_registry_record(
    request: Request,
    *,
    project_id: str,
    bundle_type: DecisionEvidenceBundleType,
    operation_id: str,
) -> tuple[dict, bytes]:
    operation_id = _require_guided_review_registry_operation_id(operation_id)
    try:
        return _guided_review_disposition_registry(
            request,
            project_id=project_id,
            bundle_type=bundle_type,
        ).read_canonical(
            operation_id,
            reviewer_user_id=_guided_review_registry_owner(request),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail="Guided Decision Review 처리 이력이 없습니다.",
        ) from exc
    except GuidedDecisionReviewDispositionRegistryError as exc:
        logger.error("Guided review registry read failed closed.", exc_info=exc)
        raise HTTPException(
            status_code=503,
            detail="Guided Decision Review 처리 이력을 조회할 수 없습니다.",
        ) from exc


@router.get(
    "/projects/{project_id}/guided-decision-review-dispositions/{operation_id}",
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def read_guided_decision_review_disposition_record(
    project_id: str,
    operation_id: str,
    request: Request,
    bundle_type: DecisionEvidenceBundleType = Query(...),
) -> Response:
    request.state.audit_action = "procurement.guided_review_registry_read"
    _load_guided_review_registry_scope(
        request,
        project_id=project_id,
        bundle_type=bundle_type,
    )
    record, _ = _read_guided_review_registry_record(
        request,
        project_id=project_id,
        bundle_type=bundle_type,
        operation_id=operation_id,
    )
    _set_guided_review_registry_audit(request, record, replay=False)
    return _guided_review_registry_record_response(record, status_code=200)


@router.get(
    (
        "/projects/{project_id}/guided-decision-review-dispositions/"
        "{operation_id}/download"
    ),
    dependencies=[Depends(require_session_bound_procurement_reviewer)],
)
def download_guided_decision_review_disposition_record(
    project_id: str,
    operation_id: str,
    request: Request,
    bundle_type: DecisionEvidenceBundleType = Query(...),
) -> Response:
    request.state.audit_action = "procurement.guided_review_registry_download"
    _load_guided_review_registry_scope(
        request,
        project_id=project_id,
        bundle_type=bundle_type,
    )
    record, _ = _read_guided_review_registry_record(
        request,
        project_id=project_id,
        bundle_type=bundle_type,
        operation_id=operation_id,
    )
    _set_guided_review_registry_audit(request, record, replay=False)
    return _guided_review_registry_record_response(
        record,
        status_code=200,
        attachment=True,
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
