"""Core /generate request/response schemas: DocType, GenerateRequest, feedback, errors."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocType(str, Enum):
    adr = "adr"
    onepager = "onepager"
    eval_plan = "eval_plan"
    ops_checklist = "ops_checklist"


def default_doc_types() -> list[DocType]:
    return [
        DocType.adr,
        DocType.onepager,
        DocType.eval_plan,
        DocType.ops_checklist,
    ]


class GenerateRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1)
    goal: str = Field(..., min_length=1)
    context: str = ""
    constraints: str = ""
    priority: str = "maintainability > security > cost > performance > speed"
    doc_types: list[DocType] = Field(default_factory=default_doc_types, min_length=1)
    audience: str = "mixed"
    timeline: str = ""        # 예: "3개월", "2025 Q3까지"
    budget_range: str = ""    # 예: "5억 이하", "$500K"
    team_size: str = ""       # 예: "5명 스타트업", "50명 엔지니어링팀"
    industry: str = ""        # 예: "헬스케어", "핀테크", "교육"
    assumptions: list[str] = Field(default_factory=list)
    bundle_type: str = Field(default="tech_decision", min_length=1)
    doc_tone: str = Field(default="formal", description="문서 톤: formal|concise|detailed|executive")
    project_id: str | None = None  # optional project linkage
    style_profile_id: str | None = None  # optional style profile chosen in the Web UI

    @field_validator("doc_types", mode="before")
    @classmethod
    def parse_doc_types(cls, value):
        if value is None:
            return value
        if not isinstance(value, list):
            return value
        return [DocType(item) if isinstance(item, str) else item for item in value]


class FreeformRequest(BaseModel):
    """Payload for POST /generate/freeform — unmatched request recording.

    No bundle_id required; the request is logged for pattern analysis
    and potential future auto-bundle expansion.
    """

    title: str = ""
    goal: str = ""
    context: str = ""


class HealthResponse(BaseModel):
    status: str
    provider: str
    maintenance: bool | None = None
    checks: dict[str, str] | None = None
    provider_routes: dict[str, str] | None = None
    provider_route_checks: dict[str, str] | None = None
    provider_policy_checks: dict[str, str] | None = None
    provider_policy_issues: dict[str, list[str]] | None = None


class GeneratedDoc(BaseModel):
    doc_type: str  # str (not DocType enum) — supports all bundle types
    markdown: str
    total_slides: int | None = None
    slide_outline: list[dict[str, Any]] | None = None


class GenerateResponse(BaseModel):
    request_id: str
    bundle_id: str
    title: str
    provider: str
    schema_version: str
    cache_hit: bool | None = None
    llm_total_tokens: int | None = None
    applied_references: list[dict[str, Any]] = Field(default_factory=list)
    docs: list[GeneratedDoc]


class ExportedFile(BaseModel):
    doc_type: str  # str (not DocType enum) — supports all bundle types
    path: str


class GenerateExportResponse(BaseModel):
    request_id: str
    bundle_id: str
    title: str
    provider: str
    schema_version: str
    cache_hit: bool | None = None
    export_dir: str
    files: list[ExportedFile]


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    bundle_id: str = Field(..., min_length=1)
    bundle_type: str = Field(..., min_length=1)
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(default="", max_length=500)
    docs: list[dict] = Field(default_factory=list)
    request_id: str = ""


class FeedbackResponse(BaseModel):
    feedback_id: str
    saved: bool


class ErrorResponse(BaseModel):
    code: str
    message: str
    request_id: str
    errors: list[str] | None = None


class SectionRewriteRequest(BaseModel):
    """Payload for POST /generate/rewrite-section — AI-assisted single-section rewrite."""

    bundle_id: str
    section_title: str
    current_content: str
    instruction: str
