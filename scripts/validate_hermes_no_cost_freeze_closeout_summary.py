#!/usr/bin/env python3
"""Validate the Hermes no-cost freeze closeout summary."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_hermes_no_cost_freeze_closeout_receipt import (  # noqa: E402
    validate_hermes_no_cost_freeze_closeout_receipt,
)


DEFAULT_SUMMARY_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/phase46_no_cost_freeze_closeout_summary/no_cost_freeze_closeout_summary.json"
)
EXPECTED_REPORT_TYPE = "document_ops_phase46_no_cost_freeze_closeout_summary"
EXPECTED_VALIDATION_REPORT_TYPE = "document_ops_phase46_no_cost_freeze_closeout_summary_validation"
EXPECTED_STATUS = "no_cost_freeze_closeout_summary_validated_no_aws_no_training_authorization"
REQUIRED_SUMMARY_TRUE_FIELDS = (
    "all_closeout_receipts_valid",
    "all_closeout_receipts_confirm_freeze",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_SUMMARY_FALSE_FIELDS = (
    "service_resume_authorized",
    "production_ui_called",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_hermes_no_cost_freeze_closeout_summary(summary_path: Path = DEFAULT_SUMMARY_PATH) -> dict[str, Any]:
    resolved_summary = summary_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        summary = _load_json(resolved_summary)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "summary_path": str(resolved_summary),
            "errors": [str(exc)],
            "warnings": [],
        }

    if summary.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if summary.get("phase") != 46:
        errors.append("phase must be 46")
    if summary.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")
    if summary.get("recommended_decision") != "keep_service_frozen":
        errors.append("recommended_decision must be keep_service_frozen")

    receipts = [_as_dict(item) for item in _as_list(summary.get("receipts"))]
    if not receipts:
        errors.append("receipts must include at least one closeout receipt")
    if summary.get("receipt_count") != len(receipts):
        errors.append("receipt_count must equal len(receipts)")

    for index, receipt in enumerate(receipts):
        receipt_path_value = receipt.get("path")
        if not isinstance(receipt_path_value, str) or not receipt_path_value:
            errors.append(f"receipts[{index}].path must be a non-empty string")
            continue
        receipt_path = Path(receipt_path_value)
        resolved_receipt = receipt_path if receipt_path.is_absolute() else REPO_ROOT / receipt_path
        if not resolved_receipt.exists():
            errors.append(f"receipts[{index}].path must exist: {receipt_path_value}")
            continue
        if receipt.get("sha256") != _sha256_file(resolved_receipt):
            errors.append(f"receipts[{index}].sha256 must match {receipt_path_value}")
        receipt_result = validate_hermes_no_cost_freeze_closeout_receipt(resolved_receipt)
        if receipt_result.get("ok") is not True:
            errors.append(f"receipts[{index}] must pass closeout receipt validation")
            for error in receipt_result.get("errors", []):
                errors.append(f"receipts[{index}]: {error}")
        if receipt.get("validator_result") != "pass":
            errors.append(f"receipts[{index}].validator_result must be pass")
        if receipt.get("service_operation_state") != "freeze_preserved":
            errors.append(f"receipts[{index}].service_operation_state must be freeze_preserved")

    summary_boundary = _as_dict(summary.get("summary_boundary"))
    for field in REQUIRED_SUMMARY_TRUE_FIELDS:
        if summary_boundary.get(field) is not True:
            errors.append(f"summary_boundary.{field} must be true")
    for field in REQUIRED_SUMMARY_FALSE_FIELDS:
        if summary_boundary.get(field) is not False:
            errors.append(f"summary_boundary.{field} must be false")
    if summary_boundary.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("summary_boundary.aws_cost_boundary must be no_cost_increase")
    if summary_boundary.get("training_boundary") != "not_authorized":
        errors.append("summary_boundary.training_boundary must be not_authorized")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "summary_path": str(resolved_summary),
        "closeout_summary_valid": not errors,
        "receipt_count": len(receipts),
        "service_operation_state": "freeze_preserved",
        "aws_cost_boundary": summary_boundary.get("aws_cost_boundary", ""),
        "training_boundary": summary_boundary.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the Hermes no-cost freeze closeout summary.")
    parser.add_argument(
        "summary",
        nargs="?",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help="Path to no_cost_freeze_closeout_summary.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_hermes_no_cost_freeze_closeout_summary(args.summary)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS hermes no-cost freeze closeout summary validated")
        print(f"closeout_summary_valid={str(result['closeout_summary_valid']).lower()}")
        print(f"receipt_count={result['receipt_count']}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL hermes no-cost freeze closeout summary validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
