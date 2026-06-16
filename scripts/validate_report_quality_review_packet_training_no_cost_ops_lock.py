#!/usr/bin/env python3
"""Validate a local no-cost ops lock manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence


EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_ops_lock.v1"
SUMMARY_SCHEMA = "decisiondoc_report_quality_training_no_cost_resume_guard_summary.v1"
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


def validate_resume_guard_summary_ready(summary: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if summary.get("schema_version") != SUMMARY_SCHEMA:
        errors.append(f"summary.schema_version must be {SUMMARY_SCHEMA!r}")
    if summary.get("report_type") != "report_quality_training_no_cost_resume_guard_summary":
        errors.append("summary.report_type must be report_quality_training_no_cost_resume_guard_summary")
    if summary.get("ok") is not True:
        errors.append("summary.ok must be true")
    if summary.get("read_only") is not True:
        errors.append("summary.read_only must be true")
    readiness = _as_dict(summary.get("readiness"))
    if readiness.get("status") != "all_resume_guards_confirm_no_cost_block":
        errors.append("summary.readiness.status must confirm no-cost resume blocks")
    if readiness.get("resume_blocked") is not True:
        errors.append("summary.readiness.resume_blocked must be true")
    for key in (
        "operation_resume_approved",
        "aws_cost_increase_allowed",
        "service_operation_allowed",
        "external_dataset_upload_authorized",
        "provider_fine_tune_api_call_authorized",
        "provider_job_creation_authorized",
        "training_execution_authorized",
        "model_promotion_authorized",
    ):
        if readiness.get(key) is not False:
            errors.append(f"summary.readiness.{key} must be false")

    counts = _as_dict(summary.get("counts"))
    resume_guard_count = counts.get("resume_guard_count")
    if not isinstance(resume_guard_count, int) or resume_guard_count < 1:
        errors.append("summary.counts.resume_guard_count must be at least 1")
    for field in ("valid_resume_guard_count", "active_resume_guard_count"):
        if counts.get(field) != resume_guard_count:
            errors.append(f"summary.counts.{field} must match resume_guard_count")
    if counts.get("invalid_resume_guard_count") != 0:
        errors.append("summary.counts.invalid_resume_guard_count must be 0")
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


def validate_training_no_cost_ops_lock(
    ops_lock_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_ops_lock = ops_lock_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        ops_lock = _load_json(resolved_ops_lock)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_no_cost_ops_lock_validation",
            "ok": False,
            "require_ready": require_ready,
            "ops_lock_manifest_path": str(resolved_ops_lock),
            "errors": [str(exc)],
            "warnings": [],
        }

    if ops_lock.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if ops_lock.get("report_type") != "report_quality_training_no_cost_ops_lock":
        errors.append("report_type must be report_quality_training_no_cost_ops_lock")

    recorded_ops_lock_path = _resolve_path(
        ops_lock.get("ops_lock_manifest_path"),
        field="ops_lock_manifest_path",
        errors=errors,
    )
    if recorded_ops_lock_path is not None and recorded_ops_lock_path != resolved_ops_lock:
        warnings.append("ops_lock_manifest_path points to a different path than the validated manifest")

    markdown_path = _resolve_path(
        ops_lock.get("ops_lock_markdown_path"),
        field="ops_lock_markdown_path",
        errors=errors,
    )
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training No-Cost Ops Lock" not in markdown:
            errors.append("ops lock markdown is missing title")
        if "ops_lock_active: `true`" not in markdown:
            errors.append("ops lock markdown must show ops_lock_active=true")
        if "service_operation_locked: `true`" not in markdown:
            errors.append("ops lock markdown must show service_operation_locked=true")
        if "resume_blocked: `true`" not in markdown:
            errors.append("ops lock markdown must show resume_blocked=true")
        if "operation_resume_approved: `false`" not in markdown:
            errors.append("ops lock markdown must show operation_resume_approved=false")
        if "aws_cost_increase_allowed: `false`" not in markdown:
            errors.append("ops lock markdown must show aws_cost_increase_allowed=false")
        if "training_execution_started: `false`" not in markdown:
            errors.append("ops lock markdown must show training_execution_started=false")

    summary_path = _resolve_path(
        ops_lock.get("resume_guard_summary_path"),
        field="resume_guard_summary_path",
        errors=errors,
    )
    _validate_hash(
        path=summary_path,
        expected_hash=ops_lock.get("resume_guard_summary_sha256"),
        field="resume_guard_summary_sha256",
        errors=errors,
    )
    summary_validation: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    if summary_path is not None:
        summary = _load_json(summary_path)
        summary_validation = validate_resume_guard_summary_ready(summary)
        if require_ready and summary_validation.get("ok") is not True:
            errors.append("resume guard summary validation must pass")

    embedded_summary_validation = _as_dict(ops_lock.get("summary_validation"))
    if require_ready and embedded_summary_validation.get("ok") is not True:
        errors.append("embedded summary_validation.ok must be true")

    lock_state = _as_dict(ops_lock.get("lock_state"))
    if require_ready and lock_state.get("ok") is not True:
        errors.append("lock_state.ok must be true")
    if lock_state.get("status") != "no_cost_ops_lock_active":
        errors.append("lock_state.status must be no_cost_ops_lock_active")
    if lock_state.get("lock_only") is not True:
        errors.append("lock_state.lock_only must be true")
    if lock_state.get("service_operation_locked") is not True:
        errors.append("lock_state.service_operation_locked must be true")
    if lock_state.get("resume_blocked") is not True:
        errors.append("lock_state.resume_blocked must be true")

    source_files = _as_dict(ops_lock.get("source_files"))
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

    counts = _as_dict(ops_lock.get("counts"))
    if counts.get("source_file_count") != len(source_files):
        errors.append("counts.source_file_count must match source_files length")
    if counts.get("missing_file_count") != missing_file_count:
        errors.append("counts.missing_file_count must match missing source files")
    if summary:
        summary_counts = _as_dict(summary.get("counts"))
        for field in ("resume_guard_count", "valid_resume_guard_count", "active_resume_guard_count"):
            if counts.get(field) != summary_counts.get(field):
                errors.append(f"counts.{field} must match resume guard summary counts")

    lock_controls = ops_lock.get("lock_controls")
    if not isinstance(lock_controls, list) or len(lock_controls) < 4:
        errors.append("lock_controls must include at least four controls")
    else:
        control_text = "\n".join(str(item) for item in lock_controls)
        if "Do not deploy AWS resources" not in control_text:
            errors.append("lock_controls must explicitly prohibit AWS deployment")
        if "Do not call provider APIs" not in control_text:
            errors.append("lock_controls must explicitly prohibit provider calls")
        if "Do not start training execution" not in control_text:
            errors.append("lock_controls must explicitly prohibit training execution")

    unlock_prerequisites = ops_lock.get("unlock_prerequisites")
    if not isinstance(unlock_prerequisites, list) or len(unlock_prerequisites) < 5:
        errors.append("unlock_prerequisites must include at least five prerequisites")
    else:
        prereq_text = "\n".join(str(item) for item in unlock_prerequisites)
        if "AWS budget review" not in prereq_text:
            errors.append("unlock_prerequisites must include AWS budget review")
        if "Provider approval" not in prereq_text:
            errors.append("unlock_prerequisites must include provider approval")
        if "rollback plan" not in prereq_text:
            errors.append("unlock_prerequisites must include rollback plan")

    for finding in _scan_forbidden_true(ops_lock):
        errors.append(f"training_no_cost_ops_lock: {finding}")

    return {
        "report_type": "report_quality_training_no_cost_ops_lock_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "ops_lock_manifest_path": str(resolved_ops_lock),
        "schema_version": ops_lock.get("schema_version"),
        "ops_lock_active": lock_state.get("ok") is True,
        "service_operation_locked": lock_state.get("service_operation_locked") is True,
        "resume_blocked": lock_state.get("resume_blocked") is True,
        "aws_cost_boundary": "no_cost_increase"
        if lock_state.get("aws_cost_increase_allowed") is False
        else "cost_increase_possible",
        "summary_validation_ok": summary_validation.get("ok") if summary_validation else None,
        "source_file_count": len(source_files),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a local no-cost ops lock manifest.")
    parser.add_argument("ops_lock_manifest", type=Path, help="Path to *-training-no-cost-ops-lock-manifest.json.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_no_cost_ops_lock(
        args.ops_lock_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost ops lock validated")
        print(f"ops_lock_active={str(result['ops_lock_active']).lower()}")
        print(f"service_operation_locked={str(result['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(result['resume_blocked']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training no-cost ops lock validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
