"""app/routers/projects.py — Project management endpoints.

Extracted from app/main.py to keep the main module lean.
"""
from __future__ import annotations

import json as _json
import logging
import re
import urllib.parse
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from app.auth.api_key import require_api_key
from app.config import get_g2b_api_key
from app.dependencies import get_tenant_id, get_user_id, require_admin
from app.schemas import (
    AddDocumentToProjectRequest,
    CreateProjectRequest,
    DecisionCouncilRunRequest,
    DecisionCouncilSessionResponse,
    ImportProjectProcurementOpportunityRequest,
    ImportVoiceBriefDocumentRequest,
    NormalizedProcurementOpportunity,
    ProcurementDecisionUpsert,
    RecordProjectProcurementRemediationLinkCopyRequest,
    RecordProjectProcurementRemediationLinkOpenRequest,
    UpdateProjectProcurementOverrideReasonRequest,
    UpdateProjectRequest,
)
from app.services.docx_service import build_docx
from app.services.decision_council_service import (
    describe_procurement_council_document_status,
)
from app.services.excel_service import build_excel
from app.services.hwp_service import build_hwp
from app.services.voice_brief_import_service import (
    VoiceBriefImportBlockedError,
    VoiceBriefRemoteError,
)

logger = logging.getLogger("decisiondoc.projects")

router = APIRouter(tags=["projects"])


# ── Helpers ──────────────────────────────────────────────────────────────


def _resolve_gov_options(gov_options_dict: dict | None):
    if not gov_options_dict:
        return None
    try:
        from app.schemas import GovDocOptions
        return GovDocOptions(**gov_options_dict)
    except Exception:
        return None


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
) -> None:
    request.state.procurement_action = action
    request.state.procurement_project_id = project_id
    request.state.procurement_operation = operation
    request.state.procurement_source_kind = source_kind
    request.state.procurement_source_id = source_id

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


def _serialize_project_detail(
    request: Request,
    *,
    tenant_id: str,
    project,
) -> dict:
    payload = asdict(project)
    if not getattr(request.app.state, "procurement_copilot_enabled", False):
        return payload

    service = getattr(request.app.state, "decision_council_service", None)
    procurement_store = getattr(request.app.state, "procurement_store", None)
    if service is None or procurement_store is None:
        return payload

    latest_session = service.get_latest_procurement_council(
        tenant_id=tenant_id,
        project_id=project.project_id,
    )
    if latest_session is not None:
        latest_session = service.attach_procurement_binding(
            session=latest_session,
            procurement_record=procurement_store.get(project.project_id, tenant_id=tenant_id),
        )

    for doc in payload.get("documents", []):
        status_meta = describe_procurement_council_document_status(
            bundle_id=str(doc.get("bundle_id") or ""),
            source_session_id=doc.get("source_decision_council_session_id"),
            source_session_revision=doc.get("source_decision_council_session_revision"),
            latest_session=latest_session,
        )
        if not status_meta:
            continue
        doc["decision_council_document_status"] = status_meta["status"]
        doc["decision_council_document_status_tone"] = status_meta["tone"]
        doc["decision_council_document_status_copy"] = status_meta["copy"]
        doc["decision_council_document_status_summary"] = status_meta["summary"]
    return payload


def _load_pdf_builder():
    try:
        from app.services.pdf_service import build_pdf as _build_pdf
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="PDF export is not available in this deployment.",
        ) from exc
    return _build_pdf


# ── Endpoints ────────────────────────────────────────────────────────────


@router.post("/projects", dependencies=[Depends(require_api_key)])
def create_project_endpoint(payload: CreateProjectRequest, request: Request) -> dict:
    """Create a new project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    proj = project_store.create(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        client=payload.client,
        contract_number=payload.contract_number,
        fiscal_year=payload.fiscal_year,
    )
    return asdict(proj)


@router.get("/projects/search", dependencies=[Depends(require_api_key)])
def search_projects_endpoint(
    request: Request,
    q: str = "",
    fiscal_year: int | None = None,
) -> dict:
    """Search projects by name, client, document title, tags."""
    tenant_id = get_tenant_id(request)
    if not q:
        return {"results": []}
    project_store = request.app.state.project_store
    results = project_store.search(tenant_id, q, fiscal_year=fiscal_year)
    return {"results": results}


@router.get("/projects/stats", dependencies=[Depends(require_api_key)])
def project_stats_endpoint(request: Request) -> dict:
    """Get project dashboard stats."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    return project_store.get_stats(tenant_id)


@router.get("/projects/archive/{fiscal_year}", dependencies=[Depends(require_api_key)])
def project_archive_endpoint(fiscal_year: int, request: Request) -> dict:
    """Get yearly archive summary."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    return project_store.get_yearly_archive(tenant_id, fiscal_year)


@router.get("/projects", dependencies=[Depends(require_api_key)])
def list_projects_endpoint(
    request: Request,
    status: str | None = None,
    fiscal_year: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List projects for the current tenant with pagination."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    projects = project_store.list_by_tenant(tenant_id, status=status, fiscal_year=fiscal_year)
    total = len(projects)
    limit = max(1, min(limit, 200))
    paginated = projects[offset: offset + limit]
    return {
        "projects": [asdict(p) for p in paginated],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }


@router.get("/projects/{project_id}", dependencies=[Depends(require_api_key)])
def get_project_endpoint(project_id: str, request: Request) -> dict:
    """Get project detail with all documents."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    proj = project_store.get(project_id, tenant_id=tenant_id)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    return _serialize_project_detail(request, tenant_id=tenant_id, project=proj)


