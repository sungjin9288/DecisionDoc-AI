"""Deterministic public procurement decision evaluation for project-scoped state.

Package split from the former single-file ``app.services.procurement_decision_service``
module. ``ProcurementDecisionService`` is assembled from focused mixins:
``ServiceCoreMixin`` (init + evaluate/recommend entry points + input building),
``HardFiltersMixin`` (blocking eligibility/compliance gates),
``SoftFitScoringMixin`` (weighted fit score breakdown),
``RecommendationMixin`` (Go/No-Go/Conditional-Go summary), and
``ChecklistMixin`` (bid-readiness checklist items).
"""
from __future__ import annotations

from app.services.procurement_decision.checklist import ChecklistMixin
from app.services.procurement_decision.hard_filters import HardFiltersMixin
from app.services.procurement_decision.recommendation import RecommendationMixin
from app.services.procurement_decision.service_core_mixin import ServiceCoreMixin
from app.services.procurement_decision.soft_fit_scoring import SoftFitScoringMixin


class ProcurementDecisionService(
    ServiceCoreMixin,
    HardFiltersMixin,
    SoftFitScoringMixin,
    RecommendationMixin,
    ChecklistMixin,
):
    """Deterministic evaluator for project-scoped procurement decisions."""


__all__ = ["ProcurementDecisionService"]
