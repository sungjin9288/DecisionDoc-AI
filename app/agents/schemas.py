"""Schemas for DecisionDoc-native DocumentOps agents."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


_DOCUMENT_COMPARISON_TASK_TYPE = "document_comparison_review"
_DOCUMENT_COMPARISON_MAX_TEXT_LENGTH = 20_000
_DOCUMENT_COMPARISON_MAX_CRITERIA = 8
_DOCUMENT_COMPARISON_MAX_CRITERION_LENGTH = 120


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

    _comparison_context: "DocumentOpsComparisonContext | None" = PrivateAttr(default=None)

    @model_validator(mode="after")
    def validate_document_comparison_inputs(self) -> "DocumentOpsRequest":
        """Fail before skill resolution when a comparison request is malformed."""
        if self.task_type != _DOCUMENT_COMPARISON_TASK_TYPE:
            return self

        baseline = _required_comparison_document(self.requirements, "baseline_document_text")
        candidate = _required_comparison_document(self.requirements, "candidate_document_text")
        criteria = _normalized_comparison_criteria(self.requirements.get("comparison_criteria"))
        try:
            baseline_bytes = baseline.encode("utf-8")
            candidate_bytes = candidate.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("comparison document text must be valid UTF-8.") from exc
        self._comparison_context = DocumentOpsComparisonContext(
            schema_version="document_ops_comparison_context_v1",
            baseline_sha256=hashlib.sha256(baseline_bytes).hexdigest(),
            candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
            documents_identical=baseline_bytes == candidate_bytes,
            comparison_criteria=criteria,
            raw_content_included=False,
        )
        return self

    @property
    def comparison_context(self) -> "DocumentOpsComparisonContext | None":
        """Return only the server-derived, raw-content-free comparison context."""
        return self._comparison_context


class DocumentOpsComparisonContext(BaseModel):
    """Trusted public comparison metadata derived from exact UTF-8 input bytes."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal["document_ops_comparison_context_v1"]
    baseline_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    candidate_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    documents_identical: bool
    comparison_criteria: list[str] = Field(default_factory=list, max_length=_DOCUMENT_COMPARISON_MAX_CRITERIA)
    raw_content_included: Literal[False] = False


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
    comparison_context: DocumentOpsComparisonContext | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    trajectory: dict[str, Any] | None = None


def _required_comparison_document(requirements: dict[str, Any], field_name: str) -> str:
    value = requirements.get(field_name)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a non-blank string.")
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-blank string.")
    if len(value) > _DOCUMENT_COMPARISON_MAX_TEXT_LENGTH:
        raise ValueError(
            f"{field_name} must not exceed {_DOCUMENT_COMPARISON_MAX_TEXT_LENGTH} characters."
        )
    return value


def _normalized_comparison_criteria(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("comparison_criteria must be a list of strings.")
    if len(value) > _DOCUMENT_COMPARISON_MAX_CRITERIA:
        raise ValueError(
            f"comparison_criteria must not contain more than {_DOCUMENT_COMPARISON_MAX_CRITERIA} items."
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("comparison_criteria must contain only strings.")
        criterion = item.strip()
        if not criterion:
            raise ValueError("comparison_criteria must not contain blank items.")
        if len(criterion) > _DOCUMENT_COMPARISON_MAX_CRITERION_LENGTH:
            raise ValueError(
                "comparison_criteria items must not exceed "
                f"{_DOCUMENT_COMPARISON_MAX_CRITERION_LENGTH} characters."
            )
        duplicate_key = criterion.casefold()
        if duplicate_key in seen:
            raise ValueError("comparison_criteria must not contain duplicate items.")
        seen.add(duplicate_key)
        normalized.append(criterion)
    return normalized
