"""Post-approval promotion transitions: project/knowledge promotion and
opt-in learning-artifact capture."""
from __future__ import annotations

from typing import Any

from app.storage.report_workflow.models import (
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    _now_iso,
)


class ReportWorkflowPromotionMixin:
    """Project/knowledge promotion and learning-artifact append."""

    def mark_project_promoted(
        self,
        report_workflow_id: str,
        *,
        project_id: str,
        project_document_id: str,
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            if rec.status != ReportWorkflowStatus.FINAL_APPROVED.value:
                raise ValueError("최종 승인된 보고서 워크플로우만 프로젝트로 승격할 수 있습니다.")
            rec.project_id = project_id
            rec.project_document_id = project_document_id
            rec.project_promoted_at = rec.project_promoted_at or _now_iso()
            return self._flush(tid, records, idx, rec)

    def mark_knowledge_promoted(
        self,
        report_workflow_id: str,
        *,
        project_id: str,
        document_count: int,
        documents: list[dict[str, Any]],
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            if rec.status != ReportWorkflowStatus.FINAL_APPROVED.value:
                raise ValueError("최종 승인된 보고서 워크플로우만 지식 후보로 승격할 수 있습니다.")
            rec.knowledge_project_id = project_id
            rec.knowledge_document_count = int(document_count)
            rec.knowledge_documents = list(documents)
            rec.knowledge_promoted_at = rec.knowledge_promoted_at or _now_iso()
            return self._flush(tid, records, idx, rec)

    def append_learning_artifact(
        self,
        report_workflow_id: str,
        *,
        kind: str,
        payload: dict[str, Any],
        actor: str = "",
        tenant_id: str,
    ) -> ReportWorkflowRecord:
        with self._lock(tenant_id):
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            if rec.status != ReportWorkflowStatus.FINAL_APPROVED.value:
                raise ValueError("최종 승인된 보고서 워크플로우만 학습 artifact를 저장할 수 있습니다.")
            if not rec.learning_opt_in:
                raise ValueError("learning_opt_in=true인 워크플로우만 학습 artifact를 저장할 수 있습니다.")
            rec.learning_artifacts.append(self._learning_artifact(kind, payload, actor=actor))
            return self._flush(tid, records, idx, rec)
