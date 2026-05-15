#!/usr/bin/env python3
"""Create a review manifest from Report Workflow quality correction JSONL."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import (  # noqa: E402
    FORBIDDEN_BOUNDARY_KEYS,
    REQUIRED_DIMENSIONS,
    validate_correction_artifact,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    values = value if isinstance(value, list) else []
    return [str(item).strip() for item in values if str(item).strip()]


def _score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _score_summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "avg": None, "min": None, "max": None}
    return {
        "count": len(values),
        "avg": round(mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _counter_payload(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _artifact_summary(payload: dict[str, Any], validation: dict[str, Any], *, line_no: int) -> dict[str, Any]:
    workflow = _as_dict(payload.get("workflow_reference"))
    profile = _as_dict(payload.get("document_profile"))
    quality = _as_dict(payload.get("quality_baseline"))
    correction = _as_dict(payload.get("correction"))
    labels = _as_dict(payload.get("learning_labels"))
    return {
        "line": line_no,
        "artifact_id": payload.get("artifact_id", ""),
        "report_workflow_id": workflow.get("report_workflow_id", ""),
        "workflow_status": workflow.get("workflow_status", ""),
        "learning_opt_in": bool(workflow.get("learning_opt_in")),
        "document_type": profile.get("document_type", ""),
        "domain": profile.get("domain", ""),
        "language": profile.get("language", ""),
        "slide_count": profile.get("slide_count"),
        "reviewer": correction.get("reviewer", ""),
        "reviewed_at": correction.get("reviewed_at", ""),
        "overall_score": quality.get("overall_score"),
        "task_types": _string_list(labels.get("task_types")),
        "skills": _string_list(labels.get("skills")),
        "confirmed_claim_count": len(_as_list(labels.get("confirmed_claims"))),
        "validation_ok": bool(validation.get("ok")),
        "ready_for_learning": bool(validation.get("ready_for_learning")),
        "validation_errors": list(validation.get("errors") or []),
        "validation_warnings": list(validation.get("warnings") or []),
    }


def _load_artifacts(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    artifacts: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            parse_errors.append({"line": line_no, "error": f"invalid JSON ({exc.msg})"})
            continue
        if not isinstance(payload, dict):
            parse_errors.append({"line": line_no, "error": "artifact root must be an object"})
            continue
        artifacts.append({"line": line_no, "payload": payload})
    return artifacts, parse_errors


def _boundary_issues(artifacts: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    for item in artifacts:
        line_no = int(item.get("line") or 0)
        payload = _as_dict(item.get("payload"))
        boundary = _as_dict(payload.get("training_boundary"))
        for key in FORBIDDEN_BOUNDARY_KEYS:
            if boundary.get(key) is not False:
                issues.append(f"line {line_no}: training_boundary.{key} must be false")
    return issues


def create_report_quality_batch_manifest(
    *,
    jsonl_path: Path,
    batch_id: str = "",
    min_records: int = 3,
) -> dict[str, Any]:
    resolved_path = jsonl_path.expanduser().resolve()
    min_records = max(1, int(min_records or 1))
    if not resolved_path.exists():
        raise SystemExit(f"JSONL file not found: {resolved_path}")

    loaded_artifacts, parse_errors = _load_artifacts(resolved_path)
    artifact_rows: list[dict[str, Any]] = []
    overall_scores: list[float] = []
    dimension_scores: dict[str, list[float]] = {dimension: [] for dimension in REQUIRED_DIMENSIONS}
    document_types: Counter[str] = Counter()
    domains: Counter[str] = Counter()
    reviewers: Counter[str] = Counter()
    task_types: Counter[str] = Counter()
    skills: Counter[str] = Counter()

    for item in loaded_artifacts:
        payload = _as_dict(item.get("payload"))
        validation = validate_correction_artifact(payload)
        row = _artifact_summary(payload, validation, line_no=int(item.get("line") or 0))
        artifact_rows.append(row)

        quality = _as_dict(payload.get("quality_baseline"))
        score = _score(quality.get("overall_score"))
        if score is not None:
            overall_scores.append(score)
        raw_dimension_scores = _as_dict(quality.get("dimension_scores"))
        for dimension in REQUIRED_DIMENSIONS:
            value = _score(raw_dimension_scores.get(dimension))
            if value is not None:
                dimension_scores[dimension].append(value)

        if row["document_type"]:
            document_types[str(row["document_type"])] += 1
        if row["domain"]:
            domains[str(row["domain"])] += 1
        if row["reviewer"]:
            reviewers[str(row["reviewer"])] += 1
        task_types.update(row["task_types"])
        skills.update(row["skills"])

    artifact_count = len(artifact_rows)
    valid_artifacts = sum(1 for row in artifact_rows if row["validation_ok"])
    ready_artifacts = sum(1 for row in artifact_rows if row["ready_for_learning"])
    boundary_issues = _boundary_issues(loaded_artifacts)
    blocker_reasons: list[str] = []
    if parse_errors:
        blocker_reasons.append("jsonl_parse_errors")
    if artifact_count < min_records:
        blocker_reasons.append("minimum_record_count_not_met")
    if valid_artifacts != artifact_count:
        blocker_reasons.append("invalid_artifacts_present")
    if ready_artifacts != artifact_count:
        blocker_reasons.append("not_ready_artifacts_present")
    if boundary_issues:
        blocker_reasons.append("training_boundary_violation")

    ready_for_human_training_review = not blocker_reasons and artifact_count >= min_records
    manifest = {
        "report_type": "report_quality_correction_batch_manifest",
        "schema_version": "decisiondoc_report_quality_correction_batch_manifest.v1",
        "batch_id": batch_id.strip() or f"rqc_batch_{uuid.uuid4().hex[:12]}",
        "generated_at": _now_iso(),
        "source": {
            "jsonl_path": str(resolved_path),
            "jsonl_sha256": _sha256(resolved_path),
        },
        "readiness": {
            "ok": ready_for_human_training_review,
            "status": "ready_for_human_training_review"
            if ready_for_human_training_review
            else "follow_up_required",
            "min_records": min_records,
            "blocker_reasons": blocker_reasons,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "artifact_count": artifact_count,
            "valid_artifacts": valid_artifacts,
            "ready_artifacts": ready_artifacts,
            "not_ready_artifacts": artifact_count - ready_artifacts,
            "parse_errors": len(parse_errors),
            "reviewer_count": len(reviewers),
            "document_type_count": len(document_types),
        },
        "quality": {
            "overall_score": _score_summary(overall_scores),
            "dimension_scores": {
                dimension: _score_summary(values)
                for dimension, values in dimension_scores.items()
            },
        },
        "distribution": {
            "document_types": _counter_payload(document_types),
            "domains": _counter_payload(domains),
            "reviewers": _counter_payload(reviewers),
            "task_types": _counter_payload(task_types),
            "skills": _counter_payload(skills),
        },
        "parse_errors": parse_errors,
        "boundary_issues": boundary_issues,
        "artifacts": artifact_rows,
        "side_effect_boundary": {
            "reads_local_jsonl": True,
            "writes_manifest_only": True,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }
    return manifest


def render_batch_markdown(manifest: dict[str, Any]) -> str:
    readiness = _as_dict(manifest.get("readiness"))
    counts = _as_dict(manifest.get("counts"))
    quality = _as_dict(manifest.get("quality"))
    overall = _as_dict(quality.get("overall_score"))
    distribution = _as_dict(manifest.get("distribution"))
    blockers = list(readiness.get("blocker_reasons") or [])
    artifact_rows = _as_list(manifest.get("artifacts"))
    artifact_table = "\n".join(
        "| {artifact_id} | {document_type} | {reviewer} | {overall_score} | {ready} |".format(
            artifact_id=str(row.get("artifact_id") or "-"),
            document_type=str(row.get("document_type") or "-"),
            reviewer=str(row.get("reviewer") or "-"),
            overall_score=str(row.get("overall_score") if row.get("overall_score") is not None else "-"),
            ready="yes" if row.get("ready_for_learning") else "no",
        )
        for row in artifact_rows[:25]
        if isinstance(row, dict)
    )
    if not artifact_table:
        artifact_table = "| - | - | - | - | - |"
    return f"""# Report Quality Correction Batch Summary

