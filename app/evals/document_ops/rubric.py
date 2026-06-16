"""Deterministic rubric definitions for DocumentOps outputs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_FORBIDDEN_TERMS = (
    "평가기준",
    "평가항목",
    "배점",
    "가중치",
    "Scorecard",
    "확인기준",
    "PoC",
    "native editable",
    "native objects",
    "visual refinement",
    "v1.1",
    "v1.2",
)

OVERCONFIDENT_PATTERNS = (
    "100%",
    "무조건",
    "반드시 성공",
    "완전 해결",
    "확정 KPI",
    "확정 비용",
    "비용 절감 확정",
    "성과 보장",
)

GOVERNANCE_TASK_TYPES = {
    "policy_planning_brief",
    "develop_quality_improvement",
    "report_workflow_planning",
    "procurement_planning_brief",
}


class RubricDimension(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    key: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    weight: float = Field(..., ge=0.0, le=1.0)
    description: str = Field(..., min_length=1)


class DocumentOpsGateIssue(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    code: str = Field(..., min_length=1)
    severity: Literal["blocker", "warning"]
    message: str = Field(..., min_length=1)
    evidence: list[str] = Field(default_factory=list)


class DocumentOpsGateResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    hard_gate_pass: bool
    issues: list[DocumentOpsGateIssue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    overall_score: float = Field(ge=0.0, le=1.0)
    recommended_next_action: Literal["approve", "request_changes", "collect_more_evidence"]


DOCUMENT_OPS_RUBRIC = (
    RubricDimension(
        key="policy_logic",
        label="Policy logic",
        weight=0.25,
        description="Problem, evidence, intervention, operation, and expected effect are connected.",
    ),
    RubricDimension(
        key="evidence_grounding",
        label="Evidence grounding",
        weight=0.30,
        description="Confirmed facts, assumptions, and gaps are separated with source references.",
    ),
    RubricDimension(
        key="public_sector_tone",
        label="Public-sector tone",
        weight=0.15,
        description="Language is restrained, non-marketing, and avoids forbidden/procurement-sensitive terms.",
    ),
    RubricDimension(
        key="implementation_detail",
        label="Implementation detail",
        weight=0.15,
        description="Roles, process, timeline, data, governance, security, and risk are specific enough.",
    ),
    RubricDimension(
        key="artifact_readiness",
        label="Artifact readiness",
        weight=0.15,
        description="Output can become planning brief or approval material with minimal rewrite.",
    ),
)
