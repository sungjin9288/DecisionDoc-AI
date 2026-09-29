"""Deterministic demo procurement decision record seeding.

Seeds a local ProcurementDecisionStore with a fixed demo decision record used by
the decision package demo run. Local and deterministic only; it does not call
providers, AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

from pathlib import Path

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)
from app.services.procurement_decision_package.constants import (
    DEMO_PROJECT_ID,
    DEMO_RECOMMENDATION,
    DEMO_TENANT_ID,
)
from app.storage.procurement_store import ProcurementDecisionStore


def seed_demo_decision_record(
    *,
    data_dir: Path,
    tenant_id: str = DEMO_TENANT_ID,
    project_id: str = DEMO_PROJECT_ID,
) -> str:
    store = ProcurementDecisionStore(base_dir=str(data_dir))

    record = store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id=tenant_id,
            opportunity=_demo_decision_opportunity(),
            hard_filters=_demo_decision_hard_filters(),
            score_breakdown=_demo_decision_score_breakdown(),
            soft_fit_score=68.0,
            soft_fit_status="scored",
            missing_data=_demo_decision_missing_data(),
            checklist_items=_demo_decision_checklist_items(),
            recommendation=_demo_decision_recommendation(),
            notes=(
                "Local package demo seed record. "
                "Does not authorize operational action."
            ),
        )
    )

    return record.decision_id


def _demo_decision_opportunity() -> NormalizedProcurementOpportunity:
    return NormalizedProcurementOpportunity(
        source_kind="local_demo",
        source_id="local-procurement-demo-001",
        title="Public Agency Document Workflow Modernization Pilot",
        issuer="Sample Public Agency",
        budget="KRW 80M-120M",
        deadline="21 days",
        bid_type="local_fixture",
        category="document_operations",
        region="sample",
        raw_text_preview="Local deterministic procurement package demo.",
    )


def _demo_decision_hard_filters() -> list[ProcurementHardFilterResult]:
    return [
        ProcurementHardFilterResult(
            code="security_plan",
            label="Security handling plan",
            status="unknown",
            blocking=True,
            reason=(
                "Security handling plan owner must be confirmed "
                "before proposal drafting."
            ),
        ),
    ]


def _demo_decision_score_breakdown() -> list[ProcurementScoreBreakdownItem]:
    return [
        ProcurementScoreBreakdownItem(
            key="domain_fit",
            label="Domain fit",
            score=78.0,
            weight=0.25,
            weighted_score=19.5,
            summary="Document workflow capability is aligned with the opportunity.",
            evidence=["document workflow consulting"],
        ),
        ProcurementScoreBreakdownItem(
            key="security_readiness",
            label="Security readiness",
            score=52.0,
            weight=0.25,
            weighted_score=13.0,
            summary="Security plan requires owner assignment.",
            evidence=["security plan draft required"],
        ),
    ]


def _demo_decision_checklist_items() -> list[ProcurementChecklistItem]:
    return [
        ProcurementChecklistItem(
            category="security_plan",
            title="Finalize security handling plan",
            status="action_needed",
            severity="high",
            remediation_note="Assign owner before proposal drafting.",
        ),
        ProcurementChecklistItem(
            category="training_staffing",
            title="Assign operator training staffing owner",
            status="action_needed",
            severity="medium",
            remediation_note="Confirm trainer availability before kickoff.",
        ),
    ]


def _demo_decision_recommendation() -> ProcurementRecommendation:
    return ProcurementRecommendation(
        value=DEMO_RECOMMENDATION,
        summary=(
            "Conditional go pending security and "
            "training ownership confirmation."
        ),
        evidence=[
            "Weighted fit score: 68.00",
            "Document workflow capability aligns with the opportunity.",
        ],
        missing_data=_demo_decision_missing_data(),
        remediation_notes=[
            "Assign security plan owner.",
            "Assign operator training staffing owner.",
        ],
    )


def _demo_decision_missing_data() -> list[str]:
    return [
        "security plan owner",
        "operator training staffing owner",
    ]
