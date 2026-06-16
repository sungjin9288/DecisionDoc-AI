#!/usr/bin/env python3
"""Validate a no-cost operator handoff closeout receipt summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_operator_handoff_closeout_receipt_summary.v1"
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


def validate_training_no_cost_operator_handoff_closeout_receipt_summary(
    summary_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_summary = summary_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        summary = _load_json(resolved_summary)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": (
                "report_quality_training_no_cost_operator_handoff_closeout_receipt_summary_validation"
            ),
            "ok": False,
            "require_ready": require_ready,
            "summary_path": str(resolved_summary),
            "errors": [str(exc)],
            "warnings": [],
        }

    if summary.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if summary.get("report_type") != "report_quality_training_no_cost_operator_handoff_closeout_receipt_summary":
        errors.append("report_type must be report_quality_training_no_cost_operator_handoff_closeout_receipt_summary")
    if require_ready and summary.get("ok") is not True:
        errors.append("summary.ok must be true")
    if summary.get("read_only") is not True:
        errors.append("summary.read_only must be true")

    readiness = _as_dict(summary.get("readiness"))
    if readiness.get("status") != "all_operator_handoff_closeout_receipts_confirm_service_lock":
        errors.append("readiness.status must be all_operator_handoff_closeout_receipts_confirm_service_lock")
    if readiness.get("service_operation_locked") is not True:
        errors.append("readiness.service_operation_locked must be true")
    if readiness.get("resume_blocked") is not True:
        errors.append("readiness.resume_blocked must be true")
    if require_ready and _as_list(readiness.get("blocker_reasons")):
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
    receipt_count = counts.get("receipt_count")
    if not isinstance(receipt_count, int) or receipt_count < 1:
        errors.append("counts.receipt_count must be at least 1")
    for field in ("valid_receipt_count", "ready_receipt_count"):
        if counts.get(field) != receipt_count:
            errors.append(f"counts.{field} must match receipt_count")
    if counts.get("invalid_receipt_count") != 0:
        errors.append("counts.invalid_receipt_count must be 0")
    if counts.get("load_error_count") != 0:
        errors.append("counts.load_error_count must be 0")

    receipts = _as_list(summary.get("receipts"))
    if len(receipts) != receipt_count:
        errors.append("receipts length must match receipt_count")

    totals = {
        "signoff_count": 0,
        "valid_signoff_count": 0,
        "completed_signoff_count": 0,
        "accepted_signoff_count": 0,
        "operator_handoff_review_count": 0,
        "source_file_count": 0,
        "missing_file_count": 0,
    }
    for index, receipt_value in enumerate(receipts, start=1):
        receipt = _as_dict(receipt_value)
        prefix = f"receipts[{index}]"
        validation = _as_dict(receipt.get("validation"))
        if validation.get("ok") is not True:
            errors.append(f"{prefix}.validation.ok must be true")
        if validation.get("summary_validation_ok") is not True:
            errors.append(f"{prefix}.validation.summary_validation_ok must be true")
        if receipt.get("status") != "no_cost_operator_handoff_closeout_receipt_ready":
            errors.append(f"{prefix}.status must be no_cost_operator_handoff_closeout_receipt_ready")
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
        for field in totals:
            totals[field] += int(receipt.get(field) or 0)

    for field, total in totals.items():
        if counts.get(field) != total:
            errors.append(f"counts.{field} must match receipts")
    if counts.get("signoff_count") != counts.get("operator_handoff_review_count"):
        errors.append("counts.operator_handoff_review_count must match signoff_count")

    boundary = _as_dict(summary.get("side_effect_boundary"))
    if boundary.get("reads_local_operator_handoff_closeout_receipts") is not True:
        errors.append("side_effect_boundary.reads_local_operator_handoff_closeout_receipts must be true")
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
        errors.append(f"training_no_cost_operator_handoff_closeout_receipt_summary: {finding}")

    return {
        "report_type": "report_quality_training_no_cost_operator_handoff_closeout_receipt_summary_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "summary_path": str(resolved_summary),
        "schema_version": summary.get("schema_version"),
        "operator_handoff_closeout_receipt_summary_ready": summary.get("ok") is True,
        "service_operation_locked": readiness.get("service_operation_locked") is True,
        "resume_blocked": readiness.get("resume_blocked") is True,
        "aws_cost_boundary": "no_cost_increase"
        if readiness.get("aws_cost_increase_allowed") is False
        else "cost_increase_possible",
        "receipt_count": receipt_count,
        "ready_receipt_count": counts.get("ready_receipt_count"),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a no-cost operator handoff closeout receipt summary."
    )
    parser.add_argument(
        "summary",
        type=Path,
        help="Path to *-training-no-cost-operator-handoff-closeout-receipt-summary.json.",
    )
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_no_cost_operator_handoff_closeout_receipt_summary(
        args.summary,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost operator handoff closeout receipt summary validated")
        print(
            "operator_handoff_closeout_receipt_summary_ready="
            f"{str(result['operator_handoff_closeout_receipt_summary_ready']).lower()}"
        )
        print(f"service_operation_locked={str(result['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(result['resume_blocked']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training no-cost operator handoff closeout receipt summary validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
