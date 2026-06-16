#!/usr/bin/env python3
"""Summarize report quality review packet sign-off records."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNOFF_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_signoff.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_review_packet_signoff_summary.v1"
GENERATION_BOUNDARY_FALSE_KEYS = (
    "actual_reviewer_approval_recorded",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_started",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "training_execution_started",
    "model_promotion_started",
)


def _load_signoff_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_signoff",
        SIGNOFF_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load sign-off validator: {SIGNOFF_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SIGNOFF_VALIDATOR = _load_signoff_validator()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _expand_paths(paths: Sequence[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        candidate = path.expanduser()
        if candidate.is_dir():
            expanded.extend(sorted(item for item in candidate.glob("*.json") if item.is_file()))
        else:
            expanded.append(candidate)
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in expanded:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(resolved)
    return deduped


def _boundary_ok(payload: dict[str, Any]) -> tuple[bool, list[str]]:
    findings: list[str] = []
    signoff_boundary = _as_dict(payload.get("signoff_boundary"))
    for key in _SIGNOFF_VALIDATOR.FORBIDDEN_BOUNDARY_KEYS:
        if signoff_boundary.get(key) is not False:
            findings.append(f"signoff_boundary.{key} must be false")

    generation_boundary = _as_dict(payload.get("generation_boundary"))
    for key in GENERATION_BOUNDARY_FALSE_KEYS:
        if key in generation_boundary and generation_boundary.get(key) is not False:
            findings.append(f"generation_boundary.{key} must be false")
    return not findings, findings


def _record_status(
    *,
    base_validation: dict[str, Any],
    complete_validation: dict[str, Any],
    boundary_ok: bool,
    decision: str,
) -> str:
    if not boundary_ok:
        return "attention_required_boundary_violation"
    if base_validation.get("ok") is not True:
        return "invalid_signoff_record"
    if complete_validation.get("ok") is True and complete_validation.get("completed") is True:
        return "completed_signoff_evidence_only"
    if decision == "pending":
        return "pending_manual_signoff_no_training_authorization"
    return "incomplete_signoff_requires_follow_up"


def summarize_signoff_record(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    base_validation = _SIGNOFF_VALIDATOR.validate_review_packet_signoff(payload, require_complete=False)
    complete_validation = _SIGNOFF_VALIDATOR.validate_review_packet_signoff(payload, require_complete=True)
    boundary_ok, boundary_findings = _boundary_ok(payload)
    decision = str(payload.get("decision", ""))
    evidence_reviewed = _as_list(payload.get("evidence_reviewed"))
    reviewer = _as_dict(payload.get("reviewer"))
    acknowledgements = _as_dict(payload.get("acknowledgements"))
    checked_acknowledgements = sorted(key for key, value in acknowledgements.items() if value is True)
    unchecked_acknowledgements = sorted(key for key, value in acknowledgements.items() if value is not True)
    status = _record_status(
        base_validation=base_validation,
        complete_validation=complete_validation,
        boundary_ok=boundary_ok,
        decision=decision,
    )
    return {
        "path": str(path),
        "schema_version": payload.get("schema_version"),
        "signoff_id": payload.get("signoff_id", ""),
        "created_at": payload.get("created_at", ""),
        "decision": decision,
        "record_status": status,
        "completed": complete_validation.get("completed") is True and complete_validation.get("ok") is True,
        "reviewer": {
            "name_present": bool(str(reviewer.get("name", "")).strip()),
            "title_or_team_present": bool(str(reviewer.get("title_or_team", "")).strip()),
            "reviewed_at_present": bool(str(reviewer.get("reviewed_at", "")).strip()),
        },
        "evidence_reviewed_count": len(evidence_reviewed),
        "acknowledgements": {
            "checked_count": len(checked_acknowledgements),
            "unchecked_count": len(unchecked_acknowledgements),
            "checked": checked_acknowledgements,
            "unchecked": unchecked_acknowledgements,
        },
        "handoff_manifest_path": payload.get("handoff_manifest_path", ""),
        "handoff_validation_ok": complete_validation.get("handoff_validation_ok"),
        "boundary_ok": boundary_ok,
        "boundary_findings": boundary_findings,
        "validation": {
            "base_ok": base_validation.get("ok") is True,
            "complete_ok": complete_validation.get("ok") is True,
            "base_errors": base_validation.get("errors", []),
            "complete_errors": complete_validation.get("errors", []),
            "warnings": sorted(set(base_validation.get("warnings", []) + complete_validation.get("warnings", []))),
        },
    }


def build_signoff_summary(
    paths: Sequence[Path],
    *,
    generated_at: str | None = None,
    require_complete: bool = False,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            records.append(summarize_signoff_record(path, _load_json(path)))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            load_errors.append({"path": str(path), "error": str(exc)})

    decision_counts = {key: 0 for key in ("pending", "accepted", "changes_requested", "rejected", "other")}
    for record in records:
        decision = record.get("decision")
        decision_counts[decision if decision in decision_counts else "other"] += 1

    completed_count = sum(1 for record in records if record["completed"])
    pending_count = sum(1 for record in records if record["decision"] == "pending" and record["validation"]["base_ok"])
    boundary_ok = all(record["boundary_ok"] for record in records)
    invalid_count = sum(1 for record in records if not record["validation"]["base_ok"] or not record["boundary_ok"])
    incomplete_non_pending = sum(
        1
        for record in records
        if record["decision"] != "pending" and not record["completed"] and record["validation"]["base_ok"]
    )
    require_complete_ok = (
        bool(records)
        and not load_errors
        and completed_count == len(records)
        and invalid_count == 0
        and incomplete_non_pending == 0
    )
    ok = not load_errors and invalid_count == 0 and (require_complete_ok if require_complete else True)
    return {
        "report_type": "report_quality_review_packet_signoff_summary",
        "schema_version": EXPECTED_SCHEMA,
        "generated_at": generated_at or _now_iso(),
        "read_only": True,
        "require_complete": require_complete,
        "ok": ok,
        "readiness": {
            "status": "completed_signoffs_ready_for_human_training_discussion"
            if require_complete_ok
            else "pending_or_follow_up_required",
            "require_complete_ok": require_complete_ok,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "counts": {
            "record_count": len(records),
            "completed_record_count": completed_count,
            "pending_record_count": pending_count,
            "invalid_record_count": invalid_count,
            "incomplete_non_pending_record_count": incomplete_non_pending,
            "load_error_count": len(load_errors),
            "decision_counts": decision_counts,
        },
        "records": records,
        "load_errors": load_errors,
        "side_effect_boundary": {
            "reads_local_signoff_files": True,
            "writes_summary_only": True,
            "actual_reviewer_approval_recorded_by_summary": False,
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }


def render_summary_markdown(summary: dict[str, Any]) -> str:
    counts = _as_dict(summary.get("counts"))
    readiness = _as_dict(summary.get("readiness"))
    records = _as_list(summary.get("records"))
    rows = "\n".join(
        "| {signoff_id} | {decision} | {status} | {completed} | `{path}` |".format(
            signoff_id=record.get("signoff_id", "-"),
            decision=record.get("decision", "-"),
            status=record.get("record_status", "-"),
            completed=str(record.get("completed") is True).lower(),
            path=record.get("path", ""),
        )
        for record in records
    )
    if not rows:
        rows = "| - | - | - | - | - |"
    return f"""# Report Quality Review Packet Sign-Off Summary

