"""Deterministic public procurement decision evaluation for project-scoped state.

The implementation now lives in the ``app.services.procurement_decision``
package, split into focused modules (constants, text_utils, service_core_mixin,
hard_filters, soft_fit_scoring, recommendation, checklist). This module is kept
as a backward-compatible facade that re-exports the full public and internal
API so existing ``from app.services.procurement_decision_service import X``
imports keep working unchanged.
"""
from __future__ import annotations

from app.services.procurement_decision.constants import (
    CERTIFICATION_GROUPS,
    CONSORTIUM_REQUIRED_TERMS,
    DEFAULT_MIN_READY_DAYS,
    DEFAULT_MIN_SCORABLE_WEIGHT,
    DOMAIN_GROUPS,
    ELIGIBILITY_GROUPS,
    EXPERIENCE_REQUIREMENT_TERMS,
    NEGATIVE_SIGNAL_TERMS,
    PARTNER_TERMS,
    REFERENCE_TERMS,
    REGION_TERMS,
    RISK_TERMS,
    SCORE_WEIGHTS,
    STAFFING_TERMS,
    _EvaluationInputs,
)
from app.services.procurement_decision.text_utils import (
    _contains_any,
    _detect_region,
    _extract_budget_amount,
    _has_negative_signal,
    _matched_groups,
    _normalize_text,
    _now_utc,
    _parse_deadline,
    _score_from_overlap,
    _unique,
)
from app.services.procurement_decision import ProcurementDecisionService

__all__ = [
    "ProcurementDecisionService",
    "DEFAULT_MIN_READY_DAYS",
    "DEFAULT_MIN_SCORABLE_WEIGHT",
    "SCORE_WEIGHTS",
    "DOMAIN_GROUPS",
    "CERTIFICATION_GROUPS",
    "ELIGIBILITY_GROUPS",
    "REGION_TERMS",
    "PARTNER_TERMS",
    "REFERENCE_TERMS",
    "STAFFING_TERMS",
    "RISK_TERMS",
    "EXPERIENCE_REQUIREMENT_TERMS",
    "CONSORTIUM_REQUIRED_TERMS",
    "NEGATIVE_SIGNAL_TERMS",
]
