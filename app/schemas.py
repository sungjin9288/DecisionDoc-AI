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


def _coerce_enum(value, enum_cls):
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        return enum_cls(value)
    return value


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


class EditedDocInput(BaseModel):
    """One user-edited document section for /generate/export-edited."""

    model_config = ConfigDict(strict=True, extra="forbid")

    doc_type: str
    markdown: str
    total_slides: int | None = None
    slide_outline: list[dict[str, Any]] = Field(default_factory=list)


class VisualAssetDocInput(BaseModel):
    """Slide-aware document payload for visual asset generation."""

    model_config = ConfigDict(strict=True, extra="forbid")

    doc_type: str
    markdown: str = ""
    total_slides: int | None = None
    slide_outline: list[dict[str, Any]] = Field(default_factory=list)


class GeneratedVisualAsset(BaseModel):
    asset_id: str
    doc_type: str
    slide_title: str
    visual_type: str = ""
    visual_brief: str = ""
    layout_hint: str = ""
    source_kind: str
    source_model: str = ""
    prompt: str = ""
    media_type: str
    encoding: Literal["base64"] = "base64"
    content_base64: str


class GenerateVisualAssetsRequest(BaseModel):
    """Payload for POST /generate/visual-assets."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1)
    goal: str = ""
    bundle_type: str = Field(default="tech_decision", min_length=1)
    docs: list[VisualAssetDocInput] = Field(default_factory=list, min_length=1)
    max_assets: int = Field(default=6, ge=1, le=12)


class GenerateVisualAssetsResponse(BaseModel):
    title: str
    bundle_type: str
    count: int
    assets: list[GeneratedVisualAsset]


class UpdateHistoryVisualAssetsRequest(BaseModel):
    """Payload for persisting generated visual asset snapshots onto history entries."""

    model_config = ConfigDict(strict=True, extra="forbid")

    visual_assets: list[GeneratedVisualAsset] = Field(default_factory=list, max_length=12)


class PromoteKnowledgeReferenceRequest(BaseModel):
    """Promote approved generated docs into project knowledge as gold references."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1)
    bundle_type: str = Field(..., min_length=1)
    docs: list[EditedDocInput] = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)
    quality_tier: str = "gold"
    success_state: str = "approved"
    source_organization: str = ""
    reference_year: int | None = None
    notes: str = ""
    source_bundle_id: str = ""
    source_request_id: str = ""


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
    bundle_type: str = "tech_decision"
    title: str = "문서"
    format: str  # "docx" | "pdf" | "excel" | "hwp"
    docs: list[EditedDocInput]
    visual_assets: list[GeneratedVisualAsset] = Field(default_factory=list)
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


class CreateReportWorkflowRequest(BaseModel):
    """Payload for POST /report-workflows."""

    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(..., min_length=1)
    goal: str = ""
    client: str = ""
    report_type: str = "proposal_presentation"
    audience: str = ""
    owner: str = ""
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


class ImportVoiceBriefDocumentRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    recording_id: str = Field(..., min_length=1)
    revision_id: str | None = Field(default=None, min_length=1)


class TranscribeMeetingRecordingRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    language: str | None = Field(default=None, min_length=2, max_length=16)


class GenerateMeetingRecordingDocumentsRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    bundle_types: list[str] = Field(
        default_factory=lambda: ["meeting_minutes_kr", "project_report_kr"],
        min_length=1,
    )
    context_note: str = ""


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


class UpdateProjectProcurementOverrideReasonRequest(BaseModel):
    """Payload for project-scoped override / disagreement note capture."""

    model_config = ConfigDict(strict=True, extra="forbid")

    reason: str = Field(..., min_length=1, max_length=4000)


class RecordProjectProcurementRemediationLinkCopyRequest(BaseModel):
    """Payload for recording procurement remediation-link handoff activity."""

    model_config = ConfigDict(strict=True, extra="forbid")

    source: Literal["project_detail", "location_summary"]
    context_kind: Literal["blocked_event", "override_candidate", "recent_event"]
    bundle_type: str = ""
    error_code: str = ""
    recommendation: str = ""


class RecordProjectProcurementRemediationLinkOpenRequest(BaseModel):
    """Payload for recording procurement remediation-link open activity."""

    model_config = ConfigDict(strict=True, extra="forbid")

    source: Literal["url_restore"]
    context_kind: Literal["blocked_event", "override_candidate", "recent_event"]
    bundle_type: str = ""
    error_code: str = ""
    recommendation: str = ""


class DecisionCouncilRunRequest(BaseModel):
    """Payload for running the procurement-scoped Decision Council thin slice."""

    model_config = ConfigDict(strict=True, extra="forbid")

    goal: str = Field(..., min_length=1, max_length=2000)
    context: str = Field(default="", max_length=8000)
    constraints: str = Field(default="", max_length=4000)


