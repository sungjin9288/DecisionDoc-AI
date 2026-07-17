"""Tenant-scoped report workflow storage.

This store owns the intermediate production workflow for staged report
creation: planning approval, slide-level approval, final approval, and
opt-in learning artifacts.

The implementation now lives in the ``app.storage.report_workflow`` package,
split into focused mixins (core_mixin, helpers_mixin, planning_mixin,
slide_mixin, approval_mixin, promotion_mixin) and a standalone ``models``
module for enums/dataclasses. This module is kept as a backward-compatible
facade that re-exports the full public API so existing
``from app.storage.report_workflow_store import X`` imports keep working
unchanged.
"""
from __future__ import annotations

from app.storage.report_workflow import (
    ApprovalStep,
    PlanningVersion,
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    ReportWorkflowStore,
    ReportWorkflowStoreError,
    SlideDraft,
    SlidePlan,
    SlideStatus,
    WorkflowComment,
)

__all__ = [
    "ReportWorkflowStatus",
    "SlideStatus",
    "WorkflowComment",
    "SlidePlan",
    "PlanningVersion",
    "SlideDraft",
    "ApprovalStep",
    "ReportWorkflowRecord",
    "ReportWorkflowStore",
    "ReportWorkflowStoreError",
]
