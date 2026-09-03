"""Document-ops agent run, trajectory review/export, and training approval schemas."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


_COMPARISON_MAX_TEXT_LENGTH = 20_000
_COMPARISON_MAX_CRITERIA = 8
_COMPARISON_MAX_CRITERION_LENGTH = 120
_COMPARISON_HUNK_MAX_COMBINED_LINES = 200


def _normalize_comparison_criteria(value: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        criterion = item.strip()
        if not criterion:
            raise ValueError("comparison_criteria must not contain blank items.")
        if len(criterion) > _COMPARISON_MAX_CRITERION_LENGTH:
            raise ValueError(
                "comparison_criteria items must not exceed "
                f"{_COMPARISON_MAX_CRITERION_LENGTH} characters."
            )
        try:
            criterion.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("comparison_criteria items must be valid UTF-8.") from exc
        duplicate_key = criterion.casefold()
        if duplicate_key in seen:
            raise ValueError("comparison_criteria must not contain duplicate items.")
        seen.add(duplicate_key)
        normalized.append(criterion)
    return normalized


class DocumentOpsComparisonChangeSetRequest(BaseModel):
    """Strict raw-text request for the deterministic local line comparison."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal["document_ops_comparison_change_set_request_v1"] = (
        "document_ops_comparison_change_set_request_v1"
    )
    baseline_document_text: str = Field(..., min_length=1, max_length=_COMPARISON_MAX_TEXT_LENGTH)
    candidate_document_text: str = Field(..., min_length=1, max_length=_COMPARISON_MAX_TEXT_LENGTH)
    comparison_criteria: list[str] = Field(default_factory=list, max_length=_COMPARISON_MAX_CRITERIA)

    @model_validator(mode="after")
    def validate_inputs(self) -> "DocumentOpsComparisonChangeSetRequest":
        if not self.baseline_document_text.strip() or not self.candidate_document_text.strip():
            raise ValueError("comparison document text must be non-blank.")
        try:
            self.baseline_document_text.encode("utf-8")
            self.candidate_document_text.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("comparison document text must be valid UTF-8.") from exc
        self.comparison_criteria = _normalize_comparison_criteria(self.comparison_criteria)
        return self


class DocumentOpsComparisonChangeSetHunk(BaseModel):
    """One SequenceMatcher opcode with zero-based, half-open source ranges."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    opcode: Literal["equal", "insert", "delete", "replace"]
    baseline_start: int = Field(..., ge=0)
    baseline_end: int = Field(..., ge=0)
    candidate_start: int = Field(..., ge=0)
    candidate_end: int = Field(..., ge=0)
    baseline_lines: list[str]
    candidate_lines: list[str]

    @model_validator(mode="after")
    def validate_ranges_and_content(self) -> "DocumentOpsComparisonChangeSetHunk":
        baseline_count = self.baseline_end - self.baseline_start
        candidate_count = self.candidate_end - self.candidate_start
        if baseline_count < 0 or candidate_count < 0:
            raise ValueError("comparison hunk ranges must be ordered.")
        if self.opcode == "equal" and (baseline_count <= 0 or baseline_count != candidate_count):
            raise ValueError("equal hunks require matching non-empty sides.")
        if self.opcode == "insert" and (baseline_count != 0 or candidate_count <= 0):
            raise ValueError("insert hunks require only a candidate side.")
        if self.opcode == "delete" and (baseline_count <= 0 or candidate_count != 0):
            raise ValueError("delete hunks require only a baseline side.")
        if self.opcode == "replace" and (baseline_count <= 0 or candidate_count <= 0):
            raise ValueError("replace hunks require both sides.")
        if len(self.baseline_lines) != baseline_count or len(self.candidate_lines) != candidate_count:
            raise ValueError("comparison hunk ranges must match exposed line content.")
        included = len(self.baseline_lines) + len(self.candidate_lines)
        if included > _COMPARISON_HUNK_MAX_COMBINED_LINES:
            raise ValueError("comparison hunk content exceeds the combined line limit.")
        if self.opcode == "equal" and self.baseline_lines != self.candidate_lines:
            raise ValueError("equal hunk line content must match.")
        try:
            for line in (*self.baseline_lines, *self.candidate_lines):
                line.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("comparison hunk lines must be valid UTF-8.") from exc
        return self


class DocumentOpsComparisonChangeSetAuthority(BaseModel):
    """Salvage boundary: line evidence grants no execution or semantic authority."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    approval: Literal[False] = False
    code_execution: Literal[False] = False
    external_effect: Literal[False] = False
    external_runtime: Literal[False] = False
    persistence: Literal[False] = False
    provider_call: Literal[False] = False
    semantic: Literal[False] = False


