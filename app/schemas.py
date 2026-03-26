from dataclasses import dataclass, field as dc_field
from enum import Enum
from typing import Any, Literal

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


class GeneratedDoc(BaseModel):
    doc_type: str  # str (not DocType enum) — supports all bundle types
    markdown: str


class GenerateResponse(BaseModel):
    request_id: str
    bundle_id: str
    title: str
    provider: str
    schema_version: str
    cache_hit: bool | None = None
    llm_total_tokens: int | None = None
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


class EditedDocInput(BaseModel):
    """One user-edited document section for /generate/export-edited."""

    doc_type: str
    markdown: str


@dataclass
class GovDocOptions:
    """행안부 공문서 표준 서식 옵션.

    모든 필드는 선택사항이며 기본값을 가집니다.
    ``is_government_format=True`` 로 설정 시 공문서 헤더 블록과 결재란이 추가됩니다.
    """

    # 공문서 메타데이터
    doc_number: str = ""          # 문서번호 (예: "행정안전부-1234")
    recipient: str = ""           # 수신 (예: "수신자 참조")
    via: str = ""                 # 경유
    classification: str = ""      # 보안 등급 (예: "대외비", "비밀")
    org_name: str = ""            # 발신기관명 (예: "행정안전부")
    dept_name: str = ""           # 부서명
    contact: str = ""             # 담당자 연락처
    attachments: list[str] = dc_field(default_factory=list)  # 붙임 목록

    # 결재란
    drafter: str = ""             # 기안자
    reviewer: str = ""            # 검토자
    approver: str = ""            # 결재자

    # 페이지 레이아웃 (행안부 표준 기본값)
    top_margin_mm: int = 30       # 위 여백 (행안부 표준: 30mm)
    bottom_margin_mm: int = 15    # 아래 여백 (행안부 표준: 15mm)
    left_margin_mm: int = 20      # 좌 여백 (행안부 표준: 20mm)
    right_margin_mm: int = 20     # 우 여백 (행안부 표준: 20mm)

    # 글꼴 설정
    font_name: str = "맑은 고딕"   # 한글 폰트 (행안부 표준: 맑은 고딕)
    font_size_pt: float = 10.5    # 글자 크기 (행안부 표준: 10.5pt)
    line_spacing_pct: int = 160   # 줄간격 % (행안부 표준: 160%)

    # 플래그
    is_government_format: bool = False  # 공문서 표준 서식 적용 여부


class EditedExportRequest(BaseModel):
    """Payload for POST /generate/export-edited — export pre-rendered (possibly
    user-edited) docs without re-running LLM generation."""

    bundle_id: str = ""
    title: str = "문서"
    format: str  # "docx" | "pdf" | "excel" | "hwp"
    docs: list[EditedDocInput]
    gov_options: dict | None = None  # serialized GovDocOptions fields


class CreateApprovalRequest(BaseModel):
    """Payload for POST /approvals — start an approval workflow."""
    request_id: str = ""
    bundle_id: str = ""
    title: str
    drafter: str
    docs: list[dict] = Field(default_factory=list)
    gov_options: dict | None = None


class ApprovalActionRequest(BaseModel):
    """Payload for approval action endpoints (submit, review, approve, reject)."""
    username: str
    comment: str = ""
    reviewer: str | None = None   # used in submit_for_review
    approver: str | None = None   # used in approve_review → sets approver


class UpdateApprovalDocsRequest(BaseModel):
    """Payload for PUT /approvals/{id}/docs — update docs after revision."""
    username: str
    docs: list[dict] = Field(default_factory=list)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    client: str = ""
    contract_number: str = ""
    fiscal_year: int = Field(default_factory=lambda: __import__('datetime').datetime.now().year)

class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    client: str | None = None
    contract_number: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    fiscal_year: int | None = None

class AddDocumentToProjectRequest(BaseModel):
    request_id: str = ""
    bundle_id: str = ""
    title: str = ""
    docs: list[dict] = Field(default_factory=list)
    approval_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class ImportVoiceBriefDocumentRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    recording_id: str = Field(..., min_length=1)
    revision_id: str | None = Field(default=None, min_length=1)


class G2BFetchRequest(BaseModel):
    """Payload for POST /g2b/fetch — fetch a G2B announcement by URL or bid number."""

    url_or_number: str  # G2B URL or bid announcement number (e.g. "20250317001-00")


class ImportProjectProcurementOpportunityRequest(BaseModel):
    """Payload for project-scoped procurement opportunity attachment/import."""

    model_config = ConfigDict(strict=True, extra="forbid")

    url_or_number: str = Field(..., min_length=1)
    parsed_rfp_fields: dict[str, Any] | None = None
    structured_context: str = ""
    notes: str = ""


class ProcurementRecommendationValue(str, Enum):
    GO = "GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    NO_GO = "NO_GO"


class ProcurementHardFilterStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class ProcurementScoreStatus(str, Enum):
    SCORED = "scored"
    INSUFFICIENT_DATA = "insufficient_data"


