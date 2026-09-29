"""Private helpers for app/routers/projects/procurement.py.

Moved verbatim from procurement.py to keep the router module within the
800-line guide; public names stay importable from procurement.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request

from app.schemas import (
    DecisionCouncilSessionResponse,
    NormalizedProcurementOpportunity,
)
from app.services.generation.procurement_source import ProcurementGenerationError
from app.storage.procurement_store import ProcurementDecisionStoreError


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
    decision_id: str | None = None,
    expected_decision_revision: int | None = None,
):
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    scoped_context = _resolve_scoped_procurement_context(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
        decision_id=decision_id,
        expected_decision_revision=expected_decision_revision,
    )
    if scoped_context is None:
        procurement_store = request.app.state.procurement_store
        record = procurement_store.get(project_id, tenant_id=tenant_id)
        source_binding = None
    else:
        entry, source = scoped_context
        record = entry.record
        source_binding = source.binding
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
    return project, record, source_binding


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
    source_binding=None,
) -> DecisionCouncilSessionResponse:
    service = request.app.state.decision_council_service
    return service.attach_procurement_binding(
        session=session,
        procurement_record=record,
        source_binding=source_binding,
    )


def _raise_scoped_error(request: Request, *, code: str, status: int, message: str):
    request.state.error_code = code
    raise HTTPException(
        status_code=status,
        detail={"code": code, "message": message},
    )


def _resolve_scoped_procurement_context(
    request: Request,
    *,
    project_id: str,
    tenant_id: str,
    decision_id: str | None,
    expected_decision_revision: int | None,
):
    """Resolve one exact v2 entry without consulting the active selection."""
    if (decision_id is None) != (expected_decision_revision is None):
        _raise_scoped_error(
            request,
            code="procurement_scope_invalid",
            status=422,
            message=(
                "decision_id와 expected_decision_revision을 함께 제공해야 합니다."
            ),
        )
    scoped = getattr(request.app.state, "procurement_opportunity_service", None)
    if scoped is None:
        if decision_id is not None:
            _raise_scoped_error(
                request,
                code="FEATURE_DISABLED",
                status=403,
                message="공고별 lifecycle이 이 앱 인스턴스에서 비활성화되어 있습니다.",
            )
        return None

    try:
        state = scoped.store.get(project_id, tenant_id=tenant_id)
    except ProcurementDecisionStoreError:
        _raise_scoped_error(
            request,
            code="procurement_state_unavailable",
            status=503,
            message="저장 상태를 확인할 수 없습니다.",
        )
    entries = state.entries if state is not None else []
    if decision_id is None:
        if len(entries) > 1:
            _raise_scoped_error(
                request,
                code="procurement_opportunity_selection_required",
                status=409,
                message="공고 ID와 revision을 명시해야 합니다.",
            )
        if not entries:
            return None
        entry = entries[0]
    else:
        try:
            entry = scoped.get_decision(
                project_id,
                tenant_id=tenant_id,
                decision_id=decision_id,
            )
        except LookupError:
            _raise_scoped_error(
                request,
                code="procurement_opportunity_not_found",
                status=404,
                message="공고를 찾을 수 없습니다.",
            )
        if entry.decision_revision != expected_decision_revision:
            _raise_scoped_error(
                request,
                code="procurement_context_changed",
                status=409,
                message="공고 revision이 변경되었습니다. 최신 상태를 확인하세요.",
            )

    resolver = request.app.state.procurement_generation_resolver
    try:
        source = resolver.capture(
            project_id,
            tenant_id=tenant_id,
            decision_id=entry.record.decision_id,
            expected_revision=entry.decision_revision,
        )
    except ProcurementGenerationError as exc:
        _raise_scoped_error(
            request,
            code=exc.code,
            status=exc.status_code,
            message="공고 원문 결속을 확인할 수 없습니다.",
        )
    return entry, source


def _require_scoped_fields(
    request: Request,
    *,
    scoped,
    scoped_fields: tuple,
    missing_message: str,
) -> None:
    """Require all opt-in scope fields when enabled, and none when disabled."""
    if scoped is not None and not all(value is not None for value in scoped_fields):
        _raise_scoped_error(
            request,
            code="procurement_scope_invalid",
            status=422,
            message=missing_message,
        )
    if scoped is None and any(value is not None for value in scoped_fields):
        _raise_scoped_error(
            request,
            code="FEATURE_DISABLED",
            status=403,
            message="공고별 lifecycle이 이 앱 인스턴스에서 비활성화되어 있습니다.",
        )


def _record_remediation_link_event(
    request: Request,
    *,
    action: str,
    project_id: str,
    project_name: str,
    payload,
) -> dict:
    """Shape observability state and response for remediation link events."""
    request.state.procurement_action = action
    request.state.procurement_project_id = project_id
    request.state.procurement_operation = payload.source
    request.state.procurement_context_kind = payload.context_kind
    request.state.procurement_recommendation = payload.recommendation.strip() or None
    request.state.bundle_type = payload.bundle_type.strip() or None
    request.state.procurement_error_code = payload.error_code.strip() or None

    return {
        "project_id": project_id,
        "project_name": project_name,
        "logged": True,
        "source": payload.source,
        "context_kind": payload.context_kind,
    }
