"""Session-authorized, decision-scoped requirement review annotations."""
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.dependencies import (
    get_tenant_id,
    require_session_bound_admin,
    require_session_bound_procurement_reviewer,
)
from app.routers.projects.procurement_opportunities import (
    DecisionID,
    _record_receipt,
    _service as opportunity_service,
    procurement_errors,
)
from app.routers.projects.procurement import _apply_procurement_observability
from app.schemas.procurement_applicability import (
    AnnotateProcurementRequirementRequest,
    CreateProcurementRequirementRequest,
)
from app.services.procurement_applicability_service import (
    ProcurementApplicabilityService, redact_requirement_actors,
)
from app.services.procurement_review_access import authorized_review_records, get_procurement_review_access
from app.storage.procurement_review_models import ProcurementReviewStoreError
from app.storage.procurement_store import ProcurementDecisionStoreError


router = APIRouter(prefix="/projects/{project_id}/procurement/opportunities/{decision_id}/requirements")


def _service(project_id: str, request: Request) -> ProcurementApplicabilityService:
    opportunity_service(project_id, request)
    service = getattr(request.app.state, "procurement_applicability_service", None)
    if service is None:
        raise HTTPException(status_code=403, detail={"code": "FEATURE_DISABLED"})
    return service


Service = Annotated[ProcurementApplicabilityService, Depends(_service)]


@contextmanager
def _errors(request: Request):
    with procurement_errors(request):
        try:
            yield
        except ProcurementReviewStoreError as exc:
            request.state.error_code = "procurement_state_unavailable"
            raise HTTPException(status_code=503, detail={"code": "procurement_state_unavailable"}) from exc
        except ProcurementDecisionStoreError:
            raise
        except ValueError as exc:
            request.state.error_code = "procurement_requirement_invalid"
            raise HTTPException(status_code=422, detail={"code": "procurement_requirement_invalid"}) from exc


def _read_access(project_id: str, decision_id: str, request: Request) -> bool:
    access = get_procurement_review_access(request)
    request.state.procurement_review_access_scope = access.scope
    if access.is_admin:
        return True
    store = request.app.state.procurement_review_store
    records = store.list_by_project(
        tenant_id=get_tenant_id(request), project_id=project_id, reviewer_user_id=access.user_id,
    )
    authorized = store.filter_by_decision(
        authorized_review_records(records, access), tenant_id=get_tenant_id(request),
        project_id=project_id, decision_id=decision_id,
    )
    request.state.procurement_review_authorized_count = len(authorized)
    if not authorized:
        raise HTTPException(status_code=404, detail="요구사항을 조회할 수 없습니다.")
    return False


def _headers(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-DecisionDoc-Operational-Approval"] = "false"


@router.get("", dependencies=[Depends(require_session_bound_procurement_reviewer)])
def list_requirements(
    project_id: str, decision_id: DecisionID, request: Request, response: Response, service: Service,
    expected_decision_revision: int | None = Query(default=None, ge=1),
) -> dict:
    _apply_procurement_observability(request, action="requirement_list", project_id=project_id)
    request.state.procurement_decision_id = decision_id
    with _errors(request):
        is_admin = _read_access(project_id, decision_id, request)
        captured = service.capture(project_id, tenant_id=get_tenant_id(request), decision_id=decision_id,
                                   expected_revision=expected_decision_revision)
        requirements = service.project_requirements(captured)
        service.assert_current(captured)
    if not is_admin:
        requirements = redact_requirement_actors(requirements)
    _headers(response)
    request.state.procurement_decision_revision = captured.binding.decision_revision
    return {"project_id": project_id, "decision_id": decision_id,
            "decision_revision": captured.binding.decision_revision,
            "requirements": requirements, "operational_approval": False, "export_available": True}


@router.get("/sources", dependencies=[Depends(require_session_bound_admin)])
def list_requirement_sources(
    project_id: str, decision_id: DecisionID, request: Request, response: Response, service: Service,
    expected_decision_revision: int = Query(ge=1),
) -> dict:
    _apply_procurement_observability(request, action="requirement_sources", project_id=project_id)
    request.state.procurement_decision_id = decision_id
    with _errors(request):
        captured = service.capture(project_id, tenant_id=get_tenant_id(request), decision_id=decision_id,
                                   expected_revision=expected_decision_revision)
        sources = service.list_sources(captured)
    _headers(response)
    request.state.procurement_decision_revision = captured.binding.decision_revision
    return {"decision_id": decision_id, "decision_revision": captured.binding.decision_revision,
            "sources": sources, "operational_approval": False}


def _command_audit(project_id: str, decision_id: str, payload, request: Request, *, action: str) -> None:
    _apply_procurement_observability(request, action=action, project_id=project_id)
    request.state.procurement_decision_id = decision_id
    request.state.procurement_operation_id = payload.operation_id
    request.state.procurement_expected_decision_revision = payload.expected_decision_revision
    request.state.procurement_review_operational_approval = False


@router.post("", dependencies=[Depends(require_session_bound_admin)])
def create_requirement(project_id: str, decision_id: DecisionID, payload: CreateProcurementRequirementRequest, request: Request, response: Response, service: Service) -> dict:
    _command_audit(project_id, decision_id, payload, request, action="requirement_create")
    with _errors(request):
        receipt = service.create_requirement(
            project_id, tenant_id=get_tenant_id(request), decision_id=decision_id,
            actor_id=request.state.user_id, payload=payload,
        )
    _record_receipt(request, receipt)
    _headers(response)
    return {"project_id": project_id, "receipt": receipt.model_dump(mode="json"), "operational_approval": False}


@router.post("/{requirement_id}/applicability", dependencies=[Depends(require_session_bound_admin)])
def annotate_requirement(project_id: str, decision_id: DecisionID, requirement_id: DecisionID, payload: AnnotateProcurementRequirementRequest, request: Request, response: Response, service: Service) -> dict:
    _command_audit(project_id, decision_id, payload, request, action="requirement_annotate")
    with _errors(request):
        receipt = service.annotate_requirement(
            project_id, tenant_id=get_tenant_id(request), decision_id=decision_id,
            requirement_id=requirement_id, actor_id=request.state.user_id, payload=payload,
        )
    _record_receipt(request, receipt)
    _headers(response)
    return {"project_id": project_id, "receipt": receipt.model_dump(mode="json"), "operational_approval": False}
