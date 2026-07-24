"""Read-only response models for the project Decision Evidence Map."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    bundle_type: str = Field(min_length=1)
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
