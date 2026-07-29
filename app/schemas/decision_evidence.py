"""Read-only response models for the project Decision Evidence Map."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


EvidenceNodeType = Literal[
    "source",
    "claim",
    "requirement",
    "alternative",
    "risk",
    "recommendation",
    "document",
    "review",
    "approval",
    "export",
]
CoverageStatus = Literal["explicit", "candidate", "missing", "unverifiable"]
EvidenceLevel = Literal["authoritative", "record_binding", "derived"]
DecisionEvidenceBundleType = Literal[
    "bid_decision_kr",
    "rfp_analysis_kr",
    "proposal_kr",
    "performance_plan_kr",
]


class DecisionEvidenceSourceRevision(_StrictModel):
    source_kind: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    revision: str = ""
    content_sha256: str = Field(min_length=1)


class DecisionEvidenceNode(_StrictModel):
    node_id: str = Field(min_length=1)
    node_type: EvidenceNodeType
    label: str = Field(min_length=1)
    status: str = Field(min_length=1)
    summary: str = ""
    updated_at: str = ""
    relation_count: int = Field(default=0, ge=0)
    evidence_level: EvidenceLevel
    coverage_status: CoverageStatus | None = None
    diagnostic_codes: list[str] = Field(default_factory=list)
    actual_export_observed: bool = False


class DecisionEvidenceProvenance(_StrictModel):
    source_kind: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_revision: str = ""
    field_path: str = Field(min_length=1)
    content_sha256: str = Field(min_length=1)
    evidence_level: EvidenceLevel


class DecisionEvidenceEdge(_StrictModel):
    edge_id: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    source_node_id: str = Field(min_length=1)
    target_node_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    provenance: DecisionEvidenceProvenance


class DecisionEvidenceCoverageItem(_StrictModel):
    requirement_node_id: str = Field(min_length=1)
    status: CoverageStatus
    summary: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class DecisionEvidenceCoverageSummary(_StrictModel):
    total: int = Field(ge=0)
    explicit: int = Field(ge=0)
    candidate: int = Field(ge=0)
    missing: int = Field(ge=0)
    unverifiable: int = Field(ge=0)
    items: list[DecisionEvidenceCoverageItem] = Field(default_factory=list)


class DecisionEvidenceDiagnostic(_StrictModel):
    code: str = Field(min_length=1)
    severity: Literal["info", "warning", "error"]
    message: str = Field(min_length=1)
    node_ids: list[str] = Field(default_factory=list)
    next_action: str = ""


class DecisionEvidenceLimits(_StrictModel):
    max_nodes: int = Field(default=200, ge=1)
    max_edges: int = Field(default=400, ge=1)


class DecisionEvidenceProposalSlide(_StrictModel):
    slide_id: str = Field(min_length=1)
    title: str = ""
    status: str = ""
    source_refs: list[str] = Field(default_factory=list)
    reference_refs: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    data_needs: list[str] = Field(default_factory=list)


class DecisionEvidenceProposalBlueprint(_StrictModel):
    status: str = Field(min_length=1)
    report_workflow_id: str | None = None
    workflow_status: str = ""
    narrative_arc: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    slides: list[DecisionEvidenceProposalSlide] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    actual_export_observed: Literal[False] = False


class DecisionEvidenceAuthority(_StrictModel):
    mutation: Literal[False] = False
    approval: Literal[False] = False
    export_execution: Literal[False] = False
    provider_call: Literal[False] = False
    bid_submission: Literal[False] = False
    legal_contractual_commitment: Literal[False] = False


class DecisionEvidenceMapResponse(_StrictModel):
    contract_version: Literal["decision_evidence_map.v1"] = "decision_evidence_map.v1"
    generated_at: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    bundle_type: DecisionEvidenceBundleType
    read_only: Literal[True] = True
    snapshot_atomic: Literal[False] = False
    projection_fingerprint: str = Field(min_length=1)
    source_revisions: list[DecisionEvidenceSourceRevision] = Field(default_factory=list)
    nodes: list[DecisionEvidenceNode] = Field(default_factory=list)
    edges: list[DecisionEvidenceEdge] = Field(default_factory=list)
    coverage: DecisionEvidenceCoverageSummary
    diagnostics: list[DecisionEvidenceDiagnostic] = Field(default_factory=list)
    limits: DecisionEvidenceLimits = Field(default_factory=DecisionEvidenceLimits)
    truncated: bool = False
    proposal_blueprint: DecisionEvidenceProposalBlueprint
    authority: DecisionEvidenceAuthority = Field(default_factory=DecisionEvidenceAuthority)


GuidedDecisionReviewStageName = Literal[
    "Decision",
    "Evidence",
    "Review",
    "Documents",
]
GuidedDecisionReviewStageStatus = Literal[
    "not_observed",
    "needs_attention",
    "in_review",
    "observed",
]


class GuidedDecisionReviewStage(_StrictModel):
    name: GuidedDecisionReviewStageName
    status: GuidedDecisionReviewStageStatus
    evidence: str = Field(min_length=1)


class GuidedDecisionReviewNextCheck(_StrictModel):
    stage: GuidedDecisionReviewStageName
    instruction: str = Field(min_length=1)


class GuidedDecisionReviewHandoffResponse(_StrictModel):
    contract_version: Literal["guided-decision-review-handoff.v1"] = (
        "guided-decision-review-handoff.v1"
    )
    source_contract_version: Literal["decision_evidence_map.v1"] = (
        "decision_evidence_map.v1"
    )
    source_generated_at: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    bundle_type: DecisionEvidenceBundleType
    projection_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    read_only: Literal[True] = True
    snapshot_atomic: Literal[False] = False
    requires_recheck_before_reliance: Literal[True] = True
    handoff_persisted: Literal[False] = False
    overall_state: Literal[
        "Needs review",
        "Review in progress",
        "No blocking signal observed",
    ]
    recommended_next_check: GuidedDecisionReviewNextCheck
    stages: list[GuidedDecisionReviewStage] = Field(min_length=4, max_length=4)
    authority: DecisionEvidenceAuthority = Field(default_factory=DecisionEvidenceAuthority)

    @model_validator(mode="after")
    def validate_stage_order(self) -> "GuidedDecisionReviewHandoffResponse":
        expected = ["Decision", "Evidence", "Review", "Documents"]
        if [stage.name for stage in self.stages] != expected:
            raise ValueError("guided decision review stages must use the canonical order")
        return self


def _require_explicit_fields(model: BaseModel, label: str) -> None:
    missing = set(type(model).model_fields) - model.model_fields_set
    if missing:
        raise ValueError(f"{label} is missing required contract fields")


def require_complete_guided_decision_review_handoff(
    handoff: GuidedDecisionReviewHandoffResponse,
    label: str,
) -> None:
    _require_explicit_fields(handoff, label)
    _require_explicit_fields(handoff.recommended_next_check, f"{label}.next_check")
    _require_explicit_fields(handoff.authority, f"{label}.authority")
    for index, stage in enumerate(handoff.stages):
        _require_explicit_fields(stage, f"{label}.stages[{index}]")


def require_complete_guided_decision_review_recheck_receipt(
    receipt: GuidedDecisionReviewRecheckReceipt,
    label: str = "source_recheck_receipt",
) -> None:
    _require_explicit_fields(receipt, label)
    _require_explicit_fields(receipt.authority, f"{label}.authority")
    require_complete_guided_decision_review_handoff(
        receipt.source_handoff,
        f"{label}.source_handoff",
    )
    require_complete_guided_decision_review_handoff(
        receipt.current_handoff,
        f"{label}.current_handoff",
    )


class GuidedDecisionReviewRecheckRequest(_StrictModel):
    contract_version: Literal["guided-decision-review-recheck-request.v1"]
    source_handoff: GuidedDecisionReviewHandoffResponse
    source_handoff_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def require_complete_source_handoff(
        self,
    ) -> "GuidedDecisionReviewRecheckRequest":
        require_complete_guided_decision_review_handoff(
            self.source_handoff,
            "source_handoff",
        )
        return self


class GuidedDecisionReviewRecheckReceipt(_StrictModel):
    contract_version: Literal["guided-decision-review-recheck-receipt.v1"] = (
        "guided-decision-review-recheck-receipt.v1"
    )
    source_handoff: GuidedDecisionReviewHandoffResponse
    source_handoff_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    current_handoff: GuidedDecisionReviewHandoffResponse
    current_handoff_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_review_state_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    current_review_state_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_state_status: Literal["unchanged", "changed"]
    fingerprint_algorithm: Literal["sha256"] = "sha256"
    volatile_fields_excluded: list[Literal["source_generated_at"]] = Field(
        default_factory=lambda: ["source_generated_at"],
    )
    review_state_only: Literal[True] = True
    review_only: Literal[True] = True
    read_only: Literal[True] = True
    snapshot_atomic: Literal[False] = False
    requires_recheck_before_reliance: Literal[True] = True
    recheck_persisted: Literal[False] = False
    authority: DecisionEvidenceAuthority = Field(default_factory=DecisionEvidenceAuthority)

    @model_validator(mode="after")
    def validate_volatile_fields(self) -> "GuidedDecisionReviewRecheckReceipt":
        if self.volatile_fields_excluded != ["source_generated_at"]:
            raise ValueError(
                "guided decision review recheck must exclude only source_generated_at"
            )
        return self


class GuidedDecisionReviewDispositionRequest(_StrictModel):
    contract_version: Literal[
        "guided-decision-review-disposition-request.v1"
    ]
    source_recheck_receipt: GuidedDecisionReviewRecheckReceipt
    source_recheck_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_disposition: Literal[
        "acknowledged_unchanged",
        "new_handoff_required",
        "review_deferred",
    ]

    @model_validator(mode="after")
    def require_complete_source_receipt(
        self,
    ) -> "GuidedDecisionReviewDispositionRequest":
        require_complete_guided_decision_review_recheck_receipt(
            self.source_recheck_receipt,
        )
        return self


class GuidedDecisionReviewDispositionReceipt(_StrictModel):
    contract_version: Literal[
        "guided-decision-review-disposition-receipt.v1"
    ] = "guided-decision-review-disposition-receipt.v1"
    project_id: str = Field(min_length=1)
    bundle_type: DecisionEvidenceBundleType
    source_recheck_receipt: GuidedDecisionReviewRecheckReceipt
    source_recheck_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    current_handoff_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    current_review_state_fingerprint_sha256: str = Field(
        pattern=r"^[a-f0-9]{64}$"
    )
    review_state_status: Literal["unchanged", "changed"]
    review_disposition: Literal[
        "acknowledged_unchanged",
        "new_handoff_required",
        "review_deferred",
    ]
    disposition_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_status: Literal["issued"] = "issued"
    review_state_only: Literal[True] = True
    review_only: Literal[True] = True
    read_only: Literal[True] = True
    reviewer_identity_bound: Literal[False] = False
    snapshot_atomic: Literal[False] = False
    requires_recheck_before_reliance: Literal[True] = True
    disposition_receipt_persisted: Literal[False] = False
    authority: DecisionEvidenceAuthority = Field(
        default_factory=DecisionEvidenceAuthority
    )

    @model_validator(mode="after")
    def validate_disposition_matrix(
        self,
    ) -> "GuidedDecisionReviewDispositionReceipt":
        allowed = {
            "unchanged": {"acknowledged_unchanged", "review_deferred"},
            "changed": {"new_handoff_required", "review_deferred"},
        }
        if self.review_disposition not in allowed[self.review_state_status]:
            raise ValueError(
                "guided decision review disposition does not match review state"
            )
        return self
