#!/usr/bin/env python3
"""Validate completed DocumentOps reviewer sign-off records.

This script is local-only. It validates human governance metadata and never
starts training, uploads files, calls provider APIs, creates provider jobs, or
promotes models.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_REVIEWER_ROLES = {
    "product_pm_reviewer",
    "ml_ai_owner",
    "compliance_security_reviewer",
    "release_owner",
}

DEFAULT_ALLOWED_DECISIONS = {
    "pending",
    "sign_off_ready_for_human_review",
    "changes_requested",
    "blocked",
}

PROTECTED_FALSE_BOUNDARY_KEYS = {
    "training_execution_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
}

REQUIRED_ACKNOWLEDGEMENTS = {
    "reviewed_phase20_handoff_for_role",
    "does_not_authorize_model_training",
    "does_not_authorize_dataset_upload",
    "does_not_authorize_provider_fine_tune_api_calls",
    "does_not_authorize_provider_job_creation_or_polling",
    "does_not_authorize_model_promotion",
    "blocking_issues_recorded_in_notes",
}


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


def validate_signoff_record(record: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    reviewers = record.get("required_reviewers")
    if not isinstance(reviewers, list):
        errors.append("required_reviewers must be a list")
        reviewers = []

    allowed_decisions = record.get("allowed_decisions") or sorted(DEFAULT_ALLOWED_DECISIONS)
    if not isinstance(allowed_decisions, list) or not all(isinstance(item, str) for item in allowed_decisions):
        errors.append("allowed_decisions must be a list of strings")
        allowed_decisions = sorted(DEFAULT_ALLOWED_DECISIONS)
    allowed_decision_set = set(allowed_decisions)

    reviewer_roles = {
        reviewer.get("reviewer_role")
        for reviewer in reviewers
        if isinstance(reviewer, dict) and isinstance(reviewer.get("reviewer_role"), str)
    }
    missing_roles = sorted(REQUIRED_REVIEWER_ROLES - reviewer_roles)
    if missing_roles:
        errors.append(f"missing required reviewer roles: {', '.join(missing_roles)}")

    for role in sorted(reviewer_roles - REQUIRED_REVIEWER_ROLES):
        warnings.append(f"unexpected reviewer role present: {role}")

    for index, reviewer in enumerate(reviewers, start=1):
        if not isinstance(reviewer, dict):
            errors.append(f"reviewer[{index}] must be an object")
            continue

        role = _as_text(reviewer.get("reviewer_role")) or f"reviewer[{index}]"
        if role in REQUIRED_REVIEWER_ROLES:
            name = _as_text(reviewer.get("reviewer_name"))
            if not name:
                errors.append(f"{role}: reviewer_name is required")

            title_or_team = _as_text(reviewer.get("reviewer_title_or_team"))
            if not title_or_team:
                errors.append(f"{role}: reviewer_title_or_team is required")

            reviewed_at = _as_text(reviewer.get("reviewed_at"))
            if not _is_iso_datetime(reviewed_at):
                errors.append(f"{role}: reviewed_at must be an ISO 8601 datetime")

            decision = _as_text(reviewer.get("decision"))
            if decision not in allowed_decision_set:
                errors.append(f"{role}: decision must be one of {', '.join(sorted(allowed_decision_set))}")
            elif decision == "pending":
                errors.append(f"{role}: decision must not be pending for completed sign-off validation")

            evidence_reviewed = reviewer.get("evidence_reviewed")
            if not isinstance(evidence_reviewed, list) or not evidence_reviewed:
                errors.append(f"{role}: evidence_reviewed must be a non-empty list")
            elif not all(_as_text(item) for item in evidence_reviewed):
                errors.append(f"{role}: evidence_reviewed entries must be non-empty strings")

            acknowledgements = reviewer.get("required_acknowledgements")
            if not isinstance(acknowledgements, dict):
                errors.append(f"{role}: required_acknowledgements must be an object")
                acknowledgements = {}
            missing_acknowledgements = sorted(REQUIRED_ACKNOWLEDGEMENTS - set(acknowledgements))
            if missing_acknowledgements:
                errors.append(f"{role}: missing acknowledgements: {', '.join(missing_acknowledgements)}")
            unchecked = sorted(key for key in REQUIRED_ACKNOWLEDGEMENTS if acknowledgements.get(key) is not True)
            if unchecked:
                errors.append(f"{role}: unchecked acknowledgements: {', '.join(unchecked)}")

            notes = _as_text(reviewer.get("notes"))
            if decision in {"changes_requested", "blocked"} and not notes:
                errors.append(f"{role}: notes are required when decision is {decision}")

    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        errors.append("signoff_boundary must be an object")
        boundary = {}

    missing_boundary = sorted(PROTECTED_FALSE_BOUNDARY_KEYS - set(boundary))
    if missing_boundary:
        errors.append(f"missing signoff_boundary keys: {', '.join(missing_boundary)}")

    for key in sorted(PROTECTED_FALSE_BOUNDARY_KEYS):
        if boundary.get(key) is not False:
            errors.append(f"signoff_boundary.{key} must remain false")

    completion_rule = record.get("completion_rule")
    if isinstance(completion_rule, dict):
        for key in (
            "all_required_reviewers_have_non_empty_name",
            "all_required_reviewers_have_timestamp",
            "all_required_reviewers_decided",
            "all_required_acknowledgements_checked",
            "changes_requested_or_blocked_records_have_notes",
            "manual_signoff_complete",
        ):
            if completion_rule.get(key) is not True:
                errors.append(f"completion_rule.{key} must be true for completed sign-off validation")
    else:
        warnings.append("completion_rule missing; reviewer fields and boundary flags were validated directly")

    return {
        "valid": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "reviewer_roles": sorted(role for role in reviewer_roles if isinstance(role, str)),
        "protected_boundary_keys": sorted(PROTECTED_FALSE_BOUNDARY_KEYS),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a completed DocumentOps reviewer sign-off JSON record.")
    parser.add_argument("record", type=Path, help="Path to a completed reviewer sign-off JSON record.")
    args = parser.parse_args(argv)

    try:
        record = _load_json(args.record)
        result = validate_signoff_record(record)
    except Exception as exc:  # pragma: no cover - defensive CLI error path
        result = {
            "valid": False,
            "error_count": 1,
            "warning_count": 0,
            "errors": [str(exc)],
            "warnings": [],
            "reviewer_roles": [],
            "protected_boundary_keys": sorted(PROTECTED_FALSE_BOUNDARY_KEYS),
        }

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
