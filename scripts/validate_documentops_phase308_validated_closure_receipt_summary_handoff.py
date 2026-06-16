#!/usr/bin/env python3
"""Validate the DocumentOps Phase 307/308 validated closure receipt summary handoff."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


DEFAULT_HANDOFF_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/"
    "phase309_local_feature_completion_validated_closure_receipt_summary_handoff/"
    "validated_closure_receipt_summary_handoff.json"
)
EXPECTED_REPORT_TYPE = (
    "document_ops_phase309_local_feature_completion_validated_closure_receipt_summary_handoff"
)
EXPECTED_VALIDATION_REPORT_TYPE = (
    "document_ops_phase309_local_feature_completion_validated_closure_receipt_summary_handoff_validation"
)
EXPECTED_STATUS = (
    "local_feature_completion_validated_closure_receipt_summary_handoff_ready_no_aws_no_training_authorization"
)
READY_STATUS = "all_phase306_validated_closure_receipts_confirm_no_cost_freeze"
HANDOFF_VALID_KEY = "phase307_validated_closure_receipt_summary_handoff_valid"
SOURCE_SUMMARY_VALIDATION_CONTRACT_PATH = (
    "docs/specs/hermes_decisiondoc_agent/"
    "phase308_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_validation/"
    "validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_validation_contract.json"
)
SOURCE_SUMMARY_CONTRACT_PATH = (
    "docs/specs/hermes_decisiondoc_agent/"
    "phase307_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary/"
    "validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_contract.json"
)
SOURCE_SUMMARY_VALIDATOR_PATH = "scripts/validate_documentops_phase307_validated_closure_receipt_summary.py"
SOURCE_SUMMARY_REPORTER_PATH = "scripts/summarize_documentops_phase306_validated_closure_receipts.py"
REQUIRED_RECIPIENTS = {
    "release_owner",
    "operator",
    "product_pm_reviewer",
    "ml_ai_owner",
    "compliance_security_reviewer",
}
REQUIRED_ACTION_IDS = {
    "generate_phase307_summary",
    "run_phase308_validator",
    "confirm_validated_local_phase307_summary",
    "confirm_no_cost_boundary",
    "preserve_service_freeze",
    "require_separate_resume_approval",
}
REQUIRED_TRUE_BOUNDARY_FIELDS = (
    "local_phase307_validated_closure_receipt_summary_handoff_recorded",
    "source_summary_validation_contract_valid",
    "generated_summary_validation_passed",
    "operator_handoff_ready",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_FALSE_BOUNDARY_FIELDS = (
    "actual_reviewer_approval_recorded_by_handoff",
    "service_resume_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "production_download_open_verification_authorized",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "aws_deploy_started",
    "aws_resource_created",
    "scheduled_job_enabled",
    "cloudwatch_polling_started",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "external_dataset_uploaded",
    "training_execution_started",
    "model_candidate_emitted",
    "model_promoted",
)
FORBIDDEN_TRUE_KEYS = set(REQUIRED_FALSE_BOUNDARY_FIELDS) | {
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_summary",
    "actual_reviewer_approval_recorded_by_validator",
    "actual_operation_resume_approved",
    "service_operation_allowed",
    "service_operation_authorized",
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "provider_api_calls_allowed",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_upload_allowed",
    "external_dataset_upload_authorized",
    "training_execution_allowed",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_allowed",
    "model_training_started",
}
PASS_MESSAGE = "PASS documentops phase309 validated closure receipt summary handoff validated"
FAIL_MESSAGE = "FAIL documentops phase309 validated closure receipt summary handoff validation failed"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def validate_documentops_phase308_validated_closure_receipt_summary_handoff(
    handoff_path: Path = DEFAULT_HANDOFF_PATH,
) -> dict[str, Any]:
    resolved_handoff = handoff_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        handoff = _load_json(resolved_handoff)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "handoff_path": str(resolved_handoff),
            "errors": [str(exc)],
            "warnings": [],
        }

    if handoff.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if handoff.get("phase") != 309:
        errors.append("phase must be 309")
    if handoff.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")
    expected_scope = "operator_handoff_for_validated_phase307_closure_receipt_summary"
    if handoff.get("handoff_scope") != expected_scope:
        errors.append(f"handoff_scope must be {expected_scope}")
    if handoff.get("recommended_decision") != "keep_service_frozen":
        errors.append("recommended_decision must be keep_service_frozen")

    source = _as_dict(handoff.get("source_summary_validation"))
    expected_source_paths = {
        "path": SOURCE_SUMMARY_VALIDATION_CONTRACT_PATH,
        "validator": SOURCE_SUMMARY_VALIDATOR_PATH,
        "summary_contract_path": SOURCE_SUMMARY_CONTRACT_PATH,
        "summary_reporter": SOURCE_SUMMARY_REPORTER_PATH,
    }
    for field, expected_path in expected_source_paths.items():
        if source.get(field) != expected_path:
            errors.append(f"source_summary_validation.{field} must be {expected_path}")
        path = _repo_path(expected_path)
        if not path.exists():
            errors.append(f"source_summary_validation.{field} path must exist: {expected_path}")

    hash_fields = {
        "sha256": SOURCE_SUMMARY_VALIDATION_CONTRACT_PATH,
        "validator_sha256": SOURCE_SUMMARY_VALIDATOR_PATH,
        "summary_contract_sha256": SOURCE_SUMMARY_CONTRACT_PATH,
        "summary_reporter_sha256": SOURCE_SUMMARY_REPORTER_PATH,
    }
    for field, relative_path in hash_fields.items():
        path = _repo_path(relative_path)
        if path.exists() and source.get(field) != _sha256_file(path):
            errors.append(f"source_summary_validation.{field} must match {relative_path}")
    if source.get("validator_result") != "pass":
        errors.append("source_summary_validation.validator_result must be pass")
    if source.get("service_operation_state") != "freeze_preserved":
        errors.append("source_summary_validation.service_operation_state must be freeze_preserved")

    recipients = set(_as_list(handoff.get("handoff_recipients")))
    missing_recipients = REQUIRED_RECIPIENTS - recipients
    if missing_recipients:
        errors.append(f"handoff_recipients missing required roles {sorted(missing_recipients)}")

    actions = [_as_dict(action) for action in _as_list(handoff.get("handoff_actions"))]
    action_ids = {action.get("id") for action in actions}
    if action_ids != REQUIRED_ACTION_IDS:
        errors.append(f"handoff_actions ids must be {sorted(REQUIRED_ACTION_IDS)}")
    for action in actions:
        action_id = action.get("id", "<unknown>")
        if action.get("required") is not True:
            errors.append(f"handoff_actions.{action_id}.required must be true")
        if action.get("side_effect") is not False:
            errors.append(f"handoff_actions.{action_id}.side_effect must be false")

    boundary = _as_dict(handoff.get("handoff_boundary"))
    for field in REQUIRED_TRUE_BOUNDARY_FIELDS:
        if boundary.get(field) is not True:
            errors.append(f"handoff_boundary.{field} must be true")
    for field in REQUIRED_FALSE_BOUNDARY_FIELDS:
        if boundary.get(field) is not False:
            errors.append(f"handoff_boundary.{field} must be false")
    if boundary.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("handoff_boundary.aws_cost_boundary must be no_cost_increase")
    if boundary.get("training_boundary") != "not_authorized":
        errors.append("handoff_boundary.training_boundary must be not_authorized")

    for finding in _scan_forbidden_true(handoff):
        errors.append(f"documentops_phase309_validated_closure_receipt_summary_handoff: {finding}")

    source_validation_ok = source.get("validator_result") == "pass"

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "handoff_path": str(resolved_handoff),
        HANDOFF_VALID_KEY: not errors,
        "handoff_action_count": len(actions),
        "generated_summary_validation_ok": source_validation_ok and not errors,
        "generated_summary_readiness": READY_STATUS if source_validation_ok and not errors else "",
        "service_operation_state": "freeze_preserved",
        "recommended_decision": handoff.get("recommended_decision", ""),
        "aws_cost_boundary": boundary.get("aws_cost_boundary", ""),
        "training_boundary": boundary.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the DocumentOps Phase 307/308 validated closure receipt summary handoff."
    )
    parser.add_argument(
        "handoff",
        nargs="?",
        type=Path,
        default=DEFAULT_HANDOFF_PATH,
        help="Path to Phase 309 validated closure receipt summary handoff JSON.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_documentops_phase308_validated_closure_receipt_summary_handoff(args.handoff)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(PASS_MESSAGE)
        print(f"{HANDOFF_VALID_KEY}={str(result[HANDOFF_VALID_KEY]).lower()}")
        print(f"handoff_action_count={result['handoff_action_count']}")
        print(f"generated_summary_validation_ok={str(result['generated_summary_validation_ok']).lower()}")
        print(f"generated_summary_readiness={result['generated_summary_readiness']}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"recommended_decision={result['recommended_decision']}")
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
