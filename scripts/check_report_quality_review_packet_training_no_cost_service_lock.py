#!/usr/bin/env python3
"""Check that report quality training remains under a no-cost service lock."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_closeout_receipt_summary.v1"
FORBIDDEN_TRUE_KEYS = {
    "operation_resume_approved",
    "actual_operation_resume_approved",
    "service_operation_allowed",
    "service_operation_authorized",
    "server_file_written",
    "persisted_learning_artifact",
    "aws_deploy_started",
    "aws_deploy_authorized",
    "aws_resource_created",
    "aws_resource_creation_authorized",
    "aws_runtime_enabled",
    "aws_runtime_authorized",
    "aws_cost_increase_allowed",
    "aws_cost_increase_authorized",
    "scheduled_job_enabled",
    "scheduled_job_authorized",
    "cloudwatch_polling_started",
    "cloudwatch_polling_authorized",
    "external_dataset_upload_started",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_fine_tune_api_call_authorized",
    "provider_job_created",
    "provider_job_creation_authorized",
    "provider_job_polled",
    "provider_job_polling_authorized",
    "training_execution_started",
    "training_execution_authorized",
    "model_promotion_started",
    "model_promotion_authorized",
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _require_false_fields(mapping: dict[str, Any], fields: Sequence[str], *, prefix: str, errors: list[str]) -> None:
    for field in fields:
        if mapping.get(field) is not False:
            errors.append(f"{prefix}.{field} must be false")


def validate_no_cost_service_lock(summary_path: Path) -> dict[str, Any]:
    resolved_summary = summary_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        summary = _load_json(resolved_summary)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_no_cost_service_lock_check",
            "ok": False,
            "summary_path": str(resolved_summary),
            "service_operation_locked": False,
            "resume_blocked": False,
            "aws_cost_boundary": "unknown",
            "errors": [str(exc)],
            "warnings": [],
        }

    if summary.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if summary.get("report_type") != "report_quality_training_no_cost_closeout_receipt_summary":
        errors.append("report_type must be report_quality_training_no_cost_closeout_receipt_summary")
    if summary.get("ok") is not True:
        errors.append("summary.ok must be true")
    if summary.get("read_only") is not True:
        errors.append("summary.read_only must be true")

    readiness = _as_dict(summary.get("readiness"))
    if readiness.get("status") != "all_closeout_receipts_confirm_no_cost_service_lock":
        errors.append("readiness.status must be all_closeout_receipts_confirm_no_cost_service_lock")
    if readiness.get("service_operation_locked") is not True:
        errors.append("readiness.service_operation_locked must be true")
    if readiness.get("resume_blocked") is not True:
        errors.append("readiness.resume_blocked must be true")
    if _as_list(readiness.get("blocker_reasons")):
        errors.append("readiness.blocker_reasons must be empty")
    _require_false_fields(
        readiness,
        (
            "operation_resume_approved",
            "service_operation_allowed",
            "aws_cost_increase_allowed",
            "external_dataset_upload_authorized",
            "provider_fine_tune_api_call_authorized",
            "provider_job_creation_authorized",
            "training_execution_authorized",
            "model_promotion_authorized",
        ),
        prefix="readiness",
        errors=errors,
    )

    counts = _as_dict(summary.get("counts"))
    receipt_count = counts.get("closeout_receipt_count")
    if not isinstance(receipt_count, int) or receipt_count < 1:
        errors.append("counts.closeout_receipt_count must be at least 1")
    for field in ("valid_closeout_receipt_count", "ready_closeout_receipt_count"):
        if counts.get(field) != receipt_count:
            errors.append(f"counts.{field} must match closeout_receipt_count")
    if counts.get("invalid_closeout_receipt_count") != 0:
        errors.append("counts.invalid_closeout_receipt_count must be 0")
    if counts.get("missing_file_count") != 0:
        errors.append("counts.missing_file_count must be 0")
    if counts.get("load_error_count") != 0:
        errors.append("counts.load_error_count must be 0")

    closeout_receipts = _as_list(summary.get("closeout_receipts"))
    if len(closeout_receipts) != receipt_count:
        errors.append("closeout_receipts length must match closeout_receipt_count")
    for index, receipt_value in enumerate(closeout_receipts, start=1):
        receipt = _as_dict(receipt_value)
        prefix = f"closeout_receipts[{index}]"
        if _as_dict(receipt.get("validation")).get("ok") is not True:
            errors.append(f"{prefix}.validation.ok must be true")
        if receipt.get("status") != "no_cost_closeout_receipt_ready":
            errors.append(f"{prefix}.status must be no_cost_closeout_receipt_ready")
        if receipt.get("ready") is not True:
            errors.append(f"{prefix}.ready must be true")
        if receipt.get("closeout_only") is not True:
            errors.append(f"{prefix}.closeout_only must be true")
        if receipt.get("service_operation_locked") is not True:
            errors.append(f"{prefix}.service_operation_locked must be true")
        if receipt.get("resume_blocked") is not True:
            errors.append(f"{prefix}.resume_blocked must be true")
        if receipt.get("aws_cost_boundary") != "no_cost_increase":
            errors.append(f"{prefix}.aws_cost_boundary must be no_cost_increase")
        if receipt.get("missing_file_count") != 0:
            errors.append(f"{prefix}.missing_file_count must be 0")
        _require_false_fields(
            receipt,
            (
                "operation_resume_approved",
                "service_operation_allowed",
                "aws_cost_increase_allowed",
                "external_dataset_upload_authorized",
                "provider_fine_tune_api_call_authorized",
                "provider_job_creation_authorized",
                "training_execution_authorized",
                "model_promotion_authorized",
            ),
            prefix=prefix,
            errors=errors,
        )

    boundary = _as_dict(summary.get("side_effect_boundary"))
    if boundary.get("reads_local_closeout_receipts") is not True:
        errors.append("side_effect_boundary.reads_local_closeout_receipts must be true")
    if boundary.get("writes_summary_only") is not True:
        errors.append("side_effect_boundary.writes_summary_only must be true")
    _require_false_fields(
        boundary,
        (
            "server_file_written",
            "persisted_learning_artifact",
            "operation_resume_approved",
            "service_operation_allowed",
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
        ),
        prefix="side_effect_boundary",
        errors=errors,
    )

    if _as_list(summary.get("load_errors")):
        errors.append("load_errors must be empty")
    for finding in _scan_forbidden_true(summary):
        errors.append(f"training_no_cost_service_lock: {finding}")

    return {
        "report_type": "report_quality_training_no_cost_service_lock_check",
        "ok": not errors,
        "summary_path": str(resolved_summary),
        "schema_version": summary.get("schema_version"),
        "status": "service_locked" if not errors else "follow_up_required",
        "service_operation_locked": readiness.get("service_operation_locked") is True,
        "resume_blocked": readiness.get("resume_blocked") is True,
        "operation_resume_approved": readiness.get("operation_resume_approved") is True,
        "aws_cost_boundary": "no_cost_increase"
        if readiness.get("aws_cost_increase_allowed") is False
        else "cost_increase_possible",
        "closeout_receipt_count": receipt_count,
        "ready_closeout_receipt_count": counts.get("ready_closeout_receipt_count"),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check no-cost service lock status from a closeout receipt summary.")
    parser.add_argument(
        "closeout_receipt_summary",
        type=Path,
        help="Path to *-training-no-cost-closeout-receipt-summary.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable check result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_no_cost_service_lock(args.closeout_receipt_summary)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost service lock checked")
        print(f"status={result['status']}")
        print(f"service_operation_locked={str(result['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(result['resume_blocked']).lower()}")
        print("operation_resume_approved=false")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print("training_boundary=not_authorized")
    else:
        print("FAIL report quality training no-cost service lock check failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
