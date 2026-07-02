"""Deterministic project-scoped Decision Council synthesis for procurement v1.

The implementation now lives in the ``app.services.decision_council`` package,
split into focused modules (``binding``, ``council_synthesis_mixin``,
``service``). This module is kept as a backward-compatible facade that
re-exports the full public and internal API so existing
``from app.services.decision_council_service import X`` imports keep working
unchanged.
"""
from __future__ import annotations

from app.services.decision_council import (
    _DECISION_COUNCIL_SUPPORTED_BUNDLE_TYPES,
    _ROLE_ORDER,
    _build_procurement_binding_metrics,
    build_procurement_council_generation_context,
    describe_procurement_council_binding,
    describe_procurement_council_document_status,
    DecisionCouncilService,
)

__all__ = [
    "_ROLE_ORDER",
    "_DECISION_COUNCIL_SUPPORTED_BUNDLE_TYPES",
    "_build_procurement_binding_metrics",
    "build_procurement_council_generation_context",
    "describe_procurement_council_binding",
    "describe_procurement_council_document_status",
    "DecisionCouncilService",
]
