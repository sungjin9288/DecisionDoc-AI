"""Report workflow service for staged planning, slide generation, and export.

The implementation now lives in the ``app.services.report_workflow``
package, split into focused modules (helpers, service_core_mixin,
service_export_mixin, service_quality_mixin, service_approval_mixin). This
module is kept as a backward-compatible facade that re-exports the full
public and internal API so existing
``from app.services.report_workflow_service import X`` imports keep working
unchanged.
"""
from __future__ import annotations

from app.services.pptx_service import build_pptx
from app.services.report_workflow import ProviderFactory, ReportWorkflowService
from app.services.report_workflow.helpers import (
    _as_list,
    _clean_json_text,
    _dedupe_strings,
    _now_iso,
    _safe_slide_id,
    _string_list,
)
from app.services.report_workflow.service_core_mixin import logger

__all__ = ["ReportWorkflowService", "ProviderFactory"]