class DecisionCouncilRoleOpinion(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    role: Literal[
        "Requirement Analyst",
        "Risk Reviewer",
        "Domain Strategist",
        "Compliance Reviewer",
        "Drafting Lead",
    ]
    stance: Literal["support", "caution", "block"]
    summary: str = Field(..., min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)


class DecisionCouncilConsensus(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    alignment: Literal["aligned", "mixed", "contested"]
    recommended_direction: Literal["proceed", "proceed_with_conditions", "do_not_proceed"]
    summary: str = Field(..., min_length=1)
    strategy_options: list[str] = Field(default_factory=list)
    disagreements: list[str] = Field(default_factory=list)
    top_risks: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class DecisionCouncilHandoff(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    target_bundle_type: Literal["bid_decision_kr"]
    recommended_direction: Literal["proceed", "proceed_with_conditions", "do_not_proceed"]
    drafting_brief: str = Field(..., min_length=1)
    must_include: list[str] = Field(default_factory=list)
    must_address: list[str] = Field(default_factory=list)
    must_not_claim: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    source_procurement_decision_id: str = Field(..., min_length=1)


class DecisionCouncilSessionResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    session_id: str = Field(..., min_length=1)
    session_key: str = Field(..., min_length=1)
    session_revision: int = Field(default=1, ge=1)
    tenant_id: str = Field(..., min_length=1)
    project_id: str = Field(..., min_length=1)
    use_case: Literal["public_procurement"]
    target_bundle_type: Literal["bid_decision_kr"]
    supported_bundle_types: list[Literal["bid_decision_kr", "proposal_kr"]] = Field(
        default_factory=lambda: ["bid_decision_kr", "proposal_kr"],
        min_length=1,
    )
    goal: str = Field(..., min_length=1)
    context: str = ""
    constraints: str = ""
    source_procurement_decision_id: str = Field(..., min_length=1)
    source_procurement_updated_at: str = ""
    source_procurement_recommendation_value: str = ""
    source_procurement_missing_data_count: int = 0
    source_procurement_action_needed_count: int = 0
    source_procurement_blocking_hard_filter_count: int = 0
    source_snapshot_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(..., min_length=1)
    updated_at: str = Field(..., min_length=1)
    operation: Literal["created", "updated"] | None = None
    current_procurement_binding_status: Literal["current", "stale"] = "current"
    current_procurement_binding_reason_code: str = ""
    current_procurement_binding_summary: str = ""
    current_procurement_updated_at: str = ""
    current_procurement_recommendation_value: str = ""
    current_procurement_missing_data_count: int = 0
    current_procurement_action_needed_count: int = 0
    current_procurement_blocking_hard_filter_count: int = 0
    role_opinions: list[DecisionCouncilRoleOpinion] = Field(default_factory=list, min_length=1)
    disagreements: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    consensus: DecisionCouncilConsensus
    handoff: DecisionCouncilHandoff


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
    status: ProcurementHardFilterStatus
    blocking: bool = False
    reason: str = ""
    evidence: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value):
        return _coerce_enum(value, ProcurementHardFilterStatus)


class ProcurementScoreBreakdownItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    score: float = Field(..., ge=0.0, le=100.0)
    weight: float = Field(..., ge=0.0, le=1.0)
    weighted_score: float = Field(..., ge=0.0, le=100.0)
    status: ProcurementScoreStatus = ProcurementScoreStatus.SCORED
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value):
        return _coerce_enum(value, ProcurementScoreStatus)


class ProcurementChecklistItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    category: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    status: ProcurementChecklistStatus
    severity: ProcurementChecklistSeverity
    evidence: str = ""
    remediation_note: str = ""
    owner: str | None = None
    due_date: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value):
        return _coerce_enum(value, ProcurementChecklistStatus)

    @field_validator("severity", mode="before")
    @classmethod
    def parse_severity(cls, value):
        return _coerce_enum(value, ProcurementChecklistSeverity)


