"""PPTX export, export snapshot, and visual asset generation for ReportWorkflowService."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.services.report_workflow.helpers import _dedupe_strings, _now_iso
from app.services.visual_asset_service import generate_visual_assets_from_docs, index_visual_assets_by_slide_title
from app.storage.report_workflow_store import ReportWorkflowRecord, SlideDraft


class ReportWorkflowExportMixin:
    """PPTX export, export snapshot, and visual asset generation."""

    def build_pptx_export(self, report_workflow_id: str, *, tenant_id: str) -> bytes:
        from app.services.report_workflow_service import build_pptx

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
