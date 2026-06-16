#!/usr/bin/env python3
"""Validate a local no-cost freeze manifest for report quality training planning."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
RECORD_TEMPLATE_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_record_template.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_freeze.v1"
FORBIDDEN_TRUE_KEYS = {
    "actual_training_approval_recorded",
    "approval_record_completed",
    "approval_effective",
    "final_training_approval_granted",
    "service_operation_allowed",
    "server_file_written",
    "persisted_learning_artifact",
    "aws_deploy_started",
    "aws_resource_created",
    "aws_runtime_enabled",
    "aws_cost_increase_allowed",
    "scheduled_job_enabled",
    "cloudwatch_polling_started",
    "external_dataset_upload_authorized",
    "external_dataset_upload_started",
    "external_upload_allowed",
    "provider_api_calls_allowed",
    "provider_fine_tune_api_call_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "provider_job_created",
    "provider_job_polled",
    "provider_job_started",
    "training_execution_authorized",
    "training_execution_allowed",
    "training_execution_started",
    "model_promotion_authorized",
    "model_promotion_allowed",
    "model_promotion_started",
}


def _load_record_template_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_final_approval_record_template",
        RECORD_TEMPLATE_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load final approval record template validator: {RECORD_TEMPLATE_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RECORD_TEMPLATE_VALIDATOR = _load_record_template_validator()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def validate_training_no_cost_freeze(
    freeze_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_freeze = freeze_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        freeze = _load_json(resolved_freeze)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_no_cost_freeze_validation",
            "ok": False,
            "require_ready": require_ready,
            "freeze_manifest_path": str(resolved_freeze),
            "errors": [str(exc)],
            "warnings": [],
        }

    if freeze.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if freeze.get("report_type") != "report_quality_training_no_cost_freeze":
        errors.append("report_type must be report_quality_training_no_cost_freeze")
    if not isinstance(freeze.get("freeze_id"), str) or not freeze.get("freeze_id", "").strip():
        errors.append("freeze_id must be non-empty")

    recorded_freeze_path = _resolve_path(
        freeze.get("freeze_manifest_path"),
        field="freeze_manifest_path",
        errors=errors,
    )
    if recorded_freeze_path is not None and recorded_freeze_path != resolved_freeze:
        warnings.append("freeze_manifest_path points to a different path than the validated manifest")

    markdown_path = _resolve_path(freeze.get("freeze_markdown_path"), field="freeze_markdown_path", errors=errors)
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training No-Cost Freeze" not in markdown:
            errors.append("freeze markdown is missing title")
        if "aws_cost_increase_allowed: `false`" not in markdown:
            errors.append("freeze markdown must show aws_cost_increase_allowed=false")
        if "training_execution_started: `false`" not in markdown:
            errors.append("freeze markdown must show training_execution_started=false")

    record_path = _resolve_path(
        freeze.get("approval_record_template_path"),
        field="approval_record_template_path",
        errors=errors,
    )
    _validate_hash(
        path=record_path,
        expected_hash=freeze.get("approval_record_template_sha256"),
        field="approval_record_template_sha256",
        errors=errors,
    )
    record_validation: dict[str, Any] = {}
    if record_path is not None:
        record_validation = _RECORD_TEMPLATE_VALIDATOR.validate_training_final_approval_record_template(record_path)
        if require_ready and record_validation.get("ok") is not True:
            errors.append("final approval record template validation must pass")

    embedded_record_validation = _as_dict(freeze.get("approval_record_template_validation"))
    if require_ready and embedded_record_validation.get("ok") is not True:
        errors.append("embedded approval_record_template_validation.ok must be true")

    freeze_state = _as_dict(freeze.get("freeze_state"))
    if freeze_state.get("freeze_only") is not True:
        errors.append("freeze_state.freeze_only must be true")
    if freeze_state.get("status") != "no_cost_hold":
        errors.append("freeze_state.status must be no_cost_hold")

    source_files = _as_dict(freeze.get("source_files"))
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
    counts = _as_dict(freeze.get("counts"))
    if counts.get("source_file_count") != len(source_files):
        errors.append("counts.source_file_count must match source_files length")
    if counts.get("missing_file_count") != missing_file_count:
        errors.append("counts.missing_file_count must match missing source files")

    job_spec = _as_dict(freeze.get("job_spec_snapshot"))
    execution_steps = _as_list(job_spec.get("execution_steps"))
    if len(execution_steps) < 5:
        errors.append("job_spec_snapshot.execution_steps must include at least five steps")
    for index, step_value in enumerate(execution_steps, start=1):
        step = _as_dict(step_value)
        if step.get("status") != "not_started":
            errors.append(f"job_spec_snapshot.execution_steps[{index}].status must be not_started")

    operator_actions = freeze.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 3:
        errors.append("operator_actions must include at least three actions")
    else:
        action_text = "\n".join(str(item) for item in operator_actions)
        if "Do not deploy AWS resources" not in action_text:
            errors.append("operator_actions must explicitly prohibit AWS deployment")
        if "Do not call provider APIs" not in action_text:
            errors.append("operator_actions must explicitly prohibit provider calls")

    resume_requirements = freeze.get("resume_requirements")
    if not isinstance(resume_requirements, list) or len(resume_requirements) < 4:
        errors.append("resume_requirements must include at least four requirements")

    for finding in _scan_forbidden_true(freeze):
        errors.append(f"training_no_cost_freeze: {finding}")

    return {
        "report_type": "report_quality_training_no_cost_freeze_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "freeze_manifest_path": str(resolved_freeze),
        "schema_version": freeze.get("schema_version"),
        "freeze_only": freeze_state.get("freeze_only") is True,
        "aws_cost_boundary": "no_cost_increase"
        if freeze_state.get("aws_cost_increase_allowed") is False
        else "cost_increase_possible",
        "approval_record_template_validation_ok": record_validation.get("ok") if record_validation else None,
        "source_file_count": len(source_files),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a report quality training no-cost freeze manifest.")
    parser.add_argument("freeze_manifest", type=Path, help="Path to *-training-no-cost-freeze-manifest.json.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_no_cost_freeze(
        args.freeze_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost freeze validated")
        print(f"freeze_only={str(result['freeze_only']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training no-cost freeze validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
