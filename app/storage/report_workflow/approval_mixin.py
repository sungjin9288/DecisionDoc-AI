"""Final-review report workflow transitions: submission, approval-step
sign-off, change requests, and legacy single-step final approval."""
from __future__ import annotations

import uuid
from dataclasses import asdict

from app.storage.report_workflow.models import (
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    SlideStatus,
    WorkflowComment,
    _now_iso,
)


class ReportWorkflowApprovalMixin:
    """Final review submission, approval-step sign-off, and legacy approve."""

    def submit_final(
        self,
        report_workflow_id: str,
        *,
        author: str,
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            if not rec.slides or any(item.status != SlideStatus.APPROVED.value for item in rec.slides):
                raise ValueError("모든 장표가 승인되어야 최종 검토로 이동할 수 있습니다.")
            rec.status = ReportWorkflowStatus.FINAL_REVIEW.value
            rec.final_submitted_at = _now_iso()
            rec.final_approved_by = None
            rec.final_approved_at = None
            rec.final_approval_id = None
            rec.final_approval_status = None
            rec.final_approval_synced_at = None
            rec.approval_steps = self._default_approval_steps(rec.pm_reviewer, rec.executive_approver)
            rec.comments.append(WorkflowComment(
                comment_id=str(uuid.uuid4()),
                target_type="final",
                target_id=report_workflow_id,
                author=author,
                content="최종 검토 요청",
                created_at=_now_iso(),
                is_change_request=False,
            ))
            return self._flush(tid, records, idx, rec)

    def link_final_approval(
        self,
        report_workflow_id: str,
        *,
        approval_id: str,
        approval_status: str,
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            if rec.status not in {
                ReportWorkflowStatus.FINAL_REVIEW.value,
                ReportWorkflowStatus.FINAL_APPROVED.value,
                ReportWorkflowStatus.FINAL_CHANGES_REQUESTED.value,
            }:
                raise ValueError("최종 결재 단계에서만 결재함 항목을 연결할 수 있습니다.")
            rec.final_approval_id = approval_id
            rec.final_approval_status = approval_status
            rec.final_approval_synced_at = _now_iso()
            return self._flush(tid, records, idx, rec)

    def sync_final_approval_status(
        self,
        report_workflow_id: str,
        *,
        approval_status: str,
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            if not rec.final_approval_id:
                return rec
            rec.final_approval_status = approval_status
            rec.final_approval_synced_at = _now_iso()
            return self._flush(tid, records, idx, rec)

    def approve_final_step(
        self,
        report_workflow_id: str,
        *,
        stage: str,
        author: str,
        comment: str = "",
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            if rec.status != ReportWorkflowStatus.FINAL_REVIEW.value:
                raise ValueError("최종 검토 상태에서만 결재할 수 있습니다.")
            if not rec.approval_steps:
                rec.approval_steps = self._default_approval_steps(rec.pm_reviewer, rec.executive_approver)
            if stage == "executive_review":
                pm_step = self._approval_step(rec, "pm_review")
                if pm_step.status != "approved":
                    raise ValueError("PM 검토 승인 후 대표 최종 승인을 진행할 수 있습니다.")
            step = self._approval_step(rec, stage)
            if step.status == "approved":
                raise ValueError("이미 승인된 결재 단계입니다.")
            self._record_approval_actor_warnings(rec, stage=stage, author=author, step=step)
            step.status = "approved"
            step.actor = author
            step.decided_at = _now_iso()
            step.comment = comment
            rec.comments.append(WorkflowComment(
                comment_id=str(uuid.uuid4()),
                target_type="final",
                target_id=stage,
                author=author,
                content=comment or f"{step.label} 승인",
                created_at=_now_iso(),
                is_change_request=False,
            ))
            if stage == "executive_review":
                rec.status = ReportWorkflowStatus.FINAL_APPROVED.value
                rec.final_approved_by = author
                rec.final_approved_at = step.decided_at
            if rec.learning_opt_in and stage == "executive_review":
                rec.learning_artifacts.append(self._learning_artifact(
                    "final_approved",
                    {
                        "planning": asdict(rec.planning) if rec.planning else None,
                        "slides": [asdict(item) for item in rec.slides],
                        "approval_steps": [asdict(item) for item in rec.approval_steps],
                        "quality_warnings": rec.quality_warnings,
                    },
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)

    def request_final_changes(
        self,
        report_workflow_id: str,
        *,
        author: str,
        comment: str,
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            if rec.status != ReportWorkflowStatus.FINAL_REVIEW.value:
                raise ValueError("최종 검토 상태에서만 수정 요청할 수 있습니다.")
            if not rec.approval_steps:
                rec.approval_steps = self._default_approval_steps(rec.pm_reviewer, rec.executive_approver)
            pending_step = next((item for item in rec.approval_steps if item.status != "approved"), rec.approval_steps[-1])
            pending_step.status = "changes_requested"
            pending_step.actor = author
            pending_step.decided_at = _now_iso()
            pending_step.comment = comment
            rec.status = ReportWorkflowStatus.FINAL_CHANGES_REQUESTED.value
            rec.final_approved_by = None
            rec.final_approved_at = None
            rec.comments.append(WorkflowComment(
                comment_id=str(uuid.uuid4()),
                target_type="final",
                target_id=pending_step.stage,
                author=author,
                content=comment,
                created_at=_now_iso(),
                is_change_request=True,
            ))
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "final_change_request",
                    {"stage": pending_step.stage, "comment": comment},
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)

    def approve_final(
        self,
        report_workflow_id: str,
        *,
        author: str,
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            if rec.status != ReportWorkflowStatus.FINAL_REVIEW.value:
                raise ValueError("최종 검토 상태에서만 최종 승인할 수 있습니다.")
            if not rec.approval_steps:
                rec.approval_steps = self._default_approval_steps(rec.pm_reviewer, rec.executive_approver)
            now = _now_iso()
            for step in rec.approval_steps:
                if step.status != "approved":
                    self._record_approval_actor_warnings(rec, stage=step.stage, author=author, step=step)
                    step.status = "approved"
                    step.actor = author
                    step.decided_at = now
                    step.comment = step.comment or "legacy final approve"
            rec.status = ReportWorkflowStatus.FINAL_APPROVED.value
            rec.final_approved_by = author
            rec.final_approved_at = now
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "final_approved",
                    {
                        "planning": asdict(rec.planning) if rec.planning else None,
                        "slides": [asdict(item) for item in rec.slides],
                        "approval_steps": [asdict(item) for item in rec.approval_steps],
                        "quality_warnings": rec.quality_warnings,
                    },
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)
