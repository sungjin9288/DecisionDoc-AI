"""Strict requirement-level applicability request and persisted-state models."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ApplicabilityValue = Literal["applies", "not_applicable", "unknown"]
ProcurementRequirementCategory = Literal[
    "eligibility_and_compliance",
    "certifications_and_licenses",
    "domain_capability_fit",
    "reference_cases_and_proof_points",
    "staffing_and_partner_readiness",
    "schedule_and_deadline_readiness",
    "deliverables_and_scope_clarity",
    "security_data_infrastructure_obligations",
    "pricing_budget_contract_risk",
    "executive_approval_internal_readiness",
]


def _canonical_uuid(value: str, *, field: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError(f"{field} must be a canonical UUID")
    return value


class _SnapshotQuoteRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    snapshot_id: str = Field(min_length=1)
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote_start: int = Field(ge=0)
    quote_end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    expected_decision_revision: int = Field(ge=1)
    operation_id: str

    @field_validator("operation_id")
    @classmethod
    def validate_operation_id(cls, value: str) -> str:
        return _canonical_uuid(value, field="operation_id")

    @model_validator(mode="after")
    def validate_quote_range(self):
        if self.quote_end <= self.quote_start:
            raise ValueError("quote_end must be greater than quote_start")
        if len(self.quote) != self.quote_end - self.quote_start:
            raise ValueError("quote length must match Unicode code-point range")
        return self


class CreateProcurementRequirementRequest(_SnapshotQuoteRequest):
    title: str = Field(min_length=1, max_length=500)
    category: ProcurementRequirementCategory

    @field_validator("title")
    @classmethod
    def normalize_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized


class AnnotateProcurementRequirementRequest(_SnapshotQuoteRequest):
    applicability: ApplicabilityValue
    rationale: str = Field(min_length=1, max_length=4000)

    @field_validator("rationale")
    @classmethod
    def normalize_rationale(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("rationale must not be blank")
        return normalized


class ProcurementApplicabilityAnnotation(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    annotation_id: str
    applicability: ApplicabilityValue
    rationale: str = Field(min_length=1, max_length=4000)
    snapshot_id: str = Field(min_length=1)
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote_start: int = Field(ge=0)
    quote_end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    expected_decision_revision: int = Field(ge=1)
    operation_id: str

    @field_validator("annotation_id", "operation_id")
    @classmethod
    def validate_uuid_fields(cls, value: str, info) -> str:
        return _canonical_uuid(value, field=info.field_name)

    @field_validator("rationale", "actor_id", "created_at")
    @classmethod
    def validate_non_blank_fields(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("stored text must be canonical and non-blank")
        return value

    @model_validator(mode="after")
    def validate_quote_range(self):
        if self.quote_end <= self.quote_start:
            raise ValueError("quote_end must be greater than quote_start")
        if len(self.quote) != self.quote_end - self.quote_start:
            raise ValueError("quote length must match Unicode code-point range")
        return self


class ProcurementRequirement(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    requirement_id: str
    title: str = Field(min_length=1, max_length=500)
    category: ProcurementRequirementCategory
    snapshot_id: str = Field(min_length=1)
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote_start: int = Field(ge=0)
    quote_end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    created_by_actor_id: str = Field(min_length=1)
    created_at: str = Field(min_length=1)
    annotations: list[ProcurementApplicabilityAnnotation] = Field(default_factory=list)

    @field_validator("requirement_id")
    @classmethod
    def validate_requirement_id(cls, value: str) -> str:
        return _canonical_uuid(value, field="requirement_id")

    @field_validator("title", "created_by_actor_id", "created_at")
    @classmethod
    def validate_non_blank_fields(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("stored text must be canonical and non-blank")
        return value

    @model_validator(mode="after")
    def validate_evidence_and_history(self):
        if self.quote_end <= self.quote_start:
            raise ValueError("quote_end must be greater than quote_start")
        if len(self.quote) != self.quote_end - self.quote_start:
            raise ValueError("quote length must match Unicode code-point range")
        identities = [item.annotation_id for item in self.annotations]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate procurement applicability annotation identity")
        return self
