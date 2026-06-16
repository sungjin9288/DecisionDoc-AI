#!/usr/bin/env python3
"""Validate a local no-cost archive closure for report quality training evidence."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNOFF_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_archive_closure.v1"
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


def _load_signoff_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff",
        SIGNOFF_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"failed to load no-cost freeze handoff signoff validator: {SIGNOFF_VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SIGNOFF_VALIDATOR = _load_signoff_validator()


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


def validate_training_no_cost_archive_closure(
    archive_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_archive = archive_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        closure = _load_json(resolved_archive)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_no_cost_archive_closure_validation",
            "ok": False,
            "require_ready": require_ready,
            "archive_manifest_path": str(resolved_archive),
            "errors": [str(exc)],
            "warnings": [],
        }

    if closure.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if closure.get("report_type") != "report_quality_training_no_cost_archive_closure":
        errors.append("report_type must be report_quality_training_no_cost_archive_closure")

    recorded_archive_path = _resolve_path(
        closure.get("archive_manifest_path"),
        field="archive_manifest_path",
        errors=errors,
    )
    if recorded_archive_path is not None and recorded_archive_path != resolved_archive:
        warnings.append("archive_manifest_path points to a different path than the validated manifest")

    markdown_path = _resolve_path(closure.get("archive_markdown_path"), field="archive_markdown_path", errors=errors)
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training No-Cost Archive Closure" not in markdown:
            errors.append("archive markdown is missing title")
        if "aws_cost_increase_allowed: `false`" not in markdown:
            errors.append("archive markdown must show aws_cost_increase_allowed=false")
        if "training_execution_started: `false`" not in markdown:
            errors.append("archive markdown must show training_execution_started=false")
        if "operation_resume_approved: `false`" not in markdown:
            errors.append("archive markdown must show operation_resume_approved=false")

    signoff_path = _resolve_path(closure.get("signoff_path"), field="signoff_path", errors=errors)
    _validate_hash(
        path=signoff_path,
        expected_hash=closure.get("signoff_sha256"),
        field="signoff_sha256",
        errors=errors,
    )
    signoff_validation: dict[str, Any] = {}
    if signoff_path is not None:
        signoff = _load_json(signoff_path)
        signoff_validation = _SIGNOFF_VALIDATOR.validate_training_no_cost_freeze_handoff_signoff(
            signoff,
            require_complete=True,
        )
        if require_ready and signoff_validation.get("ok") is not True:
            errors.append("completed no-cost freeze handoff signoff validation must pass")

    handoff_path = _resolve_path(closure.get("handoff_manifest_path"), field="handoff_manifest_path", errors=errors)
    _validate_hash(
        path=handoff_path,
        expected_hash=closure.get("handoff_manifest_sha256"),
        field="handoff_manifest_sha256",
        errors=errors,
    )

    embedded_signoff_validation = _as_dict(closure.get("signoff_validation"))
    if require_ready and embedded_signoff_validation.get("ok") is not True:
        errors.append("embedded signoff_validation.ok must be true")
    if require_ready and embedded_signoff_validation.get("completed") is not True:
        errors.append("embedded signoff_validation.completed must be true")

    state = _as_dict(closure.get("closure_state"))
    if require_ready and state.get("ok") is not True:
        errors.append("closure_state.ok must be true")
    if state.get("status") != "archived_no_cost_hold":
        errors.append("closure_state.status must be archived_no_cost_hold")
    if state.get("archive_only") is not True:
        errors.append("closure_state.archive_only must be true")
    if state.get("freeze_handoff_signoff_completed") is not True:
        errors.append("closure_state.freeze_handoff_signoff_completed must be true")

    source_files = _as_dict(closure.get("source_files"))
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

    counts = _as_dict(closure.get("counts"))
    if counts.get("source_file_count") != len(source_files):
        errors.append("counts.source_file_count must match source_files length")
    if counts.get("missing_file_count") != missing_file_count:
        errors.append("counts.missing_file_count must match missing source files")
    if require_ready and counts.get("freeze_count", 0) < 1:
        errors.append("counts.freeze_count must be at least 1")
    if counts.get("freeze_count") != counts.get("valid_freeze_count"):
        errors.append("counts.freeze_count must match counts.valid_freeze_count")
    if counts.get("freeze_count") != counts.get("no_cost_hold_count"):
        errors.append("counts.freeze_count must match counts.no_cost_hold_count")

    operator_actions = closure.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 4:
        errors.append("operator_actions must include at least four actions")
    else:
        action_text = "\n".join(str(item) for item in operator_actions)
        if "Do not deploy AWS resources" not in action_text:
            errors.append("operator_actions must explicitly prohibit AWS deployment")
        if "Do not call provider APIs" not in action_text:
            errors.append("operator_actions must explicitly prohibit provider calls")
        if "Resume only after" not in action_text:
            errors.append("operator_actions must include resume prerequisites")

    for finding in _scan_forbidden_true(closure):
        errors.append(f"training_no_cost_archive_closure: {finding}")

    return {
        "report_type": "report_quality_training_no_cost_archive_closure_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "archive_manifest_path": str(resolved_archive),
        "schema_version": closure.get("schema_version"),
        "archive_ready": state.get("ok") is True,
        "aws_cost_boundary": "no_cost_increase"
        if state.get("aws_cost_increase_allowed") is False
        else "cost_increase_possible",
        "signoff_validation_ok": signoff_validation.get("ok") if signoff_validation else None,
        "source_file_count": len(source_files),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a local no-cost archive closure manifest.")
    parser.add_argument("archive_manifest", type=Path, help="Path to *-training-no-cost-archive-closure-manifest.json.")
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_no_cost_archive_closure(
        args.archive_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost archive closure validated")
        print(f"archive_ready={str(result['archive_ready']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training no-cost archive closure validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