class DocumentOpsComparisonChangeSetResponse(BaseModel):
    """Self-consistent, deterministic line change set with no runtime authority."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    schema_version: Literal["document_ops_comparison_change_set_v1"] = (
        "document_ops_comparison_change_set_v1"
    )
    baseline_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    candidate_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    baseline_line_count: int = Field(..., ge=0)
    candidate_line_count: int = Field(..., ge=0)
    documents_identical: bool
    comparison_criteria: list[str] = Field(default_factory=list, max_length=_COMPARISON_MAX_CRITERIA)
    equal_line_count: int = Field(..., ge=0)
    added_line_count: int = Field(..., ge=0)
    removed_line_count: int = Field(..., ge=0)
    baseline_replaced_line_count: int = Field(..., ge=0)
    candidate_replaced_line_count: int = Field(..., ge=0)
    replaced_line_count: int = Field(..., ge=0)
    total_hunk_count: int = Field(..., ge=1)
    hunks_truncated: bool
    hunks: list[DocumentOpsComparisonChangeSetHunk]
    authority: DocumentOpsComparisonChangeSetAuthority = Field(
        default_factory=DocumentOpsComparisonChangeSetAuthority
    )

    @model_validator(mode="after")
    def validate_change_set(self) -> "DocumentOpsComparisonChangeSetResponse":
        normalized = _normalize_comparison_criteria(self.comparison_criteria)
        if normalized != self.comparison_criteria:
            raise ValueError("comparison_criteria must already be normalized.")
        identical_hashes = self.baseline_sha256 == self.candidate_sha256
        if self.documents_identical is not identical_hashes:
            raise ValueError("documents_identical must agree with the source hashes.")
        if not self.hunks or len(self.hunks) > self.total_hunk_count:
            raise ValueError("comparison change set requires a valid hunk prefix.")

        if self.replaced_line_count != max(
            self.baseline_replaced_line_count,
            self.candidate_replaced_line_count,
        ):
            raise ValueError("replaced_line_count must be the aggregate side maximum.")
        if self.baseline_line_count != (
            self.equal_line_count
            + self.removed_line_count
            + self.baseline_replaced_line_count
        ) or self.candidate_line_count != (
            self.equal_line_count
            + self.added_line_count
            + self.candidate_replaced_line_count
        ):
            raise ValueError("comparison aggregate counts cannot describe the sources.")

        baseline_cursor = 0
        candidate_cursor = 0
        equal_count = 0
        added_count = 0
        removed_count = 0
        baseline_replaced = 0
        candidate_replaced = 0
        exposed_line_count = 0
        for hunk in self.hunks:
            if hunk.baseline_start != baseline_cursor or hunk.candidate_start != candidate_cursor:
                raise ValueError("comparison hunk ranges must be continuous.")
            baseline_count = hunk.baseline_end - hunk.baseline_start
            candidate_count = hunk.candidate_end - hunk.candidate_start
            exposed_line_count += baseline_count + candidate_count
            baseline_cursor = hunk.baseline_end
            candidate_cursor = hunk.candidate_end
            if hunk.opcode == "equal":
                equal_count += baseline_count
            elif hunk.opcode == "insert":
                added_count += candidate_count
            elif hunk.opcode == "delete":
                removed_count += baseline_count
            else:
                baseline_replaced += baseline_count
                candidate_replaced += candidate_count

        if exposed_line_count > _COMPARISON_HUNK_MAX_COMBINED_LINES:
            raise ValueError("comparison hunks exceed the global line budget.")
        expected_counts = (
            equal_count,
            added_count,
            removed_count,
            baseline_replaced,
            candidate_replaced,
            max(baseline_replaced, candidate_replaced),
        )
        actual_counts = (
            self.equal_line_count,
            self.added_line_count,
            self.removed_line_count,
            self.baseline_replaced_line_count,
            self.candidate_replaced_line_count,
            self.replaced_line_count,
        )
        if self.hunks_truncated:
            if exposed_line_count not in {
                _COMPARISON_HUNK_MAX_COMBINED_LINES - 1,
                _COMPARISON_HUNK_MAX_COMBINED_LINES,
            }:
                raise ValueError("truncated comparison hunks must exhaust the global line budget.")
            if (
                equal_count > self.equal_line_count
                or added_count > self.added_line_count
                or removed_count > self.removed_line_count
                or baseline_replaced > self.baseline_replaced_line_count
                or candidate_replaced > self.candidate_replaced_line_count
            ):
                raise ValueError("comparison hunk prefix exceeds aggregate counts.")
            if (
                baseline_cursor == self.baseline_line_count
                and candidate_cursor == self.candidate_line_count
                and len(self.hunks) == self.total_hunk_count
            ):
                raise ValueError("hunks_truncated cannot describe complete coverage.")
        elif (
            len(self.hunks) != self.total_hunk_count
            or baseline_cursor != self.baseline_line_count
            or candidate_cursor != self.candidate_line_count
            or actual_counts != expected_counts
        ):
            raise ValueError("non-truncated comparison hunks require complete coverage.")
        if identical_hashes and (
            self.added_line_count
            or self.removed_line_count
            or self.replaced_line_count
            or self.equal_line_count != self.baseline_line_count
            or self.baseline_line_count != self.candidate_line_count
            or any(hunk.opcode != "equal" for hunk in self.hunks)
        ):
            raise ValueError("identical documents require equal-only complete coverage.")
        return self


class DocumentOpsComparisonDocumentResponse(BaseModel):
    """Strict, no-effect response for one comparison file extraction."""

    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal["document_ops_comparison_document_v1"] = (
        "document_ops_comparison_document_v1"
    )
    filename: str = Field(..., min_length=1, max_length=255)
    source_size_bytes: int = Field(..., ge=1, le=20 * 1024 * 1024)
    source_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    extracted_text: str = Field(..., min_length=1)
    extracted_text_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    extracted_char_count: int = Field(..., ge=1)
    content_may_be_truncated: bool
    extraction_mode: Literal["deterministic_local_existing_parser"] = (
        "deterministic_local_existing_parser"
    )
    provider_called: Literal[False] = False
    persisted: Literal[False] = False


class DocumentOpsAgentRunRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    task_type: str = Field(..., min_length=1)
    requirements: dict[str, Any] = Field(default_factory=dict)
    project_context: dict[str, Any] = Field(default_factory=dict)
    source_summaries: list[str] = Field(default_factory=list)
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    skill_name: str | None = None
    capture_trajectory: bool = False
    operation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )

    @model_validator(mode="after")
    def require_capture_for_retry_identity(self) -> "DocumentOpsAgentRunRequest":
        if self.operation_id is not None and not self.capture_trajectory:
            raise ValueError("operation_id requires capture_trajectory=true.")
        return self


class DocumentOpsTrajectoryReviewRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    accepted: bool
    expected_review_version: int = Field(..., ge=0)
    reviewer: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=2000)
    quality_score: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentOpsTrajectoryExportRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    task_type: str | None = None
    min_records: int = Field(default=1, ge=1)
    accepted_only: bool = True
    include_metadata: bool = True


class DocumentOpsTrajectoryExportPreviewRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    task_type: str | None = None
    min_records: int = Field(default=1, ge=1)
    accepted_only: bool = True
    include_metadata: bool = True
    sample_limit: int = Field(default=5, ge=0, le=25)


class DocumentOpsDatasetFreezeRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    reviewer: str = Field(..., min_length=1)
    notes: str = ""
    sample_limit: int = Field(default=5, ge=0, le=25)
    training_allowed: bool = False
    operation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )


class DocumentOpsTrainingApprovalRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    approver: str = Field(..., min_length=1)
    eval_plan: dict[str, Any] = Field(..., min_length=1)
    notes: str = ""
    dry_run: bool = True
    start_training: bool = False
    operation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )


class DocumentOpsTrainingExecutionRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    requester: str = Field(..., min_length=1)
    provider: str = Field(default="provider_agnostic", min_length=1, max_length=80)
    base_model: str | None = Field(default=None, max_length=120)
    notes: str = ""
    start_training: bool = False
    upload_dataset: bool = False
    call_provider_api: bool = False
    operation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )


class DocumentOpsTrainingAuditExportRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    auditor: str = Field(..., min_length=1)
    provider: str = Field(default="provider_agnostic", min_length=1, max_length=80)
    base_model: str | None = Field(default=None, max_length=120)
    notes: str = ""
    start_training: bool = False
    upload_dataset: bool = False
    call_provider_api: bool = False
    operation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
