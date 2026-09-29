"""Read-only Decision Evidence Map for one tenant-owned project."""
from __future__ import annotations

import hashlib
import logging
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
from app.routers.projects._guided_review_registry import (
    _guided_review_disposition_registry,
    _guided_review_registry_owner,
    _guided_review_registry_record_response,
    _read_guided_review_registry_record,
    _set_guided_review_registry_audit,
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
from app.services.procurement_document_binding import resolver_from_app_state
from app.storage.knowledge_store import KnowledgeStore
from app.storage.guided_decision_review_disposition_registry import (
    GuidedDecisionReviewDispositionRegistryConflictError,
    GuidedDecisionReviewDispositionRegistryError,
    GuidedDecisionReviewDispositionRegistryValidationError,
    canonical_guided_review_registry_json_bytes,
)
from app.storage.guided_decision_review_disposition_issuance_registry import (
    GuidedDecisionReviewDispositionIssuanceRegistryError,
    get_guided_decision_review_disposition_issuance_registry,
    guided_review_issuance_sha256,
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
    project_documents: tuple[dict, ...]


def _load_current_procurement_source(
    request: Request,
    *,
    tenant_id: str,
    project_id: str,
) -> tuple[object | None, object | None]:
    resolver = resolver_from_app_state(request.app.state)
    if resolver is None:
        return (
            request.app.state.procurement_store.get(
                project_id,
                tenant_id=tenant_id,
            ),
            None,
        )

    store = getattr(resolver, "store", None)
    capture = getattr(resolver, "capture", None)
    if store is None or not callable(getattr(store, "get", None)) or not callable(capture):
        raise RuntimeError("Procurement generation resolver is incomplete")
    procurement_project = store.get(project_id, tenant_id=tenant_id)
    if procurement_project is None or procurement_project.active_decision_id is None:
        return None, None
    entry = next(
        (
            item
            for item in procurement_project.entries
            if item.record.decision_id == procurement_project.active_decision_id
        ),
        None,
    )
    if entry is None:
        raise RuntimeError("Active procurement decision is missing")
    captured = capture(
        project_id,
        tenant_id=tenant_id,
        decision_id=entry.record.decision_id,
        expected_revision=entry.decision_revision,
    )
    if captured is None:
        raise RuntimeError("Active procurement decision is unavailable")
    return captured.record, captured.binding


def _load_decision_evidence_context(
    project_id: str,
    request: Request,
    *,
    bundle_type: DecisionEvidenceBundleType,
) -> _DecisionEvidenceContext:
    _ensure_procurement_copilot_enabled(request)

    tenant_id = get_tenant_id(request)
    project, authorized_reviews = _load_authorized_decision_evidence_project(
        project_id,
        request,
    )
    procurement_record, source_binding = _load_current_procurement_source(
        request,
        tenant_id=tenant_id,
        project_id=project_id,
    )
    if resolver_from_app_state(request.app.state) is not None:
        authorized_reviews = (
            request.app.state.procurement_review_store.filter_by_decision(
                list(authorized_reviews), tenant_id=tenant_id, project_id=project_id,
                decision_id=procurement_record.decision_id,
            ) if procurement_record is not None else []
        )
    access = get_procurement_review_access(request)
    request.state.procurement_review_total = len(authorized_reviews)
    request.state.procurement_review_authorized_count = len(authorized_reviews)
    if not access.is_admin and not authorized_reviews:
        raise HTTPException(
            status_code=404,
            detail="Decision evidence is not available for this opportunity.",
        )
    review_summaries = tuple(review_summary(record, access) for record in authorized_reviews)
    council_session = request.app.state.decision_council_service.get_latest_procurement_council(
        tenant_id=tenant_id,
        project_id=project_id,
        decision_id=(
            getattr(procurement_record, "decision_id", None)
            if source_binding is not None
            else None
        ),
    )
    if council_session is not None:
        council_session = request.app.state.decision_council_service.attach_procurement_binding(
            session=council_session,
            procurement_record=procurement_record,
            source_binding=source_binding,
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
    project_documents = _serialize_project_documents(
        request,
        tenant_id=tenant_id,
        project=project,
    )
    if resolver_from_app_state(request.app.state) is not None:
        decision_id = getattr(procurement_record, "decision_id", None)
        project_documents = [
            document for document in project_documents
            if decision_id is not None
            and (document.get("source_procurement_binding") or {}).get("decision_id") == decision_id
        ]
        document_ids = {document["doc_id"] for document in project_documents}
        approvals = [record for record in approvals if record.project_document_id in document_ids]
        report_workflows = [record for record in report_workflows if record.project_document_id in document_ids]

    projection = request.app.state.decision_evidence_service.build(
        project_id=project_id,
        bundle_type=bundle_type,
        procurement_record=procurement_record,
        review_summaries=review_summaries,
        council_session=council_session,
        project_documents=project_documents,
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
        project_documents=tuple(project_documents),
    )


def _load_authorized_decision_evidence_project(
    project_id: str,
    request: Request,
) -> tuple[object, tuple[object, ...]]:
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

    return project, tuple(authorized_reviews)


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
    """Issue a non-persistent H128 receipt after same-backend proof."""
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
    try:
        issuance_metadata, _ = (
            get_guided_decision_review_disposition_issuance_registry(
                tenant_id=get_tenant_id(request),
                project_id=project_id,
                bundle_type=receipt.bundle_type,
                backend=request.app.state.state_backend,
            ).create(
                disposition_receipt_sha256=body_sha256,
            )
        )
    except GuidedDecisionReviewDispositionIssuanceRegistryError as exc:
        logger.error("Guided review H128 issuance proof failed closed.", exc_info=exc)
        raise HTTPException(
            status_code=503,
            detail="Guided Decision Review 처리 영수증의 발급 근거를 확인할 수 없습니다.",
        ) from exc
    issuance_record_sha256 = guided_review_issuance_sha256(issuance_metadata)
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
    request.state.guided_review_issuance_record_sha256 = issuance_record_sha256
    request.state.guided_review_issuance_binding_sha256 = issuance_metadata[
        "issuance_binding_sha256"
    ]
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
            "X-DecisionDoc-Guided-Review-Disposition-Issuance-Record-SHA256": (
                issuance_record_sha256
            ),
            "X-DecisionDoc-Projection-Fingerprint": (
                current_handoff.projection_fingerprint
            ),
            "X-DecisionDoc-Review-State-Status": receipt.review_state_status,
            "X-DecisionDoc-Operational-Approval": "false",
        },
    )


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
            contract_version=payload.contract_version,
            allow_legacy_create=False,
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
    return request.app.state.guided_decision_review_service.build(
        projection=context.projection,
        procurement_record=context.procurement_record,
        review_summaries=context.review_summaries,
        council_session=context.council_session,
        project_documents=context.project_documents,
    )