- batch_id: `{manifest.get('batch_id', '-')}`
- generated_at: `{manifest.get('generated_at', '-')}`
- readiness: `{readiness.get('status', 'follow_up_required')}`
- training_authorized: `false`
- artifact_count: `{counts.get('artifact_count', 0)}`
- ready_artifacts: `{counts.get('ready_artifacts', 0)}`
- min_records: `{readiness.get('min_records', 0)}`
- reviewer_count: `{counts.get('reviewer_count', 0)}`
- document_type_count: `{counts.get('document_type_count', 0)}`
- overall_score_avg: `{overall.get('avg', '-')}`

## Blockers

{chr(10).join(f'- `{item}`' for item in blockers) if blockers else '- none'}

## Distribution

- document_types: `{json.dumps(distribution.get('document_types') or {}, ensure_ascii=False, sort_keys=True)}`
- reviewers: `{json.dumps(distribution.get('reviewers') or {}, ensure_ascii=False, sort_keys=True)}`
- task_types: `{json.dumps(distribution.get('task_types') or {}, ensure_ascii=False, sort_keys=True)}`
- skills: `{json.dumps(distribution.get('skills') or {}, ensure_ascii=False, sort_keys=True)}`

## Artifact Sample

| artifact_id | document_type | reviewer | overall_score | ready |
| --- | --- | --- | --- | --- |
{artifact_table}

## Side-Effect Boundary

- external_dataset_upload_started: `false`
- provider_fine_tune_api_called: `false`
- provider_job_created: `false`
- training_execution_started: `false`
- model_promotion_started: `false`
"""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize Report Workflow quality correction JSONL into a pilot batch manifest.",
    )
    parser.add_argument("jsonl", type=Path, help="Path to report_quality_correction_artifacts.jsonl")
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--min-records", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("reports/report-quality/batch_manifest.json"))
    parser.add_argument("--markdown", type=Path, default=Path("reports/report-quality/batch_summary.md"))
    parser.add_argument("--json", action="store_true", help="Print manifest JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    manifest = create_report_quality_batch_manifest(
        jsonl_path=args.jsonl,
        batch_id=args.batch_id,
        min_records=args.min_records,
    )
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output, manifest_text)
    if args.markdown:
        _write_text_atomic(args.markdown, render_batch_markdown(manifest))
    if args.json:
        print(manifest_text, end="")
    else:
        print(f"Report quality batch readiness: {'PASS' if manifest['readiness']['ok'] else 'FAIL'}")
        print(f"Batch id: {manifest['batch_id']}")
        print(f"Artifact count: {manifest['counts']['artifact_count']}")
        print(f"Ready artifacts: {manifest['counts']['ready_artifacts']}")
        print(f"Manifest: {args.output}")
        print(f"Markdown: {args.markdown}")
    return 0 if manifest["readiness"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