@router.patch("/projects/{project_id}", dependencies=[Depends(require_api_key)])
def update_project_endpoint(project_id: str, payload: UpdateProjectRequest, request: Request) -> dict:
    """Update project fields."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        proj = project_store.update(
            project_id,
            tenant_id=tenant_id,
            **{k: v for k, v in payload.model_dump().items() if v is not None}
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return asdict(proj)


@router.delete("/projects/{project_id}", dependencies=[Depends(require_api_key)])
def delete_project_endpoint(project_id: str, request: Request) -> dict:
    """Permanently delete a project (admin only). Documents are unlinked, not deleted."""
    require_admin(request)
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        project_store.delete(project_id, tenant_id=tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    logger.info(
        "[Project] Deleted project %s by user %s",
        project_id,
        get_user_id(request),
    )
    return {"message": "프로젝트가 삭제되었습니다.", "project_id": project_id}


@router.post("/projects/{project_id}/archive", dependencies=[Depends(require_api_key)])
def archive_project_endpoint(project_id: str, request: Request) -> dict:
    """Archive a project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        proj = project_store.archive(project_id, tenant_id=tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return asdict(proj)


@router.post("/projects/{project_id}/documents", dependencies=[Depends(require_api_key)])
def add_document_to_project_endpoint(
    project_id: str, payload: AddDocumentToProjectRequest, request: Request
) -> dict:
    """Manually add a document to a project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        doc = project_store.add_document(
            project_id=project_id,
            request_id=payload.request_id,
            bundle_id=payload.bundle_id,
            title=payload.title,
            docs=payload.docs,
            approval_id=payload.approval_id,
            tags=payload.tags,
            tenant_id=tenant_id,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return asdict(doc)


@router.post(
    "/projects/{project_id}/imports/voice-brief",
    dependencies=[Depends(require_api_key)],
)
def import_voice_brief_document_endpoint(
    project_id: str,
    payload: ImportVoiceBriefDocumentRequest,
    request: Request,
) -> dict:
    """Import an approved Voice Brief document package into an existing project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    import_service = getattr(request.app.state, "voice_brief_import_service", None)
    if import_service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "voice_brief_not_configured",
                "message": "VOICE_BRIEF_API_BASE_URL is not configured.",
            },
        )

    try:
        result = import_service.import_into_project(
            project_store=project_store,
            project_id=project_id,
            tenant_id=tenant_id,
            recording_id=payload.recording_id,
            revision_id=payload.revision_id,
        )
    except VoiceBriefImportBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
            },
        ) from exc
    except VoiceBriefRemoteError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "voice_brief_not_found",
                    "message": str(exc),
                },
            ) from exc
        raise HTTPException(
            status_code=502,
            detail={
                "code": "voice_brief_upstream_error",
                "message": str(exc),
            },
        ) from exc

    return {
        "project_id": project_id,
        "operation": result.operation,
        "import_outcome": result.outcome,
        "source_key": result.source_key,
        "document_id": result.document_id,
        "source_recording_id": result.source_recording_id,
        "source_summary_revision_id": result.source_summary_revision_id,
        "document": asdict(result.document),
        "voice_brief": {
            "recording_id": result.source_recording_id,
            "summary_revision_id": result.source_summary_revision_id,
            "summary_review_status": result.voice_brief_document.get("summaryReviewStatus"),
            "summary_sync_status": result.voice_brief_document.get("summarySyncStatus"),
        },
    }


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


@router.delete("/projects/{project_id}/documents/{doc_id}", dependencies=[Depends(require_api_key)])
def remove_document_from_project_endpoint(
    project_id: str, doc_id: str, request: Request
) -> dict:
    """Remove a document from a project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    try:
        project_store.remove_document(project_id, doc_id, tenant_id=tenant_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.get(
    "/projects/{project_id}/documents/{doc_id}/download/{fmt}",
    dependencies=[Depends(require_api_key)],
)
async def download_project_doc_endpoint(
    project_id: str, doc_id: str, fmt: str, request: Request
) -> Response:
    """Download a specific project document."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    proj = project_store.get(project_id, tenant_id=tenant_id)
    if proj is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    doc = next((d for d in proj.documents if d.doc_id == doc_id), None)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없습니다: {doc_id}")
    try:
        docs = _json.loads(doc.doc_snapshot)
    except Exception:
        docs = []
    gov_opts = _resolve_gov_options(doc.gov_options)
    title = doc.title
    safe_title = re.sub(r'[\\/*?:"<>|]', "_", title)[:100]
    encoded_title = urllib.parse.quote(safe_title, safe="")
    fmt_lower = fmt.lower().lstrip(".")
    if fmt_lower == "docx":
        content = build_docx(docs, title=title, gov_options=gov_opts)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    elif fmt_lower == "pdf":
        build_pdf = _load_pdf_builder()
        content = await build_pdf(docs, title=title, gov_options=gov_opts)
        media_type = "application/pdf"
        ext = "pdf"
    elif fmt_lower in ("hwp", "hwpx"):
        content = build_hwp(docs, title=title, gov_options=gov_opts)
        media_type = "application/hwp+zip"
        ext = "hwpx"
    elif fmt_lower in ("excel", "xlsx"):
        content = build_excel(docs, title=title)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 포맷: {fmt}")
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="document.{ext}"; '
                f"filename*=UTF-8''{encoded_title}.{ext}"
            )
        },
    )
