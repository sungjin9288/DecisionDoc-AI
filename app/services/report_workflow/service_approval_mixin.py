"""Final approval workflow and project/knowledge promotion for ReportWorkflowService."""
from __future__ import annotations

import re
from typing import Any

from app.storage.approval_store import ApprovalStatus
from app.storage.knowledge_store import KnowledgeEntry, KnowledgeStore
from app.storage.project_store import ProjectDocument
from app.storage.report_workflow_store import ReportWorkflowRecord


class ReportWorkflowApprovalMixin:
    """Final approval workflow (PM review / executive review) and project/knowledge promotion."""

    def submit_final(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        author: str,
    ) -> ReportWorkflowRecord:
        rec = self.store.submit_final(report_workflow_id, author=author, tenant_id=tenant_id)
        if self._approval_store is None:
            return rec

        approval = self._approval_store.create(
            tenant_id=tenant_id,
            request_id=self._approval_request_id(rec),
            bundle_id="report_workflow",
            title=f"[보고서 워크플로우] {rec.title}",
            drafter=author,
            docs=self._approval_docs(rec),
            gov_options=self._approval_gov_options(rec),
        )
        approval = self._approval_store.submit_for_review(
            approval.approval_id,
            reviewer=rec.pm_reviewer or "pm_review",
            tenant_id=tenant_id,
        )
        approval = self._approval_store.submit_for_approval(
            approval.approval_id,
            approver=rec.executive_approver or "executive_review",
            tenant_id=tenant_id,
        )
        return self.store.link_final_approval(
            report_workflow_id,
            approval_id=approval.approval_id,
            approval_status=approval.status,
            tenant_id=tenant_id,
        )

    def approve_final_step(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        stage: str,
        author: str,
        comment: str = "",
    ) -> ReportWorkflowRecord:
        rec = self.store.approve_final_step(
            report_workflow_id,
            stage=stage,
            author=author,
            comment=comment,
            tenant_id=tenant_id,
        )
        if self._approval_store is None or not rec.final_approval_id:
            return rec

        approval_status = rec.final_approval_status or ApprovalStatus.IN_REVIEW.value
        if stage == "pm_review":
            approval = self._approval_store.approve_review(
                rec.final_approval_id,
                author=author,
                comment=comment,
                tenant_id=tenant_id,
            )
            approval_status = approval.status
        elif stage == "executive_review":
            approval = self._approval_store.approve_final(
                rec.final_approval_id,
                author=author,
                comment=comment,
                tenant_id=tenant_id,
            )
            approval_status = approval.status
        return self.store.sync_final_approval_status(
            report_workflow_id,
            approval_status=approval_status,
            tenant_id=tenant_id,
        )

    def approve_final(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        author: str,
        comment: str = "",
    ) -> ReportWorkflowRecord:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if not rec.final_approval_id:
            return self.store.approve_final(report_workflow_id, author=author, tenant_id=tenant_id)

        pm_step = next((item for item in rec.approval_steps if item.stage == "pm_review"), None)
        if pm_step is None or pm_step.status != "approved":
            rec = self.approve_final_step(
                report_workflow_id,
                tenant_id=tenant_id,
                stage="pm_review",
                author=author,
                comment=comment or "legacy final approve: PM 검토 자동 승인",
            )
        if rec.status == "final_approved":
            return rec
        return self.approve_final_step(
            report_workflow_id,
            tenant_id=tenant_id,
            stage="executive_review",
            author=author,
            comment=comment,
        )

    def request_final_changes(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        author: str,
        comment: str,
    ) -> ReportWorkflowRecord:
        rec = self.store.request_final_changes(
            report_workflow_id,
            author=author,
            comment=comment,
            tenant_id=tenant_id,
        )
        if self._approval_store is None or not rec.final_approval_id:
            return rec
        approval = self._approval_store.request_changes(
            rec.final_approval_id,
            author=author,
            comment=comment,
            tenant_id=tenant_id,
        )
        return self.store.sync_final_approval_status(
            report_workflow_id,
            approval_status=approval.status,
            tenant_id=tenant_id,
        )

    def promote_final_artifacts(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        project_id: str,
        promote_to_knowledge: bool = False,
        tags: list[str] | None = None,
        quality_tier: str = "gold",
        success_state: str = "approved",
        source_organization: str = "",
        reference_year: int | None = None,
        notes: str = "",
    ) -> ReportWorkflowRecord:
        if self._project_store is None:
            raise ValueError("프로젝트 저장소가 설정되어 있지 않습니다.")
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if rec.status != "final_approved":
            raise ValueError("최종 승인된 보고서 워크플로우만 프로젝트로 승격할 수 있습니다.")
        if rec.project_document_id and rec.project_id and rec.project_id != project_id:
            raise ValueError("이미 다른 프로젝트로 승격된 보고서 워크플로우입니다.")

        project = self._project_store.get(project_id, tenant_id=tenant_id)
        if project is None:
            raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

        docs = self._approval_docs(rec)
        resolved_tags = self._promotion_tags(rec, tags or [])
        project_doc: ProjectDocument | None = None
        if not rec.project_document_id:
            project_doc = self._project_store.add_document(
                project_id=project_id,
                request_id=self._approval_request_id(rec),
                bundle_id="report_workflow",
                title=rec.title,
                docs=docs,
                approval_id=rec.final_approval_id,
                tags=resolved_tags,
                tenant_id=tenant_id,
                source_kind="report_workflow",
            )
            rec = self.store.mark_project_promoted(
                report_workflow_id,
                project_id=project_id,
                project_document_id=project_doc.doc_id,
                tenant_id=tenant_id,
            )

        if promote_to_knowledge:
            if not rec.learning_opt_in:
                raise ValueError("learning_opt_in=true인 워크플로우만 지식 후보로 승격할 수 있습니다.")
            knowledge_payload = self._promote_docs_to_knowledge(
                rec,
                tenant_id=tenant_id,
                project_id=project_id,
                docs=docs,
                tags=resolved_tags,
                quality_tier=quality_tier,
                success_state=success_state,
                source_organization=source_organization,
                reference_year=reference_year,
                notes=notes,
            )
            rec = self.store.mark_knowledge_promoted(
                report_workflow_id,
                project_id=project_id,
                document_count=len(knowledge_payload),
                documents=knowledge_payload,
                tenant_id=tenant_id,
            )
        return rec

    @staticmethod
    def _approval_request_id(rec: ReportWorkflowRecord) -> str:
        return f"report_workflow:{rec.report_workflow_id}:slides:{rec.current_slide_version}"

    @staticmethod
    def _promotion_tags(rec: ReportWorkflowRecord, tags: list[str]) -> list[str]:
        result = ["report_workflow", rec.report_type or "proposal_presentation"]
        if rec.client:
            result.append(rec.client)
        for tag in tags:
            normalized = str(tag or "").strip()
            if normalized:
                result.append(normalized)
        deduped: list[str] = []
        for tag in result:
            if tag and tag not in deduped:
                deduped.append(tag)
        return deduped

    @staticmethod
    def _knowledge_filename(title: str, doc_type: str) -> str:
        safe_title = re.sub(r'[\\/:*?"<>|]+', "-", str(title or "report-workflow").strip())
        safe_type = re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", str(doc_type or "doc").strip()) or "doc"
        return f"{safe_title} - {safe_type}.md"

    @staticmethod
    def _knowledge_entry_payload(entry: KnowledgeEntry, *, doc_type: str, reused: bool) -> dict[str, Any]:
        return {
            "doc_id": entry.doc_id,
            "filename": entry.filename,
            "doc_type": doc_type,
            "learning_mode": entry.learning_mode,
            "quality_tier": entry.quality_tier,
            "success_state": entry.success_state,
            "source_bundle_id": entry.source_bundle_id,
            "source_request_id": entry.source_request_id,
            "source_doc_type": entry.source_doc_type,
            "reused": reused,
        }

    def _promote_docs_to_knowledge(
        self,
        rec: ReportWorkflowRecord,
        *,
        tenant_id: str,
        project_id: str,
        docs: list[dict[str, Any]],
        tags: list[str],
        quality_tier: str,
        success_state: str,
        source_organization: str,
        reference_year: int | None,
        notes: str,
    ) -> list[dict[str, Any]]:
        store = KnowledgeStore(
            project_id,
            data_dir=self._data_dir,
            tenant_id=tenant_id,
        )
        source_request_id = self._approval_request_id(rec)
        promoted: list[dict[str, Any]] = []
        for item in docs:
            markdown = str(item.get("markdown") or "").strip()
            doc_type = str(item.get("doc_type") or "report_workflow").strip()
            if not markdown:
                continue
            existing = store.find_promoted_document(
                source_request_id=source_request_id,
                source_doc_type=doc_type,
                source_bundle_id="report_workflow",
            )
            if existing is not None:
                promoted.append(self._knowledge_entry_payload(existing, doc_type=doc_type, reused=True))
                continue
            entry = store.add_document(
                filename=self._knowledge_filename(rec.title, doc_type),
                text=markdown,
                tags=tags + [doc_type],
                learning_mode="approved_output",
                quality_tier=quality_tier,
                applicable_bundles=["report_workflow", rec.report_type],
                source_organization=source_organization or rec.client,
                reference_year=reference_year,
                success_state=success_state,
                notes=notes or f"Report Workflow final approved artifact: {rec.report_workflow_id}",
                source_bundle_id="report_workflow",
                source_request_id=source_request_id,
                source_doc_type=doc_type,
            )
            promoted.append(self._knowledge_entry_payload(entry, doc_type=doc_type, reused=False))
        if not promoted:
            raise ValueError("지식 후보로 승격할 승인 산출물이 없습니다.")
        return promoted

    @staticmethod
    def _approval_gov_options(rec: ReportWorkflowRecord) -> dict[str, Any]:
        return {
            "source_kind": "report_workflow",
            "report_workflow_id": rec.report_workflow_id,
            "workflow_status": rec.status,
            "current_plan_version": rec.current_plan_version,
            "current_slide_version": rec.current_slide_version,
            "learning_opt_in": rec.learning_opt_in,
            "owner": rec.owner,
            "pm_reviewer": rec.pm_reviewer,
            "executive_approver": rec.executive_approver,
        }

    @staticmethod
    def _approval_docs(rec: ReportWorkflowRecord) -> list[dict[str, Any]]:
        planning = rec.planning
        planning_summary = ""
        if planning is not None:
            planning_summary = "\n".join([
                f"# 기획 설계서: {rec.title}",
                "",
                f"- 목적: {planning.objective}",
                f"- 대상: {planning.audience}",
                f"- 핵심 메시지: {planning.executive_message}",
                "",
                "## Narrative Arc",
                *[f"- {item}" for item in planning.narrative_arc],
                "",
                "## Quality Bar",
                *[f"- {item}" for item in planning.quality_bar],
            ]).strip()
        slide_summary = "\n\n".join(
            [
                "\n".join([
                    f"## {slide.page}. {slide.title}",
                    "",
                    slide.body,
                    "",
                    f"- 시각화: {slide.visual_spec}",
                    f"- 발표 노트: {slide.speaker_note}",
                    f"- 출처: {', '.join(slide.source_refs) if slide.source_refs else 'n/a'}",
                ]).strip()
                for slide in sorted(rec.slides, key=lambda item: item.page)
            ]
        )
        return [
            {
                "doc_type": "report_workflow_planning",
                "title": f"{rec.title} 기획 설계서",
                "markdown": planning_summary or f"# 기획 설계서: {rec.title}",
            },
            {
                "doc_type": "report_workflow_slides",
                "title": f"{rec.title} 승인 장표 초안",
                "markdown": f"# 승인 장표 초안: {rec.title}\n\n{slide_summary}".strip(),
            },
        ]
