"""Portable source identity, without credentials or raw source content."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProcurementSnapshotFingerprint(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    snapshot_id: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size_bytes: int = Field(ge=0)


class ProcurementSourceBinding(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal["procurement.source_binding.v1"] = (
        "procurement.source_binding.v1"
    )
    tenant_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    decision_revision: int = Field(ge=1)
    source_kind: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_updated_at: str = Field(min_length=1)
    record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    snapshots: list[ProcurementSnapshotFingerprint] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_snapshots(self):
        identities = [item.snapshot_id for item in self.snapshots]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate procurement snapshot identity")
        return self
