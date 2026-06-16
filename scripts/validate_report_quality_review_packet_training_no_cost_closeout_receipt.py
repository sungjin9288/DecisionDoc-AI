#!/usr/bin/env python3
"""Validate a no-cost closeout receipt for report quality training work."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence


EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_closeout_receipt.v1"
FINAL_HOLD_SUMMARY_SCHEMA = "decisiondoc_report_quality_training_no_cost_final_hold_summary.v1"
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_path(path_value: Any, *, field: str, errors: list[str]) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        errors.append(f"{field} must be a non-empty path")
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.exists() or not path.is_file():
        errors.append(f"{field} does not exist: {path}")
        return None
    return path


def _validate_hash(*, path: Path | None, expected_hash: Any, field: str, errors: list[str]) -> None:
    if path is None:
        return
    if not isinstance(expected_hash, str) or not expected_hash.strip():
        errors.append(f"{field} must be non-empty")
    elif expected_hash != _sha256(path):
        errors.append(f"{field} does not match referenced file")


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


def validate_final_hold_summary_ready(summary: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if summary.get("schema_version") != FINAL_HOLD_SUMMARY_SCHEMA:
        errors.append(f"summary.schema_version must be {FINAL_HOLD_SUMMARY_SCHEMA!r}")
    if summary.get("report_type") != "report_quality_training_no_cost_final_hold_summary":
        errors.append("summary.report_type must be report_quality_training_no_cost_final_hold_summary")
    if summary.get("ok") is not True:
        errors.append("summary.ok must be true")
    if summary.get("read_only") is not True:
        errors.append("summary.read_only must be true")

    readiness = _as_dict(summary.get("readiness"))
    if readiness.get("status") != "all_final_holds_confirm_no_cost_service_lock":
        errors.append("summary.readiness.status must confirm final holds")
    if readiness.get("service_operation_locked") is not True:
        errors.append("summary.readiness.service_operation_locked must be true")
    if readiness.get("resume_blocked") is not True:
        errors.append("summary.readiness.resume_blocked must be true")
    for key in (
        "operation_resume_approved",
        "service_operation_allowed",
        "aws_cost_increase_allowed",
        "external_dataset_upload_authorized",
        "provider_fine_tune_api_call_authorized",
        "provider_job_creation_authorized",
        "training_execution_authorized",
        "model_promotion_authorized",
    ):
        if readiness.get(key) is not False:
            errors.append(f"summary.readiness.{key} must be false")

    counts = _as_dict(summary.get("counts"))
    final_hold_count = counts.get("final_hold_count")
    if not isinstance(final_hold_count, int) or final_hold_count < 1:
        errors.append("summary.counts.final_hold_count must be at least 1")
    for field in ("valid_final_hold_count", "active_final_hold_count"):
        if counts.get(field) != final_hold_count:
            errors.append(f"summary.counts.{field} must match final_hold_count")
    if counts.get("invalid_final_hold_count") != 0:
        errors.append("summary.counts.invalid_final_hold_count must be 0")
    if counts.get("load_error_count") != 0:
        errors.append("summary.counts.load_error_count must be 0")

    boundary = _as_dict(summary.get("side_effect_boundary"))
    for key in (
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
    ):
        if boundary.get(key) is not False:
            errors.append(f"summary.side_effect_boundary.{key} must be false")
    return {"ok": not errors, "errors": errors}


def validate_training_no_cost_closeout_receipt(
    closeout_receipt_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_manifest = closeout_receipt_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        receipt = _load_json(resolved_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_no_cost_closeout_receipt_validation",
            "ok": False,
            "require_ready": require_ready,
            "closeout_receipt_manifest_path": str(resolved_manifest),
            "errors": [str(exc)],
            "warnings": [],
        }

    if receipt.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if receipt.get("report_type") != "report_quality_training_no_cost_closeout_receipt":
        errors.append("report_type must be report_quality_training_no_cost_closeout_receipt")

    recorded_manifest = _resolve_path(
        receipt.get("closeout_receipt_manifest_path"),
        field="closeout_receipt_manifest_path",
        errors=errors,
    )
    if recorded_manifest is not None and recorded_manifest != resolved_manifest:
        warnings.append("closeout_receipt_manifest_path points to a different path than the validated manifest")

    markdown_path = _resolve_path(
        receipt.get("closeout_receipt_markdown_path"),
        field="closeout_receipt_markdown_path",
        errors=errors,
    )
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training No-Cost Closeout Receipt" not in markdown:
            errors.append("closeout receipt markdown is missing title")
        if "receipt_ready: `true`" not in markdown:
            errors.append("closeout receipt markdown must show receipt_ready=true")
        if "service_operation_locked: `true`" not in markdown:
            errors.append("closeout receipt markdown must show service_operation_locked=true")
        if "resume_blocked: `true`" not in markdown:
            errors.append("closeout receipt markdown must show resume_blocked=true")
        if "operation_resume_approved: `false`" not in markdown:
            errors.append("closeout receipt markdown must show operation_resume_approved=false")
        if "aws_cost_increase_allowed: `false`" not in markdown:
            errors.append("closeout receipt markdown must show aws_cost_increase_allowed=false")
        if "training_execution_started: `false`" not in markdown:
            errors.append("closeout receipt markdown must show training_execution_started=false")

    summary_path = _resolve_path(
        receipt.get("final_hold_summary_path"),
        field="final_hold_summary_path",
        errors=errors,
    )
    _validate_hash(
        path=summary_path,
        expected_hash=receipt.get("final_hold_summary_sha256"),
        field="final_hold_summary_sha256",
        errors=errors,
    )
    summary: dict[str, Any] = {}
    summary_validation: dict[str, Any] = {}
    if summary_path is not None:
        summary = _load_json(summary_path)
        summary_validation = validate_final_hold_summary_ready(summary)
        if require_ready and summary_validation.get("ok") is not True:
            errors.append("no-cost final hold summary validation must pass")

    embedded_summary_validation = _as_dict(receipt.get("summary_validation"))
    if require_ready and embedded_summary_validation.get("ok") is not True:
        errors.append("embedded summary_validation.ok must be true")

    state = _as_dict(receipt.get("receipt_state"))
    if require_ready and state.get("ready") is not True:
        errors.append("receipt_state.ready must be true")
    if state.get("status") != "no_cost_closeout_receipt_ready":
        errors.append("receipt_state.status must be no_cost_closeout_receipt_ready")
    if state.get("closeout_only") is not True:
        errors.append("receipt_state.closeout_only must be true")
    if state.get("service_operation_locked") is not True:
        errors.append("receipt_state.service_operation_locked must be true")
    if state.get("resume_blocked") is not True:
        errors.append("receipt_state.resume_blocked must be true")

    source_files = _as_dict(receipt.get("source_files"))
    missing_file_count = 0
    for name, file_value in source_files.items():
        file_record = _as_dict(file_value)
        path = _resolve_path(file_record.get("path"), field=f"source_files.{name}.path", errors=errors)
        if file_record.get("exists") is not True:
            errors.append(f"source_files.{name}.exists must be true")
            missing_file_count += 1
        _validate_hash(
            path=path,
            expected_hash=file_record.get("sha256"),
            field=f"source_files.{name}.sha256",
            errors=errors,
        )

    counts = _as_dict(receipt.get("counts"))
    if counts.get("source_file_count") != len(source_files):
        errors.append("counts.source_file_count must match source_files length")
    if counts.get("missing_file_count") != missing_file_count:
        errors.append("counts.missing_file_count must match missing source files")
    if summary:
        summary_counts = _as_dict(summary.get("counts"))
        for field in (
            "final_hold_count",
            "valid_final_hold_count",
            "active_final_hold_count",
            "signoff_count",
            "service_lock_review_count",
        ):
            if counts.get(field) != summary_counts.get(field):
                errors.append(f"counts.{field} must match final hold summary counts")

    operator_actions = receipt.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 5:
        errors.append("operator_actions must include at least five actions")
    else:
        action_text = "\n".join(str(item) for item in operator_actions)
        if "Keep service operation disabled" not in action_text:
            errors.append("operator_actions must keep service operation disabled")
        if "Do not deploy AWS resources" not in action_text:
            errors.append("operator_actions must explicitly prohibit AWS deployment")
        if "Do not call provider APIs" not in action_text:
            errors.append("operator_actions must explicitly prohibit provider calls")
        if "Do not execute training" not in action_text:
            errors.append("operator_actions must explicitly prohibit training execution")
        if "Resume only after" not in action_text:
            errors.append("operator_actions must include resume prerequisites")

    for finding in _scan_forbidden_true(receipt):
        errors.append(f"training_no_cost_closeout_receipt: {finding}")

    return {
        "report_type": "report_quality_training_no_cost_closeout_receipt_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "closeout_receipt_manifest_path": str(resolved_manifest),
        "schema_version": receipt.get("schema_version"),
        "receipt_ready": state.get("ready") is True,
        "service_operation_locked": state.get("service_operation_locked") is True,
        "resume_blocked": state.get("resume_blocked") is True,
        "aws_cost_boundary": "no_cost_increase"
        if state.get("aws_cost_increase_allowed") is False
        else "cost_increase_possible",
        "summary_validation_ok": summary_validation.get("ok") if summary_validation else None,
        "source_file_count": len(source_files),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a no-cost closeout receipt manifest.")
    parser.add_argument(
        "closeout_receipt_manifest",
        type=Path,
        help="Path to *-training-no-cost-closeout-receipt-manifest.json.",
    )
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_no_cost_closeout_receipt(
        args.closeout_receipt_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost closeout receipt validated")
        print(f"receipt_ready={str(result['receipt_ready']).lower()}")
        print(f"service_operation_locked={str(result['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(result['resume_blocked']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training no-cost closeout receipt validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
