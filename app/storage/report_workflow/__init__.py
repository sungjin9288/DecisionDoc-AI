"""Tenant-scoped report workflow storage.

This store owns the intermediate production workflow for staged report
creation: planning approval, slide-level approval, final approval, and
opt-in learning artifacts.

The implementation is split into focused mixins (core_mixin, helpers_mixin,
planning_mixin, slide_mixin, approval_mixin, promotion_mixin) plus the
standalone ``models`` module for enums/dataclasses. This package composes
them into the single public ``ReportWorkflowStore`` class and re-exports
every public and internal symbol so existing
``from app.storage.report_workflow_store import X`` imports keep working
unchanged.
"""
from __future__ import annotations

from app.storage.base import BaseJsonStore

from app.storage.report_workflow.models import (
    ApprovalStep,
    PlanningVersion,
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    SlideDraft,
    SlidePlan,
    SlideStatus,
    WorkflowComment,
    _now_iso,
)
from app.storage.report_workflow.core_mixin import ReportWorkflowCoreMixin
from app.storage.report_workflow.helpers_mixin import ReportWorkflowHelpersMixin
from app.storage.report_workflow.planning_mixin import ReportWorkflowPlanningMixin
from app.storage.report_workflow.slide_mixin import ReportWorkflowSlideMixin
from app.storage.report_workflow.approval_mixin import ReportWorkflowApprovalMixin
from app.storage.report_workflow.promotion_mixin import ReportWorkflowPromotionMixin

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
]


class ReportWorkflowStore(
    ReportWorkflowHelpersMixin,
    ReportWorkflowCoreMixin,
    ReportWorkflowPlanningMixin,
    ReportWorkflowSlideMixin,
    ReportWorkflowApprovalMixin,
    ReportWorkflowPromotionMixin,
    BaseJsonStore,
):
    """Thread-safe, tenant-scoped JSON-backed report workflow store."""
