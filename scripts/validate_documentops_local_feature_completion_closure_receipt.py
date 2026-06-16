#!/usr/bin/env python3
"""Validate the DocumentOps local feature completion closure receipt."""
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

from scripts.validate_documentops_local_feature_completion_closure_index import (  # noqa: E402
    validate_documentops_local_feature_completion_closure_index,
)


DEFAULT_RECEIPT_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/"
    "phase54_local_feature_completion_closure_receipt/local_feature_completion_closure_receipt.json"
)
EXPECTED_REPORT_TYPE = "document_ops_phase54_local_feature_completion_closure_receipt"
EXPECTED_VALIDATION_REPORT_TYPE = "document_ops_phase54_local_feature_completion_closure_receipt_validation"
EXPECTED_STATUS = "local_feature_completion_closure_receipt_recorded_no_aws_no_training_authorization"
REQUIRED_SOURCE_HASH_PATHS = {
    "phase53_closure_index_sha256": (
        "docs/specs/hermes_decisiondoc_agent/"
        "phase53_local_feature_completion_closure_index/local_feature_completion_closure_index.json"
    ),
    "phase53_closure_validator_sha256": "scripts/validate_documentops_local_feature_completion_closure_index.py",
}
REQUIRED_TRUE_BOUNDARY_FIELDS = (
    "local_receipt_recorded",
    "phase53_closure_index_valid",
    "phase47_to_phase52_chain_valid",
    "temporary_probe_only",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_FALSE_BOUNDARY_FIELDS = (
    "actual_reviewer_approval_recorded_by_receipt",
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
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_dataset_upload_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_summary",
    "actual_reviewer_approval_recorded_by_validator",
    "actual_operation_resume_approved",
    "service_operation_allowed",
    "service_operation_authorized",
    "provider_api_calls_allowed",
    "external_upload_allowed",
    "training_execution_allowed",
    "model_promotion_allowed",
    "model_training_started",
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def validate_documentops_local_feature_completion_closure_receipt(
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
) -> dict[str, Any]:
    resolved_receipt = receipt_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        receipt = _load_json(resolved_receipt)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "receipt_path": str(resolved_receipt),
            "errors": [str(exc)],
            "warnings": [],
        }

    if receipt.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if receipt.get("phase") != 54:
        errors.append("phase must be 54")
    if receipt.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")
    if receipt.get("operator_decision") != "keep_service_frozen":
        errors.append("operator_decision must be keep_service_frozen")

    source_gate = _as_dict(receipt.get("source_closure_gate"))
    if source_gate.get("command") != "python3 scripts/validate_documentops_local_feature_completion_closure_index.py":
        errors.append(
            "source_closure_gate.command must be "
            "python3 scripts/validate_documentops_local_feature_completion_closure_index.py"
        )
    if source_gate.get("result") != "pass":
        errors.append("source_closure_gate.result must be pass")
    if source_gate.get("closure_index_valid") is not True:
        errors.append("source_closure_gate.closure_index_valid must be true")
    if source_gate.get("source_artifact_count") != 6:
        errors.append("source_closure_gate.source_artifact_count must be 6")
    if source_gate.get("probe_count") != 6:
        errors.append("source_closure_gate.probe_count must be 6")
    if source_gate.get("temporary_summary_readiness") != "pending_signoff_review_no_training_authorization":
        errors.append(
            "source_closure_gate.temporary_summary_readiness must be "
            "pending_signoff_review_no_training_authorization"
        )
    if source_gate.get("service_operation_state") != "freeze_preserved":
        errors.append("source_closure_gate.service_operation_state must be freeze_preserved")
    if source_gate.get("recommended_decision") != "keep_service_frozen":
        errors.append("source_closure_gate.recommended_decision must be keep_service_frozen")
    if source_gate.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("source_closure_gate.aws_cost_boundary must be no_cost_increase")
    if source_gate.get("training_boundary") != "not_authorized":
        errors.append("source_closure_gate.training_boundary must be not_authorized")

    source_hashes = _as_dict(receipt.get("source_hashes"))
    for hash_key, relative_path in REQUIRED_SOURCE_HASH_PATHS.items():
        path = REPO_ROOT / relative_path
        if not path.exists():
            errors.append(f"source_hashes.{hash_key} source path must exist: {relative_path}")
            continue
        if source_hashes.get(hash_key) != _sha256_file(path):
            errors.append(f"source_hashes.{hash_key} must match {relative_path}")

    boundary = _as_dict(receipt.get("receipt_boundary"))
    for field in REQUIRED_TRUE_BOUNDARY_FIELDS:
        if boundary.get(field) is not True:
            errors.append(f"receipt_boundary.{field} must be true")
    for field in REQUIRED_FALSE_BOUNDARY_FIELDS:
        if boundary.get(field) is not False:
            errors.append(f"receipt_boundary.{field} must be false")
    if boundary.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("receipt_boundary.aws_cost_boundary must be no_cost_increase")
    if boundary.get("training_boundary") != "not_authorized":
        errors.append("receipt_boundary.training_boundary must be not_authorized")

    for finding in _scan_forbidden_true(receipt):
        errors.append(f"documentops_closure_receipt: {finding}")

    gate_result = validate_documentops_local_feature_completion_closure_index()
    if gate_result.get("ok") is not True:
        errors.append("source_closure_gate must still pass Phase 53 closure index validation")
        for error in gate_result.get("errors", []):
            errors.append(f"source_closure_gate: {error}")
    else:
        expected_pairs = {
            "closure_index_valid": True,
            "source_artifact_count": 6,
            "probe_count": 6,
            "temporary_summary_readiness": "pending_signoff_review_no_training_authorization",
            "service_operation_state": "freeze_preserved",
            "recommended_decision": "keep_service_frozen",
            "aws_cost_boundary": "no_cost_increase",
            "training_boundary": "not_authorized",
        }
        for field, expected_value in expected_pairs.items():
            if source_gate.get(field) != expected_value or gate_result.get(field) != expected_value:
                errors.append(f"source_closure_gate.{field} must match current Phase 53 validation")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "receipt_path": str(resolved_receipt),
        "closure_receipt_valid": not errors,
        "source_closure_gate_valid": not errors and gate_result.get("ok") is True,
        "service_operation_state": "freeze_preserved",
        "operator_decision": receipt.get("operator_decision", ""),
        "aws_cost_boundary": boundary.get("aws_cost_boundary", ""),
        "training_boundary": boundary.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the DocumentOps local feature completion closure receipt.")
    parser.add_argument(
        "receipt",
        nargs="?",
        type=Path,
        default=DEFAULT_RECEIPT_PATH,
        help="Path to phase54 local_feature_completion_closure_receipt.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_documentops_local_feature_completion_closure_receipt(args.receipt)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS documentops local feature completion closure receipt validated")
        print(f"closure_receipt_valid={str(result['closure_receipt_valid']).lower()}")
        print(f"source_closure_gate_valid={str(result['source_closure_gate_valid']).lower()}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"operator_decision={result['operator_decision']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL documentops local feature completion closure receipt validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