- generated_at: `{summary.get('generated_at', '-')}`
- status: `{readiness.get('status', '-')}`
- require_complete: `{str(summary.get('require_complete') is True).lower()}`
- ok: `{str(summary.get('ok') is True).lower()}`
- record_count: `{counts.get('record_count', 0)}`
- completed_record_count: `{counts.get('completed_record_count', 0)}`
- pending_record_count: `{counts.get('pending_record_count', 0)}`
- invalid_record_count: `{counts.get('invalid_record_count', 0)}`
- training_authorized: `false`

## Records

| signoff_id | decision | status | completed | path |
| --- | --- | --- | --- | --- |
{rows}

## Side-Effect Boundary

- actual_reviewer_approval_recorded_by_summary: `false`
- server_file_written: `false`
- persisted_learning_artifact: `false`
- external_dataset_upload_started: `false`
- provider_fine_tune_api_called: `false`
- provider_job_created: `false`
- training_execution_started: `false`
- model_promotion_started: `false`
"""


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize report quality review packet sign-off JSON records.")
    parser.add_argument("signoffs", nargs="+", type=Path, help="Sign-off JSON file(s) or directories.")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic output.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional output path for summary JSON.")
    parser.add_argument("--markdown", type=Path, help="Optional output path for summary Markdown.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = build_signoff_summary(
        args.signoffs,
        generated_at=args.generated_at,
        require_complete=bool(args.require_complete),
    )
    summary_text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_text_atomic(args.output.expanduser().resolve(), summary_text)
    if args.markdown:
        _write_text_atomic(args.markdown.expanduser().resolve(), render_summary_markdown(summary))

    if args.json:
        print(summary_text, end="")
    else:
        print(f"Report quality review packet signoff summary: {'PASS' if summary['ok'] else 'FAIL'}")
        print(f"record_count={summary['counts']['record_count']}")
        print(f"completed_record_count={summary['counts']['completed_record_count']}")
        print(f"pending_record_count={summary['counts']['pending_record_count']}")
        print("training_boundary=not_authorized")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