class ProcurementChecklistStatus(str, Enum):
    READY = "ready"
    ACTION_NEEDED = "action_needed"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class ProcurementChecklistSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NormalizedProcurementOpportunity(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    source_kind: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    source_url: str = ""
    title: str = Field(..., min_length=1)
    issuer: str = ""
    budget: str = ""
    deadline: str = ""
    bid_type: str = ""
    category: str = ""
    region: str = ""
    raw_text_preview: str = ""


class CapabilityProfileReference(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    source_kind: str = Field(..., min_length=1)
    source_ref: str = Field(..., min_length=1)
    title: str = ""
    summary: str = ""
    document_ids: list[str] = Field(default_factory=list)


class ProcurementHardFilterResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    code: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    status: Literal["pass", "fail", "unknown"]
    blocking: bool = False
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)


class ProcurementScoreBreakdownItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    score: float = Field(..., ge=0.0, le=100.0)
    weight: float = Field(..., ge=0.0, le=1.0)
    weighted_score: float = Field(..., ge=0.0, le=100.0)
    status: Literal["scored", "insufficient_data"] = ProcurementScoreStatus.SCORED
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)


class ProcurementChecklistItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    category: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    status: Literal["ready", "action_needed", "blocked", "unknown"]
    severity: Literal["critical", "high", "medium", "low"]
    evidence: str = ""
    remediation_note: str = ""
    owner: str | None = None
    due_date: str | None = None


class ProcurementRecommendation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    value: Literal["GO", "CONDITIONAL_GO", "NO_GO"]
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    remediation_notes: list[str] = Field(default_factory=list)
    decided_at: str | None = None


class ProcurementSourceSnapshotMetadata(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    snapshot_id: str = Field(..., min_length=1)
    source_kind: str = Field(..., min_length=1)
    source_label: str = ""
    external_id: str = ""
    captured_at: str = Field(..., min_length=1)
    storage_path: str = Field(..., min_length=1)
    content_type: str = "application/json"


class ProcurementDecisionUpsert(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    project_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    schema_version: str = Field(default="v1", min_length=1)
    opportunity: NormalizedProcurementOpportunity | None = None
    capability_profile: CapabilityProfileReference | None = None
    hard_filters: list[ProcurementHardFilterResult] = Field(default_factory=list)
    score_breakdown: list[ProcurementScoreBreakdownItem] = Field(default_factory=list)
    soft_fit_score: float | None = Field(default=None, ge=0.0, le=100.0)
    soft_fit_status: Literal["scored", "insufficient_data"] = ProcurementScoreStatus.INSUFFICIENT_DATA
    missing_data: list[str] = Field(default_factory=list)
    checklist_items: list[ProcurementChecklistItem] = Field(default_factory=list)
    recommendation: ProcurementRecommendation | None = None
    source_snapshots: list[ProcurementSourceSnapshotMetadata] = Field(default_factory=list)
    notes: str = ""


class ProcurementDecisionRecord(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    decision_id: str = Field(..., min_length=1)
    project_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    schema_version: str = Field(default="v1", min_length=1)
    created_at: str = Field(..., min_length=1)
    updated_at: str = Field(..., min_length=1)
    opportunity: NormalizedProcurementOpportunity | None = None
    capability_profile: CapabilityProfileReference | None = None
    hard_filters: list[ProcurementHardFilterResult] = Field(default_factory=list)
    score_breakdown: list[ProcurementScoreBreakdownItem] = Field(default_factory=list)
    soft_fit_score: float | None = Field(default=None, ge=0.0, le=100.0)
    soft_fit_status: Literal["scored", "insufficient_data"] = ProcurementScoreStatus.INSUFFICIENT_DATA
    missing_data: list[str] = Field(default_factory=list)
    checklist_items: list[ProcurementChecklistItem] = Field(default_factory=list)
    recommendation: ProcurementRecommendation | None = None
    source_snapshots: list[ProcurementSourceSnapshotMetadata] = Field(default_factory=list)
    notes: str = ""


# ── Auth schemas ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    display_name: str
    email: str
    password: str
    role: str = "member"


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None


# ── Message schemas ────────────────────────────────────────────────────────────

class PostMessageRequest(BaseModel):
    content: str
    context_type: str = "general"
    context_id: str = "global"


class EditMessageRequest(BaseModel):
    content: str


class CreateStyleProfileRequest(BaseModel):
    name: str
    description: str = ""


class UpdateToneGuideRequest(BaseModel):
    formality: str = ""
    density: str = ""
    perspective: str = ""
    custom_rules: list[str] = []
    forbidden_words: list[str] = []
    preferred_words: list[str] = []


class OpsInvestigateRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    window_minutes: int = Field(default=30, ge=1, le=180)
    reason: str = Field(default="", max_length=200)
    stage: Literal["dev", "prod"] | None = None
    force: bool = False
    notify: bool = True


class OpsInvestigateResponse(BaseModel):
    incident_id: str
    summary: dict[str, Any]
    statuspage_incident_url: str | None = None
    report_s3_key: str
    report_md_key: str | None = None
    incident_key: str = ""
    deduped: bool = False
    statuspage_posted: bool | None = None
    statuspage_skipped: bool | None = None
    statuspage_error: str | None = None
    report_json_key: str | None = None  # deprecated: identical to report_s3_key


class CheckoutRequest(BaseModel):
    plan_id: str


class PlanOverrideRequest(BaseModel):
    plan_id: str
    reason: str = ""


class WithdrawRequest(BaseModel):
    password: str
    reason: str = ""


class CreateShareRequest(BaseModel):
    request_id: str
    title: str
    bundle_id: str = ""
    expires_days: int = 7


class InviteUserRequest(BaseModel):
    email: str = ""
    role: str = "member"
    send_email: bool = False


class AcceptInviteRequest(BaseModel):
    username: str
    display_name: str
    password: str
