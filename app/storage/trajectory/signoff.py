"""Reviewer sign-off record validation and summary helpers."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.storage.trajectory.constants import (
    _SIGNOFF_DEFAULT_ALLOWED_DECISIONS,
    _SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS,
    _SIGNOFF_PROTECTED_FALSE_GENERATION_KEYS,
    _SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS,
    _SIGNOFF_REQUIRED_REVIEWER_ROLES,
)
from app.storage.trajectory.redaction import _dedupe


def _list_reviewer_signoff_record_paths(directory: Path, *, limit: int) -> list[Path]:
    if not directory.is_dir():
        return []
    paths = [
        path
        for path in directory.glob("*.json")
        if path.is_file() and Path(path.name).name == path.name
    ]
    paths.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return paths[:limit]


def _load_json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("sign-off record must be a JSON object")
    return data


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


def _signoff_acknowledgement_summary(value: Any) -> dict[str, Any]:
    acknowledgements = value if isinstance(value, dict) else {}
    checked = sum(1 for key in _SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS if acknowledgements.get(key) is True)
    total = len(_SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS)
    return {
        "checked": checked,
        "total": total,
        "complete": checked == total,
        "unchecked": sorted(
            key
            for key in _SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS
            if acknowledgements.get(key) is not True
        ),
    }


def _summarize_signoff_reviewer(reviewer: dict[str, Any]) -> dict[str, Any]:
    role = _as_text(reviewer.get("reviewer_role"))
    decision = _as_text(reviewer.get("decision")) or "missing"
    reviewed_at = _as_text(reviewer.get("reviewed_at"))
    evidence = reviewer.get("evidence_reviewed")
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    acknowledgements = _signoff_acknowledgement_summary(reviewer.get("required_acknowledgements"))
    notes = _as_text(reviewer.get("notes"))
    complete = all(
        [
            role in _SIGNOFF_REQUIRED_REVIEWER_ROLES,
            bool(_as_text(reviewer.get("reviewer_name"))),
            bool(_as_text(reviewer.get("reviewer_title_or_team"))),
            _is_iso_datetime(reviewed_at),
            decision in _SIGNOFF_DEFAULT_ALLOWED_DECISIONS,
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


def _signoff_boundary_summary(record: dict[str, Any]) -> dict[str, Any]:
    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        boundary = {}
    generation_boundary = record.get("generation_boundary")
    if not isinstance(generation_boundary, dict):
        generation_boundary = {}
    protected = {key: boundary.get(key) for key in sorted(_SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS)}
    generation_side_effects = {
        key: generation_boundary.get(key, False)
        for key in sorted(_SIGNOFF_PROTECTED_FALSE_GENERATION_KEYS)
    }
    return {
        "actual_reviewer_approval_recorded": boundary.get("actual_reviewer_approval_recorded") is True,
        "protected_training_flags": protected,
        "generation_side_effect_flags": generation_side_effects,
        "training_execution_authorized": False,
        "external_dataset_upload_authorized": False,
        "provider_fine_tune_api_call_authorized": False,
        "provider_job_creation_authorized": False,
        "provider_job_polling_authorized": False,
        "model_candidate_emission_authorized": False,
        "model_promotion_authorized": False,
        "protected_training_flags_false": all(value is False for value in protected.values()),
        "generation_side_effect_flags_false": all(value is False for value in generation_side_effects.values()),
    }


def _validate_reviewer_signoff_record(record: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    reviewers = record.get("required_reviewers")
    if not isinstance(reviewers, list):
        errors.append("required_reviewers must be a list")
        reviewers = []
    allowed_decisions = record.get("allowed_decisions") or sorted(_SIGNOFF_DEFAULT_ALLOWED_DECISIONS)
    if not isinstance(allowed_decisions, list) or not all(isinstance(item, str) for item in allowed_decisions):
        errors.append("allowed_decisions must be a list of strings")
        allowed_decisions = sorted(_SIGNOFF_DEFAULT_ALLOWED_DECISIONS)
    allowed_decision_set = set(allowed_decisions)
    reviewer_roles = {
        reviewer.get("reviewer_role")
        for reviewer in reviewers
        if isinstance(reviewer, dict) and isinstance(reviewer.get("reviewer_role"), str)
    }
    missing_roles = sorted(_SIGNOFF_REQUIRED_REVIEWER_ROLES - reviewer_roles)
    if missing_roles:
        errors.append(f"missing required reviewer roles: {', '.join(missing_roles)}")
    for role in sorted(reviewer_roles - _SIGNOFF_REQUIRED_REVIEWER_ROLES):
        warnings.append(f"unexpected reviewer role present: {role}")
    for index, reviewer in enumerate(reviewers, start=1):
        if not isinstance(reviewer, dict):
            errors.append(f"reviewer[{index}] must be an object")
            continue
        role = _as_text(reviewer.get("reviewer_role")) or f"reviewer[{index}]"
        if role not in _SIGNOFF_REQUIRED_REVIEWER_ROLES:
            continue
        if not _as_text(reviewer.get("reviewer_name")):
            errors.append(f"{role}: reviewer_name is required")
        if not _as_text(reviewer.get("reviewer_title_or_team")):
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
        missing_acknowledgements = sorted(_SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS - set(acknowledgements))
        if missing_acknowledgements:
            errors.append(f"{role}: missing acknowledgements: {', '.join(missing_acknowledgements)}")
        unchecked = sorted(
            key
            for key in _SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS
            if acknowledgements.get(key) is not True
        )
        if unchecked:
            errors.append(f"{role}: unchecked acknowledgements: {', '.join(unchecked)}")
        notes = _as_text(reviewer.get("notes"))
        if decision in {"changes_requested", "blocked"} and not notes:
            errors.append(f"{role}: notes are required when decision is {decision}")

    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        errors.append("signoff_boundary must be an object")
        boundary = {}
    missing_boundary = sorted(_SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS - set(boundary))
    if missing_boundary:
        errors.append(f"missing signoff_boundary keys: {', '.join(missing_boundary)}")
    for key in sorted(_SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS):
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
    }


def _signoff_record_status(
    validation: dict[str, Any],
    boundary: dict[str, Any],
    decision_counts: dict[str, int],
) -> str:
    if not boundary["protected_training_flags_false"] or not boundary["generation_side_effect_flags_false"]:
        return "attention_required_boundary_violation"
    if validation["valid"]:
        return "manual_signoff_complete_no_training_authorization"
    if decision_counts.get("blocked") or decision_counts.get("changes_requested"):
        return "manual_follow_up_required_no_training_authorization"
    return "pending_manual_signoff_no_training_authorization"


def _summarize_reviewer_signoff_record(filename: str, record: dict[str, Any]) -> dict[str, Any]:
    validation = _validate_reviewer_signoff_record(record)
    reviewers_raw = record.get("required_reviewers")
    reviewers = (
        [_summarize_signoff_reviewer(item) for item in reviewers_raw if isinstance(item, dict)]
        if isinstance(reviewers_raw, list)
        else []
    )
    boundary = _signoff_boundary_summary(record)
    completed_roles = sorted(item["reviewer_role"] for item in reviewers if item["complete"])
    pending_roles = sorted(
        {
            item["reviewer_role"] or "unknown"
            for item in reviewers
            if item["decision"] == "pending" or not item["complete"]
        }
    )
    decision_counts: dict[str, int] = {}
    for reviewer in reviewers:
        decision = reviewer["decision"] or "missing"
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    return {
        "filename": filename,
        "report_type": record.get("report_type", ""),
        "signoff_record_id": record.get("signoff_record_id", ""),
        "created_at": record.get("created_at", ""),
        "record_status": _signoff_record_status(validation, boundary, decision_counts),
        "reviewers": reviewers,
        "reviewers_complete_count": len(completed_roles),
        "pending_reviewer_count": len(pending_roles),
        "changes_requested_count": int(decision_counts.get("changes_requested") or 0),
        "blocked_count": int(decision_counts.get("blocked") or 0),
        "completed_reviewer_roles": completed_roles,
        "pending_reviewer_roles": pending_roles,
        "decision_counts": decision_counts,
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


def _reviewer_signoff_summary_blockers(
    *,
    records: list[dict[str, Any]],
    load_errors: list[dict[str, str]],
    overall_status: str,
) -> list[str]:
    blockers: list[str] = []
    if overall_status == "no_signoff_records_found":
        blockers.append("no_reviewer_signoff_records_found")
    if load_errors:
        blockers.append("reviewer_signoff_record_load_errors")
    for record in records:
        status = str(record.get("record_status") or "")
        if status == "attention_required_boundary_violation":
            blockers.append(f"{record.get('filename')}: boundary_violation")
        elif status == "manual_follow_up_required_no_training_authorization":
            blockers.append(f"{record.get('filename')}: reviewer_follow_up_required")
        elif status == "pending_manual_signoff_no_training_authorization":
            blockers.append(f"{record.get('filename')}: pending_manual_signoff")
    return _dedupe(blockers)
