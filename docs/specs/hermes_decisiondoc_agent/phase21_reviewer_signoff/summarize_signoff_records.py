#!/usr/bin/env python3
"""Summarize DocumentOps reviewer sign-off records.

This command is read-only. It never records reviewer approval, starts training,
uploads datasets, calls provider APIs, creates provider jobs, or promotes models.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_signoff_record import (
PROTECTED_FALSE_BOUNDARY_KEYS,
    REQUIRED_ACKNOWLEDGEMENTS,
    REQUIRED_REVIEWER_ROLES,
    validate_signoff_record,
)

PROTECTED_FALSE_GENERATION_KEYS = {
    "training_execution_started",
    "external_dataset_uploaded",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "model_promoted",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_iso_datetime(value: str) -> bool:
    if not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("sign-off record must be a JSON object")
    return data


def _expand_paths(paths: list[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in paths:
        if path.is_dir():
            expanded.extend(sorted(candidate for candidate in path.glob("*.json") if candidate.is_file()))
        else:
            expanded.append(path)
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in expanded:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        deduped.append(path)
    return deduped


def _acknowledgement_summary(value: Any) -> dict[str, Any]:
    acknowledgements = value if isinstance(value, dict) else {}
    checked = sum(1 for key in REQUIRED_ACKNOWLEDGEMENTS if acknowledgements.get(key) is True)
    total = len(REQUIRED_ACKNOWLEDGEMENTS)
    return {
        "checked": checked,
        "total": total,
        "complete": checked == total,
        "unchecked": sorted(key for key in REQUIRED_ACKNOWLEDGEMENTS if acknowledgements.get(key) is not True),
    }


def _summarize_reviewer(reviewer: dict[str, Any]) -> dict[str, Any]:
    role = _as_text(reviewer.get("reviewer_role"))
    decision = _as_text(reviewer.get("decision")) or "missing"
    reviewed_at = _as_text(reviewer.get("reviewed_at"))
    evidence = reviewer.get("evidence_reviewed")
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    acknowledgements = _acknowledgement_summary(reviewer.get("required_acknowledgements"))
    notes = _as_text(reviewer.get("notes"))
    complete = all(
        [
            role in REQUIRED_REVIEWER_ROLES,
            bool(_as_text(reviewer.get("reviewer_name"))),
            bool(_as_text(reviewer.get("reviewer_title_or_team"))),
            _is_iso_datetime(reviewed_at),
            decision != "pending",
            evidence_count > 0,
            acknowledgements["complete"],
            bool(notes) if decision in {"changes_requested", "blocked"} else True,
        ]
    )
    return {
        "reviewer_role": role,
        "reviewer_name_present": bool(_as_text(reviewer.get("reviewer_name"))),
        "reviewer_title_or_team_present": bool(_as_text(reviewer.get("reviewer_title_or_team"))),
        "reviewed_at_present": bool(reviewed_at),
        "reviewed_at_valid": _is_iso_datetime(reviewed_at),
        "decision": decision,
        "evidence_reviewed_count": evidence_count,
        "acknowledgements": acknowledgements,
        "notes_present": bool(notes),
        "complete": complete,
    }


def _boundary_summary(record: dict[str, Any]) -> dict[str, Any]:
    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        boundary = {}
    generation_boundary = record.get("generation_boundary")
    if not isinstance(generation_boundary, dict):
        generation_boundary = {}
    protected = {key: boundary.get(key) for key in sorted(PROTECTED_FALSE_BOUNDARY_KEYS)}
    generation_side_effects = {
        key: generation_boundary.get(key, False)
        for key in sorted(PROTECTED_FALSE_GENERATION_KEYS)
    }
    return {
        "actual_reviewer_approval_recorded": boundary.get("actual_reviewer_approval_recorded"),
        "training_execution_authorized": boundary.get("training_execution_authorized"),
        "external_dataset_upload_authorized": boundary.get("external_dataset_upload_authorized"),
        "provider_fine_tune_api_call_authorized": boundary.get("provider_fine_tune_api_call_authorized"),
        "provider_job_creation_authorized": boundary.get("provider_job_creation_authorized"),
        "provider_job_polling_authorized": boundary.get("provider_job_polling_authorized"),
        "model_candidate_emission_authorized": boundary.get("model_candidate_emission_authorized"),
        "model_promotion_authorized": boundary.get("model_promotion_authorized"),
        "protected_training_flags_false": all(value is False for value in protected.values()),
        "generation_side_effect_flags_false": all(value is False for value in generation_side_effects.values()),
    }


def _record_status(validation: dict[str, Any], boundary: dict[str, Any]) -> str:
    if not boundary["protected_training_flags_false"] or not boundary["generation_side_effect_flags_false"]:
        return "attention_required_boundary_violation"
    if validation["valid"]:
        return "manual_signoff_complete_no_training_authorization"
    return "pending_manual_signoff_no_training_authorization"


def summarize_record(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    validation = validate_signoff_record(record)
    reviewers_raw = record.get("required_reviewers")
    reviewers = [_summarize_reviewer(item) for item in reviewers_raw if isinstance(item, dict)] if isinstance(reviewers_raw, list) else []
    boundary = _boundary_summary(record)
    completed_roles = sorted(item["reviewer_role"] for item in reviewers if item["complete"])
    pending_roles = sorted({item["reviewer_role"] for item in reviewers if item["decision"] == "pending" or not item["complete"]})
    return {
        "path": str(path),
        "report_type": record.get("report_type", ""),
        "signoff_record_id": record.get("signoff_record_id", ""),
        "created_at": record.get("created_at", ""),
        "record_status": _record_status(validation, boundary),
        "reviewers": reviewers,
        "reviewers_complete_count": len(completed_roles),
        "pending_reviewer_count": len(pending_roles),
        "completed_reviewer_roles": completed_roles,
        "pending_reviewer_roles": pending_roles,
        "completion_rule": record.get("completion_rule", {}),
        "boundary": boundary,
        "completed_validation": {
            "valid": validation["valid"],
            "error_count": validation["error_count"],
            "warning_count": validation["warning_count"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
    }


def build_summary(paths: list[Path], *, generated_at: str | None = None) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    load_errors: list[dict[str, str]] = []
    for path in _expand_paths(paths):
        try:
            records.append(summarize_record(path, _load_json(path)))
        except Exception as exc:
            load_errors.append({"path": str(path), "error": str(exc)})
    completed_count = sum(1 for item in records if item["completed_validation"]["valid"])
    pending_count = sum(1 for item in records if not item["completed_validation"]["valid"])
    all_protected_false = all(
        item["boundary"]["protected_training_flags_false"] and item["boundary"]["generation_side_effect_flags_false"]
        for item in records
    )
    return {
        "report_type": "document_ops_phase24_signoff_record_summary",
        "generated_at": generated_at or _utc_now(),
        "read_only": True,
        "record_count": len(records),
        "overall_status": (
            "manual_signoff_complete_no_training_authorization"
            if records and completed_count == len(records) and all_protected_false
            else "pending_manual_signoff_no_training_authorization"
        ),
        "records": records,
        "load_errors": load_errors,
        "aggregate": {
            "completed_record_count": completed_count,
            "pending_record_count": pending_count,
            "load_error_count": len(load_errors),
            "all_protected_training_flags_false": all_protected_false,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "side_effect_boundary": {
            "actual_reviewer_approval_recorded_by_summary": False,
            "training_execution_started": False,
            "external_dataset_uploaded": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "model_promoted": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize DocumentOps reviewer sign-off JSON records.")
    parser.add_argument("records", nargs="+", type=Path, help="Sign-off JSON file(s) or directories containing JSON files.")
    parser.add_argument("--generated-at", help="Optional ISO timestamp for deterministic report output.")
    parser.add_argument("--output", type=Path, help="Optional output path for the summary JSON.")
    args = parser.parse_args(argv)

    summary = build_summary(args.records, generated_at=args.generated_at)
    output = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if not summary["load_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
