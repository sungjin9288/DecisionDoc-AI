"""Slide-stage report workflow transitions and visual-asset management."""
from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from app.storage.report_workflow.models import (
    ReportWorkflowRecord,
    ReportWorkflowStatus,
    SlideDraft,
    SlideStatus,
    WorkflowComment,
    _now_iso,
)


class ReportWorkflowSlideMixin:
    """Slide draft/change-request/approval and visual-asset transitions."""

    def save_slides(
        self,
        report_workflow_id: str,
        slides: list[SlideDraft],
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
            if rec.status != ReportWorkflowStatus.PLANNING_APPROVED.value and not (
                rec.planning and rec.planning.status == "approved"
            ):
                raise ValueError("기획안 승인 후 장표를 생성할 수 있습니다.")
            rec.current_slide_version += 1
            for slide in slides:
                slide.draft_version = rec.current_slide_version
                slide.status = SlideStatus.DRAFT.value
                slide.approved_by = None
                slide.approved_at = None
            rec.slides = slides
            rec.status = ReportWorkflowStatus.SLIDES_DRAFT.value
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
            rec.quality_warnings.extend(quality_warnings or [])
            return self._flush(tid, records, idx, rec)

    def request_slide_changes(
        self,
        report_workflow_id: str,
        slide_id: str,
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
            slide = next((item for item in rec.slides if item.slide_id == slide_id), None)
            if slide is None:
                raise KeyError(f"장표를 찾을 수 없습니다: {slide_id}")
            slide.status = SlideStatus.CHANGES_REQUESTED.value
            slide.approved_by = None
            slide.approved_at = None
            slide.comments.append(WorkflowComment(
                comment_id=str(uuid.uuid4()),
                target_type="slide",
                target_id=slide_id,
                author=author,
                content=comment,
                created_at=_now_iso(),
                is_change_request=True,
            ))
            rec.status = ReportWorkflowStatus.SLIDES_CHANGES_REQUESTED.value
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "slide_change_request",
                    {"slide_id": slide_id, "comment": comment, "draft_version": slide.draft_version},
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)

    def approve_slide(
        self,
        report_workflow_id: str,
        slide_id: str,
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
            slide = next((item for item in rec.slides if item.slide_id == slide_id), None)
            if slide is None:
                raise KeyError(f"장표를 찾을 수 없습니다: {slide_id}")
            slide.status = SlideStatus.APPROVED.value
            slide.approved_by = author
            slide.approved_at = _now_iso()
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "slide_approved",
                    asdict(slide),
                    actor=author,
                ))
            if rec.slides and all(item.status == SlideStatus.APPROVED.value for item in rec.slides):
                rec.status = ReportWorkflowStatus.SLIDES_APPROVED.value
            else:
                rec.status = ReportWorkflowStatus.SLIDES_DRAFT.value
            return self._flush(tid, records, idx, rec)

    def update_slide_visual_assets(
        self,
        report_workflow_id: str,
        slide_id: str,
        *,
        visual_prompt: str = "",
        reference_refs: list[str] | None = None,
        generated_asset_ids: list[str] | None = None,
        selected_asset_id: str = "",
        selected_asset: dict[str, Any] | None = None,
        author: str = "",
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            slide = next((item for item in rec.slides if item.slide_id == slide_id), None)
            if slide is None:
                raise KeyError(f"장표를 찾을 수 없습니다: {slide_id}")

            slide.visual_prompt = str(visual_prompt or "").strip()[:4000]
            slide.reference_refs = [str(item).strip() for item in (reference_refs or []) if str(item).strip()][:12]
            slide.generated_asset_ids = [
                str(item).strip() for item in (generated_asset_ids or []) if str(item).strip()
            ][:12]
            slide.selected_asset_id = str(selected_asset_id or "").strip()[:200]
            slide.selected_asset = self._sanitize_visual_asset(dict(selected_asset or {})) if selected_asset else {}
            if slide.selected_asset:
                rec.visual_assets = self._merge_visual_assets(rec.visual_assets, [slide.selected_asset])
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "slide_visual_asset_updated",
                    {
                        "slide_id": slide_id,
                        "visual_prompt": slide.visual_prompt,
                        "reference_refs": slide.reference_refs,
                        "generated_asset_ids": slide.generated_asset_ids,
                        "selected_asset_id": slide.selected_asset_id,
                        "selected_asset": slide.selected_asset,
                    },
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)

    def add_visual_assets(
        self,
        report_workflow_id: str,
        assets: list[dict[str, Any]],
        *,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            rec.visual_assets = self._merge_visual_assets(rec.visual_assets, assets)
            return self._flush(tid, records, idx, rec)

    def select_slide_visual_asset(
        self,
        report_workflow_id: str,
        slide_id: str,
        *,
        asset_id: str,
        author: str = "",
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            slide = next((item for item in rec.slides if item.slide_id == slide_id), None)
            if slide is None:
                raise KeyError(f"장표를 찾을 수 없습니다: {slide_id}")
            normalized_asset_id = str(asset_id or "").strip()
            selected_asset = next(
                (asset for asset in rec.visual_assets if str(asset.get("asset_id") or "").strip() == normalized_asset_id),
                None,
            )
            if selected_asset is None:
                raise KeyError(f"시각자료 asset을 찾을 수 없습니다: {normalized_asset_id}")
            slide.selected_asset_id = normalized_asset_id
            slide.selected_asset = dict(selected_asset)
            if normalized_asset_id not in slide.generated_asset_ids:
                slide.generated_asset_ids = [*slide.generated_asset_ids, normalized_asset_id][:12]
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "slide_visual_asset_selected",
                    {"slide_id": slide_id, "asset_id": normalized_asset_id},
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)
