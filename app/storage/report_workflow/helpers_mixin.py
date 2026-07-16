"""Shared static/class helpers used by the report workflow mixins.

Covers dict<->dataclass conversion, mutability guards, quality-warning
bookkeeping, visual-asset sanitization, and default approval-step wiring.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.config import (
    get_report_workflow_visual_asset_max_base64_chars,
    get_report_workflow_visual_asset_max_count,
)

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
from app.tenant import require_tenant_id


class ReportWorkflowHelpersMixin:
    """Dict conversion, mutability guard, and quality-warning helpers."""

    @staticmethod
    def _comment_from_dict(data: dict) -> WorkflowComment:
        if not isinstance(data, dict):
            raise ValueError("Invalid report workflow comment")
        comment_id = data.get("comment_id")
        created_at = data.get("created_at")
        if not isinstance(comment_id, str) or not comment_id:
            raise ValueError("Invalid report workflow comment identity")
        if not isinstance(created_at, str) or not created_at:
            raise ValueError("Invalid report workflow comment identity")
        return WorkflowComment(
            comment_id=comment_id,
            target_type=data.get("target_type", ""),
            target_id=data.get("target_id", ""),
            author=data.get("author", ""),
            content=data.get("content", ""),
            created_at=created_at,
            is_change_request=bool(data.get("is_change_request", False)),
        )

    @classmethod
    def _slide_plan_from_dict(cls, data: dict) -> SlidePlan:
        if not isinstance(data, dict):
            raise ValueError("Invalid report workflow slide plan")
        slide_id = data.get("slide_id")
        if not isinstance(slide_id, str) or not slide_id:
            raise ValueError("Invalid report workflow slide plan identity")
        return SlidePlan(
            slide_id=slide_id,
            page=int(data.get("page") or 0),
            title=data.get("title", ""),
            purpose=data.get("purpose", ""),
            key_message=data.get("key_message", ""),
            decision_question=data.get("decision_question", ""),
            narrative_role=data.get("narrative_role", ""),
            layout=data.get("layout", ""),
            visual_direction=data.get("visual_direction", ""),
            required_evidence=list(data.get("required_evidence") or []),
            content_blocks=list(data.get("content_blocks") or []),
            data_needs=list(data.get("data_needs") or []),
            design_notes=list(data.get("design_notes") or []),
            acceptance_criteria=list(data.get("acceptance_criteria") or []),
            approval_status=data.get("approval_status", "pending"),
        )

    @classmethod
    def _planning_from_dict(cls, data: dict | None) -> PlanningVersion | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            raise ValueError("Invalid report workflow planning record")
        plan_id = data.get("plan_id")
        created_at = data.get("created_at")
        slide_plans = data.get("slide_plans", [])
        if not isinstance(plan_id, str) or not plan_id:
            raise ValueError("Invalid report workflow planning identity")
        if not isinstance(created_at, str) or not created_at:
            raise ValueError("Invalid report workflow planning identity")
        if not isinstance(slide_plans, list):
            raise ValueError("Invalid report workflow slide plans")
        return PlanningVersion(
            plan_id=plan_id,
            version=int(data.get("version") or 1),
            status=data.get("status", "draft"),
            objective=data.get("objective", ""),
            audience=data.get("audience", ""),
            executive_message=data.get("executive_message", ""),
            table_of_contents=list(data.get("table_of_contents") or []),
            slide_plans=[cls._slide_plan_from_dict(item) for item in slide_plans],
            open_questions=list(data.get("open_questions") or []),
            risk_notes=list(data.get("risk_notes") or []),
            created_by=data.get("created_by", "ai"),
            created_at=created_at,
            planning_brief=data.get("planning_brief", ""),
            audience_decision_needs=list(data.get("audience_decision_needs") or []),
            narrative_arc=list(data.get("narrative_arc") or []),
            template_guidance=list(data.get("template_guidance") or []),
            source_strategy=list(data.get("source_strategy") or []),
            quality_bar=list(data.get("quality_bar") or []),
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
        )

    @classmethod
    def _slide_from_dict(cls, data: dict) -> SlideDraft:
        if not isinstance(data, dict):
            raise ValueError("Invalid report workflow slide")
        slide_id = data.get("slide_id")
        comments = data.get("comments", [])
        if not isinstance(slide_id, str) or not slide_id:
            raise ValueError("Invalid report workflow slide identity")
        if not isinstance(comments, list):
            raise ValueError("Invalid report workflow slide comments")
        return SlideDraft(
            slide_id=slide_id,
            page=int(data.get("page") or 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            visual_spec=data.get("visual_spec", ""),
            speaker_note=data.get("speaker_note", ""),
            source_refs=list(data.get("source_refs") or []),
            status=data.get("status", SlideStatus.DRAFT.value),
            draft_version=int(data.get("draft_version") or 1),
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
            comments=[cls._comment_from_dict(item) for item in comments],
            visual_prompt=data.get("visual_prompt", ""),
            reference_refs=list(data.get("reference_refs") or []),
            generated_asset_ids=list(data.get("generated_asset_ids") or []),
            selected_asset_id=data.get("selected_asset_id", ""),
            selected_asset=dict(data.get("selected_asset") or {}),
        )

    @staticmethod
    def _approval_step_from_dict(data: dict) -> ApprovalStep:
        if not isinstance(data, dict):
            raise ValueError("Invalid report workflow approval step")
        step_id = data.get("step_id")
        stage = data.get("stage")
        if not isinstance(step_id, str) or not step_id:
            raise ValueError("Invalid report workflow approval identity")
        if not isinstance(stage, str) or not stage:
            raise ValueError("Invalid report workflow approval identity")
        return ApprovalStep(
            step_id=step_id,
            stage=stage,
            label=data.get("label", ""),
            assignee=data.get("assignee", ""),
            status=data.get("status", "pending"),
            actor=data.get("actor"),
            decided_at=data.get("decided_at"),
            comment=data.get("comment", ""),
        )

    @classmethod
    def _from_dict(cls, data: dict) -> ReportWorkflowRecord:
        if not isinstance(data, dict):
            raise ValueError("Invalid report workflow record")
        report_workflow_id = data.get("report_workflow_id")
        tenant_id = data.get("tenant_id")
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")
        status = data.get("status")
        if not isinstance(report_workflow_id, str) or not report_workflow_id:
            raise ValueError("Invalid report workflow identity")
        require_tenant_id(tenant_id)
        if not isinstance(created_at, str) or not created_at:
            raise ValueError("Invalid report workflow identity")
        if not isinstance(updated_at, str) or not updated_at:
            raise ValueError("Invalid report workflow identity")
        if status not in {item.value for item in ReportWorkflowStatus}:
            raise ValueError("Invalid report workflow status")

        list_fields = (
            "source_refs",
            "slides",
            "comments",
            "approval_steps",
            "quality_warnings",
            "learning_artifacts",
            "visual_assets",
            "knowledge_documents",
        )
        if any(not isinstance(data.get(field, []), list) for field in list_fields):
            raise ValueError("Invalid report workflow list field")

        record = ReportWorkflowRecord(
            report_workflow_id=report_workflow_id,
            tenant_id=tenant_id,
            title=data.get("title", ""),
            goal=data.get("goal", ""),
            client=data.get("client", ""),
            report_type=data.get("report_type", ""),
            audience=data.get("audience", ""),
            owner=data.get("owner", ""),
            pm_reviewer=data.get("pm_reviewer", ""),
            executive_approver=data.get("executive_approver", ""),
            status=status,
            source_bundle_id=data.get("source_bundle_id", "presentation_kr"),
            source_request_id=data.get("source_request_id", ""),
            slide_count=int(data.get("slide_count") or 6),
            attachments_context=data.get("attachments_context", ""),
            source_refs=list(data.get("source_refs") or []),
            learning_opt_in=bool(data.get("learning_opt_in", False)),
            created_at=created_at,
            updated_at=updated_at,
            current_plan_version=int(data.get("current_plan_version") or 0),
            current_slide_version=int(data.get("current_slide_version") or 0),
            planning=cls._planning_from_dict(data.get("planning")),
            slides=[cls._slide_from_dict(item) for item in data.get("slides", [])],
            comments=[cls._comment_from_dict(item) for item in data.get("comments", [])],
            approval_steps=[cls._approval_step_from_dict(item) for item in data.get("approval_steps", [])],
            quality_warnings=list(data.get("quality_warnings") or []),
            learning_artifacts=list(data.get("learning_artifacts") or []),
            visual_assets=list(data.get("visual_assets") or []),
            final_submitted_at=data.get("final_submitted_at"),
            final_approved_by=data.get("final_approved_by"),
            final_approved_at=data.get("final_approved_at"),
            final_approval_id=data.get("final_approval_id"),
            final_approval_status=data.get("final_approval_status"),
            final_approval_synced_at=data.get("final_approval_synced_at"),
            project_id=data.get("project_id"),
            project_document_id=data.get("project_document_id"),
            project_promoted_at=data.get("project_promoted_at"),
            knowledge_project_id=data.get("knowledge_project_id"),
            knowledge_document_count=int(data.get("knowledge_document_count") or 0),
            knowledge_documents=list(data.get("knowledge_documents") or []),
            knowledge_promoted_at=data.get("knowledge_promoted_at"),
        )
        cls._validate_record(record)
        return record

    @staticmethod
    def _require_unique_ids(values: list[str], *, label: str) -> None:
        if any(not isinstance(value, str) or not value for value in values):
            raise ValueError(f"Invalid {label} identity")
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {label} identity")

    @classmethod
    def _validate_record(cls, record: ReportWorkflowRecord) -> None:
        if not record.report_workflow_id or not record.created_at or not record.updated_at:
            raise ValueError("Invalid report workflow identity")
        require_tenant_id(record.tenant_id)
        if record.status not in {item.value for item in ReportWorkflowStatus}:
            raise ValueError("Invalid report workflow status")
        if not 1 <= record.slide_count <= 40:
            raise ValueError("Invalid report workflow slide_count")
        if record.current_plan_version < 0 or record.current_slide_version < 0:
            raise ValueError("Invalid report workflow version")

        if record.planning is not None:
            if not record.planning.plan_id or not record.planning.created_at:
                raise ValueError("Invalid report workflow planning identity")
            if record.planning.status not in {"draft", "changes_requested", "approved"}:
                raise ValueError("Invalid report workflow planning status")
            cls._require_unique_ids(
                [slide.slide_id for slide in record.planning.slide_plans],
                label="report workflow slide plan",
            )

        if any(slide.status not in {item.value for item in SlideStatus} for slide in record.slides):
            raise ValueError("Invalid report workflow slide status")
        cls._require_unique_ids(
            [slide.slide_id for slide in record.slides],
            label="report workflow slide",
        )

        comments = [*record.comments]
        for slide in record.slides:
            comments.extend(slide.comments)
        if any(not comment.created_at for comment in comments):
            raise ValueError("Invalid report workflow comment identity")
        cls._require_unique_ids(
            [comment.comment_id for comment in comments],
            label="report workflow comment",
        )

        if any(
            step.status not in {"pending", "approved", "changes_requested"}
            for step in record.approval_steps
        ):
            raise ValueError("Invalid report workflow approval status")
        cls._require_unique_ids(
            [step.step_id for step in record.approval_steps],
            label="report workflow approval step",
        )
        cls._require_unique_ids(
            [step.stage for step in record.approval_steps],
            label="report workflow approval stage",
        )

        if any(not isinstance(artifact, dict) for artifact in record.learning_artifacts):
            raise ValueError("Invalid report workflow learning artifact")
        cls._require_unique_ids(
            [artifact.get("artifact_id") for artifact in record.learning_artifacts],
            label="report workflow learning artifact",
        )

        if any(not isinstance(asset, dict) for asset in record.visual_assets):
            raise ValueError("Invalid report workflow visual asset")
        cls._require_unique_ids(
            [asset.get("asset_id") for asset in record.visual_assets],
            label="report workflow visual asset",
        )

    @staticmethod
    def _ensure_mutable(rec: ReportWorkflowRecord) -> None:
        if rec.status in {ReportWorkflowStatus.FINAL_APPROVED.value, ReportWorkflowStatus.DELIVERED.value}:
            raise ValueError("최종 승인된 보고서 워크플로우는 수정할 수 없습니다.")

    @staticmethod
    def _normalize_actor(value: str | None) -> str:
        return str(value or "").strip().casefold()

    @staticmethod
    def _append_quality_warning(rec: ReportWorkflowRecord, warning: str) -> None:
        normalized = str(warning or "").strip()
        if normalized and normalized not in rec.quality_warnings:
            rec.quality_warnings.append(normalized)

    def _record_approval_actor_warnings(
        self,
        rec: ReportWorkflowRecord,
        *,
        stage: str,
        author: str,
        step: ApprovalStep,
    ) -> None:
        actor = str(author or "").strip()
        if not actor:
            return
        assignee = str(step.assignee or "").strip()
        if assignee and self._normalize_actor(actor) != self._normalize_actor(assignee):
            self._append_quality_warning(
                rec,
                f"approval_assignee_mismatch:{stage}:expected={assignee}:actual={actor}",
            )
        if stage == "executive_review" and rec.owner and self._normalize_actor(actor) == self._normalize_actor(rec.owner):
            self._append_quality_warning(
                rec,
                f"self_final_approval_warning:executive_actor_matches_owner:{actor}",
            )

    @staticmethod
    def _learning_artifact(kind: str, payload: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
        return {
            "artifact_id": str(uuid.uuid4()),
            "kind": kind,
            "actor": actor,
            "created_at": _now_iso(),
            "payload": payload,
        }

    @staticmethod
    def _sanitize_visual_asset(asset: dict[str, Any]) -> dict[str, Any]:
        sanitized = dict(asset)
        raw_content = sanitized.get("content_base64")
        if raw_content in (None, ""):
            sanitized.pop("content_base64", None)
            return sanitized
        encoded = str(raw_content)
        limit = get_report_workflow_visual_asset_max_base64_chars()
        sanitized["content_base64_len"] = len(encoded)
        if limit and len(encoded) > limit:
            sanitized.pop("content_base64", None)
            sanitized["content_base64_dropped"] = True
            sanitized["content_base64_limit"] = limit
            return sanitized
        sanitized["content_base64"] = encoded
        return sanitized

    @classmethod
    def _merge_visual_assets(cls, existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for asset in [*existing, *incoming]:
            if not isinstance(asset, dict):
                continue
            asset_id = str(asset.get("asset_id") or "").strip()
            if not asset_id:
                continue
            if asset_id not in merged:
                order.append(asset_id)
            merged[asset_id] = cls._sanitize_visual_asset(asset)
        max_count = get_report_workflow_visual_asset_max_count()
        return [merged[asset_id] for asset_id in order][-max_count:]

    @staticmethod
    def _default_approval_steps(
        pm_reviewer: str = "",
        executive_approver: str = "",
    ) -> list[ApprovalStep]:
        return [
            ApprovalStep(
                step_id=str(uuid.uuid4()),
                stage="pm_review",
                label="PM 검토",
                assignee=pm_reviewer,
            ),
            ApprovalStep(
                step_id=str(uuid.uuid4()),
                stage="executive_review",
                label="대표 최종 승인",
                assignee=executive_approver,
            ),
        ]

    @staticmethod
    def _approval_step(rec: ReportWorkflowRecord, stage: str) -> ApprovalStep:
        step = next((item for item in rec.approval_steps if item.stage == stage), None)
        if step is None:
            raise ValueError(f"결재 단계를 찾을 수 없습니다: {stage}")
        return step
