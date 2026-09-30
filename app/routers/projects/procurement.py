"""app/routers/projects/procurement.py — Procurement Go/No-Go and Decision Council endpoints.

Extracted from app/routers/projects.py (moved verbatim; no behavior changes).
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth.api_key import require_api_key
from app.config import get_g2b_api_key
from app.dependencies import get_tenant_id
from app.routers.projects._procurement_helpers import (
    _append_procurement_override_reason,
    _apply_decision_council_observability,
    _apply_procurement_observability,
    _attach_decision_council_binding,
    _build_g2b_structured_context,
    _ensure_procurement_copilot_enabled,
    _load_decision_council_procurement_context_or_raise,
    _normalize_procurement_opportunity,
    _raise_scoped_error,
    _record_remediation_link_event,
    _require_scoped_fields,
    _resolve_scoped_procurement_context as _resolve_scoped_procurement_context,
)
from app.schemas import (
    DecisionCouncilRunRequest,
    DecisionCouncilSessionResponse,
    ImportProjectProcurementOpportunityRequest,
    ProcurementDecisionUpsert,
    ProcurementUUID,
    RecordProjectProcurementRemediationLinkCopyRequest,
    RecordProjectProcurementRemediationLinkOpenRequest,
    UpdateProjectProcurementOverrideReasonRequest,
)
from app.services.generation.procurement_source import ProcurementGenerationError
from app.storage.procurement_project_store import ProcurementProjectConflict

router = APIRouter()


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
    from app.middleware.billing import acquire_billing_admission
    from app.services.generation.context_store import record_direct_provider_usage
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

    scoped = getattr(request.app.state, "procurement_opportunity_service", None)
    scoped_fields = (
        payload.expected_selection_revision,
        payload.expected_decision_revision,
        payload.operation_id,
    )
    _require_scoped_fields(
        request,
        scoped=scoped,
        scoped_fields=scoped_fields,
        missing_message=(
            "opt-in import에는 expected_selection_revision, "
            "expected_decision_revision, operation_id가 필요합니다."
        ),
    )

    request_identity = payload.model_dump(
        mode="json",
        exclude={
            "expected_selection_revision",
            "expected_decision_revision",
            "operation_id",
        },
    )
    if scoped is not None:
        command = scoped.store.import_command(
            payload=None,
            expected_selection_revision=payload.expected_selection_revision,
            expected_decision_revision=payload.expected_decision_revision,
            request_identity=request_identity,
        )
        try:
            replay = scoped.store.replay_operation(
                project_id,
                tenant_id=tenant_id,
                operation_id=payload.operation_id,
                command=command,
            )
        except ProcurementProjectConflict:
            _raise_scoped_error(
                request,
                code="procurement_context_changed",
                status=409,
                message="operation_id가 다른 import 요청에 이미 사용되었습니다.",
            )
        if replay is not None:
            _apply_procurement_observability(
                request,
                action="import",
                project_id=project_id,
                operation="replayed",
            )
            request.state.procurement_operation_id = replay.operation_id
            request.state.procurement_decision_id = replay.decision_id
            request.state.procurement_decision_revision = replay.decision_revision
            request.state.procurement_selection_revision = replay.selection_revision
            return {
                "project_id": project_id,
                "operation": "replayed",
                "project_name": project.name,
                "receipt": replay.model_dump(mode="json"),
            }
        try:
            scoped.store.assert_import_preconditions(
                project_id,
                tenant_id=tenant_id,
                expected_selection_revision=payload.expected_selection_revision,
            )
        except ProcurementProjectConflict:
            _raise_scoped_error(
                request,
                code="procurement_context_changed",
                status=409,
                message="공고 선택 상태가 변경되었습니다. 최신 상태를 확인하세요.",
            )

    try:
        announcement = await fetch_announcement_detail(
            url_or_number=payload.url_or_number,
            api_key=get_g2b_api_key(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not announcement:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다.")

    normalized_opportunity = _normalize_procurement_opportunity(
        announcement,
        url_or_number=payload.url_or_number,
    )
    if scoped is not None:
        try:
            scoped.store.assert_import_preconditions(
                project_id,
                tenant_id=tenant_id,
                expected_selection_revision=payload.expected_selection_revision,
                expected_decision_revision=payload.expected_decision_revision,
                source_kind=normalized_opportunity.source_kind,
                source_id=normalized_opportunity.source_id,
            )
        except ProcurementProjectConflict:
            _raise_scoped_error(
                request,
                code="procurement_context_changed",
                status=409,
                message="공고 상태가 변경되었습니다. 최신 상태를 확인하세요.",
            )

    parsed_rfp_fields = payload.parsed_rfp_fields
    if parsed_rfp_fields is None and announcement.raw_text:
        admission_lock, rejection = await acquire_billing_admission(request)
        if rejection is not None:
            return rejection
        try:
            provider = get_provider_for_bundle("rfp_analysis_kr", tenant_id)
            parsed_rfp_fields = parse_rfp_fields(announcement.raw_text, provider=provider)
            record_direct_provider_usage(
                request,
                provider,
                bundle_id="procurement.g2b-rfp-analysis",
            )
        finally:
            if admission_lock is not None:
                admission_lock.release()
    if parsed_rfp_fields is None:
        parsed_rfp_fields = {}

    structured_context = payload.structured_context or _build_g2b_structured_context(announcement)
    procurement_store = (
        request.app.state.procurement_opportunity_snapshot_store
        if scoped is not None
        else request.app.state.procurement_store
    )
    existing = (
        procurement_store.get(project_id, tenant_id=tenant_id)
        if scoped is None
        else None
    )
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

    if scoped is None:
        source_snapshots = list(existing.source_snapshots) if existing else []
        source_snapshots.append(snapshot)
        # A new snapshot invalidates derived judgments, even for the same notice ID.
        record = procurement_store.upsert(
            ProcurementDecisionUpsert(
                project_id=project_id,
                tenant_id=tenant_id,
                schema_version=existing.schema_version if existing else "v1",
                opportunity=normalized_opportunity,
                source_snapshots=source_snapshots,
                notes=payload.notes if payload.notes else (existing.notes if existing else ""),
            )
        )
        receipt = None
        operation = "updated" if existing else "created"
    else:
        try:
            receipt = scoped.store.import_opportunity(
                ProcurementDecisionUpsert(
                    project_id=project_id,
                    tenant_id=tenant_id,
                    opportunity=normalized_opportunity,
                    source_snapshots=[snapshot],
                    notes=payload.notes,
                ),
                expected_selection_revision=payload.expected_selection_revision,
                expected_decision_revision=payload.expected_decision_revision,
                operation_id=payload.operation_id,
                request_identity=request_identity,
            )
        except ProcurementProjectConflict:
            _raise_scoped_error(
                request,
                code="procurement_context_changed",
                status=409,
                message="공고 상태가 변경되었습니다. 최신 상태를 확인하세요.",
            )
        record = scoped.get_decision(
            project_id,
            tenant_id=tenant_id,
            decision_id=receipt.decision_id,
        ).record
        operation = "created" if receipt.decision_revision == 1 else "updated"
    _apply_procurement_observability(
        request,
        action="import",
        project_id=project_id,
        operation=operation,
        source_kind="g2b",
        source_id=record.opportunity.source_id if record.opportunity else None,
        record=record,
    )

    response = {
        "project_id": project_id,
        "operation": operation,
        "project_name": project.name,
        "opportunity": record.opportunity.model_dump(mode="json") if record.opportunity else None,
        "decision": record.model_dump(mode="json"),
        "source_snapshot": snapshot.model_dump(mode="json"),
    }
    if receipt is not None:
        response["receipt"] = receipt.model_dump(mode="json")
        request.state.procurement_operation_id = receipt.operation_id
        request.state.procurement_decision_id = receipt.decision_id
        request.state.procurement_decision_revision = receipt.decision_revision
        request.state.procurement_selection_revision = receipt.selection_revision
    return response


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

    scoped = getattr(request.app.state, "procurement_opportunity_service", None)
    selection = {}
    if scoped is None:
        record = request.app.state.procurement_store.get(project_id, tenant_id=tenant_id)
    else:
        from app.routers.projects.procurement_opportunities import procurement_errors
        with procurement_errors(request):
            state = scoped.store.get(project_id, tenant_id=tenant_id)
        record = None
        if state is not None:
            record = next((entry.record for entry in state.entries
                           if entry.record.decision_id == state.active_decision_id), None)
        selection = {"active_decision_id": state.active_decision_id if state else None,
                     "selection_revision": state.selection_revision if state else 0}
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
        **selection,
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
        state_backend=request.app.state.state_backend,
    )
    try:
        scoped = getattr(request.app.state, "procurement_opportunity_service", None)
        if scoped is None:
            record = service.evaluate_project(project_id=project_id, tenant_id=tenant_id)
        else:
            from app.routers.projects.procurement_opportunities import procurement_errors
            with procurement_errors(request):
                record = scoped.calculate_legacy(project_id, tenant_id=tenant_id, action="evaluate")
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
        state_backend=request.app.state.state_backend,
    )
    try:
        scoped = getattr(request.app.state, "procurement_opportunity_service", None)
        if scoped is None:
            record = service.recommend_project(project_id=project_id, tenant_id=tenant_id)
        else:
            from app.routers.projects.procurement_opportunities import procurement_errors
            with procurement_errors(request):
                record = scoped.calculate_legacy(project_id, tenant_id=tenant_id, action="recommend")
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
    decision_id: ProcurementUUID | None = Query(default=None),
    expected_decision_revision: int | None = Query(default=None, ge=1),
) -> DecisionCouncilSessionResponse:
    """Run the procurement-scoped deterministic Decision Council v1."""
    _ensure_procurement_copilot_enabled(request)
    tenant_id = get_tenant_id(request)
    _, record, source_binding = _load_decision_council_procurement_context_or_raise(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
        decision_id=decision_id,
        expected_decision_revision=expected_decision_revision,
    )

    service = request.app.state.decision_council_service
    session = service.run_procurement_council(
        tenant_id=tenant_id,
        project_id=project_id,
        goal=payload.goal,
        context=payload.context,
        constraints=payload.constraints,
        procurement_record=record,
        source_binding=source_binding,
    )
    if source_binding is not None:
        resolver = request.app.state.procurement_generation_resolver
        try:
            current_source = resolver.capture(
                project_id,
                tenant_id=tenant_id,
                decision_id=source_binding.decision_id,
                expected_revision=source_binding.decision_revision,
            )
        except ProcurementGenerationError:
            current_source = None
        if current_source is None:
            scoped = request.app.state.procurement_opportunity_service
            try:
                record = scoped.get_decision(
                    project_id,
                    tenant_id=tenant_id,
                    decision_id=source_binding.decision_id,
                ).record
            except LookupError:
                pass
            source_binding = None
        else:
            record = current_source.record
            source_binding = current_source.binding
    session = _attach_decision_council_binding(
        request,
        session=session,
        record=record,
        source_binding=source_binding,
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
    decision_id: ProcurementUUID | None = Query(default=None),
    expected_decision_revision: int | None = Query(default=None, ge=1),
) -> DecisionCouncilSessionResponse:
    """Return the latest canonical Decision Council session for the project."""
    _ensure_procurement_copilot_enabled(request)
    tenant_id = get_tenant_id(request)
    _, record, source_binding = _load_decision_council_procurement_context_or_raise(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
        decision_id=decision_id,
        expected_decision_revision=expected_decision_revision,
    )

    service = request.app.state.decision_council_service
    session = service.get_latest_procurement_council(
        tenant_id=tenant_id,
        project_id=project_id,
        decision_id=record.decision_id if source_binding is not None else None,
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
        source_binding=source_binding,
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

    scoped = getattr(request.app.state, "procurement_opportunity_service", None)
    scoped_fields = (
        payload.decision_id,
        payload.expected_decision_revision,
        payload.operation_id,
    )
    _require_scoped_fields(
        request,
        scoped=scoped,
        scoped_fields=scoped_fields,
        missing_message=(
            "opt-in override에는 decision_id, expected_decision_revision, "
            "operation_id가 필요합니다."
        ),
    )

    if scoped is None:
        procurement_store = request.app.state.procurement_store
        existing = procurement_store.get(project_id, tenant_id=tenant_id)
    else:
        try:
            entry = scoped.get_decision(
                project_id,
                tenant_id=tenant_id,
                decision_id=payload.decision_id,
            )
        except LookupError:
            _raise_scoped_error(
                request,
                code="procurement_opportunity_not_found",
                status=404,
                message="공고를 찾을 수 없습니다.",
            )
        existing = entry.record
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
    if scoped is None:
        updated = procurement_store.update_notes(
            project_id=project_id,
            tenant_id=tenant_id,
            notes=_append_procurement_override_reason(
                existing.notes,
                username=username,
                reason=payload.reason,
            ),
        )
        receipt = None
    else:
        try:
            receipt = scoped.store.update_notes(
                project_id,
                tenant_id=tenant_id,
                decision_id=payload.decision_id,
                expected_decision_revision=payload.expected_decision_revision,
                operation_id=payload.operation_id,
                command_identity={"actor": username, "reason": payload.reason},
                update=lambda notes: _append_procurement_override_reason(
                    notes,
                    username=username,
                    reason=payload.reason,
                ),
            )
        except ProcurementProjectConflict:
            _raise_scoped_error(
                request,
                code="procurement_context_changed",
                status=409,
                message="공고 상태가 변경되었습니다. 최신 상태를 확인하세요.",
            )
        updated = scoped.get_decision(
            project_id,
            tenant_id=tenant_id,
            decision_id=receipt.decision_id,
        ).record
    _apply_procurement_observability(
        request,
        action="override_reason",
        project_id=project_id,
        operation="updated",
        record=updated,
    )
    response = {
        "project_id": project_id,
        "project_name": project.name,
        "decision": updated.model_dump(mode="json"),
        "override_reason_saved": True,
    }
    if receipt is not None:
        response["receipt"] = receipt.model_dump(mode="json")
        request.state.procurement_operation_id = receipt.operation_id
        request.state.procurement_decision_id = receipt.decision_id
        request.state.procurement_decision_revision = receipt.decision_revision
    return response


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

    return _record_remediation_link_event(
        request,
        action="remediation_link_copied",
        project_id=project_id,
        project_name=project.name,
        payload=payload,
    )


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

    return _record_remediation_link_event(
        request,
        action="remediation_link_opened",
        project_id=project_id,
        project_name=project.name,
        payload=payload,
    )
