"""Scoped procurement router. Not registered by the default app factory yet."""
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id
from app.routers.projects.procurement import _apply_procurement_observability, _ensure_procurement_copilot_enabled
from app.schemas.procurement import ProcurementEvaluationRequest, ProcurementSelectionRequest, ProcurementUUID
from app.services.procurement_opportunity_service import (
    ProcurementOpportunityNotFound,
    ProcurementOpportunitySelectionRequired,
    ProcurementOpportunityService,
)
from app.storage.procurement_project_store import ProcurementProjectConflict
from app.storage.procurement_project_state import ProcurementMutationReceipt
from app.storage.procurement_store import ProcurementDecisionStoreError


router = APIRouter(prefix="/projects/{project_id}/procurement", dependencies=[Depends(require_api_key)])
DecisionID = Annotated[ProcurementUUID, Path()]


@contextmanager
def procurement_errors(request: Request):
    try:
        yield
    except ProcurementOpportunityNotFound as exc:
        code, status, message = "procurement_opportunity_not_found", 404, "공고를 찾을 수 없습니다."
        error = exc
    except ProcurementOpportunitySelectionRequired as exc:
        code, status, message = "procurement_opportunity_selection_required", 409, "공고 ID를 명시해야 합니다."
        error = exc
    except ProcurementProjectConflict as exc:
        code, status, message = "procurement_context_changed", 409, "상태가 변경되었습니다. 최신 상태를 확인하세요."
        error = exc
    except ProcurementDecisionStoreError as exc:
        code, status, message = "procurement_state_unavailable", 503, "저장 상태를 확인할 수 없습니다."
        error = exc
    except KeyError as exc:
        if exc.args != ("procurement_opportunity_not_attached",):
            raise
        code, status, message = "procurement_opportunity_not_attached", 409, "평가할 공고가 연결되어 있지 않습니다."
        error = exc
    else:
        return
    request.state.error_code = code
    raise HTTPException(status_code=status, detail={"code": code, "message": message}) from error


def _service(project_id: str, request: Request) -> ProcurementOpportunityService:
    _ensure_procurement_copilot_enabled(request)
    if request.app.state.project_store.get(project_id, tenant_id=get_tenant_id(request)) is None:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")
    service = getattr(request.app.state, "procurement_opportunity_service", None)
    if service is None:
        raise HTTPException(status_code=403, detail={"code": "FEATURE_DISABLED"})
    return service


ScopedService = Annotated[ProcurementOpportunityService, Depends(_service)]


@router.get("/opportunities")
def list_opportunities(
    project_id: str, request: Request, service: ScopedService,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    with procurement_errors(request):
        project = service.store.get(project_id, tenant_id=get_tenant_id(request))
    entries = project.entries if project else []
    items = []
    for entry in entries[offset:offset + limit]:
        record = entry.record
        opportunity = record.opportunity
        items.append({
            "decision_id": record.decision_id, "decision_revision": entry.decision_revision,
            "title": opportunity.title if opportunity else "",
            "source_id": opportunity.source_id if opportunity else "",
            "source_kind": opportunity.source_kind if opportunity else "",
            "updated_at": record.updated_at,
            "recommendation": record.recommendation.value if record.recommendation else None,
        })
    _apply_procurement_observability(request, action="list_opportunities", project_id=project_id)
    return {"project_id": project_id, "active_decision_id": project.active_decision_id if project else None,
            "selection_revision": project.selection_revision if project else 0,
            "items": items, "total": len(entries), "limit": limit, "offset": offset}


@router.get("/opportunities/{decision_id}")
def get_opportunity(project_id: str, decision_id: DecisionID, request: Request, service: ScopedService) -> dict:
    request.state.procurement_decision_id = decision_id
    with procurement_errors(request):
        entry = service.get_decision(project_id, tenant_id=get_tenant_id(request), decision_id=decision_id)
    _apply_procurement_observability(request, action="read", project_id=project_id, record=entry.record)
    request.state.procurement_decision_revision = entry.decision_revision
    return {"project_id": project_id, "decision_revision": entry.decision_revision,
            "decision": entry.record.model_dump(mode="json")}


@router.post("/selection")
def select_opportunity(
    project_id: str, payload: ProcurementSelectionRequest, request: Request, service: ScopedService,
) -> dict:
    _apply_procurement_observability(request, action="select", project_id=project_id)
    request.state.procurement_decision_id = payload.decision_id
    request.state.procurement_operation_id = payload.operation_id
    request.state.procurement_expected_selection_revision = payload.expected_selection_revision
    with procurement_errors(request):
        service.get_decision(project_id, tenant_id=get_tenant_id(request), decision_id=payload.decision_id)
        receipt = service.store.select(project_id, tenant_id=get_tenant_id(request), **payload.model_dump())
    _record_receipt(request, receipt)
    return {"project_id": project_id, "receipt": receipt.model_dump(mode="json")}


def _record_receipt(request: Request, receipt: ProcurementMutationReceipt) -> None:
    for field, value in receipt.model_dump().items():
        setattr(request.state, "procurement_" + field, value)


def _calculate(
    project_id: str, decision_id: str, payload: ProcurementEvaluationRequest,
    request: Request, service: ProcurementOpportunityService, *, action: str,
) -> dict:
    _apply_procurement_observability(request, action=action, project_id=project_id)
    request.state.procurement_decision_id = decision_id
    request.state.procurement_operation_id = payload.operation_id
    request.state.procurement_expected_decision_revision = payload.expected_decision_revision
    with procurement_errors(request):
        receipt = service.calculate(project_id, tenant_id=get_tenant_id(request), decision_id=decision_id,
                                    action=action, **payload.model_dump())
    _record_receipt(request, receipt)
    return {"project_id": project_id, "receipt": receipt.model_dump(mode="json")}


@router.post("/opportunities/{decision_id}/evaluate")
def evaluate_opportunity(
    project_id: str, decision_id: DecisionID, payload: ProcurementEvaluationRequest,
    request: Request, service: ScopedService,
) -> dict:
    return _calculate(project_id, decision_id, payload, request, service, action="evaluate")


@router.post("/opportunities/{decision_id}/recommend")
def recommend_opportunity(
    project_id: str, decision_id: DecisionID, payload: ProcurementEvaluationRequest,
    request: Request, service: ScopedService,
) -> dict:
    return _calculate(project_id, decision_id, payload, request, service, action="recommend")
