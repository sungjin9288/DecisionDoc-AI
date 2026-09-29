"""Decision-scoped procurement operations; runtime activation is intentionally deferred."""
from uuid import uuid4

from app.schemas import ProcurementDecisionRecord
from app.services.procurement_decision_service import ProcurementDecisionService
from app.storage.procurement_project_state import ProcurementDecisionEntry, ProcurementMutationReceipt
from app.storage.procurement_project_store import ProcurementProjectConflict, ProcurementProjectStore


class ProcurementOpportunityNotFound(LookupError):
    pass


class ProcurementOpportunitySelectionRequired(ProcurementProjectConflict):
    pass


class ProcurementOpportunityService:
    def __init__(self, *, store: ProcurementProjectStore, evaluator: ProcurementDecisionService) -> None:
        self.store = store
        self._evaluator = evaluator

    def get_decision(self, project_id: str, *, tenant_id: str, decision_id: str) -> ProcurementDecisionEntry:
        project = self.store.get(project_id, tenant_id=tenant_id)
        if project is not None:
            for entry in project.entries:
                if entry.record.decision_id == decision_id:
                    return entry
        raise ProcurementOpportunityNotFound("Procurement opportunity not found")

    def calculate(
        self, project_id: str, *, tenant_id: str, decision_id: str, action: str,
        expected_decision_revision: int, operation_id: str,
    ) -> ProcurementMutationReceipt:
        self.get_decision(project_id, tenant_id=tenant_id, decision_id=decision_id)
        if action == "evaluate":
            compute = self._evaluator.evaluate_record
        elif action == "recommend":
            compute = self._evaluator.recommend_record
        else:
            raise ValueError("Unsupported procurement calculation")
        return self.store.compute_decision(
            project_id, tenant_id=tenant_id, decision_id=decision_id, action=action,
            expected_decision_revision=expected_decision_revision, operation_id=operation_id, compute=compute,
        )

    def calculate_legacy(self, project_id: str, *, tenant_id: str, action: str) -> ProcurementDecisionRecord:
        project = self.store.get(project_id, tenant_id=tenant_id)
        if project is None or not project.entries:
            raise KeyError("procurement_opportunity_not_attached")
        if len(project.entries) != 1:
            raise ProcurementOpportunitySelectionRequired("Explicit decision identity is required")
        entry = project.entries[0]
        self.calculate(
            project_id, tenant_id=tenant_id, decision_id=entry.record.decision_id, action=action,
            expected_decision_revision=entry.decision_revision, operation_id=str(uuid4()),
        )
        return self.get_decision(project_id, tenant_id=tenant_id, decision_id=entry.record.decision_id).record
