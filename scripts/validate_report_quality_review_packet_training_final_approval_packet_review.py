#!/usr/bin/env python3
"""Validate a human review record for a report quality training final approval packet."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKET_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_packet.py"
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_final_approval_packet_review.v1"
VALID_DECISIONS = {"pending", "packet_review_complete", "changes_requested", "rejected"}
COMPLETED_DECISIONS = {"packet_review_complete", "changes_requested", "rejected"}
VALID_NEXT_STEPS = {"none", "prepare_final_approval_record_template", "revise_final_approval_packet", "archive_no_training"}
REQUIRED_ACKS = (
    "final_approval_packet_validated",
    "required_approver_roles_reviewed",
    "job_spec_not_started_reviewed",
    "final_training_approval_not_recorded",
    "no_dataset_upload_authorized",
    "no_provider_fine_tune_authorized",
    "no_provider_job_authorized",
    "no_training_execution_authorized",
    "no_model_promotion_authorized",
)
FORBIDDEN_FALSE_KEYS = (
    "actual_training_approval_recorded",
    "final_training_approval_granted",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
)
FORBIDDEN_STARTED_KEYS = (
    "actual_training_approval_recorded",
    "final_training_approval_granted",
    "server_file_written",
    "persisted_learning_artifact",
    "external_dataset_upload_started",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "training_execution_started",
    "model_promotion_started",
)


def _load_packet_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_final_approval_packet",
        PACKET_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load final approval packet validator: {PACKET_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PACKET_VALIDATOR = _load_packet_validator()


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


def validate_training_final_approval_packet_review(
    payload: dict[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if not _non_empty_string(payload.get("review_id")):
        errors.append("review_id must be non-empty")
    if require_complete and not _non_empty_string(payload.get("created_at")):
        errors.append("completed packet review requires created_at")

    decision = payload.get("decision")
    if decision not in VALID_DECISIONS:
        errors.append(f"decision must be one of {sorted(VALID_DECISIONS)}")
    completed = decision in COMPLETED_DECISIONS
    if require_complete and not completed:
        errors.append("packet review decision must be completed when --require-complete is used")

    requested_next_step = payload.get("requested_next_step")
    if requested_next_step not in VALID_NEXT_STEPS:
        errors.append(f"requested_next_step must be one of {sorted(VALID_NEXT_STEPS)}")
    if completed:
        expected_next_steps = {
            "packet_review_complete": "prepare_final_approval_record_template",
            "changes_requested": "revise_final_approval_packet",
            "rejected": "archive_no_training",
        }
        if requested_next_step != expected_next_steps.get(str(decision)):
            errors.append(f"{decision} decision requires requested_next_step={expected_next_steps.get(str(decision))}")

    packet_path_value = payload.get("packet_manifest_path")
    packet_validation: dict[str, Any] = {}
    if _non_empty_string(packet_path_value):
        packet_path = Path(str(packet_path_value)).expanduser().resolve()
        if not packet_path.exists() or not packet_path.is_file():
            errors.append(f"packet_manifest_path does not exist: {packet_path}")
        else:
            expected_hash = payload.get("packet_manifest_sha256")
            if expected_hash and expected_hash != _sha256(packet_path):
                errors.append("packet_manifest_sha256 does not match packet_manifest_path")
            packet_validation = _PACKET_VALIDATOR.validate_training_final_approval_packet(packet_path)
            if completed and packet_validation.get("ok") is not True:
                errors.append("completed review requires valid final approval packet")
    elif completed or require_complete:
        errors.append("completed review requires packet_manifest_path")

    reviewers = _as_list(payload.get("reviewers"))
    if completed or require_complete:
        if not reviewers:
            errors.append("completed review requires at least one reviewer")
        for index, reviewer_value in enumerate(reviewers, start=1):
            reviewer = _as_dict(reviewer_value)
            for field in ("name", "role_or_team", "reviewed_at"):
                if not _non_empty_string(reviewer.get(field)):
                    errors.append(f"completed review requires reviewers[{index}].{field}")

    if completed or require_complete:
        for field in ("review_summary", "decision_rationale"):
            if not _non_empty_string(payload.get(field)):
                errors.append(f"completed review requires {field}")
        if not _as_list(payload.get("evidence_reviewed")):
            errors.append("completed review requires evidence_reviewed")

    if decision == "changes_requested" and not _as_list(payload.get("conditions")):
        errors.append("changes_requested review requires conditions")

    acknowledgements = _as_dict(payload.get("acknowledgements"))
    if completed:
        for key in REQUIRED_ACKS:
            if acknowledgements.get(key) is not True:
                errors.append(f"completed review requires acknowledgements.{key}=true")

    _validate_boundary(
        _as_dict(payload.get("review_boundary")),
        keys=FORBIDDEN_FALSE_KEYS,
        prefix="review_boundary",
        errors=errors,
    )
    _validate_boundary(
        _as_dict(payload.get("generation_boundary")),
        keys=FORBIDDEN_STARTED_KEYS,
        prefix="generation_boundary",
        errors=errors,
    )

    if completed:
        warnings.append("completed packet reviews authorize approval-record preparation only; they do not authorize training")

    return {
        "report_type": "report_quality_training_final_approval_packet_review_validation",
        "ok": not errors,
        "completed": completed and not errors,
        "require_complete": require_complete,
        "decision": decision,
        "review_id": payload.get("review_id"),
        "requested_next_step": requested_next_step,
        "packet_validation_ok": packet_validation.get("ok") if packet_validation else None,
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a report quality final approval packet review record.")
    parser.add_argument("review_record", type=Path, help="Path to final approval packet review JSON.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.review_record)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "report_type": "report_quality_training_final_approval_packet_review_validation",
            "ok": False,
            "completed": False,
            "require_complete": bool(args.require_complete),
            "errors": [str(exc)],
            "warnings": [],
        }
    else:
        result = validate_training_final_approval_packet_review(payload, require_complete=bool(args.require_complete))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training final approval packet review validated")
        print(f"completed={str(result['completed']).lower()}")
        print(f"decision={result.get('decision')}")
        print(f"requested_next_step={result.get('requested_next_step')}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training final approval packet review validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
