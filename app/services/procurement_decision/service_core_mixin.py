"""Core orchestration mixin: init, evaluate/recommend entry points, input building.

Extracted from ``app.services.procurement_decision_service`` (pure code
move, no behavior changes).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from app.schemas import (
    CapabilityProfileReference,
    ProcurementDecisionRecord,
    ProcurementDecisionUpsert,
)
from app.services.procurement_decision.constants import _EvaluationInputs
from app.services.procurement_decision.text_utils import _now_utc, _unique
from app.storage.knowledge_store import KnowledgeStore
from app.storage.procurement_store import ProcurementDecisionStore


class ServiceCoreMixin:
    """Init, top-level evaluate/recommend entry points, and input assembly."""

    _procurement_store: ProcurementDecisionStore
    _data_dir: str
    _now_provider: Callable[[], datetime]

    def __init__(
        self,
        *,
        procurement_store: ProcurementDecisionStore,
        data_dir: str = "data",
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._procurement_store = procurement_store
        self._data_dir = data_dir
        self._now_provider = now_provider or _now_utc

    def evaluate_project(self, *, project_id: str, tenant_id: str) -> ProcurementDecisionRecord:
        existing = self._procurement_store.get(project_id, tenant_id=tenant_id)
        if existing is None or existing.opportunity is None:
            raise KeyError("procurement_opportunity_not_attached")

        inputs = self._build_inputs(existing)
        hard_filters, missing_data = self._evaluate_hard_filters(existing, inputs)
        score_breakdown, soft_fit_score, soft_fit_status, scoring_missing = self._evaluate_soft_fit(
            hard_filters,
            inputs,
        )
        payload = ProcurementDecisionUpsert(
            project_id=existing.project_id,
            tenant_id=existing.tenant_id,
            schema_version=existing.schema_version,
            opportunity=existing.opportunity,
            capability_profile=inputs.capability_profile,
            hard_filters=hard_filters,
            score_breakdown=score_breakdown,
            soft_fit_score=soft_fit_score,
            soft_fit_status=soft_fit_status,
            missing_data=_unique(missing_data + scoring_missing),
            checklist_items=list(existing.checklist_items),
            recommendation=existing.recommendation,
            source_snapshots=list(existing.source_snapshots),
            notes=existing.notes,
        )
        return self._procurement_store.upsert(payload)

    def recommend_project(self, *, project_id: str, tenant_id: str) -> ProcurementDecisionRecord:
        evaluated = self.evaluate_project(project_id=project_id, tenant_id=tenant_id)
        recommendation = self._build_recommendation(evaluated)
        checklist_items = self._build_checklist(evaluated)
        payload = ProcurementDecisionUpsert(
            project_id=evaluated.project_id,
            tenant_id=evaluated.tenant_id,
            schema_version=evaluated.schema_version,
            opportunity=evaluated.opportunity,
            capability_profile=evaluated.capability_profile,
            hard_filters=list(evaluated.hard_filters),
            score_breakdown=list(evaluated.score_breakdown),
            soft_fit_score=evaluated.soft_fit_score,
            soft_fit_status=evaluated.soft_fit_status,
            missing_data=list(evaluated.missing_data),
            checklist_items=checklist_items,
            recommendation=recommendation,
            source_snapshots=list(evaluated.source_snapshots),
            notes=evaluated.notes,
        )
        return self._procurement_store.upsert(payload)

    def _build_inputs(self, record: ProcurementDecisionRecord) -> _EvaluationInputs:
        capability_profile, capability_text = self._resolve_capability_profile(record.project_id)
        latest_snapshot_payload = self._load_latest_snapshot_payload(record)
        parsed_rfp_fields = latest_snapshot_payload.get("extracted_fields", {}) or {}
        opportunity_text = "\n".join(
            filter(
                None,
                [
                    record.opportunity.title if record.opportunity else "",
                    record.opportunity.issuer if record.opportunity else "",
                    record.opportunity.raw_text_preview if record.opportunity else "",
                    latest_snapshot_payload.get("structured_context", ""),
                    latest_snapshot_payload.get("announcement", {}).get("raw_text", ""),
                    parsed_rfp_fields.get("objective", ""),
                    "\n".join(parsed_rfp_fields.get("key_requirements", []) or []),
                    "\n".join(parsed_rfp_fields.get("evaluation_criteria", []) or []),
                ],
            )
        )
        deadline_text = parsed_rfp_fields.get("deadline") or (record.opportunity.deadline if record.opportunity else "")
        budget_text = parsed_rfp_fields.get("budget") or (record.opportunity.budget if record.opportunity else "")
        return _EvaluationInputs(
            capability_profile=capability_profile,
            capability_text=capability_text,
            latest_snapshot_payload=latest_snapshot_payload,
            parsed_rfp_fields=parsed_rfp_fields,
            opportunity_text=opportunity_text,
            deadline_text=deadline_text,
            budget_text=budget_text,
        )

    def _resolve_capability_profile(
        self,
        project_id: str,
    ) -> tuple[CapabilityProfileReference | None, str]:
        store = KnowledgeStore(project_id, data_dir=self._data_dir)
        docs = store.list_documents()
        if not docs:
            return None, ""
        context = store.build_context()
        filenames = [doc.get("filename", "") for doc in docs[:3] if doc.get("filename")]
        title = ", ".join(filenames) if filenames else "project knowledge"
        summary = context[:300]
        return (
            CapabilityProfileReference(
                source_kind="knowledge_document",
                source_ref=project_id,
                title=title,
                summary=summary,
                document_ids=[doc["doc_id"] for doc in docs if doc.get("doc_id")],
            ),
            context,
        )

    def _load_latest_snapshot_payload(self, record: ProcurementDecisionRecord) -> dict[str, Any]:
        if not record.source_snapshots:
            return {}
        latest = record.source_snapshots[-1]
        payload = self._procurement_store.load_source_snapshot(
            tenant_id=record.tenant_id,
            project_id=record.project_id,
            snapshot_id=latest.snapshot_id,
        )
        return payload if isinstance(payload, dict) else {}
