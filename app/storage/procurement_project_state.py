"""Strict, I/O-free state contract for isolated multi-opportunity development."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas import ProcurementDecisionRecord
from app.schemas.procurement_applicability import ProcurementRequirement
from app.storage.procurement_store import (
    ProcurementDecisionStore,
    ProcurementDecisionStoreError,
    _require_path_segment,
    validate_procurement_record,
)
from app.tenant import require_tenant_id


def require_operation_id(value: str) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("operation_id must be a canonical UUID")
    return value


def require_revision(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Expected revision must be a non-negative integer")
    return value


class ProcurementDecisionEntry(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    record: ProcurementDecisionRecord
    decision_revision: int = Field(default=1, ge=1)
    legacy_mutation_ids: list[str] = Field(default_factory=list)
    requirements: list[ProcurementRequirement] = Field(default_factory=list)

    @field_validator("record")
    @classmethod
    def validate_record(cls, value: ProcurementDecisionRecord) -> ProcurementDecisionRecord:
        if value.schema_version != "v1":
            raise ValueError("Unsupported procurement decision schema")
        _require_path_segment(value.decision_id, field="decision_id")
        return validate_procurement_record(value.model_dump(mode="json"))

    @field_validator("legacy_mutation_ids")
    @classmethod
    def validate_history(cls, value: list[str]) -> list[str]:
        return ProcurementDecisionStore._mutation_ids({"_mutation_ids": value})

    @field_validator("requirements")
    @classmethod
    def validate_requirements(
        cls, value: list[ProcurementRequirement]
    ) -> list[ProcurementRequirement]:
        identities = [item.requirement_id for item in value]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate procurement requirement identity")
        return value


class ProcurementMutationReceipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    operation_id: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision_id: str
    decision_revision: int = Field(ge=1)
    selection_revision: int = Field(ge=0)

    @field_validator("operation_id")
    @classmethod
    def validate_operation(cls, value: str) -> str:
        return require_operation_id(value)


class ProcurementProjectState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal["procurement.project.v2"] = "procurement.project.v2"
    tenant_id: str
    project_id: str
    active_decision_id: str | None = None
    selection_revision: int = Field(default=0, ge=0)
    entries: list[ProcurementDecisionEntry] = Field(default_factory=list)
    receipts: list[ProcurementMutationReceipt] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_ownership(self) -> ProcurementProjectState:
        require_tenant_id(self.tenant_id)
        _require_path_segment(self.project_id, field="project_id")
        decisions: dict[str, ProcurementDecisionEntry] = {}
        sources: set[tuple[str, str]] = set()
        for entry in self.entries:
            record = entry.record
            if record.tenant_id != self.tenant_id or record.project_id != self.project_id:
                raise ValueError("Procurement decision ownership mismatch")
            if record.decision_id in decisions:
                raise ValueError("Duplicate procurement decision identity")
            decisions[record.decision_id] = entry
            if record.opportunity is None:
                if len(self.entries) != 1:
                    raise ValueError("Empty legacy decision cannot coexist with opportunities")
                continue
            source = (record.opportunity.source_kind, record.opportunity.source_id)
            if source in sources:
                raise ValueError("Duplicate procurement source identity")
            sources.add(source)
        if (self.entries and self.active_decision_id not in decisions) or (not self.entries and self.active_decision_id is not None):
            raise ValueError("Active procurement decision is missing")
        operations: set[str] = set()
        for receipt in self.receipts:
            entry = decisions.get(receipt.decision_id)
            if receipt.operation_id in operations or entry is None:
                raise ValueError("Invalid procurement operation receipt identity")
            operations.add(receipt.operation_id)
            if receipt.decision_revision > entry.decision_revision or receipt.selection_revision > self.selection_revision:
                raise ValueError("Invalid procurement operation receipt revision")
        return self


def decode_project(raw: dict[str, Any], *, tenant_id: str, project_id: str) -> ProcurementProjectState:
    """Project a legacy row without modifying it, or validate a complete v2 row."""
    try:
        require_tenant_id(tenant_id)
        _require_path_segment(project_id, field="project_id")
        if raw.get("schema_version") == "procurement.project.v2":
            project = ProcurementProjectState.model_validate(raw)
        elif raw.get("schema_version", "v1") == "v1":
            record = validate_procurement_record(raw)
            project = ProcurementProjectState(
                tenant_id=record.tenant_id, project_id=record.project_id,
                active_decision_id=record.decision_id,
                entries=[ProcurementDecisionEntry(
                    record=record, legacy_mutation_ids=ProcurementDecisionStore._mutation_ids(raw),
                )],
            )
        else:
            raise ValueError("Unsupported procurement schema")
        if project.tenant_id != tenant_id or project.project_id != project_id:
            raise ValueError("Procurement project ownership mismatch")
        return project
    except (ValueError, TypeError, AttributeError) as exc:
        raise ProcurementDecisionStoreError("Invalid procurement project state") from exc
