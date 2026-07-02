"""Deterministic project-scoped Decision Council synthesis for procurement v1.

Split into focused modules:

- ``binding``: standalone staleness/description helpers and the
  generation-context renderer (no service state).
- ``council_synthesis_mixin``: ``CouncilSynthesisMixin`` — private builder
  methods for role opinions, consensus, and handoff.
- ``service``: ``DecisionCouncilService`` — the public service class.

This package re-exports the full public and internal API so
``from app.services.decision_council_service import X`` (the backward-compatible
facade module) and any direct ``from app.services.decision_council import X``
imports keep working unchanged.
"""
from __future__ import annotations

from app.services.decision_council.binding import (
    _build_procurement_binding_metrics,
    _DECISION_COUNCIL_SUPPORTED_BUNDLE_TYPES,
    build_procurement_council_generation_context,
    describe_procurement_council_binding,
    describe_procurement_council_document_status,
)
from app.services.decision_council.council_synthesis_mixin import CouncilSynthesisMixin
from app.services.decision_council.service import _ROLE_ORDER, DecisionCouncilService

__all__ = [
    "_ROLE_ORDER",
    "_DECISION_COUNCIL_SUPPORTED_BUNDLE_TYPES",
    "_build_procurement_binding_metrics",
    "build_procurement_council_generation_context",
    "describe_procurement_council_binding",
    "describe_procurement_council_document_status",
    "CouncilSynthesisMixin",
    "DecisionCouncilService",
]
