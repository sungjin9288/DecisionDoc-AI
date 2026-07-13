"""Report workflow lifecycle, slide generation, and quality-correction schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateReportWorkflowRequest(BaseModel):
    """Payload for POST /report-workflows."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1)
    goal: str = ""
    client: str = ""
    report_type: str = "proposal_presentation"
    audience: str = ""
    owner: str = ""
    pm_reviewer: str = ""
    executive_approver: str = ""
    source_bundle_id: str = "presentation_kr"
    source_request_id: str = ""
    slide_count: int = Field(default=6, ge=1, le=40)
    attachments_context: str = ""
    source_refs: list[str] = Field(default_factory=list)
    learning_opt_in: bool = False


class ReportWorkflowActionRequest(BaseModel):
    """Payload for report workflow approval/change actions."""

    model_config = ConfigDict(strict=True, extra="forbid")

    username: str = ""
    comment: str = ""


class UpdateReportPlanningRequest(BaseModel):
    """Payload for future manual planning updates."""

    model_config = ConfigDict(strict=True, extra="forbid")

    username: str = ""
    planning: dict[str, Any] = Field(default_factory=dict)


class UpdateReportSlideRequest(BaseModel):
    """Payload for future manual slide updates."""

    model_config = ConfigDict(strict=True, extra="forbid")

    username: str = ""
    slide: dict[str, Any] = Field(default_factory=dict)


class GenerateReportSlidesRequest(BaseModel):
    """Payload for POST /report-workflows/{id}/slides/generate."""

    model_config = ConfigDict(strict=True, extra="forbid")

    regenerate: bool = False


class UpdateReportSlideVisualAssetsRequest(BaseModel):
    """Payload for attaching visual asset workspace metadata to a workflow slide."""

    model_config = ConfigDict(strict=True, extra="forbid")

    username: str = ""
    visual_prompt: str = Field(default="", max_length=4000)
    reference_refs: list[str] = Field(default_factory=list, max_length=12)
    generated_asset_ids: list[str] = Field(default_factory=list, max_length=12)
    selected_asset_id: str = Field(default="", max_length=200)
    selected_asset: dict[str, Any] = Field(default_factory=dict)


class GenerateReportWorkflowVisualAssetsRequest(BaseModel):
    """Payload for generating visual asset candidates from workflow slide drafts."""

    model_config = ConfigDict(strict=True, extra="forbid")

    username: str = ""
    max_assets: int = Field(default=6, ge=1, le=12)
    select_first: bool = True


class SelectReportSlideVisualAssetRequest(BaseModel):
    """Payload for selecting one persisted workflow visual asset for a slide."""

    model_config = ConfigDict(strict=True, extra="forbid")

    username: str = ""
    asset_id: str = Field(..., min_length=1, max_length=200)


class PromoteReportWorkflowRequest(BaseModel):
    """Payload for promoting a final-approved report workflow into project/knowledge rails."""

    model_config = ConfigDict(strict=True, extra="forbid")

    project_id: str = Field(..., min_length=1)
    username: str = ""
    promote_to_knowledge: bool = False
    tags: list[str] = Field(default_factory=list)
    quality_tier: str = "gold"
    success_state: str = "approved"
    source_organization: str = ""
    reference_year: int | None = None
    notes: str = ""


class ReportQualityCorrectionChangeRequest(BaseModel):
    """One human correction note for report quality learning."""

    model_config = ConfigDict(strict=True, extra="forbid")

    target: str = Field(..., min_length=1, max_length=200)
    issue: str = Field(..., min_length=1, max_length=4000)
    correction: str = Field(..., min_length=1, max_length=4000)
    rationale: str = Field(..., min_length=1, max_length=4000)


class ReportQualityCorrectionArtifactRequest(BaseModel):
    """Payload for previewing or saving a report quality correction artifact."""

    model_config = ConfigDict(strict=True, extra="forbid")

    username: str = ""
    reviewer: str = ""
    reviewed_at: str = ""
    domain: str = ""
    language: str = "ko"
    overall_score: float = Field(default=0.0, ge=0.0, le=1.0)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    hard_failures: list[str] = Field(default_factory=list)
    before_planning_summary: str = ""
    before_slide_outline_summary: list[dict[str, Any]] = Field(default_factory=list)
    visible_claims: list[dict[str, Any]] = Field(default_factory=list)
    change_requests: list[ReportQualityCorrectionChangeRequest] = Field(default_factory=list)
    rationale_by_dimension: dict[str, str] = Field(default_factory=dict)
    after_planning_summary: str = ""
    after_slide_outline_summary: list[dict[str, Any]] = Field(default_factory=list)
    final_output_reference: str = ""
    accepted_for_learning: bool = False
    task_types: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    confirmed_claims: list[str] = Field(default_factory=list)
    assumed_claims: list[str] = Field(default_factory=list)
    todo_claims: list[str] = Field(default_factory=list)
    forbidden_terms_scan: str = "not_run"
    privacy_security_scan: str = "not_run"
    human_review_status: str = "pending"
    preview_fingerprint: str = Field(default="", pattern=r"^(?:|[0-9a-f]{64})$")


class ReportQualityPilotExportRequest(BaseModel):
    """Select three to five saved artifacts for a local pilot JSONL batch."""

    model_config = ConfigDict(strict=True, extra="forbid")

    artifact_ids: list[str] = Field(..., min_length=3, max_length=5)

    @field_validator("artifact_ids")
    @classmethod
    def validate_artifact_ids(cls, value: list[str]) -> list[str]:
        normalized = [artifact_id.strip() for artifact_id in value]
        if any(not artifact_id for artifact_id in normalized):
            raise ValueError("artifact_ids must not contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("artifact_ids must be unique")
        return normalized


class ReportWorkflowDevelopQualityPreviewRequest(BaseModel):
    """Payload for running a Develop quality preview against a report workflow."""

    model_config = ConfigDict(strict=True, extra="forbid")

    username: str = ""
    focus: str = "보고서 품질 개선"
    additional_notes: str = ""
    capture_trajectory: bool = False
