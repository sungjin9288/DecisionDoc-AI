"""app/routers/projects/procurement.py — Procurement Go/No-Go and Decision Council endpoints.

Extracted from app/routers/projects.py (moved verbatim; no behavior changes).
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.api_key import require_api_key
from app.config import get_g2b_api_key
from app.dependencies import get_tenant_id
from app.schemas import (
    DecisionCouncilRunRequest,
    DecisionCouncilSessionResponse,
    ImportProjectProcurementOpportunityRequest,
    NormalizedProcurementOpportunity,
    ProcurementDecisionUpsert,
    RecordProjectProcurementRemediationLinkCopyRequest,
    RecordProjectProcurementRemediationLinkOpenRequest,
    UpdateProjectProcurementOverrideReasonRequest,
)

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────


def _normalize_procurement_opportunity(announcement, *, url_or_number: str) -> NormalizedProcurementOpportunity:
    source_id = announcement.bid_number or url_or_number
    source_url = announcement.detail_url or (url_or_number if url_or_number.startswith("http") else "")
    return NormalizedProcurementOpportunity(
        source_kind="g2b",
        source_id=source_id,
        source_url=source_url,
        title=announcement.title or source_id,
        issuer=announcement.issuer,
        budget=announcement.budget,
        deadline=announcement.deadline,
        bid_type=announcement.bid_type,
        category=announcement.category,
        region="",
        raw_text_preview=(announcement.raw_text or "")[:1_000],
    )


def _build_g2b_structured_context(announcement) -> str:
    return (
        f"발주기관: {announcement.issuer}\n"
        f"사업명: {announcement.title}\n"
        f"예산: {announcement.budget}\n"
        f"마감: {announcement.deadline}\n\n"
        + ((announcement.raw_text or "")[:5_000] if announcement.raw_text else "")
    )


def _append_procurement_override_reason(
    existing_notes: str,
    *,
    username: str,
    reason: str,
) -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    block = (
        f"[override_reason ts={timestamp} actor={username}]\n"
        f"{reason.strip()}\n"
        "[/override_reason]"
    )
    if not existing_notes.strip():
        return block
    return f"{existing_notes.rstrip()}\n\n{block}"


def _ensure_procurement_copilot_enabled(request: Request) -> None:
    if getattr(request.app.state, "procurement_copilot_enabled", False):
        return
    request.state.error_code = "FEATURE_DISABLED"
    raise HTTPException(
        status_code=403,
        detail={
            "code": "FEATURE_DISABLED",
            "message": "Public Procurement Go/No-Go Copilot is disabled in this environment.",
        },
    )


def _apply_procurement_observability(
    request: Request,
    *,
    action: str,
    project_id: str,
    operation: str | None = None,
    source_kind: str | None = None,
    source_id: str | None = None,
    record=None,
    hard_failures: list[dict] | None = None,
    packet_sha256: str | None = None,
    review_status: str | None = None,
    review_decision: str | None = None,
) -> None:
    request.state.procurement_action = action
    request.state.procurement_project_id = project_id
    request.state.procurement_operation = operation
    request.state.procurement_source_kind = source_kind
    request.state.procurement_source_id = source_id
    request.state.procurement_packet_sha256 = packet_sha256
    request.state.procurement_review_status = review_status
    request.state.procurement_review_decision = review_decision

    if record is None:
        return

    request.state.procurement_soft_fit_score = record.soft_fit_score
    request.state.procurement_soft_fit_status = record.soft_fit_status
    request.state.procurement_missing_data_count = len(record.missing_data)
    request.state.procurement_recommendation = (
        record.recommendation.value if record.recommendation else None
    )
    request.state.procurement_checklist_action_count = sum(
        1 for item in record.checklist_items if item.status in {"action_needed", "blocked"}
    )
    if hard_failures is not None:
        request.state.procurement_hard_failure_count = len(hard_failures)
    else:
        request.state.procurement_hard_failure_count = sum(
            1 for item in record.hard_filters if item.blocking and item.status == "fail"
        )


def _load_decision_council_procurement_context_or_raise(
    request: Request,
    *,
    project_id: str,
    tenant_id: str,
):
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    procurement_store = request.app.state.procurement_store
    record = procurement_store.get(project_id, tenant_id=tenant_id)
    if record is None or record.opportunity is None or record.recommendation is None:
        request.state.error_code = "decision_council_procurement_context_required"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "decision_council_procurement_context_required",
                "message": (
                    "Decision Council v1은 procurement opportunity 연결과 recommendation 생성이 완료된 "
                    "project에서만 실행할 수 있습니다."
                ),
                "project_id": project_id,
                "required_steps": [
                    "imports/g2b-opportunity",
                    "procurement/evaluate",
                    "procurement/recommend",
                ],
            },
        )
    return project, record


def _apply_decision_council_observability(
    request: Request,
    *,
    project_id: str,
    session: DecisionCouncilSessionResponse,
) -> None:
    request.state.decision_council_session_id = session.session_id
    request.state.decision_council_session_revision = session.session_revision
    request.state.decision_council_project_id = project_id
    request.state.decision_council_use_case = session.use_case
    request.state.decision_council_target_bundle = session.target_bundle_type
    request.state.decision_council_direction = session.consensus.recommended_direction
    request.state.decision_council_binding_status = session.current_procurement_binding_status


def _attach_decision_council_binding(
    request: Request,
    *,
    session: DecisionCouncilSessionResponse,
    record,
) -> DecisionCouncilSessionResponse:
    service = request.app.state.decision_council_service
    return service.attach_procurement_binding(
        session=session,
        procurement_record=record,
    )


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post(
    "/projects/{project_id}/imports/g2b-opportunity",
    dependencies=[Depends(require_api_key)],
)
async def import_project_procurement_g2b_endpoint(
    project_id: str,
    payload: ImportProjectProcurementOpportunityRequest,
    request: Request,
) -> dict:
    """Attach a G2B opportunity to project-scoped procurement decision state."""
    from app.providers.factory import get_provider_for_bundle
    from app.services.g2b_collector import fetch_announcement_detail
    from app.services.rfp_parser import parse_rfp_fields

    _ensure_procurement_copilot_enabled(request)
    _apply_procurement_observability(
        request,
        action="import",
        project_id=project_id,
    )
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    try:
        announcement = await fetch_announcement_detail(
            url_or_number=payload.url_or_number,
            api_key=get_g2b_api_key(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not announcement:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")

    parsed_rfp_fields = payload.parsed_rfp_fields
    if parsed_rfp_fields is None and announcement.raw_text:
        provider = get_provider_for_bundle("rfp_analysis_kr", tenant_id)
        parsed_rfp_fields = parse_rfp_fields(announcement.raw_text, provider=provider)
    if parsed_rfp_fields is None:
        parsed_rfp_fields = {}

    structured_context = payload.structured_context or _build_g2b_structured_context(announcement)
    procurement_store = request.app.state.procurement_store
    existing = procurement_store.get(project_id, tenant_id=tenant_id)
    snapshot = procurement_store.save_source_snapshot(
        tenant_id=tenant_id,
        project_id=project_id,
        source_kind="g2b_import",
        source_label=announcement.title or "G2B opportunity import",
        external_id=announcement.bid_number or payload.url_or_number,
        payload={
            "request": {"url_or_number": payload.url_or_number},
            "announcement": asdict(announcement),
            "extracted_fields": parsed_rfp_fields,
            "structured_context": structured_context,
        },
    )

    source_snapshots = list(existing.source_snapshots) if existing else []
    source_snapshots.append(snapshot)
    record = procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id=tenant_id,
            schema_version=existing.schema_version if existing else "v1",
            opportunity=_normalize_procurement_opportunity(
                announcement,
                url_or_number=payload.url_or_number,
            ),
            capability_profile=existing.capability_profile if existing else None,
            hard_filters=list(existing.hard_filters) if existing else [],
            score_breakdown=list(existing.score_breakdown) if existing else [],
            soft_fit_score=existing.soft_fit_score if existing else None,
            soft_fit_status=existing.soft_fit_status if existing else "insufficient_data",
            missing_data=list(existing.missing_data) if existing else [],
            checklist_items=list(existing.checklist_items) if existing else [],
            recommendation=existing.recommendation if existing else None,
            source_snapshots=source_snapshots,
            notes=payload.notes if payload.notes else (existing.notes if existing else ""),
        )
    )
    operation = "updated" if existing else "created"
    _apply_procurement_observability(
        request,
        action="import",
        project_id=project_id,
        operation=operation,
        source_kind="g2b",
        source_id=record.opportunity.source_id if record.opportunity else None,
        record=record,
    )

    return {
        "project_id": project_id,
        "operation": operation,
        "project_name": project.name,
        "opportunity": record.opportunity.model_dump(mode="json") if record.opportunity else None,
        "decision": record.model_dump(mode="json"),
        "source_snapshot": snapshot.model_dump(mode="json"),
    }


@router.get(
    "/projects/{project_id}/procurement",
    dependencies=[Depends(require_api_key)],
)
def get_project_procurement_endpoint(project_id: str, request: Request) -> dict:
    """Return the current project-scoped procurement decision state."""
    _ensure_procurement_copilot_enabled(request)
    _apply_procurement_observability(
        request,
        action="read",
        project_id=project_id,
    )
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    procurement_store = request.app.state.procurement_store
    record = procurement_store.get(project_id, tenant_id=tenant_id)
    if record is not None:
        _apply_procurement_observability(
            request,
            action="read",
            project_id=project_id,
            record=record,
        )
    return {
        "project_id": project_id,
        "project_name": project.name,
        "decision": record.model_dump(mode="json") if record else None,
    }


@router.post(
    "/projects/{project_id}/procurement/evaluate",
    dependencies=[Depends(require_api_key)],
)
def evaluate_project_procurement_endpoint(project_id: str, request: Request) -> dict:
    """Run deterministic hard filters and soft-fit scoring for the project."""
    from app.services.procurement_decision_service import ProcurementDecisionService

    _ensure_procurement_copilot_enabled(request)
    _apply_procurement_observability(
        request,
        action="evaluate",
        project_id=project_id,
    )
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    service = ProcurementDecisionService(
        procurement_store=request.app.state.procurement_store,
        data_dir=str(request.app.state.data_dir),
    )
    try:
        record = service.evaluate_project(project_id=project_id, tenant_id=tenant_id)
    except KeyError as exc:
        if str(exc).strip("'") == "procurement_opportunity_not_attached":
            request.state.error_code = "procurement_opportunity_not_attached"
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "procurement_opportunity_not_attached",
                    "message": "프로젝트에 평가할 공공조달 기회가 연결되어 있지 않습니다.",
                },
            ) from exc
        raise

    hard_failures = [
        item.model_dump(mode="json")
        for item in record.hard_filters
        if item.blocking and item.status == "fail"
    ]
    _apply_procurement_observability(
        request,
        action="evaluate",
        project_id=project_id,
        record=record,
        hard_failures=hard_failures,
    )
    return {
        "project_id": project_id,
        "project_name": project.name,
        "decision": record.model_dump(mode="json"),
        "hard_failures": hard_failures,
    }


@router.post(
    "/projects/{project_id}/procurement/recommend",
    dependencies=[Depends(require_api_key)],
)
def recommend_project_procurement_endpoint(project_id: str, request: Request) -> dict:
    """Build recommendation narrative and categorized checklist for the project."""
    from app.services.procurement_decision_service import ProcurementDecisionService

    _ensure_procurement_copilot_enabled(request)
    _apply_procurement_observability(
        request,
        action="recommend",
        project_id=project_id,
    )
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    service = ProcurementDecisionService(
        procurement_store=request.app.state.procurement_store,
        data_dir=str(request.app.state.data_dir),
    )
    try:
        record = service.recommend_project(project_id=project_id, tenant_id=tenant_id)
    except KeyError as exc:
        if str(exc).strip("'") == "procurement_opportunity_not_attached":
            request.state.error_code = "procurement_opportunity_not_attached"
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "procurement_opportunity_not_attached",
                    "message": "프로젝트에 추천을 생성할 공공조달 기회가 연결되어 있지 않습니다.",
                },
            ) from exc
        raise
    _apply_procurement_observability(
        request,
        action="recommend",
        project_id=project_id,
        record=record,
    )

    return {
        "project_id": project_id,
        "project_name": project.name,
        "decision": record.model_dump(mode="json"),
        "recommendation": record.recommendation.model_dump(mode="json") if record.recommendation else None,
        "checklist_items": [item.model_dump(mode="json") for item in record.checklist_items],
    }


@router.post(
    "/projects/{project_id}/decision-council/run",
    response_model=DecisionCouncilSessionResponse,
    dependencies=[Depends(require_api_key)],
)
def run_project_decision_council_endpoint(
    project_id: str,
    payload: DecisionCouncilRunRequest,
    request: Request,
) -> DecisionCouncilSessionResponse:
    """Run the procurement-scoped deterministic Decision Council v1."""
    _ensure_procurement_copilot_enabled(request)
    tenant_id = get_tenant_id(request)
    _, record = _load_decision_council_procurement_context_or_raise(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
    )

    service = request.app.state.decision_council_service
    session = service.run_procurement_council(
        tenant_id=tenant_id,
        project_id=project_id,
        goal=payload.goal,
        context=payload.context,
        constraints=payload.constraints,
        procurement_record=record,
    )
    session = _attach_decision_council_binding(
        request,
        session=session,
        record=record,
    )
    _apply_decision_council_observability(
        request,
        project_id=project_id,
        session=session,
    )
    return session


@router.get(
    "/projects/{project_id}/decision-council",
    response_model=DecisionCouncilSessionResponse,
    dependencies=[Depends(require_api_key)],
)
def get_project_decision_council_endpoint(
    project_id: str,
    request: Request,
) -> DecisionCouncilSessionResponse:
    """Return the latest canonical Decision Council session for the project."""
    _ensure_procurement_copilot_enabled(request)
    tenant_id = get_tenant_id(request)
    _, record = _load_decision_council_procurement_context_or_raise(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
    )

    service = request.app.state.decision_council_service
    session = service.get_latest_procurement_council(
        tenant_id=tenant_id,
        project_id=project_id,
    )
    if session is None:
        request.state.error_code = "decision_council_not_found"
        raise HTTPException(
            status_code=404,
            detail={
                "code": "decision_council_not_found",
                "message": "프로젝트에 저장된 Decision Council session이 없습니다.",
                "project_id": project_id,
            },
        )

    session = _attach_decision_council_binding(
        request,
        session=session,
        record=record,
    )
    _apply_decision_council_observability(
        request,
        project_id=project_id,
        session=session,
    )
    return session


@router.post(
    "/projects/{project_id}/procurement/override-reason",
    dependencies=[Depends(require_api_key)],
)
def update_project_procurement_override_reason_endpoint(
    project_id: str,
    payload: UpdateProjectProcurementOverrideReasonRequest,
    request: Request,
) -> dict:
    """Append a structured override / disagreement note to the procurement record."""
    _ensure_procurement_copilot_enabled(request)
    _apply_procurement_observability(
        request,
        action="override_reason",
        project_id=project_id,
    )
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    procurement_store = request.app.state.procurement_store
    existing = procurement_store.get(project_id, tenant_id=tenant_id)
    if existing is None or existing.opportunity is None:
        request.state.error_code = "procurement_opportunity_not_attached"
        raise HTTPException(
            status_code=409,
            detail={
                "code": "procurement_opportunity_not_attached",
                "message": "프로젝트에 override reason을 남길 공공조달 기회가 연결되어 있지 않습니다.",
            },
        )

    username = (
        getattr(request.state, "username", None)
        or getattr(request.state, "user_id", None)
        or "api_key_client"
    )
    updated = procurement_store.update_notes(
        project_id=project_id,
        tenant_id=tenant_id,
        notes=_append_procurement_override_reason(
            existing.notes,
            username=username,
            reason=payload.reason,
        ),
    )
    _apply_procurement_observability(
        request,
        action="override_reason",
        project_id=project_id,
        operation="updated",
        record=updated,
    )
    return {
        "project_id": project_id,
        "project_name": project.name,
        "decision": updated.model_dump(mode="json"),
        "override_reason_saved": True,
    }


@router.post(
    "/projects/{project_id}/procurement/remediation-link-copy",
    dependencies=[Depends(require_api_key)],
)
def record_project_procurement_remediation_link_copy_endpoint(
    project_id: str,
    payload: RecordProjectProcurementRemediationLinkCopyRequest,
    request: Request,
) -> dict:
    """Record that an operator copied a project-scoped remediation handoff link."""
    _ensure_procurement_copilot_enabled(request)
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    request.state.procurement_action = "remediation_link_copied"
    request.state.procurement_project_id = project_id
    request.state.procurement_operation = payload.source
    request.state.procurement_context_kind = payload.context_kind
    request.state.procurement_recommendation = payload.recommendation.strip() or None
    request.state.bundle_type = payload.bundle_type.strip() or None
    request.state.procurement_error_code = payload.error_code.strip() or None

    return {
        "project_id": project_id,
        "project_name": project.name,
        "logged": True,
        "source": payload.source,
        "context_kind": payload.context_kind,
    }


@router.post(
    "/projects/{project_id}/procurement/remediation-link-open",
    dependencies=[Depends(require_api_key)],
)
def record_project_procurement_remediation_link_open_endpoint(
    project_id: str,
    payload: RecordProjectProcurementRemediationLinkOpenRequest,
    request: Request,
) -> dict:
    """Record that a project-scoped remediation handoff link was opened/restored."""
    _ensure_procurement_copilot_enabled(request)
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    request.state.procurement_action = "remediation_link_opened"
    request.state.procurement_project_id = project_id
    request.state.procurement_operation = payload.source
    request.state.procurement_context_kind = payload.context_kind
    request.state.procurement_recommendation = payload.recommendation.strip() or None
    request.state.bundle_type = payload.bundle_type.strip() or None
    request.state.procurement_error_code = payload.error_code.strip() or None

    return {
        "project_id": project_id,
        "project_name": project.name,
        "logged": True,
        "source": payload.source,
        "context_kind": payload.context_kind,
    }
