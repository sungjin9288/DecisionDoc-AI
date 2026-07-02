"""Planning-stage report workflow transitions: save/request-changes/approve."""
from __future__ import annotations

import uuid
from dataclasses import asdict

from app.storage.report_workflow.models import (
    PlanningVersion,
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    WorkflowComment,
    _now_iso,
)


class ReportWorkflowPlanningMixin:
    """Planning draft/change-request/approval transitions."""

    def save_planning(
        self,
        report_workflow_id: str,
        planning: PlanningVersion,
        *,
        tenant_id: str | None = None,
        quality_warnings: list[str] | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            rec.current_plan_version += 1
            planning.version = rec.current_plan_version
            planning.status = "draft"
            rec.planning = planning
            rec.slides = []
            rec.current_slide_version = 0
            rec.final_submitted_at = None
            rec.final_approved_by = None
            rec.final_approved_at = None
            rec.final_approval_id = None
            rec.final_approval_status = None
            rec.final_approval_synced_at = None
            rec.project_id = None
            rec.project_document_id = None
            rec.project_promoted_at = None
            rec.knowledge_project_id = None
            rec.knowledge_document_count = 0
            rec.knowledge_documents = []
            rec.knowledge_promoted_at = None
            rec.visual_assets = []
            rec.approval_steps = []
            rec.status = ReportWorkflowStatus.PLANNING_DRAFT.value
            rec.quality_warnings.extend(quality_warnings or [])
            return self._flush(tid, records, idx, rec)

    def request_planning_changes(
        self,
        report_workflow_id: str,
        *,
        author: str,
        comment: str,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            if rec.planning is None:
                raise ValueError("수정 요청할 기획안이 없습니다.")
            rec.status = ReportWorkflowStatus.PLANNING_CHANGES_REQUESTED.value
            rec.planning.status = "changes_requested"
            rec.comments.append(WorkflowComment(
                comment_id=str(uuid.uuid4()),
                target_type="plan",
                target_id=rec.planning.plan_id,
                author=author,
                content=comment,
                created_at=_now_iso(),
                is_change_request=True,
            ))
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "planning_change_request",
                    {"comment": comment, "plan_version": rec.planning.version},
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)

    def approve_planning(
        self,
        report_workflow_id: str,
        *,
        author: str,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            if rec.planning is None:
                raise ValueError("승인할 기획안이 없습니다.")
            rec.planning.status = "approved"
            rec.planning.approved_by = author
            rec.planning.approved_at = _now_iso()
            rec.status = ReportWorkflowStatus.PLANNING_APPROVED.value
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "planning_approved",
                    asdict(rec.planning),
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)
