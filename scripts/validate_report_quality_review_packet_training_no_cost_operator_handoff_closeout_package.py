#!/usr/bin/env python3
"""Validate a no-cost operator handoff closeout package."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_VALIDATOR_PATH = (
    REPO_ROOT
    / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_operator_handoff_closeout_package.v1"
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


def _load_summary_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary",
        SUMMARY_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost operator handoff closeout summary validator: {SUMMARY_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SUMMARY_VALIDATOR = _load_summary_validator()


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


def _require_false_fields(mapping: dict[str, Any], fields: Sequence[str], *, prefix: str, errors: list[str]) -> None:
    for field in fields:
        if mapping.get(field) is not False:
            errors.append(f"{prefix}.{field} must be false")


def validate_training_no_cost_operator_handoff_closeout_package(
    closeout_package_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_manifest = closeout_package_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        package = _load_json(resolved_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_no_cost_operator_handoff_closeout_package_validation",
            "ok": False,
            "require_ready": require_ready,
            "closeout_package_manifest_path": str(resolved_manifest),
            "errors": [str(exc)],
            "warnings": [],
        }

    if package.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if package.get("report_type") != "report_quality_training_no_cost_operator_handoff_closeout_package":
        errors.append("report_type must be report_quality_training_no_cost_operator_handoff_closeout_package")

    recorded_manifest = _resolve_path(
        package.get("operator_handoff_closeout_package_manifest_path"),
        field="operator_handoff_closeout_package_manifest_path",
        errors=errors,
    )
    if recorded_manifest is not None and recorded_manifest != resolved_manifest:
        warnings.append("operator_handoff_closeout_package_manifest_path points to a different path")

    markdown_path = _resolve_path(
        package.get("operator_handoff_closeout_package_markdown_path"),
        field="operator_handoff_closeout_package_markdown_path",
        errors=errors,
    )
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training No-Cost Operator Handoff Closeout Package" not in markdown:
            errors.append("operator handoff closeout package markdown is missing title")
        for required in (
            "package_ready: `true`",
            "package_only: `true`",
            "service_operation_locked: `true`",
            "resume_blocked: `true`",
            "operation_resume_approved: `false`",
            "service_operation_allowed: `false`",
            "aws_cost_increase_allowed: `false`",
            "training_execution_started: `false`",
        ):
            if required not in markdown:
                errors.append(f"operator handoff closeout package markdown must show {required}")

    summary_path = _resolve_path(
        package.get("operator_handoff_closeout_receipt_summary_path"),
        field="operator_handoff_closeout_receipt_summary_path",
        errors=errors,
    )
    _validate_hash(
        path=summary_path,
        expected_hash=package.get("operator_handoff_closeout_receipt_summary_sha256"),
        field="operator_handoff_closeout_receipt_summary_sha256",
        errors=errors,
    )
    summary: dict[str, Any] = {}
    summary_validation: dict[str, Any] = {}
    if summary_path is not None:
        summary = _load_json(summary_path)
        summary_validation = (
            _SUMMARY_VALIDATOR.validate_training_no_cost_operator_handoff_closeout_receipt_summary(summary_path)
        )
        if require_ready and summary_validation.get("ok") is not True:
            errors.append("no-cost operator handoff closeout receipt summary validation must pass")

    embedded_summary_validation = _as_dict(package.get("summary_validation"))
    if require_ready and embedded_summary_validation.get("ok") is not True:
        errors.append("embedded summary_validation.ok must be true")

    state = _as_dict(package.get("package_state"))
    if require_ready and state.get("ready") is not True:
        errors.append("package_state.ready must be true")
    if state.get("status") != "no_cost_operator_handoff_closeout_package_ready":
        errors.append("package_state.status must be no_cost_operator_handoff_closeout_package_ready")
    if state.get("package_only") is not True:
        errors.append("package_state.package_only must be true")
    if state.get("service_operation_locked") is not True:
        errors.append("package_state.service_operation_locked must be true")
    if state.get("resume_blocked") is not True:
        errors.append("package_state.resume_blocked must be true")
    _require_false_fields(
        state,
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
        prefix="package_state",
        errors=errors,
    )

    confirmed_summary_state = _as_dict(package.get("confirmed_summary_state"))
    if confirmed_summary_state.get("status") != "all_operator_handoff_closeout_receipts_confirm_service_lock":
        errors.append("confirmed_summary_state.status must confirm operator handoff closeout service lock")
    if confirmed_summary_state.get("service_operation_locked") is not True:
        errors.append("confirmed_summary_state.service_operation_locked must be true")
    if confirmed_summary_state.get("resume_blocked") is not True:
        errors.append("confirmed_summary_state.resume_blocked must be true")
    _require_false_fields(
        confirmed_summary_state,
        (
            "operation_resume_approved",
            "service_operation_allowed",
            "aws_cost_increase_allowed",
            "training_execution_authorized",
            "model_promotion_authorized",
        ),
        prefix="confirmed_summary_state",
        errors=errors,
    )

    source_files = _as_dict(package.get("source_files"))
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

    counts = _as_dict(package.get("counts"))
    if counts.get("package_source_file_count") != len(source_files):
        errors.append("counts.package_source_file_count must match source_files length")
    if counts.get("package_missing_file_count") != missing_file_count:
        errors.append("counts.package_missing_file_count must match missing source files")
    if summary:
        summary_counts = _as_dict(summary.get("counts"))
        for field in (
            "receipt_count",
            "valid_receipt_count",
            "ready_receipt_count",
            "signoff_count",
            "operator_handoff_review_count",
        ):
            if counts.get(field) != summary_counts.get(field):
                errors.append(f"counts.{field} must match operator handoff closeout receipt summary counts")

    operator_actions = package.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 6:
        errors.append("operator_actions must include at least six actions")
    else:
        action_text = "\n".join(str(item) for item in operator_actions)
        for expected in (
            "Keep service operation disabled",
            "local operator handoff closeout evidence",
            "Do not deploy AWS resources",
            "Do not call provider APIs",
            "Do not execute training",
            "Resume only after",
        ):
            if expected not in action_text:
                errors.append(f"operator_actions must include {expected!r}")

    boundary = _as_dict(package.get("package_boundary"))
    if boundary.get("reads_local_operator_handoff_closeout_receipt_summary") is not True:
        errors.append("package_boundary.reads_local_operator_handoff_closeout_receipt_summary must be true")
    if boundary.get("writes_local_closeout_package_files") is not True:
        errors.append("package_boundary.writes_local_closeout_package_files must be true")
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
        prefix="package_boundary",
        errors=errors,
    )

    for finding in _scan_forbidden_true(package):
        errors.append(f"training_no_cost_operator_handoff_closeout_package: {finding}")

    return {
        "report_type": "report_quality_training_no_cost_operator_handoff_closeout_package_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "closeout_package_manifest_path": str(resolved_manifest),
        "schema_version": package.get("schema_version"),
        "package_ready": state.get("ready") is True,
        "service_operation_locked": state.get("service_operation_locked") is True,
        "resume_blocked": state.get("resume_blocked") is True,
        "aws_cost_boundary": "no_cost_increase"
        if state.get("aws_cost_increase_allowed") is False
        else "cost_increase_possible",
        "summary_validation_ok": summary_validation.get("ok") if summary_validation else None,
        "receipt_count": counts.get("receipt_count"),
        "ready_receipt_count": counts.get("ready_receipt_count"),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a no-cost operator handoff closeout package.")
    parser.add_argument(
        "closeout_package_manifest",
        type=Path,
        help="Path to *-training-no-cost-operator-handoff-closeout-package-manifest.json.",
    )
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_no_cost_operator_handoff_closeout_package(
        args.closeout_package_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost operator handoff closeout package validated")
        print(f"package_ready={str(result['package_ready']).lower()}")
        print(f"service_operation_locked={str(result['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(result['resume_blocked']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training no-cost operator handoff closeout package validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
