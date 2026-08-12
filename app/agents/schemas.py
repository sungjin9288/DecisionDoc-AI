"""Schemas for DecisionDoc-native DocumentOps agents."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentOpsSkill(BaseModel):
    """Curated, non-executable local skill metadata and instructions."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    task_types: list[str] = Field(default_factory=list)
    risk_level: str = Field(default="low", min_length=1)
    content_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    body: str = Field(..., min_length=1)
    source_path: str = Field(..., min_length=1)


class DocumentOpsSkillBinding(BaseModel):
    """Public, immutable provenance for one resolved first-party skill."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal["document_ops_skill_binding_v1"]
    skill_name: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$",
    )
    skill_version: str = Field(
        ...,
        pattern=(
            r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
            r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
            r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
        ),
    )
    risk_level: Literal["low", "medium", "high"]
    content_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    catalog_fingerprint: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    code_execution_authorized: Literal[False] = False
    external_runtime_authorized: Literal[False] = False


def document_ops_skill_binding_sha256(binding: DocumentOpsSkillBinding) -> str:
    """Hash the exact public binding without instructions or local paths."""
    canonical = json.dumps(
        binding.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class DocumentOpsRequest(BaseModel):
    """Internal request contract for running a DocumentOps task."""

    model_config = ConfigDict(strict=True, extra="forbid")

    task_type: str = Field(..., min_length=1)
    requirements: dict[str, Any] = Field(default_factory=dict)
    project_context: dict[str, Any] = Field(default_factory=dict)
    source_summaries: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    skill_name: str | None = None
    capture_trajectory: bool = False


class EvidenceStatus(BaseModel):
    """Evidence separation used by QA and future dataset labels."""

    model_config = ConfigDict(strict=True, extra="forbid")

    confirmed: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)


class DocumentOpsDraftOutput(BaseModel):
    """Validated subset expected from the provider response."""

    model_config = ConfigDict(strict=True, extra="forbid")

    plan: list[str] = Field(default_factory=list)
    critique: list[str] = Field(default_factory=list)
    revision_tasks: list[str] = Field(default_factory=list)
    draft: str = ""
    evidence_status: EvidenceStatus = Field(default_factory=EvidenceStatus)
    qa: dict[str, Any] = Field(default_factory=dict)


class DocumentOpsResult(BaseModel):
    """Agent output returned to services or future API routes."""

    model_config = ConfigDict(strict=True, extra="forbid")

    task_type: str = Field(..., min_length=1)
    skill_name: str = Field(..., min_length=1)
    skill_version: str = Field(..., min_length=1)
    skill_binding: DocumentOpsSkillBinding
    provider_name: str = Field(..., min_length=1)
    plan: list[str] = Field(default_factory=list)
    critique: list[str] = Field(default_factory=list)
    revision_tasks: list[str] = Field(default_factory=list)
    draft: str = ""
    evidence_status: EvidenceStatus = Field(default_factory=EvidenceStatus)
    qa: dict[str, Any] = Field(default_factory=dict)
    quality_warnings: list[str] = Field(default_factory=list)
    trajectory: dict[str, Any] | None = None
