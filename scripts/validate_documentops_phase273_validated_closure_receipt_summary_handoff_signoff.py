#!/usr/bin/env python3
"""Validate a DocumentOps Phase 273 validated closure summary handoff sign-off record."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_documentops_phase272_validated_closure_receipt_summary_handoff import (  # noqa: E402
    validate_documentops_phase272_validated_closure_receipt_summary_handoff,
)


EXPECTED_SCHEMA = "decisiondoc_documentops_phase274_validated_closure_receipt_summary_handoff_signoff.v1"
EXPECTED_VALIDATION_REPORT_TYPE = (
    "document_ops_phase274_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_validation"
)
SOURCE_HANDOFF_PATH = (
    "docs/specs/hermes_decisiondoc_agent/"
    "phase273_local_feature_completion_validated_closure_receipt_summary_handoff/"
    "validated_closure_receipt_summary_handoff.json"
)
SOURCE_HANDOFF_VALIDATOR_PATH = (
    "scripts/validate_documentops_phase272_validated_closure_receipt_summary_handoff.py"
)
SIGNOFF_ID_PREFIX = "documentops_local_feature_completion_phase273_validated_closure_receipt_summary_handoff_signoff_"
SIGNOFF_ID_PATTERN = re.compile(rf"{SIGNOFF_ID_PREFIX}[A-Za-z0-9_-]{{8,96}}")
VALID_DECISIONS = {"pending", "accepted", "changes_requested", "rejected"}
COMPLETED_DECISIONS = {"accepted", "changes_requested", "rejected"}
REQUIRED_ACKS = (
    "phase273_validated_closure_receipt_summary_handoff_reviewed",
    "phase271_summary_chain_reviewed",
    "phase272_summary_validation_reviewed",
    "operator_actions_understood",
    "service_freeze_acknowledged",
    "resume_block_acknowledged",
    "aws_no_cost_boundary_acknowledged",
    "no_production_ui_reexecution_acknowledged",
    "no_provider_calls_acknowledged",
    "no_dataset_upload_acknowledged",
    "no_training_execution_acknowledged",
    "no_model_promotion_acknowledged",
    "separate_approval_required_acknowledged",
)
REQUIRED_TRUE_BOUNDARY_FIELDS = (
    "evidence_only_signoff",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_FALSE_BOUNDARY_FIELDS = (
    "actual_reviewer_approval_recorded_by_template",
    "service_resume_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "production_download_open_verification_authorized",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_dataset_upload_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
)
FORBIDDEN_TRUE_KEYS = set(REQUIRED_FALSE_BOUNDARY_FIELDS) | {
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_handoff",
    "actual_reviewer_approval_recorded_by_signoff",
    "actual_reviewer_approval_recorded_by_summary",
    "actual_reviewer_approval_recorded_by_validator",
    "actual_operation_resume_approved",
    "service_operation_allowed",
    "service_operation_authorized",
    "aws_deploy_started",
    "aws_resource_created",
    "scheduled_job_enabled",
    "cloudwatch_polling_started",
    "provider_api_calls_allowed",
    "provider_job_created",
    "provider_job_polled",
    "external_upload_allowed",
    "external_dataset_uploaded",
    "training_execution_allowed",
    "training_execution_started",
    "model_candidate_emitted",
    "model_promotion_allowed",
    "model_training_started",
    "model_promoted",
}
PASS_MESSAGE = "PASS documentops phase274 validated closure receipt summary handoff sign-off validated"
FAIL_MESSAGE = "FAIL documentops phase274 validated closure receipt summary handoff sign-off validation failed"


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


def _repo_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_forbidden_true(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_TRUE_KEYS and child is not False:
                findings.append(f"{child_path} must be false")
            findings.extend(_scan_forbidden_true(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_scan_forbidden_true(child, path=f"{path}[{index}]"))
    return findings


def validate_documentops_phase273_validated_closure_receipt_summary_handoff_signoff(
    payload: dict[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA}")
    if payload.get("phase") != 274:
        errors.append("phase must be 274")
    expected_scope = "evidence_only_review_of_phase273_validated_closure_receipt_summary_handoff"
    if payload.get("signoff_scope") != expected_scope:
        errors.append(f"signoff_scope must be {expected_scope}")

    signoff_id = payload.get("signoff_id")
    if not _non_empty_string(signoff_id):
        errors.append("signoff_id must be non-empty")
    elif not SIGNOFF_ID_PATTERN.fullmatch(str(signoff_id)):
        errors.append(f"signoff_id must match {SIGNOFF_ID_PREFIX}[A-Za-z0-9_-]{{8,96}}")

    decision = payload.get("decision")
    if decision not in VALID_DECISIONS:
        errors.append(f"decision must be one of {sorted(VALID_DECISIONS)}")
    completed = decision in COMPLETED_DECISIONS
    if require_complete and not completed:
        errors.append("signoff decision must be completed when --require-complete is used")
    if completed and str(signoff_id).endswith("_TEMPLATE"):
        errors.append("completed signoff must use a non-template signoff_id")
    if (completed or require_complete) and not _non_empty_string(payload.get("created_at")):
        errors.append("completed signoff requires created_at")

    source = _as_dict(payload.get("source_handoff"))
    source_path_value = source.get("path")
    source_validation: dict[str, Any] = {}
    if source_path_value != SOURCE_HANDOFF_PATH:
        errors.append("source_handoff.path must reference the Phase 273 validated handoff JSON")
        source_path = _repo_path(SOURCE_HANDOFF_PATH)
    else:
        source_path = _repo_path(source_path_value)

    if not source_path.exists():
        errors.append(f"source_handoff.path must exist: {source_path}")
    else:
        if source.get("sha256") != _sha256_file(source_path):
            errors.append("source_handoff.sha256 must match the Phase 273 validated handoff JSON")
        source_validation = validate_documentops_phase272_validated_closure_receipt_summary_handoff(
            source_path
        )
        if source_validation.get("ok") is not True:
            errors.append("source_handoff must pass Phase 273 validation")
            for error in source_validation.get("errors", []):
                errors.append(f"source_handoff: {error}")

    validator_path = _repo_path(SOURCE_HANDOFF_VALIDATOR_PATH)
    if source.get("validator") != SOURCE_HANDOFF_VALIDATOR_PATH:
        errors.append(f"source_handoff.validator must be {SOURCE_HANDOFF_VALIDATOR_PATH}")
    if not validator_path.exists():
        errors.append(f"source_handoff.validator path must exist: {SOURCE_HANDOFF_VALIDATOR_PATH}")
    elif source.get("validator_sha256") != _sha256_file(validator_path):
        errors.append(f"source_handoff.validator_sha256 must match {SOURCE_HANDOFF_VALIDATOR_PATH}")
    if source.get("validator_result") != "pass":
        errors.append("source_handoff.validator_result must be pass")
    if source.get("service_operation_state") != "freeze_preserved":
        errors.append("source_handoff.service_operation_state must be freeze_preserved")

    reviewer = _as_dict(payload.get("reviewer"))
    if completed or require_complete:
        for field in ("name", "title_or_team", "reviewed_at"):
            if not _non_empty_string(reviewer.get(field)):
                errors.append(f"completed signoff requires reviewer.{field}")

    evidence_reviewed = _as_list(payload.get("evidence_reviewed"))
    if completed and not evidence_reviewed:
        errors.append("completed signoff requires evidence_reviewed")

    findings = _as_dict(payload.get("findings"))
    if decision == "accepted" and not _non_empty_string(findings.get("summary")):
        errors.append("accepted signoff requires findings.summary")
    if decision in {"changes_requested", "rejected"} and not _as_list(findings.get("changes_requested")):
        errors.append(f"{decision} signoff requires findings.changes_requested")

    acknowledgements = _as_dict(payload.get("acknowledgements"))
    if completed:
        for key in REQUIRED_ACKS:
            if acknowledgements.get(key) is not True:
                errors.append(f"completed signoff requires acknowledgements.{key}=true")

    boundary = _as_dict(payload.get("signoff_boundary"))
    for field in REQUIRED_TRUE_BOUNDARY_FIELDS:
        if boundary.get(field) is not True:
            errors.append(f"signoff_boundary.{field} must be true")
    for field in REQUIRED_FALSE_BOUNDARY_FIELDS:
        if boundary.get(field) is not False:
            errors.append(f"signoff_boundary.{field} must be false")
    if boundary.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("signoff_boundary.aws_cost_boundary must be no_cost_increase")
    if boundary.get("training_boundary") != "not_authorized":
        errors.append("signoff_boundary.training_boundary must be not_authorized")

    for finding in _scan_forbidden_true(payload):
        errors.append(f"documentops_phase273_validated_closure_receipt_summary_handoff_signoff: {finding}")

    if completed and not errors:
        warnings.append(
            "completed Phase 273 validated closure receipt summary handoff sign-off records evidence review only; "
            "it does not authorize service resume, AWS cost, provider calls, training, or model promotion"
        )

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "completed": completed and not errors,
        "require_complete": require_complete,
        "decision": decision,
        "signoff_id": payload.get("signoff_id"),
        "source_handoff_validation_ok": source_validation.get("ok") if source_validation else None,
        "service_operation_state": "freeze_preserved",
        "aws_cost_boundary": boundary.get("aws_cost_boundary", ""),
        "training_boundary": boundary.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a DocumentOps Phase 273 validated closure summary handoff sign-off record."
    )
    parser.add_argument("signoff", type=Path, help="Path to Phase 274 handoff sign-off JSON.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.signoff)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "completed": False,
            "require_complete": bool(args.require_complete),
            "decision": "",
            "signoff_id": "",
            "source_handoff_validation_ok": None,
            "service_operation_state": "freeze_preserved",
            "aws_cost_boundary": "",
            "training_boundary": "",
            "errors": [str(exc)],
            "warnings": [],
        }
    else:
        result = validate_documentops_phase273_validated_closure_receipt_summary_handoff_signoff(
            payload,
            require_complete=bool(args.require_complete),
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(PASS_MESSAGE)
        print(f"completed={str(result['completed']).lower()}")
        print(f"decision={result['decision']}")
        print(f"source_handoff_validation_ok={str(result['source_handoff_validation_ok']).lower()}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print(FAIL_MESSAGE)
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
