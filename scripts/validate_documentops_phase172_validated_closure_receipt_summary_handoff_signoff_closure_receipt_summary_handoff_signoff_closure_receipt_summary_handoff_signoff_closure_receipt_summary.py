#!/usr/bin/env python3
"""Validate a DocumentOps Phase 172 validated closure receipt summary."""
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

from scripts.validate_documentops_phase170_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt import (  # noqa: E402
    validate_documentops_phase170_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt,
)


EXPECTED_REPORT_TYPE = (
    "document_ops_phase172_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_"
    "closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary"
)
EXPECTED_VALIDATION_REPORT_TYPE = (
    "document_ops_phase173_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_"
    "closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_"
    "closure_receipt_summary_validation"
)
EXPECTED_SCHEMA = "decisiondoc_documentops_phase171_validated_closure_receipt_summary.v1"
READY_STATUS = "all_phase171_validated_closure_receipts_confirm_no_cost_freeze"
READS_LOCAL_RECEIPTS_KEY = "reads_local_phase171_validated_closure_receipts"
SUMMARY_VALID_KEY = "phase171_validated_closure_receipt_summary_valid"
PASS_MESSAGE = "PASS documentops phase172 validated closure receipt summary validated"
FAIL_MESSAGE = "FAIL documentops phase172 validated closure receipt summary validation failed"
FORBIDDEN_TRUE_KEYS = {
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_receipt",
    "actual_reviewer_approval_recorded_by_summary",
    "actual_reviewer_approval_recorded_by_validator",
    "actual_operation_resume_approved",
    "service_resume_authorized",
    "service_operation_allowed",
    "service_operation_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "production_download_open_verification_authorized",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "aws_deploy_authorized",
    "aws_deploy_started",
    "aws_resource_creation_authorized",
    "aws_resource_created",
    "scheduled_job_authorized",
    "scheduled_job_enabled",
    "cloudwatch_polling_authorized",
    "cloudwatch_polling_started",
    "provider_api_calls_allowed",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_created",
    "provider_job_polling_authorized",
    "provider_job_polled",
    "external_upload_allowed",
    "external_dataset_upload_authorized",
    "external_dataset_uploaded",
    "training_execution_allowed",
    "training_execution_authorized",
    "training_execution_started",
    "model_candidate_emission_authorized",
    "model_candidate_emitted",
    "model_promotion_allowed",
    "model_promotion_authorized",
    "model_promoted",
    "model_training_started",
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


def _resolve_path(path_value: Any) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path)


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


def _require_false_fields(mapping: dict[str, Any], fields: Sequence[str], *, prefix: str, errors: list[str]) -> None:
    for field in fields:
        if mapping.get(field) is not False:
            errors.append(f"{prefix}.{field} must be false")


def _validate_summary_shape(summary: dict[str, Any], errors: list[str]) -> tuple[dict[str, Any], dict[str, Any], int]:
    if summary.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if summary.get("phase") != 172:
        errors.append("phase must be 172")
    if summary.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA}")
    if summary.get("read_only") is not True:
        errors.append("read_only must be true")
    if summary.get("ok") is not True:
        errors.append("summary.ok must be true")

    readiness = _as_dict(summary.get("readiness"))
    if readiness.get("status") != READY_STATUS:
        errors.append(f"readiness.status must be {READY_STATUS}")
    if _as_list(readiness.get("blocker_reasons")):
        errors.append("readiness.blocker_reasons must be empty")
    if readiness.get("service_freeze_preserved") is not True:
        errors.append("readiness.service_freeze_preserved must be true")
    if readiness.get("resume_requires_separate_approval") is not True:
        errors.append("readiness.resume_requires_separate_approval must be true")
    if readiness.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("readiness.aws_cost_boundary must be no_cost_increase")
    if readiness.get("training_boundary") != "not_authorized":
        errors.append("readiness.training_boundary must be not_authorized")
    _require_false_fields(
        readiness,
        (
            "service_resume_authorized",
            "production_ui_called",
            "aws_runtime_called",
            "aws_cost_increase_allowed",
            "provider_api_calls_authorized",
            "external_dataset_uploaded",
            "training_execution_started",
            "model_promoted",
        ),
        prefix="readiness",
        errors=errors,
    )

    counts = _as_dict(summary.get("counts"))
    receipt_count = counts.get("receipt_count")
    if not isinstance(receipt_count, int) or receipt_count < 1:
        errors.append("counts.receipt_count must be at least 1")
        receipt_count = 0
    for field in (
        "valid_receipt_count",
        "invalid_receipt_count",
        "boundary_break_count",
        "load_error_count",
    ):
        if not isinstance(counts.get(field), int):
            errors.append(f"counts.{field} must be an integer")

    return readiness, counts, receipt_count


