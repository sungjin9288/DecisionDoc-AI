"""``DecisionCouncilService`` — deterministic council session from procurement state.

Public entry points (``run_procurement_council``, ``get_latest_procurement_council``,
``attach_procurement_binding``, ``build_generation_context``) live here; the
private synthesis builder methods live in ``CouncilSynthesisMixin``
(``app/services/decision_council/council_synthesis_mixin.py``).
"""
from __future__ import annotations

import uuid

from app.schemas import (
    DecisionCouncilSessionResponse,
    ProcurementDecisionRecord,
)
from app.services.decision_council.binding import (
    _build_procurement_binding_metrics,
    build_procurement_council_generation_context,
    describe_procurement_council_binding,
)
from app.services.decision_council.council_synthesis_mixin import CouncilSynthesisMixin
from app.storage.decision_council_store import DecisionCouncilStore

_ROLE_ORDER = (
    "Requirement Analyst",
    "Risk Reviewer",
    "Domain Strategist",
    "Compliance Reviewer",
    "Drafting Lead",
)


class DecisionCouncilService(CouncilSynthesisMixin):
    """Build a deterministic council session from existing procurement state."""

    def __init__(self, *, decision_council_store: DecisionCouncilStore) -> None:
        self._decision_council_store = decision_council_store

    def run_procurement_council(
        self,
        *,
        tenant_id: str,
        project_id: str,
        goal: str,
        context: str = "",
        constraints: str = "",
        procurement_record: ProcurementDecisionRecord,
    ) -> DecisionCouncilSessionResponse:
        if procurement_record.opportunity is None or procurement_record.recommendation is None:
            raise KeyError("decision_council_procurement_context_required")

        recommendation_value = procurement_record.recommendation.value
        recommendation_value_text = getattr(recommendation_value, "value", recommendation_value) or ""
        hard_failures = [
            item for item in procurement_record.hard_filters if item.blocking and item.status == "fail"
        ]
        actionable_items = [
            item for item in procurement_record.checklist_items if item.status in {"blocked", "action_needed"}
        ]
        missing_data = [item for item in procurement_record.missing_data if str(item).strip()]
        top_risks = self._build_top_risks(
            procurement_record=procurement_record,
            hard_failures=hard_failures,
            actionable_items=actionable_items,
            missing_data=missing_data,
        )
        open_questions = self._build_open_questions(missing_data=missing_data, actionable_items=actionable_items)
        conditions = self._build_conditions(
            recommendation_value=recommendation_value,
            actionable_items=actionable_items,
            missing_data=missing_data,
        )
        disagreements = self._build_disagreements(
            recommendation_value=recommendation_value,
            hard_failures=hard_failures,
            actionable_items=actionable_items,
            missing_data=missing_data,
            soft_fit_score=procurement_record.soft_fit_score,
        )
        consensus = self._build_consensus(
            procurement_record=procurement_record,
            top_risks=top_risks,
            disagreements=disagreements,
            conditions=conditions,
            open_questions=open_questions,
        )
        role_opinions = self._build_role_opinions(
            goal=goal,
            procurement_record=procurement_record,
            top_risks=top_risks,
            disagreements=disagreements,
            conditions=conditions,
            open_questions=open_questions,
        )
        handoff = self._build_handoff(
            goal=goal,
            context=context,
            constraints=constraints,
            procurement_record=procurement_record,
            top_risks=top_risks,
            conditions=conditions,
            open_questions=open_questions,
            consensus=consensus,
        )

        session = DecisionCouncilSessionResponse.model_validate(
            {
                "session_id": str(uuid.uuid4()),
                "session_key": DecisionCouncilStore.build_session_key(
                    project_id=project_id,
                    use_case="public_procurement",
                    target_bundle_type="bid_decision_kr",
                ),
                "session_revision": 1,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "use_case": "public_procurement",
                "target_bundle_type": "bid_decision_kr",
                "goal": goal,
                "context": context or "",
                "constraints": constraints or "",
                "source_procurement_decision_id": procurement_record.decision_id,
                "source_procurement_updated_at": procurement_record.updated_at,
                "source_procurement_recommendation_value": recommendation_value_text,
                "source_procurement_missing_data_count": len(missing_data),
                "source_procurement_action_needed_count": len(actionable_items),
                "source_procurement_blocking_hard_filter_count": len(hard_failures),
                "source_snapshot_ids": [
                    snapshot.snapshot_id for snapshot in procurement_record.source_snapshots
                ],
                "created_at": procurement_record.updated_at,
                "updated_at": procurement_record.updated_at,
                "role_opinions": [opinion.model_dump(mode="json") for opinion in role_opinions],
                "disagreements": disagreements,
                "risks": top_risks,
                "consensus": consensus.model_dump(mode="json"),
                "handoff": handoff.model_dump(mode="json"),
            }
        )
        stored, _ = self._decision_council_store.upsert_latest(session)
        return stored

    def get_latest_procurement_council(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> DecisionCouncilSessionResponse | None:
        return self._decision_council_store.get_latest(
            tenant_id=tenant_id,
            project_id=project_id,
            use_case="public_procurement",
            target_bundle_type="bid_decision_kr",
        )

    def attach_procurement_binding(
        self,
        *,
        session: DecisionCouncilSessionResponse,
        procurement_record: ProcurementDecisionRecord | None,
    ) -> DecisionCouncilSessionResponse:
        binding = describe_procurement_council_binding(
            session=session,
            procurement_record=procurement_record,
        )
        current_metrics = _build_procurement_binding_metrics(procurement_record)
        return session.model_copy(
            update={
                "current_procurement_binding_status": binding["status"],
                "current_procurement_binding_reason_code": binding["reason_code"],
                "current_procurement_binding_summary": binding["summary"],
                "current_procurement_updated_at": str(current_metrics["updated_at"] or ""),
                "current_procurement_recommendation_value": str(
                    current_metrics["recommendation_value"] or ""
                ),
                "current_procurement_missing_data_count": int(
                    current_metrics["missing_data_count"]
                ),
                "current_procurement_action_needed_count": int(
                    current_metrics["action_needed_count"]
                ),
                "current_procurement_blocking_hard_filter_count": int(
                    current_metrics["blocking_hard_filter_count"]
                ),
            }
        )

    def build_generation_context(
        self,
        session: DecisionCouncilSessionResponse,
        *,
        bundle_type: str = "bid_decision_kr",
    ) -> str:
        return build_procurement_council_generation_context(
            session,
            bundle_type=bundle_type,
        )
