"""Report workflow domain models: status enums and record dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ReportWorkflowStatus(str, Enum):
    PLANNING_REQUIRED = "planning_required"
    PLANNING_DRAFT = "planning_draft"
    PLANNING_CHANGES_REQUESTED = "planning_changes_requested"
    PLANNING_APPROVED = "planning_approved"
    SLIDES_DRAFT = "slides_draft"
    SLIDES_CHANGES_REQUESTED = "slides_changes_requested"
    SLIDES_APPROVED = "slides_approved"
    FINAL_REVIEW = "final_review"
    FINAL_CHANGES_REQUESTED = "final_changes_requested"
    FINAL_APPROVED = "final_approved"
    DELIVERED = "delivered"


class SlideStatus(str, Enum):
    DRAFT = "draft"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkflowComment:
    comment_id: str
    target_type: str
    target_id: str
    author: str
    content: str
    created_at: str
    is_change_request: bool = False


@dataclass
class SlidePlan:
    slide_id: str
    page: int
    title: str
    purpose: str = ""
    key_message: str = ""
    decision_question: str = ""
    narrative_role: str = ""
    layout: str = ""
    visual_direction: str = ""
    required_evidence: list[str] = field(default_factory=list)
    content_blocks: list[str] = field(default_factory=list)
    data_needs: list[str] = field(default_factory=list)
    design_notes: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    approval_status: str = "pending"


@dataclass
class PlanningVersion:
    plan_id: str
    version: int
    status: str
    objective: str
    audience: str
    executive_message: str
    table_of_contents: list[str]
    slide_plans: list[SlidePlan]
    open_questions: list[str]
    risk_notes: list[str]
    created_by: str
    created_at: str
    planning_brief: str = ""
    audience_decision_needs: list[str] = field(default_factory=list)
    narrative_arc: list[str] = field(default_factory=list)
    template_guidance: list[str] = field(default_factory=list)
    source_strategy: list[str] = field(default_factory=list)
    quality_bar: list[str] = field(default_factory=list)
    approved_by: str | None = None
    approved_at: str | None = None


@dataclass
class SlideDraft:
    slide_id: str
    page: int
    title: str
    body: str
    visual_spec: str
    speaker_note: str
    source_refs: list[str]
    status: str = SlideStatus.DRAFT.value
    draft_version: int = 1
    approved_by: str | None = None
    approved_at: str | None = None
    comments: list[WorkflowComment] = field(default_factory=list)
    visual_prompt: str = ""
    reference_refs: list[str] = field(default_factory=list)
    generated_asset_ids: list[str] = field(default_factory=list)
    selected_asset_id: str = ""
    selected_asset: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalStep:
    step_id: str
    stage: str
    label: str
    assignee: str = ""
    status: str = "pending"
    actor: str | None = None
    decided_at: str | None = None
    comment: str = ""


@dataclass
class ReportWorkflowRecord:
    report_workflow_id: str
    tenant_id: str
    title: str
    goal: str
    client: str
    report_type: str
    audience: str
    owner: str
    pm_reviewer: str
    executive_approver: str
    status: str
    source_bundle_id: str
    source_request_id: str
    slide_count: int
    attachments_context: str
    source_refs: list[str]
    learning_opt_in: bool
    created_at: str
    updated_at: str
    current_plan_version: int = 0
    current_slide_version: int = 0
    planning: PlanningVersion | None = None
    slides: list[SlideDraft] = field(default_factory=list)
    comments: list[WorkflowComment] = field(default_factory=list)
    approval_steps: list[ApprovalStep] = field(default_factory=list)
    quality_warnings: list[str] = field(default_factory=list)
    learning_artifacts: list[dict[str, Any]] = field(default_factory=list)
    visual_assets: list[dict[str, Any]] = field(default_factory=list)
    final_submitted_at: str | None = None
    final_approved_by: str | None = None
    final_approved_at: str | None = None
    final_approval_id: str | None = None
    final_approval_status: str | None = None
    final_approval_synced_at: str | None = None
    project_id: str | None = None
    project_document_id: str | None = None
    project_promoted_at: str | None = None
    knowledge_project_id: str | None = None
    knowledge_document_count: int = 0
    knowledge_documents: list[dict[str, Any]] = field(default_factory=list)
    knowledge_promoted_at: str | None = None
