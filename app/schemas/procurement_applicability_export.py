"""Strict, actor-free portable applicability projection."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.procurement_applicability import (
    ApplicabilityValue,
    ProcurementRequirementCategory,
    _canonical_uuid,
)


class _PortableQuote(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    snapshot_id: str = Field(min_length=1)
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quote_start: int = Field(ge=0)
    quote_end: int = Field(gt=0)
    quote: str = Field(min_length=1)
    created_at: str = Field(min_length=1)

    @field_validator("created_at", "snapshot_id")
    @classmethod
    def canonical_text(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("portable text must be canonical and non-blank")
        return value

    @model_validator(mode="after")
    def quote_range(self):
        if self.quote_end <= self.quote_start or len(self.quote) != self.quote_end - self.quote_start:
            raise ValueError("quote must match Unicode code-point range")
        return self


class PortableApplicabilityAnnotation(_PortableQuote):
    annotation_id: str
    applicability: ApplicabilityValue
    rationale: str = Field(min_length=1, max_length=4000)
    expected_decision_revision: int = Field(ge=1)
    operation_id: str

    @field_validator("annotation_id", "operation_id")
    @classmethod
    def uuid_fields(cls, value, info):
        return _canonical_uuid(value, field=info.field_name)

    @field_validator("rationale")
    @classmethod
    def rationale_text(cls, value):
        return cls.canonical_text(value)


class PortableRequirement(_PortableQuote):
    requirement_id: str
    title: str = Field(min_length=1, max_length=500)
    category: ProcurementRequirementCategory
    annotations: list[PortableApplicabilityAnnotation]
    applicability: ApplicabilityValue
    stale: bool

    @field_validator("requirement_id")
    @classmethod
    def uuid_field(cls, value):
        return _canonical_uuid(value, field="requirement_id")

    @field_validator("title")
    @classmethod
    def title_text(cls, value):
        return cls.canonical_text(value)


class ProcurementApplicabilityExport(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal["procurement.requirement_applicability.v1"]
    decision_id: str
    decision_revision: int = Field(ge=1)
    source_set_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    requirements: list[PortableRequirement]

    @field_validator("decision_id")
    @classmethod
    def uuid_field(cls, value):
        return _canonical_uuid(value, field="decision_id")

    @model_validator(mode="after")
    def history_and_effective_status(self):
        identities = set()
        annotation_ids = set()
        operation_ids = set()
        quote_fields = ("snapshot_id", "snapshot_sha256", "source_set_sha256",
                        "quote_start", "quote_end", "quote")
        for row in self.requirements:
            if row.requirement_id in identities:
                raise ValueError("duplicate requirement identity")
            identities.add(row.requirement_id)
            previous_revision = 0
            for annotation in row.annotations:
                if annotation.annotation_id in annotation_ids or annotation.operation_id in operation_ids:
                    raise ValueError("duplicate applicability history identity")
                annotation_ids.add(annotation.annotation_id)
                operation_ids.add(annotation.operation_id)
                if any(getattr(annotation, key) != getattr(row, key) for key in quote_fields):
                    raise ValueError("annotation must preserve original quote and source")
                if not previous_revision < annotation.expected_decision_revision < self.decision_revision:
                    raise ValueError("annotation revision history is invalid")
                previous_revision = annotation.expected_decision_revision
            stale = row.source_set_sha256 != self.source_set_sha256
            effective = row.annotations[-1].applicability if row.annotations and not stale else "unknown"
            if row.stale is not stale or row.applicability != effective:
                raise ValueError("effective applicability/stale must match source and latest history")
        return self
