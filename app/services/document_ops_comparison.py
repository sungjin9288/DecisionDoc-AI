"""Pure, deterministic line comparison for DocumentOps review evidence."""

from __future__ import annotations

import difflib
import hashlib
import json

from app.schemas.document_ops import (
    DocumentOpsComparisonChangeSetHunk,
    DocumentOpsComparisonChangeSetRequest,
    DocumentOpsComparisonChangeSetResponse,
)


MAX_COMBINED_HUNK_LINES = 200


def _bounded_hunk_prefix(
    *,
    opcode: str,
    baseline_lines: list[str],
    candidate_lines: list[str],
    remaining: int,
) -> tuple[list[str], list[str]]:
    total = len(baseline_lines) + len(candidate_lines)
    if total <= remaining:
        return baseline_lines, candidate_lines

    if opcode == "equal":
        per_side = remaining // 2
        return baseline_lines[:per_side], candidate_lines[:per_side]

    if opcode == "insert":
        return [], candidate_lines[:remaining]
    if opcode == "delete":
        return baseline_lines[:remaining], []
    if remaining < 2:
        return [], []

    baseline_limit = min(len(baseline_lines), max(1, remaining // 2))
    candidate_limit = min(len(candidate_lines), max(1, remaining // 2))
    spare = remaining - baseline_limit - candidate_limit
    baseline_limit += min(spare, len(baseline_lines) - baseline_limit)
    spare = remaining - baseline_limit - candidate_limit
    candidate_limit += min(spare, len(candidate_lines) - candidate_limit)
    return baseline_lines[:baseline_limit], candidate_lines[:candidate_limit]


def build_document_ops_comparison_change_set(
    request: DocumentOpsComparisonChangeSetRequest,
) -> DocumentOpsComparisonChangeSetResponse:
    """Build one complete opcode stream without provider, storage, or logging effects."""
    baseline_bytes = request.baseline_document_text.encode("utf-8")
    candidate_bytes = request.candidate_document_text.encode("utf-8")
    baseline_lines = request.baseline_document_text.splitlines(keepends=True)
    candidate_lines = request.candidate_document_text.splitlines(keepends=True)

    matcher = difflib.SequenceMatcher(
        a=baseline_lines,
        b=candidate_lines,
        autojunk=False,
    )
    opcodes = matcher.get_opcodes()
    hunks: list[DocumentOpsComparisonChangeSetHunk] = []
    equal_line_count = 0
    added_line_count = 0
    removed_line_count = 0
    baseline_replaced_line_count = 0
    candidate_replaced_line_count = 0

    for opcode, baseline_start, baseline_end, candidate_start, candidate_end in opcodes:
        baseline_count = baseline_end - baseline_start
        candidate_count = candidate_end - candidate_start
        if opcode == "equal":
            equal_line_count += baseline_count
        elif opcode == "insert":
            added_line_count += candidate_count
        elif opcode == "delete":
            removed_line_count += baseline_count
        else:
            baseline_replaced_line_count += baseline_count
            candidate_replaced_line_count += candidate_count

    remaining = MAX_COMBINED_HUNK_LINES
    for opcode, baseline_start, baseline_end, candidate_start, candidate_end in opcodes:
        if remaining <= 0:
            break
        full_baseline_lines = baseline_lines[baseline_start:baseline_end]
        full_candidate_lines = candidate_lines[candidate_start:candidate_end]
        shown_baseline_lines, shown_candidate_lines = _bounded_hunk_prefix(
            opcode=opcode,
            baseline_lines=full_baseline_lines,
            candidate_lines=full_candidate_lines,
            remaining=remaining,
        )
        if not shown_baseline_lines and not shown_candidate_lines:
            break
        shown_baseline_end = baseline_start + len(shown_baseline_lines)
        shown_candidate_end = candidate_start + len(shown_candidate_lines)
        hunks.append(
            DocumentOpsComparisonChangeSetHunk(
                opcode=opcode,
                baseline_start=baseline_start,
                baseline_end=shown_baseline_end,
                candidate_start=candidate_start,
                candidate_end=shown_candidate_end,
                baseline_lines=shown_baseline_lines,
                candidate_lines=shown_candidate_lines,
            )
        )
        remaining -= len(shown_baseline_lines) + len(shown_candidate_lines)
        if shown_baseline_end != baseline_end or shown_candidate_end != candidate_end:
            break

    hunks_truncated = len(hunks) != len(opcodes)
    if hunks and not hunks_truncated:
        last_opcode = opcodes[len(hunks) - 1]
        hunks_truncated = (
            hunks[-1].baseline_end != last_opcode[2]
            or hunks[-1].candidate_end != last_opcode[4]
        )

    return DocumentOpsComparisonChangeSetResponse(
        baseline_sha256=hashlib.sha256(baseline_bytes).hexdigest(),
        candidate_sha256=hashlib.sha256(candidate_bytes).hexdigest(),
        baseline_line_count=len(baseline_lines),
        candidate_line_count=len(candidate_lines),
        documents_identical=baseline_bytes == candidate_bytes,
        comparison_criteria=request.comparison_criteria,
        equal_line_count=equal_line_count,
        added_line_count=added_line_count,
        removed_line_count=removed_line_count,
        baseline_replaced_line_count=baseline_replaced_line_count,
        candidate_replaced_line_count=candidate_replaced_line_count,
        replaced_line_count=max(
            baseline_replaced_line_count,
            candidate_replaced_line_count,
        ),
        total_hunk_count=len(opcodes),
        hunks_truncated=hunks_truncated,
        hunks=hunks,
    )


def canonical_document_ops_comparison_change_set_bytes(
    response: DocumentOpsComparisonChangeSetResponse,
) -> bytes:
    """Return the exact UTF-8 JSON attachment bytes hashed by the route and browser."""
    canonical = json.dumps(
        response.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    return (canonical + "\n").encode("utf-8")
