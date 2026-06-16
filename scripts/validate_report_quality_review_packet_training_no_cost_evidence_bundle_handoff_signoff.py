#!/usr/bin/env python3
"""Validate a human sign-off record for a no-cost evidence bundle handoff."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_evidence_bundle_handoff_signoff.v1"
SIGNOFF_ID_PATTERN = re.compile(r"rqp_training_no_cost_evidence_bundle_handoff_signoff_[A-Za-z0-9_-]{8,96}")
VALID_DECISIONS = {"pending", "accepted", "changes_requested", "rejected"}
COMPLETED_DECISIONS = {"accepted", "changes_requested", "rejected"}
REQUIRED_ACKS = (
    "evidence_bundle_handoff_reviewed",
    "evidence_bundle_validated",
    "linked_evidence_bundle_files_checked",
    "archive_closure_evidence_checked",
    "aws_no_cost_boundary_acknowledged",
    "no_runtime_services_acknowledged",
    "no_provider_calls_acknowledged",
    "no_training_execution_acknowledged",
    "no_model_promotion_acknowledged",
    "resume_requires_separate_approval_acknowledged",
)
FORBIDDEN_BOUNDARY_KEYS = (
    "actual_operation_resume_approved",
    "service_operation_authorized",
    "server_file_written",
    "persisted_learning_artifact",
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "aws_runtime_authorized",
    "aws_cost_increase_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "training_execution_authorized",
    "model_promotion_authorized",
)
FORBIDDEN_GENERATION_BOUNDARY_KEYS = (
    "actual_operation_resume_approved",
    "server_file_written",
    "persisted_learning_artifact",
    "aws_deploy_started",
    "aws_resource_created",
    "aws_runtime_enabled",
    "aws_cost_increase_allowed",
    "scheduled_job_enabled",
    "cloudwatch_polling_started",
    "external_dataset_upload_started",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "training_execution_started",
    "model_promotion_started",
)


def _load_handoff_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff",
        HANDOFF_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost evidence bundle handoff validator: {HANDOFF_VALIDATOR_PATH}")
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


def _validate_false_boundary(
    boundary: dict[str, Any],
    *,
    keys: Sequence[str],
    prefix: str,
    errors: list[str],
) -> None:
    for key in keys:
        if boundary.get(key) is not False:
            errors.append(f"{prefix}.{key} must be false")


def validate_training_no_cost_evidence_bundle_handoff_signoff(
    payload: dict[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")

    signoff_id = payload.get("signoff_id")
    if not _non_empty_string(signoff_id):
        errors.append("signoff_id must be non-empty")
    elif not SIGNOFF_ID_PATTERN.fullmatch(str(signoff_id)):
        errors.append("signoff_id must match rqp_training_no_cost_evidence_bundle_handoff_signoff_[A-Za-z0-9_-]{8,96}")

    if not _non_empty_string(payload.get("created_at")) and require_complete:
        errors.append("completed signoff requires created_at")

    decision = payload.get("decision")
    if decision not in VALID_DECISIONS:
        errors.append(f"decision must be one of {sorted(VALID_DECISIONS)}")
    completed = decision in COMPLETED_DECISIONS
    if require_complete and not completed:
        errors.append("signoff decision must be completed when --require-complete is used")

    reviewer = _as_dict(payload.get("reviewer"))
    if completed or require_complete:
        for field in ("name", "title_or_team", "reviewed_at"):
            if not _non_empty_string(reviewer.get(field)):
                errors.append(f"completed signoff requires reviewer.{field}")

    handoff_path_value = payload.get("handoff_manifest_path")
    handoff_validation: dict[str, Any] = {}
    if _non_empty_string(handoff_path_value):
        handoff_path = Path(str(handoff_path_value)).expanduser().resolve()
        if not handoff_path.exists():
            errors.append(f"handoff_manifest_path does not exist: {handoff_path}")
        else:
            expected_hash = payload.get("handoff_manifest_sha256")
            if not _non_empty_string(expected_hash) and (completed or require_complete):
                errors.append("completed signoff requires handoff_manifest_sha256")
            elif expected_hash and expected_hash != _sha256(handoff_path):
                errors.append("handoff_manifest_sha256 does not match handoff_manifest_path")
            handoff_validation = _HANDOFF_VALIDATOR.validate_training_no_cost_evidence_bundle_handoff(handoff_path)
            if completed and handoff_validation.get("ok") is not True:
                errors.append("completed signoff requires valid no-cost evidence bundle handoff manifest")
    elif completed or require_complete:
        errors.append("completed signoff requires handoff_manifest_path")

    evidence_reviewed = _as_list(payload.get("evidence_reviewed"))
    if completed and not evidence_reviewed:
        errors.append("completed signoff requires evidence_reviewed")

    findings = _as_dict(payload.get("findings"))
    if decision == "accepted" and not _non_empty_string(findings.get("summary")):
        errors.append("accepted signoff requires findings.summary")
    if decision in {"changes_requested", "rejected"}:
        changes = _as_list(findings.get("changes_requested"))
        if not changes:
            errors.append(f"{decision} signoff requires findings.changes_requested")

    acknowledgements = _as_dict(payload.get("acknowledgements"))
    if completed:
        for key in REQUIRED_ACKS:
            if acknowledgements.get(key) is not True:
                errors.append(f"completed signoff requires acknowledgements.{key}=true")

    _validate_false_boundary(
        _as_dict(payload.get("signoff_boundary")),
        keys=FORBIDDEN_BOUNDARY_KEYS,
        prefix="signoff_boundary",
        errors=errors,
    )
    if "generation_boundary" in payload:
        _validate_false_boundary(
            _as_dict(payload.get("generation_boundary")),
            keys=FORBIDDEN_GENERATION_BOUNDARY_KEYS,
            prefix="generation_boundary",
            errors=errors,
        )

    if completed:
        warnings.append(
            "completed no-cost evidence bundle handoff signoff records evidence review only; "
            "it does not authorize service resume, AWS cost, provider calls, training, or model promotion"
        )

    return {
        "report_type": "report_quality_training_no_cost_evidence_bundle_handoff_signoff_validation",
        "ok": not errors,
        "completed": completed and not errors,
        "require_complete": require_complete,
        "decision": decision,
        "signoff_id": payload.get("signoff_id"),
        "handoff_validation_ok": handoff_validation.get("ok") if handoff_validation else None,
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a no-cost evidence bundle handoff sign-off record.")
    parser.add_argument("signoff", type=Path, help="Path to no-cost evidence bundle handoff sign-off JSON.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.signoff)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "report_type": "report_quality_training_no_cost_evidence_bundle_handoff_signoff_validation",
            "ok": False,
            "completed": False,
            "require_complete": bool(args.require_complete),
            "errors": [str(exc)],
            "warnings": [],
        }
    else:
        result = validate_training_no_cost_evidence_bundle_handoff_signoff(
            payload,
            require_complete=bool(args.require_complete),
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost evidence bundle handoff signoff validated")
        print(f"completed={str(result['completed']).lower()}")
        print(f"decision={result.get('decision')}")
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training no-cost evidence bundle handoff signoff validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
