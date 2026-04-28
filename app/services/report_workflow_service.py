"""Report workflow service for staged planning, slide generation, and export."""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from app.services.pptx_service import build_pptx
from app.services.visual_asset_service import generate_visual_assets_from_docs, index_visual_assets_by_slide_title
from app.storage.approval_store import ApprovalStatus, ApprovalStore
from app.storage.knowledge_store import KnowledgeEntry, KnowledgeStore
from app.storage.project_store import ProjectDocument, ProjectStore
from app.storage.report_workflow_store import (
    PlanningVersion,
    ReportWorkflowRecord,
    ReportWorkflowStore,
    SlideDraft,
    SlidePlan,
)

logger = logging.getLogger("decisiondoc.report_workflows")


ProviderFactory = Callable[[], Any]


def _clean_json_text(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    first = min([idx for idx in [text.find("{"), text.find("[")] if idx >= 0] or [0])
    if first > 0:
        text = text[first:]
    return text


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return [value]


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _safe_slide_id(value: Any, page: int) -> str:
    raw = str(value or "").strip()
    if raw:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", raw)[:48].strip("-") or f"slide-{page:03d}"
    return f"slide-{page:03d}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_strings(values: list[Any], *, limit: int = 8) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


class ReportWorkflowService:
    """Generate and export staged report workflow artifacts."""

    def __init__(
        self,
        *,
        store: ReportWorkflowStore,
        provider_factory: ProviderFactory,
        visual_provider_factory: ProviderFactory | None = None,
        approval_store: ApprovalStore | None = None,
        project_store: ProjectStore | None = None,
        data_dir: str = "data",
    ) -> None:
        self.store = store
        self._provider_factory = provider_factory
        self._visual_provider_factory = visual_provider_factory or provider_factory
        self._approval_store = approval_store
        self._project_store = project_store
        self._data_dir = data_dir

    def generate_planning(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        request_id: str,
    ) -> ReportWorkflowRecord:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        provider = self._provider_factory()
        prompt = self._build_planning_prompt(rec)
        warnings: list[str] = []
        try:
            raw = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=5200)
            data = json.loads(_clean_json_text(raw))
        except Exception as exc:
            logger.warning("report planning provider output fallback: %s", exc)
            data = {}
            warnings.append(f"planning_json_fallback:{exc.__class__.__name__}")
        planning = self._planning_from_provider_data(data, rec)
        return self.store.save_planning(
            report_workflow_id,
            planning,
            tenant_id=tenant_id,
            quality_warnings=warnings,
        )

    def generate_slides(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        request_id: str,
    ) -> ReportWorkflowRecord:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if rec.planning is None or rec.planning.status != "approved":
            raise ValueError("기획안 승인 후 장표를 생성할 수 있습니다.")
        provider = self._provider_factory()
        prompt = self._build_slides_prompt(rec)
        warnings: list[str] = []
        try:
            raw = provider.generate_raw(prompt, request_id=request_id, max_output_tokens=4500)
            data = json.loads(_clean_json_text(raw))
        except Exception as exc:
            logger.warning("report slides provider output fallback: %s", exc)
            data = {}
            warnings.append(f"slides_json_fallback:{exc.__class__.__name__}")
        slides = self._slides_from_provider_data(data, rec)
        return self.store.save_slides(
            report_workflow_id,
            slides,
            tenant_id=tenant_id,
            quality_warnings=warnings,
        )

    def build_pptx_export(self, report_workflow_id: str, *, tenant_id: str) -> bytes:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if not rec.slides:
            raise ValueError("PPTX로 내보낼 장표가 없습니다.")
        slide_outline, visual_assets = self._pptx_export_payload(rec)
        slide_data = {
            "presentation_goal": rec.goal,
            "slide_outline": slide_outline,
        }
        return build_pptx(
            slide_data,
            title=rec.title,
            include_outline_overview=True,
            visual_assets=visual_assets,
        )

    def build_export_snapshot(self, report_workflow_id: str, *, tenant_id: str) -> dict[str, Any]:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if not rec.slides:
            raise ValueError("내보낼 장표가 없습니다.")
        slide_outline, visual_assets = self._pptx_export_payload(rec)
        return {
            "export_version": "decisiondoc_report_workflow_snapshot.v1",
            "generated_at": _now_iso(),
            "tenant_id": rec.tenant_id,
            "report_workflow_id": rec.report_workflow_id,
            "title": rec.title,
            "status": rec.status,
            "goal": rec.goal,
            "client": rec.client,
            "report_type": rec.report_type,
            "audience": rec.audience,
            "source": {
                "source_bundle_id": rec.source_bundle_id,
                "source_request_id": rec.source_request_id,
                "source_refs": rec.source_refs,
            },
            "versions": {
                "planning": rec.current_plan_version,
                "slides": rec.current_slide_version,
            },
            "approval": {
                "final_approval_id": rec.final_approval_id,
                "final_approval_status": rec.final_approval_status,
                "final_submitted_at": rec.final_submitted_at,
                "final_approved_by": rec.final_approved_by,
                "final_approved_at": rec.final_approved_at,
                "approval_steps": [asdict(step) for step in rec.approval_steps],
            },
            "promotion": {
                "project_id": rec.project_id,
                "project_document_id": rec.project_document_id,
                "project_promoted_at": rec.project_promoted_at,
                "knowledge_project_id": rec.knowledge_project_id,
                "knowledge_document_count": rec.knowledge_document_count,
                "knowledge_promoted_at": rec.knowledge_promoted_at,
                "knowledge_documents": rec.knowledge_documents,
            },
            "learning": {
                "learning_opt_in": rec.learning_opt_in,
                "learning_artifact_count": len(rec.learning_artifacts),
            },
            "planning": asdict(rec.planning) if rec.planning is not None else None,
            "slide_outline": slide_outline,
            "slides": [self._slide_snapshot_payload(slide) for slide in rec.slides],
            "visual_assets": [self._redact_asset_payload(asset) for asset in visual_assets],
            "quality_warnings": rec.quality_warnings,
        }

    def _pptx_export_payload(self, rec: ReportWorkflowRecord) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        slide_outline: list[dict[str, Any]] = []
        visual_assets: list[dict[str, Any]] = []
        plans = rec.planning.slide_plans if rec.planning else []
        plans_by_id = {plan.slide_id: plan for plan in plans}
        plans_by_page = {plan.page: plan for plan in plans}
        plans_by_title = {plan.title: plan for plan in plans}
        for slide in sorted(rec.slides, key=lambda item: item.page):
            plan = plans_by_id.get(slide.slide_id) or plans_by_page.get(slide.page) or plans_by_title.get(slide.title)
            selected_asset = dict(slide.selected_asset or {})
            selected_asset_id = slide.selected_asset_id or selected_asset.get("asset_id", "")
            selected_asset_note = ""
            if selected_asset_id:
                selected_asset_note = f"선택 시각자료 ID: {selected_asset_id}"
            if slide.visual_prompt:
                selected_asset_note = " | ".join(bit for bit in [selected_asset_note, f"Visual prompt: {slide.visual_prompt}"] if bit)
            planning_notes = []
            if plan is not None:
                planning_notes = [
                    *plan.design_notes[:3],
                    *plan.acceptance_criteria[:3],
                ]
            design_tip = "\n".join(bit for bit in [
                "Editable PPTX: 텍스트, 카드, 표, 흐름도는 PowerPoint에서 직접 편집 가능한 shape로 구성",
                slide.speaker_note,
                *planning_notes,
                selected_asset_note,
            ] if bit)
            content_blocks = plan.content_blocks if plan is not None else []
            evidence_points = _dedupe_strings([
                *(plan.required_evidence if plan is not None else []),
                *slide.source_refs,
                *slide.reference_refs,
            ], limit=6)
            visual_type = slide.visual_prompt or slide.visual_spec or (plan.visual_direction if plan is not None else "")
            visual_brief = plan.visual_direction if plan is not None else slide.visual_spec
            layout_hint = (plan.layout if plan is not None else "") or slide.visual_spec
            slide_outline.append({
                "page": slide.page,
                "title": slide.title,
                "core_message": (plan.key_message if plan is not None and plan.key_message else slide.body),
                "key_content": slide.body,
                "message": slide.body,
                "visual": visual_type,
                "visual_type": visual_type,
                "visual_brief": visual_brief,
                "layout": layout_hint,
                "layout_hint": layout_hint,
                "design_tip": design_tip,
                "evidence": evidence_points,
                "evidence_points": evidence_points,
                "source_refs": slide.source_refs,
                "reference_refs": slide.reference_refs,
                "decision_question": plan.decision_question if plan is not None else "",
                "narrative_role": plan.narrative_role if plan is not None else "",
                "content_blocks": content_blocks,
                "data_needs": plan.data_needs if plan is not None else [],
                "acceptance_criteria": plan.acceptance_criteria if plan is not None else [],
            })
            if selected_asset.get("content_base64") and selected_asset.get("slide_title"):
                visual_assets.append(selected_asset)
        return slide_outline, visual_assets

    @staticmethod
    def _redact_asset_payload(asset: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(asset)
        encoded = str(redacted.pop("content_base64", "") or "")
        redacted["has_content_base64"] = bool(encoded)
        redacted["content_base64_len"] = len(encoded)
        return redacted

    @classmethod
    def _slide_snapshot_payload(cls, slide: SlideDraft) -> dict[str, Any]:
        payload = asdict(slide)
        selected_asset = payload.get("selected_asset")
        if isinstance(selected_asset, dict):
            payload["selected_asset"] = cls._redact_asset_payload(selected_asset)
        return payload

    def generate_visual_assets(
        self,
        report_workflow_id: str,
        *,
        tenant_id: str,
        request_id: str,
        author: str = "",
        max_assets: int = 6,
        select_first: bool = True,
    ) -> dict[str, Any]:
        rec = self._require_record(report_workflow_id, tenant_id=tenant_id)
        if not rec.slides:
            raise ValueError("시각자료를 생성할 장표가 없습니다.")
        if rec.status in {"final_approved", "delivered"}:
            raise ValueError("최종 승인된 보고서 워크플로우는 수정할 수 없습니다.")
        provider = self._visual_provider_factory()
        slide_outline = [
            {
                "page": slide.page,
                "title": slide.title,
                "key_content": slide.body,
                "message": slide.body,
                "visual_type": slide.visual_prompt or slide.visual_spec or "장표 시각자료",
                "visual_brief": slide.visual_prompt or slide.visual_spec,
                "layout_hint": slide.visual_spec,
                "evidence": [*slide.source_refs, *slide.reference_refs],
            }
            for slide in sorted(rec.slides, key=lambda item: item.page)
        ]
        assets = generate_visual_assets_from_docs(
            [{"doc_type": "report_workflow", "markdown": "", "slide_outline": slide_outline}],
            title=rec.title,
            goal=rec.goal,
            provider=provider,
            request_id=request_id,
            max_assets=max(1, min(int(max_assets or 6), 12)),
        )
        if assets:
            rec = self.store.add_visual_assets(report_workflow_id, assets, tenant_id=tenant_id)
        assets_by_title = index_visual_assets_by_slide_title(assets)
        updated = rec
        for slide in sorted(rec.slides, key=lambda item: item.page):
            asset = assets_by_title.get(slide.title)
            if asset is None:
                continue
            existing_ids = list(slide.generated_asset_ids or [])
            asset_id = str(asset.get("asset_id") or "").strip()
            generated_asset_ids = [*existing_ids, asset_id] if asset_id and asset_id not in existing_ids else existing_ids
            selected_asset_id = slide.selected_asset_id
            selected_asset = dict(slide.selected_asset or {})
            if select_first and asset_id:
                selected_asset_id = asset_id
                selected_asset = asset
            updated = self.store.update_slide_visual_assets(
                report_workflow_id,
                slide.slide_id,
                visual_prompt=slide.visual_prompt or slide.visual_spec,
                reference_refs=slide.reference_refs,
                generated_asset_ids=generated_asset_ids,
                selected_asset_id=selected_asset_id,
                selected_asset=selected_asset,
                author=author,
                tenant_id=tenant_id,
            )
        return {"report_workflow": updated, "assets": assets}

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
            reviewer="pm_review",
            tenant_id=tenant_id,
        )
        approval = self._approval_store.submit_for_approval(
            approval.approval_id,
            approver="executive_review",
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

    def _require_record(self, report_workflow_id: str, *, tenant_id: str) -> ReportWorkflowRecord:
        rec = self.store.get(report_workflow_id, tenant_id=tenant_id)
        if rec is None:
            raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
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
        project_id: str,
        docs: list[dict[str, Any]],
        tags: list[str],
        quality_tier: str,
        success_state: str,
        source_organization: str,
        reference_year: int | None,
        notes: str,
    ) -> list[dict[str, Any]]:
        store = KnowledgeStore(project_id, data_dir=self._data_dir)
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

    def _build_planning_prompt(self, rec: ReportWorkflowRecord) -> str:
        return f"""
You are DecisionDoc AI report workflow planner.
Return ONLY valid JSON for a staged Korean business report planning artifact.

JSON shape:
{{
  "objective": "보고서 목적",
  "audience": "대상 독자",
  "executive_message": "핵심 메시지",
  "planning_brief": "보고서가 해결해야 할 의사결정 맥락과 기획 전제",
  "audience_decision_needs": ["독자가 승인 전에 확인해야 할 판단 기준"],
  "narrative_arc": ["문제 정의", "근거", "해결 방향", "승인 요청처럼 이어지는 보고서 흐름"],
  "source_strategy": ["첨부자료/외부자료를 어떤 장표 근거로 사용할지"],
  "template_guidance": ["톤앤매너, 표지/본문/요약 장표 템플릿 방향"],
  "quality_bar": ["기획 승인 기준 또는 완성도 체크 기준"],
  "table_of_contents": ["..."],
  "slide_plans": [
    {{
      "slide_id": "slide-001",
      "page": 1,
      "title": "장표 제목",
      "purpose": "장표 목적",
      "key_message": "핵심 주장",
      "decision_question": "이 장표에서 승인권자가 답해야 할 질문",
      "narrative_role": "전체 보고서 스토리에서 이 장표의 역할",
      "layout": "장표 레이아웃 설명",
      "visual_direction": "시각화 방향",
      "required_evidence": ["필요 근거"],
      "content_blocks": ["장표에 들어갈 주요 블록"],
      "data_needs": ["추가로 필요한 데이터 또는 검증 항목"],
      "design_notes": ["색상/도표/컴포넌트/배치 지시"],
      "acceptance_criteria": ["이 장표를 승인할 수 있는 기준"]
    }}
  ],
  "open_questions": ["..."],
  "risk_notes": ["..."]
}}

Editable PPTX quality contract:
- Design every slide so it can be exported as native PowerPoint text boxes, cards, tables, timelines, matrices, or flow shapes.
- Avoid image-only slides unless the slide explicitly requires a selected visual asset.
- Put one decision-level headline in key_message, not a generic topic label.
- Make layout and visual_direction concrete enough for an automated python-pptx renderer.
- Make acceptance_criteria checkable by PM/대표 before slide production.
- Prefer PowerPoint-safe font guidance and simple shapes over web-only effects.

Report:
- title: {rec.title}
- goal: {rec.goal}
- client: {rec.client}
- report_type: {rec.report_type}
- audience: {rec.audience}
- slide_count: {rec.slide_count}
- attachments_context: {rec.attachments_context[:4000]}
- source_refs: {", ".join(rec.source_refs)}

First design the report before drafting copy. Make the plan detailed enough that a PM can approve, request changes, or assign slide production without additional explanation.
Create exactly {rec.slide_count} slide_plans unless the input clearly requires fewer.
""".strip()

    def _build_slides_prompt(self, rec: ReportWorkflowRecord) -> str:
        planning = asdict(rec.planning) if rec.planning else {}
        return f"""
You are DecisionDoc AI slide draft generator.
Return ONLY valid JSON for Korean presentation slide drafts.

JSON shape:
{{
  "slides": [
    {{
      "slide_id": "slide-001",
      "page": 1,
      "title": "장표 제목",
      "body": "장표 본문 핵심 bullet 또는 요약",
      "visual_spec": "도표/이미지/레이아웃 지시",
      "speaker_note": "PM 설명용 발표 노트",
      "source_refs": ["근거 자료"]
    }}
  ]
}}

Editable PPTX production rules:
- Use the approved planning snapshot as the source of truth; do not invent a different structure.
- Keep body concise enough to fit editable PowerPoint text boxes.
- visual_spec must name a native shape pattern such as matrix, timeline, process flow, governance chart, comparison cards, table, KPI cards, or image placeholder.
- speaker_note should explain how the PM should present the decision point.
- source_refs must preserve planning.required_evidence where available.

Report title: {rec.title}
Report goal: {rec.goal}
Approved planning snapshot:
{json.dumps(planning, ensure_ascii=False)}
""".strip()

    def _planning_from_provider_data(self, data: Any, rec: ReportWorkflowRecord) -> PlanningVersion:
        if not isinstance(data, dict):
            data = {}
        raw_slide_plans = data.get("slide_plans")
        if raw_slide_plans is None:
            raw_slide_plans = data.get("ppt_slides")
        slide_plans = self._normalize_slide_plans(raw_slide_plans, rec)
        if not slide_plans:
            slide_plans = self._fallback_slide_plans(rec)
        toc = _as_list(data.get("table_of_contents"))
        if not toc:
            toc = [plan.title for plan in slide_plans]
        planning_brief = str(
            data.get("planning_brief")
            or data.get("brief")
            or f"{rec.title}의 목적, 독자, 근거 사용 방향을 먼저 확정한 뒤 장표 제작으로 전환합니다."
        )
        audience_decision_needs = _string_list(data.get("audience_decision_needs")) or [
            "보고서 목적과 승인 요청 사항이 명확한가",
            "핵심 근거가 의사결정 기준에 충분히 연결되는가",
            "실행 계획과 리스크 대응이 승인 가능한 수준인가",
        ]
        narrative_arc = _string_list(data.get("narrative_arc")) or [
            "왜 지금 이 보고서가 필요한지 정의",
            "첨부자료와 근거로 현재 상태를 진단",
            "해결 방향과 실행안을 장표별로 구체화",
            "PM/대표 승인에 필요한 결정 사항을 명확히 제시",
        ]
        source_strategy = _string_list(data.get("source_strategy")) or [
            "첨부자료는 장표별 required_evidence에 매핑",
            "근거가 부족한 장표는 data_needs와 open_questions에 남김",
            "최종 장표에는 출처 또는 검증 필요 항목을 표시",
        ]
        template_guidance = _string_list(data.get("template_guidance")) or [
            "각 장표는 headline, evidence, action/decision block으로 구성",
            "정량 근거는 카드/표, 프로세스는 흐름도, 비교는 매트릭스로 표현",
        ]
        quality_bar = _string_list(data.get("quality_bar")) or [
            "장표별 decision_question과 key_message가 서로 연결됨",
            "승인권자가 수정 요청 없이 다음 단계 판단을 할 수 있음",
            "근거 부족, 리스크, 추가 질문이 숨겨지지 않고 표시됨",
        ]
        return PlanningVersion(
            plan_id=str(uuid.uuid4()),
            version=0,
            status="draft",
            objective=str(data.get("objective") or rec.goal or rec.title),
            audience=str(data.get("audience") or rec.audience or "PM/대표/의사결정권자"),
            executive_message=str(data.get("executive_message") or f"{rec.title}의 핵심 의사결정 메시지를 한 흐름으로 정리합니다."),
            table_of_contents=[str(item) for item in toc],
            slide_plans=slide_plans,
            open_questions=[str(item) for item in _as_list(data.get("open_questions"))],
            risk_notes=[str(item) for item in _as_list(data.get("risk_notes"))],
            created_by="ai",
            created_at=_now_iso(),
            planning_brief=planning_brief,
            audience_decision_needs=audience_decision_needs,
            narrative_arc=narrative_arc,
            template_guidance=template_guidance,
            source_strategy=source_strategy,
            quality_bar=quality_bar,
        )

    def _normalize_slide_plans(self, raw: Any, rec: ReportWorkflowRecord) -> list[SlidePlan]:
        plans: list[SlidePlan] = []
        for idx, item in enumerate(_as_list(raw), start=1):
            if not isinstance(item, dict):
                continue
            page = int(item.get("page") or idx)
            title = str(item.get("title") or f"{page}. 장표").strip()
            plans.append(SlidePlan(
                slide_id=_safe_slide_id(item.get("slide_id"), page),
                page=page,
                title=title,
                purpose=str(item.get("purpose") or item.get("key_content") or "보고서 핵심 내용을 설명합니다."),
                key_message=str(item.get("key_message") or item.get("key_content") or title),
                decision_question=str(item.get("decision_question") or f"{title}에서 승인권자가 판단해야 할 핵심 질문은 무엇인가?"),
                narrative_role=str(item.get("narrative_role") or item.get("role") or "전체 보고서 흐름에서 핵심 판단 근거를 제공합니다."),
                layout=str(item.get("layout") or item.get("design_tip") or "상단 핵심 메시지와 하단 근거/시각자료 배치"),
                visual_direction=str(item.get("visual_direction") or item.get("visual") or "핵심 흐름을 도식화"),
                required_evidence=[str(value) for value in _as_list(item.get("required_evidence") or item.get("evidence"))],
                content_blocks=_string_list(item.get("content_blocks") or item.get("sections") or item.get("blocks")),
                data_needs=_string_list(item.get("data_needs") or item.get("data_requirements") or item.get("required_evidence") or item.get("evidence")),
                design_notes=_string_list(item.get("design_notes") or item.get("design_guidance") or item.get("design_tip") or item.get("layout")),
                acceptance_criteria=_string_list(item.get("acceptance_criteria") or item.get("approval_criteria") or item.get("checks")) or [
                    "핵심 메시지가 독자 의사결정 질문에 직접 답합니다.",
                    "필요 근거와 검증 공백이 구분되어 있습니다.",
                ],
            ))
        return plans[: max(1, min(rec.slide_count, 40))]

    def _fallback_slide_plans(self, rec: ReportWorkflowRecord) -> list[SlidePlan]:
        titles = ["표지 및 핵심 메시지", "현황 및 문제 정의", "제안 방향", "실행 계획", "기대 효과", "승인 요청"]
        if rec.slide_count > len(titles):
            titles.extend([f"세부 장표 {idx}" for idx in range(len(titles) + 1, rec.slide_count + 1)])
        plans = []
        for idx, title in enumerate(titles[:rec.slide_count], start=1):
            plans.append(SlidePlan(
                slide_id=f"slide-{idx:03d}",
                page=idx,
                title=title,
                purpose=f"{rec.title} 보고서의 {title} 내용을 정리합니다.",
                key_message=rec.goal or title,
                decision_question=f"{title} 단계에서 승인권자가 확인해야 할 핵심 판단은 무엇인가?",
                narrative_role="문제 인식에서 승인 요청까지 이어지는 보고서 흐름을 구성합니다.",
                layout="상단 핵심 메시지, 본문 근거, 우측 시각자료",
                visual_direction="요약 카드와 흐름도 중심",
                required_evidence=rec.source_refs[:3],
                content_blocks=["핵심 메시지", "근거 요약", "의사결정 포인트"],
                data_needs=["첨부자료 근거 매핑", "정량 수치 또는 사례 확인"],
                design_notes=["한 장표당 하나의 결론만 강조", "상단 headline과 하단 evidence 영역 분리"],
                acceptance_criteria=["목적과 핵심 메시지가 한 문장으로 설명됨", "근거 출처 또는 검증 필요 항목이 명확함"],
            ))
        return plans

    def _slides_from_provider_data(self, data: Any, rec: ReportWorkflowRecord) -> list[SlideDraft]:
        if not isinstance(data, dict):
            data = {}
        raw_slides = data.get("slides")
        if raw_slides is None:
            raw_slides = data.get("ppt_slides")
        slides: list[SlideDraft] = []
        for idx, item in enumerate(_as_list(raw_slides), start=1):
            if not isinstance(item, dict):
                continue
            page = int(item.get("page") or idx)
            slide_id = _safe_slide_id(item.get("slide_id"), page)
            title = str(item.get("title") or f"{page}. 장표")
            body = str(item.get("body") or item.get("key_content") or "")
            slides.append(SlideDraft(
                slide_id=slide_id,
                page=page,
                title=title,
                body=body or f"{title}: {rec.goal or rec.title}",
                visual_spec=str(item.get("visual_spec") or item.get("visual") or item.get("layout") or "핵심 메시지를 도식화"),
                speaker_note=str(item.get("speaker_note") or item.get("notes") or f"{title}의 의사결정 포인트를 설명합니다."),
                source_refs=[str(value) for value in _as_list(item.get("source_refs") or item.get("evidence") or rec.source_refs)],
            ))
        if slides:
            return sorted(slides, key=lambda item: item.page)[: max(1, min(rec.slide_count, 40))]
        return self._fallback_slides(rec)

    def _fallback_slides(self, rec: ReportWorkflowRecord) -> list[SlideDraft]:
        planning = rec.planning
        plans = planning.slide_plans if planning else self._fallback_slide_plans(rec)
        slides: list[SlideDraft] = []
        for plan in plans:
            slides.append(SlideDraft(
                slide_id=plan.slide_id,
                page=plan.page,
                title=plan.title,
                body=f"{plan.key_message}\n\n- 목적: {plan.purpose}\n- 근거: {', '.join(plan.required_evidence[:3]) or '추가 근거 확인 필요'}",
                visual_spec=plan.visual_direction or plan.layout,
                speaker_note=f"{plan.title}에서는 {plan.purpose}를 중심으로 설명합니다.",
                source_refs=plan.required_evidence or rec.source_refs,
            ))
        return slides
