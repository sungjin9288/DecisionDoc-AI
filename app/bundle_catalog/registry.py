"""Bundle registry — single lookup table for all available bundle types."""
import logging

from app.bundle_catalog.spec import BundleSpec
from app.bundle_catalog.bundles.tech_decision import TECH_DECISION
from app.bundle_catalog.bundles.proposal_kr import PROPOSAL_KR
from app.bundle_catalog.bundles.business_plan_kr import BUSINESS_PLAN_KR
from app.bundle_catalog.bundles.edu_plan_kr import EDU_PLAN_KR
from app.bundle_catalog.bundles.meeting_minutes_kr import MEETING_MINUTES_KR
from app.bundle_catalog.bundles.project_report_kr import PROJECT_REPORT_KR
from app.bundle_catalog.bundles.contract_kr import CONTRACT_KR
from app.bundle_catalog.bundles.presentation_kr import PRESENTATION_KR
from app.bundle_catalog.bundles.job_description_kr import JOB_DESCRIPTION_KR
from app.bundle_catalog.bundles.okr_plan_kr import OKR_PLAN_KR
from app.bundle_catalog.bundles.prd_kr import PRD_KR
from app.bundle_catalog.bundles.rfp_analysis_kr import RFP_ANALYSIS_KR
from app.bundle_catalog.bundles.bid_decision_kr import BID_DECISION_KR
from app.bundle_catalog.bundles.performance_plan_kr import PERFORMANCE_PLAN_KR
from app.bundle_catalog.bundles.completion_report_kr import COMPLETION_REPORT_KR
from app.bundle_catalog.bundles.interim_report_kr import INTERIM_REPORT_KR
from app.bundle_catalog.bundles.task_order_kr import TASK_ORDER_KR
from app.bundle_catalog.bundles.marketing_plan_kr import MARKETING_PLAN_KR
from app.bundle_catalog.bundles.investment_pitch_kr import INVESTMENT_PITCH_KR
from app.bundle_catalog.bundles.feasibility_report_kr import FEASIBILITY_REPORT_KR

_log = logging.getLogger("decisiondoc.bundle.registry")

BUNDLE_REGISTRY: dict[str, BundleSpec] = {
    spec.id: spec
    for spec in [
        TECH_DECISION,
        PROPOSAL_KR,
        BUSINESS_PLAN_KR,
        EDU_PLAN_KR,
        MEETING_MINUTES_KR,
        PROJECT_REPORT_KR,
        CONTRACT_KR,
        PRESENTATION_KR,
        JOB_DESCRIPTION_KR,
        OKR_PLAN_KR,
        PRD_KR,
        # ── 나라장터 공공조달 특화 번들 ──────────────────────────────────
        BID_DECISION_KR,
        RFP_ANALYSIS_KR,
        PERFORMANCE_PLAN_KR,
        COMPLETION_REPORT_KR,
        INTERIM_REPORT_KR,
        TASK_ORDER_KR,
        # ── 비즈니스 기획 번들 ────────────────────────────────────────────
        MARKETING_PLAN_KR,
        INVESTMENT_PITCH_KR,
        FEASIBILITY_REPORT_KR,
    ]
}


def reload_auto_bundles() -> int:
    """Load/refresh auto-generated bundles into BUNDLE_REGISTRY.

    Adds new auto bundles without overriding existing built-in bundles.
    Safe to call multiple times (idempotent for already-loaded bundles).

    Returns:
        The number of auto bundles added in this call.
    """
    try:
        from app.bundle_catalog.auto_registry import load_auto_bundles
        auto = load_auto_bundles()
        added = 0
        for bid, spec in auto.items():
            if bid not in BUNDLE_REGISTRY:
                BUNDLE_REGISTRY[bid] = spec
                added += 1
        return added
    except Exception as exc:
        _log.warning("[AutoBundle] 로드 실패 (무시): %s", exc)
        return 0


def get_bundle_spec(bundle_id: str) -> BundleSpec:
    if bundle_id not in BUNDLE_REGISTRY:
        valid = ", ".join(f'"{k}"' for k in BUNDLE_REGISTRY)
        raise ValueError(f"Unknown bundle_type: {bundle_id!r}. Valid values: {valid}")
    return BUNDLE_REGISTRY[bundle_id]


def list_bundles() -> list[dict]:
    return [spec.ui_metadata() for spec in BUNDLE_REGISTRY.values()]


# Load auto bundles at import time (graceful — returns 0 if data dir is missing)
reload_auto_bundles()
