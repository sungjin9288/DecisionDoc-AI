"""Report workflow service: staged planning, slide generation, quality
correction learning, approval workflow, and export -- the
``ReportWorkflowService`` facade.

The implementation lives in this package, split into focused modules:

- ``helpers``: shared text/JSON parsing helpers (module-level functions).
- ``service_core_mixin``: ``__init__`` plus the planning/slide generation
  pipeline entrypoints (``generate_planning``, ``generate_slides``, prompt
  builders, provider-data normalizers, ``_require_record``).
- ``service_export_mixin``: PPTX export, export snapshot, and visual asset
  generation.
- ``service_quality_mixin``: quality correction artifact preview/save/list/
  detail/export plus the develop-quality-improvement preview flow.
- ``service_approval_mixin``: final approval workflow (PM review / executive
  review) and project/knowledge promotion.

This package re-exports the full public and internal API so existing
``from app.services.report_workflow_service import X`` imports keep working
unchanged.
"""
from __future__ import annotations

from app.services.report_workflow.helpers import (
    _as_list,
    _clean_json_text,
    _dedupe_strings,
    _now_iso,
    _safe_slide_id,
    _string_list,
)
from app.services.report_workflow.service_approval_mixin import ReportWorkflowApprovalMixin
from app.services.report_workflow.service_core_mixin import ProviderFactory, ReportWorkflowCoreMixin, logger
from app.services.report_workflow.service_export_mixin import ReportWorkflowExportMixin
from app.services.report_workflow.service_quality_mixin import ReportWorkflowQualityMixin

__all__ = ["ReportWorkflowService", "ProviderFactory"]


class ReportWorkflowService(
    ReportWorkflowCoreMixin,
    ReportWorkflowExportMixin,
    ReportWorkflowQualityMixin,
    ReportWorkflowApprovalMixin,
):
    """Generate and export staged report workflow artifacts."""
