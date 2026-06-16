#!/usr/bin/env python3
"""Validate a human discussion decision record for report quality training planning."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_discussion_handoff.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_discussion_decision.v1"
VALID_DECISIONS = {"pending", "plan_draft_requested", "changes_requested", "do_not_proceed"}
COMPLETED_DECISIONS = {"plan_draft_requested", "changes_requested", "do_not_proceed"}
VALID_NEXT_STEPS = {"none", "draft_training_experiment_plan", "revise_evidence_packet", "archive_no_training"}
REQUIRED_ACKS = (
    "training_discussion_handoff_validated",
    "readiness_manifest_reviewed",
    "signoff_summary_reviewed",
    "evidence_file_hashes_reviewed",
    "no_dataset_upload_authorized",
    "no_provider_fine_tune_authorized",
    "no_training_execution_authorized",
    "no_model_promotion_authorized",
)
FORBIDDEN_FALSE_KEYS = (
    "actual_training_approval_recorded",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
)
FORBIDDEN_STARTED_KEYS = (
    "actual_training_approval_recorded",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_started",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "training_execution_started",
    "model_promotion_started",
)


def _load_handoff_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_discussion_handoff",
        HANDOFF_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load handoff validator: {HANDOFF_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HANDOFF_VALIDATOR = _load_handoff_validator()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_boundary(
    boundary: dict[str, Any],
    *,
    keys: Sequence[str],
    prefix: str,
    errors: list[str],
) -> None:
    for key in keys:
        if boundary.get(key) is not False:
            errors.append(f"{prefix}.{key} must be false")


def validate_training_discussion_decision(
    payload: dict[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if not _non_empty_string(payload.get("decision_id")):
        errors.append("decision_id must be non-empty")
    if require_complete and not _non_empty_string(payload.get("created_at")):
        errors.append("completed decision requires created_at")

    decision = payload.get("decision")
    if decision not in VALID_DECISIONS:
        errors.append(f"decision must be one of {sorted(VALID_DECISIONS)}")
    completed = decision in COMPLETED_DECISIONS
    if require_complete and not completed:
        errors.append("training discussion decision must be completed when --require-complete is used")

    requested_next_step = payload.get("requested_next_step")
    if requested_next_step not in VALID_NEXT_STEPS:
        errors.append(f"requested_next_step must be one of {sorted(VALID_NEXT_STEPS)}")
    if completed:
        expected_next_steps = {
            "plan_draft_requested": "draft_training_experiment_plan",
            "changes_requested": "revise_evidence_packet",
            "do_not_proceed": "archive_no_training",
        }
        if requested_next_step != expected_next_steps.get(str(decision)):
            errors.append(f"{decision} decision requires requested_next_step={expected_next_steps.get(str(decision))}")

    handoff_path_value = payload.get("discussion_handoff_manifest_path")
    handoff_validation: dict[str, Any] = {}
    if _non_empty_string(handoff_path_value):
        handoff_path = Path(str(handoff_path_value)).expanduser().resolve()
        if not handoff_path.exists() or not handoff_path.is_file():
            errors.append(f"discussion_handoff_manifest_path does not exist: {handoff_path}")
        else:
            expected_hash = payload.get("discussion_handoff_manifest_sha256")
            if expected_hash and expected_hash != _sha256(handoff_path):
                errors.append("discussion_handoff_manifest_sha256 does not match discussion_handoff_manifest_path")
            handoff_validation = _HANDOFF_VALIDATOR.validate_training_discussion_handoff_manifest(handoff_path)
            if completed and handoff_validation.get("ok") is not True:
                errors.append("completed decision requires valid training discussion handoff")
    elif completed or require_complete:
        errors.append("completed decision requires discussion_handoff_manifest_path")

    participants = _as_list(payload.get("participants"))
    if completed or require_complete:
        if not participants:
            errors.append("completed decision requires at least one participant")
        for index, participant_value in enumerate(participants, start=1):
            participant = _as_dict(participant_value)
            for field in ("name", "role_or_team", "reviewed_at"):
                if not _non_empty_string(participant.get(field)):
                    errors.append(f"completed decision requires participants[{index}].{field}")

    if completed or require_complete:
        for field in ("discussion_summary", "decision_rationale"):
            if not _non_empty_string(payload.get(field)):
                errors.append(f"completed decision requires {field}")
        if not _as_list(payload.get("evidence_reviewed")):
            errors.append("completed decision requires evidence_reviewed")

    if decision == "changes_requested" and not _as_list(payload.get("conditions")):
        errors.append("changes_requested decision requires conditions")

    acknowledgements = _as_dict(payload.get("acknowledgements"))
    if completed:
        for key in REQUIRED_ACKS:
            if acknowledgements.get(key) is not True:
                errors.append(f"completed decision requires acknowledgements.{key}=true")

    _validate_boundary(
        _as_dict(payload.get("decision_boundary")),
        keys=FORBIDDEN_FALSE_KEYS,
        prefix="decision_boundary",
        errors=errors,
    )
    _validate_boundary(
        _as_dict(payload.get("generation_boundary")),
        keys=FORBIDDEN_STARTED_KEYS,
        prefix="generation_boundary",
        errors=errors,
    )

    if completed:
        warnings.append("completed discussion decisions authorize planning only; they do not authorize training")

    return {
        "report_type": "report_quality_review_packet_training_discussion_decision_validation",
        "ok": not errors,
        "completed": completed and not errors,
        "require_complete": require_complete,
        "decision": decision,
        "decision_id": payload.get("decision_id"),
        "requested_next_step": requested_next_step,
        "handoff_validation_ok": handoff_validation.get("ok") if handoff_validation else None,
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a report quality training discussion decision record.")
    parser.add_argument("decision_record", type=Path, help="Path to training discussion decision JSON.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.decision_record)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "report_type": "report_quality_review_packet_training_discussion_decision_validation",
            "ok": False,
            "completed": False,
            "require_complete": bool(args.require_complete),
            "errors": [str(exc)],
            "warnings": [],
        }
    else:
        result = validate_training_discussion_decision(payload, require_complete=bool(args.require_complete))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training discussion decision validated")
        print(f"completed={str(result['completed']).lower()}")
        print(f"decision={result.get('decision')}")
        print(f"requested_next_step={result.get('requested_next_step')}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training discussion decision validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