def validate_documentops_phase172_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary(
    summary_path: Path,
) -> dict[str, Any]:
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

    readiness, counts, receipt_count = _validate_summary_shape(summary, errors)
    receipts = [_as_dict(item) for item in _as_list(summary.get("receipts"))]
    if len(receipts) != receipt_count:
        errors.append("receipts length must match counts.receipt_count")

    actual_valid_count = 0
    actual_boundary_break_count = 0
    for index, receipt in enumerate(receipts, start=1):
        prefix = f"receipts[{index}]"
        validation = _as_dict(receipt.get("validation"))
        if validation.get("ok") is True:
            actual_valid_count += 1
        boundary_breaks = _as_list(receipt.get("boundary_breaks"))
        if boundary_breaks:
            actual_boundary_break_count += 1
            errors.append(f"{prefix}.boundary_breaks must be empty")

        receipt_path = _resolve_path(receipt.get("path"))
        if receipt_path is None:
            errors.append(f"{prefix}.path must be non-empty")
            continue
        if not receipt_path.exists():
            errors.append(f"{prefix}.path must exist: {receipt_path}")
            continue
        if receipt.get("sha256") != _sha256_file(receipt_path):
            errors.append(f"{prefix}.sha256 must match linked Phase 171 receipt file")
            continue
        try:
            receipt_payload = _load_json(receipt_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{prefix}.path could not be loaded: {exc}")
            continue

        current_validation = (
            validate_documentops_phase170_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt(
                receipt_path
            )
        )
        if validation.get("ok") is not (current_validation.get("ok") is True):
            errors.append(f"{prefix}.validation.ok must match current Phase 171 validation")
        if validation.get("closure_receipt_valid") is not (current_validation.get("closure_receipt_valid") is True):
            errors.append(f"{prefix}.validation.closure_receipt_valid must match current Phase 171 validation")
        if validation.get("source_closure_gate_valid") is not (
            current_validation.get("source_closure_gate_valid") is True
        ):
            errors.append(f"{prefix}.validation.source_closure_gate_valid must match current Phase 171 validation")
        if current_validation.get("ok") is not True:
            for error in current_validation.get("errors", []):
                errors.append(f"{prefix}.current_validation: {error}")

        source_gate = _as_dict(receipt_payload.get("source_closure_gate"))
        source_hashes = _as_dict(receipt_payload.get("source_hashes"))
        expected_pairs = {
            "operator_decision": receipt_payload.get("operator_decision", ""),
            "source_gate_result": source_gate.get("result", ""),
            "closure_index_valid": source_gate.get("closure_index_valid") is True,
            "source_artifact_count": source_gate.get("source_artifact_count", 0),
            "probe_count": source_gate.get("probe_count", 0),
            "temporary_summary_readiness": source_gate.get("temporary_summary_readiness", ""),
            "temporary_summary_validation_ok": source_gate.get("temporary_summary_validation_ok") is True,
            "recommended_decision": source_gate.get("recommended_decision", ""),
            "phase170_closure_index_sha256": source_hashes.get("phase170_closure_index_sha256", ""),
            "phase170_closure_validator_sha256": source_hashes.get("phase170_closure_validator_sha256", ""),
            "phase171_closure_receipt_validator_sha256": source_hashes.get(
                "phase171_closure_receipt_validator_sha256", ""
            ),
        }
        for field, expected_value in expected_pairs.items():
            if receipt.get(field) != expected_value:
                errors.append(f"{prefix}.{field} must match linked Phase 171 receipt")

        side_effect_boundary = _as_dict(receipt.get("side_effect_boundary"))
        _require_false_fields(
            side_effect_boundary,
            (
                "service_resume_authorized",
                "production_ui_called",
                "aws_runtime_called",
                "aws_cost_increase_allowed",
                "provider_api_calls_authorized",
                "external_dataset_uploaded",
                "training_execution_started",
                "model_promoted",
            ),
            prefix=f"{prefix}.side_effect_boundary",
            errors=errors,
        )

    if counts.get("valid_receipt_count") != actual_valid_count:
        errors.append("counts.valid_receipt_count must match receipts")
    if counts.get("invalid_receipt_count") != receipt_count - actual_valid_count:
        errors.append("counts.invalid_receipt_count must match receipts")
    if counts.get("boundary_break_count") != actual_boundary_break_count:
        errors.append("counts.boundary_break_count must match receipts")
    if counts.get("load_error_count") != 0:
        errors.append("counts.load_error_count must be 0")
    if _as_list(summary.get("load_errors")):
        errors.append("load_errors must be empty")

    boundary = _as_dict(summary.get("side_effect_boundary"))
    if boundary.get(READS_LOCAL_RECEIPTS_KEY) is not True:
        errors.append(f"side_effect_boundary.{READS_LOCAL_RECEIPTS_KEY} must be true")
    if boundary.get("writes_summary_only") is not True:
        errors.append("side_effect_boundary.writes_summary_only must be true")
    _require_false_fields(
        boundary,
        (
            "actual_reviewer_approval_recorded_by_summary",
            "service_resume_authorized",
            "production_ui_called",
            "aws_runtime_called",
            "aws_cost_increase_allowed",
            "provider_api_calls_authorized",
            "external_dataset_uploaded",
            "training_execution_started",
            "model_promoted",
        ),
        prefix="side_effect_boundary",
        errors=errors,
    )

    for finding in _scan_forbidden_true(summary):
        errors.append(f"documentops_phase172_validated_closure_receipt_summary: {finding}")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "summary_path": str(resolved_summary),
        SUMMARY_VALID_KEY: not errors,
        "receipt_count": receipt_count,
        "readiness_status": readiness.get("status", ""),
        "service_operation_state": "freeze_preserved",
        "aws_cost_boundary": readiness.get("aws_cost_boundary", ""),
        "training_boundary": readiness.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a DocumentOps Phase 172 closure receipt summary.")
    parser.add_argument("summary", type=Path, help="Path to Phase 172 closure receipt summary JSON.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = (
        validate_documentops_phase172_validated_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary_handoff_signoff_closure_receipt_summary(
            args.summary
        )
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(PASS_MESSAGE)
        print(f"{SUMMARY_VALID_KEY}={str(result[SUMMARY_VALID_KEY]).lower()}")
        print(f"receipt_count={result['receipt_count']}")
        print(f"readiness_status={result['readiness_status']}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
    else:
        print(FAIL_MESSAGE)
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
