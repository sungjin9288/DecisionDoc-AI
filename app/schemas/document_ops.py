"""Document-ops agent run, trajectory review/export, and training approval schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DocumentOpsAgentRunRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    task_type: str = Field(..., min_length=1)
    requirements: dict[str, Any] = Field(default_factory=dict)
    project_context: dict[str, Any] = Field(default_factory=dict)
    source_summaries: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    skill_name: str | None = None
    capture_trajectory: bool = False


class DocumentOpsTrajectoryReviewRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    accepted: bool
    reviewer: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentOpsTrajectoryExportRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    task_type: str | None = None
    min_records: int = Field(default=1, ge=1)
    accepted_only: bool = True
    include_metadata: bool = True


class DocumentOpsTrajectoryExportPreviewRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    task_type: str | None = None
    min_records: int = Field(default=1, ge=1)
    accepted_only: bool = True
    include_metadata: bool = True
    sample_limit: int = Field(default=5, ge=0, le=25)


class DocumentOpsDatasetFreezeRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    reviewer: str = Field(..., min_length=1)
    notes: str = ""
    sample_limit: int = Field(default=5, ge=0, le=25)
    training_allowed: bool = False


class DocumentOpsTrainingApprovalRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    approver: str = Field(..., min_length=1)
    eval_plan: dict[str, Any] = Field(..., min_length=1)
    notes: str = ""
    dry_run: bool = True
    start_training: bool = False


class DocumentOpsTrainingExecutionRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    requester: str = Field(..., min_length=1)
    provider: str = Field(default="provider_agnostic", min_length=1, max_length=80)
    base_model: str | None = Field(default=None, max_length=120)
    notes: str = ""
    start_training: bool = False
    upload_dataset: bool = False
    call_provider_api: bool = False


class DocumentOpsTrainingAuditExportRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    auditor: str = Field(..., min_length=1)
    provider: str = Field(default="provider_agnostic", min_length=1, max_length=80)
    base_model: str | None = Field(default=None, max_length=120)
    notes: str = ""
    start_training: bool = False
    upload_dataset: bool = False
    call_provider_api: bool = False
