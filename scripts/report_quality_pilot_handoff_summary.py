"""Render the operator summary embedded in a reviewed pilot handoff."""
from __future__ import annotations

import hashlib
import html
from typing import Any, Mapping


SUMMARY_NAME = "HANDOFF_SUMMARY.md"


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _markdown_text(value: Any) -> str:
    text = html.escape(str(value if value is not None else "-"), quote=False)
    return text.replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def _code(value: Any) -> str:
    text = html.escape(str(value if value is not None else "-"), quote=False)
    text = text.replace("`", "").replace("\r", " ").replace("\n", " ")
    return f"`{text}`"


def render_report_quality_pilot_handoff_summary(
    manifest: Mapping[str, Any],
    review_manifest: Mapping[str, Any],
) -> str:
    """Return a stable, reviewer-readable view of the handoff evidence."""
    jsonl = _as_dict(manifest.get("jsonl"))
    review = _as_dict(manifest.get("review"))
    rows = [row for row in _as_list(review_manifest.get("artifacts")) if isinstance(row, dict)]
    table_rows = "\n".join(
        "| {artifact_id} | {reviewer} | {reviewed_at} | {score} | {status} | {ready} |".format(
            artifact_id=_markdown_text(row.get("artifact_id")),
            reviewer=_markdown_text(row.get("reviewer")),
            reviewed_at=_markdown_text(row.get("reviewed_at")),
            score=_markdown_text(row.get("overall_score")),
            status=_markdown_text(row.get("human_review_status")),
            ready="yes" if row.get("ready_for_learning") is True else "no",
        )
        for row in rows
    )
    if not table_rows:
        table_rows = "| - | - | - | - | - | - |"

    source_bound = _as_dict(manifest.get("pack_binding")).get("source_manifest") is not None
    return f"""# Report Quality Pilot Review Handoff

## Batch

- batch_id: {_code(manifest.get('batch_id'))}
- artifact_count: {_code(manifest.get('artifact_count'))}
- source_bound: {_code(str(source_bound).lower())}
- training_authorized: `false`

## Reviewed Artifacts

| artifact_id | reviewer | reviewed_at | overall_score | review_status | ready |
| --- | --- | --- | --- | --- | --- |
{table_rows}

## Evidence

- JSONL SHA-256: {_code(jsonl.get('sha256'))}
- human review manifest SHA-256: {_code(review.get('manifest_sha256'))}
- decision receipt SHA-256: {_code(review.get('decision_receipt_sha256'))}
- decision file SHA-256: {_code(review.get('decision_file_sha256'))}

## Authorization Boundary

- external dataset upload: `not authorized`
- provider fine-tune API: `not authorized`
- provider job creation: `not authorized`
- training execution: `not authorized`
- model promotion: `not authorized`

검증 명령:

```bash
python3 scripts/manage_report_quality_pilot_handoff.py verify <handoff.zip>
```
"""


def verify_report_quality_pilot_handoff_summary(
    entries: Mapping[str, bytes],
    manifest: Mapping[str, Any],
    review_manifest: Mapping[str, Any],
) -> None:
    """Require the packaged summary to match the reviewed evidence exactly."""
    summary = manifest.get("summary")
    if not isinstance(summary, dict) or summary.get("path") != SUMMARY_NAME:
        raise ValueError("handoff summary path is invalid")
    if SUMMARY_NAME not in entries:
        raise ValueError("handoff summary is missing")
    summary_bytes = entries[SUMMARY_NAME]
    if summary.get("sha256") != _sha256(summary_bytes):
        raise ValueError("handoff summary SHA-256 mismatch")
    expected = render_report_quality_pilot_handoff_summary(
        manifest,
        review_manifest,
    ).encode("utf-8")
    if summary_bytes != expected:
        raise ValueError("handoff summary does not match the reviewed evidence")