class ProcurementRecommendation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    value: ProcurementRecommendationValue
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    remediation_notes: list[str] = Field(default_factory=list)
    decided_at: str | None = None

    @field_validator("value", mode="before")
    @classmethod
    def parse_value(cls, value):
        return _coerce_enum(value, ProcurementRecommendationValue)


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
    soft_fit_status: ProcurementScoreStatus = ProcurementScoreStatus.INSUFFICIENT_DATA
    missing_data: list[str] = Field(default_factory=list)
    checklist_items: list[ProcurementChecklistItem] = Field(default_factory=list)
    recommendation: ProcurementRecommendation | None = None
    source_snapshots: list[ProcurementSourceSnapshotMetadata] = Field(default_factory=list)
    notes: str = ""

    @field_validator("soft_fit_status", mode="before")
    @classmethod
    def parse_soft_fit_status(cls, value):
        return _coerce_enum(value, ProcurementScoreStatus)


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
    soft_fit_status: ProcurementScoreStatus = ProcurementScoreStatus.INSUFFICIENT_DATA
    missing_data: list[str] = Field(default_factory=list)
    checklist_items: list[ProcurementChecklistItem] = Field(default_factory=list)
    recommendation: ProcurementRecommendation | None = None
    source_snapshots: list[ProcurementSourceSnapshotMetadata] = Field(default_factory=list)
    notes: str = ""

    @field_validator("soft_fit_status", mode="before")
    @classmethod
    def parse_soft_fit_status(cls, value):
        return _coerce_enum(value, ProcurementScoreStatus)


# ── Auth schemas ───────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UpdateMyProfileRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None


class CreateUserRequest(BaseModel):
    username: str
    display_name: str
    email: str
    password: str
    role: str = "member"
    job_title: str = ""
    assigned_ai_profiles: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    role: str | None = None
    is_active: bool | None = None
    job_title: str | None = None
    assigned_ai_profiles: list[str] | None = None


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


class UpdateKnowledgeMetadataRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    tags: list[str] | None = None
    learning_mode: str | None = None
    quality_tier: str | None = None
    applicable_bundles: list[str] | None = None
    source_organization: str | None = None
    reference_year: int | None = None
    success_state: str | None = None
    notes: str | None = None


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


class PostDeployReportSummary(BaseModel):
    file: str
    status: str
    base_url: str
    started_at: str
    finished_at: str
    skip_smoke: bool = False
    error: str | None = None
    provider_routes: dict[str, str] | None = None
    provider_route_checks: dict[str, str] | None = None
    provider_policy_checks: dict[str, str] | None = None
    provider_policy_issues: dict[str, list[str]] | None = None
    smoke_response_code: str | None = None
    provider_error_code: str | None = None
    smoke_message: str | None = None
    retry_after_seconds: int | None = None
    smoke_exception_type: str | None = None
    smoke_results_available: bool = False
    smoke_results: list[str] = Field(default_factory=list)


class PostDeployReportCheck(BaseModel):
    name: str
    status: str
    exit_code: int | None = None
    smoke_response_code: str | None = None
    provider_error_code: str | None = None
    smoke_message: str | None = None
    retry_after_seconds: int | None = None
    smoke_exception_type: str | None = None
    failure_line: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    smoke_results_available: bool = False
    smoke_results: list[str] = Field(default_factory=list)


class PostDeployLatestDetailsResponse(BaseModel):
    status: str
    base_url: str = "-"
    started_at: str = "-"
    finished_at: str = "-"
    skip_smoke: bool = False
    error: str | None = None
    checks: list[PostDeployReportCheck] = Field(default_factory=list)
    provider_routes: dict[str, str] | None = None
    provider_route_checks: dict[str, str] | None = None
    provider_policy_checks: dict[str, str] | None = None
    provider_policy_issues: dict[str, list[str]] | None = None
    smoke_response_code: str | None = None
    provider_error_code: str | None = None
    smoke_message: str | None = None
    retry_after_seconds: int | None = None
    smoke_exception_type: str | None = None
    smoke_results_available: bool = False
    smoke_results: list[str] = Field(default_factory=list)


class OpsPostDeployReportsResponse(BaseModel):
    report_dir: str
    index_file: str
    latest_report: str
    updated_at: str
    reports: list[PostDeployReportSummary]
    latest_details: PostDeployLatestDetailsResponse | None = None


class OpsPostDeployReportDetailResponse(BaseModel):
    report_dir: str
    report_file: str
    report_path: str
    details: dict[str, Any]


class OpsPostDeployRunRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    skip_smoke: bool = False


class OpsPostDeployRunResponse(BaseModel):
    run_id: str
    status: str
    exit_code: int | None = None
    started_at: str
    finished_at: str
    report_dir: str
    report_file: str | None = None
    report_path: str | None = None
    stdout_tail: list[str] = Field(default_factory=list)
    stderr_tail: list[str] = Field(default_factory=list)
    command: str | None = None


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
    project_id: str = ""
    project_document_id: str = ""
    decision_council_document_status: str = ""
    decision_council_document_status_tone: str = ""
    decision_council_document_status_copy: str = ""
    decision_council_document_status_summary: str = ""


class InviteUserRequest(BaseModel):
    tenant_id: str | None = None
    email: str = ""
    role: str = "member"
    send_email: bool = False
    job_title: str = ""
    assigned_ai_profiles: list[str] = Field(default_factory=list)


class AcceptInviteRequest(BaseModel):
    username: str
    display_name: str
    password: str
