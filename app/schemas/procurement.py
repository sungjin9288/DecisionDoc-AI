"""Public-procurement opportunity, Decision Council, and decision-record schemas."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _coerce_enum(value, enum_cls):
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        return enum_cls(value)
    return value


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
