#!/usr/bin/env python3
"""Validate a no-cost operator handoff manifest."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_PATH = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report_summary.py"
)
EXPECTED_SCHEMA = "decisiondoc_report_quality_training_no_cost_operator_handoff.v1"
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


def _load_service_lock_report_summary_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_service_lock_report_summary",
        SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            "failed to load no-cost service lock report summary validator: "
            f"{SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_PATH}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SUMMARY_VALIDATOR = _load_service_lock_report_summary_validator()


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


def validate_training_no_cost_operator_handoff(
    operator_handoff_manifest_path: Path,
    *,
    require_ready: bool = True,
) -> dict[str, Any]:
    resolved_handoff = operator_handoff_manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        handoff = _load_json(resolved_handoff)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": "report_quality_training_no_cost_operator_handoff_validation",
            "ok": False,
            "require_ready": require_ready,
            "operator_handoff_manifest_path": str(resolved_handoff),
            "errors": [str(exc)],
            "warnings": [],
        }

    if handoff.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA!r}")
    if handoff.get("report_type") != "report_quality_training_no_cost_operator_handoff":
        errors.append("report_type must be report_quality_training_no_cost_operator_handoff")

    recorded_handoff_path = _resolve_path(
        handoff.get("operator_handoff_manifest_path"),
        field="operator_handoff_manifest_path",
        errors=errors,
    )
    if recorded_handoff_path is not None and recorded_handoff_path != resolved_handoff:
        warnings.append("operator_handoff_manifest_path points to a different path than the validated manifest")

    markdown_path = _resolve_path(
        handoff.get("operator_handoff_markdown_path"),
        field="operator_handoff_markdown_path",
        errors=errors,
    )
    if markdown_path is not None:
        markdown = markdown_path.read_text(encoding="utf-8")
        if "Report Quality Training No-Cost Operator Handoff" not in markdown:
            errors.append("operator handoff markdown is missing title")
        if "handoff_ready: `true`" not in markdown:
            errors.append("operator handoff markdown must show handoff_ready=true")
        if "service_operation_locked: `true`" not in markdown:
            errors.append("operator handoff markdown must show service_operation_locked=true")
        if "resume_blocked: `true`" not in markdown:
            errors.append("operator handoff markdown must show resume_blocked=true")
        if "operation_resume_approved: `false`" not in markdown:
            errors.append("operator handoff markdown must show operation_resume_approved=false")
        if "service_operation_allowed: `false`" not in markdown:
            errors.append("operator handoff markdown must show service_operation_allowed=false")
        if "aws_cost_increase_allowed: `false`" not in markdown:
            errors.append("operator handoff markdown must show aws_cost_increase_allowed=false")
        if "provider_fine_tune_api_call_authorized: `false`" not in markdown:
            errors.append("operator handoff markdown must show provider_fine_tune_api_call_authorized=false")
        if "training_execution_started: `false`" not in markdown:
            errors.append("operator handoff markdown must show training_execution_started=false")
        if "model_promotion_authorized: `false`" not in markdown:
            errors.append("operator handoff markdown must show model_promotion_authorized=false")

    summary_path = _resolve_path(
        handoff.get("service_lock_report_summary_path"),
        field="service_lock_report_summary_path",
        errors=errors,
    )
    _validate_hash(
        path=summary_path,
        expected_hash=handoff.get("service_lock_report_summary_sha256"),
        field="service_lock_report_summary_sha256",
        errors=errors,
    )
    summary_validation: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    if summary_path is not None:
        summary = _load_json(summary_path)
        summary_validation = _SUMMARY_VALIDATOR.validate_training_no_cost_service_lock_report_summary(summary_path)
        if require_ready and summary_validation.get("ok") is not True:
            errors.append("no-cost service lock report summary validation must pass")

    embedded_summary_validation = _as_dict(handoff.get("summary_validation"))
    if require_ready and embedded_summary_validation.get("ok") is not True:
        errors.append("embedded summary_validation.ok must be true")

    state = _as_dict(handoff.get("handoff_state"))
    if require_ready and state.get("ready") is not True:
        errors.append("handoff_state.ready must be true")
    if state.get("status") != "no_cost_operator_handoff_ready":
        errors.append("handoff_state.status must be no_cost_operator_handoff_ready")
    if state.get("read_only_handoff") is not True:
        errors.append("handoff_state.read_only_handoff must be true")
    if state.get("service_operation_locked") is not True:
        errors.append("handoff_state.service_operation_locked must be true")
    if state.get("resume_blocked") is not True:
        errors.append("handoff_state.resume_blocked must be true")
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
        prefix="handoff_state",
        errors=errors,
    )

    confirmed_summary_state = _as_dict(handoff.get("confirmed_summary_state"))
    if confirmed_summary_state.get("status") != "all_service_lock_reports_confirm_no_cost_service_lock":
        errors.append("confirmed_summary_state.status must confirm no-cost service lock")
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

    counts = _as_dict(handoff.get("counts"))
    report_count = counts.get("service_lock_report_count")
    if not isinstance(report_count, int) or report_count < 1:
        errors.append("counts.service_lock_report_count must be at least 1")
    if counts.get("valid_service_lock_report_count") != report_count:
        errors.append("counts.valid_service_lock_report_count must match service_lock_report_count")
    if counts.get("ready_service_lock_report_count") != report_count:
        errors.append("counts.ready_service_lock_report_count must match service_lock_report_count")
    if summary:
        summary_counts = _as_dict(summary.get("counts"))
        for field in (
            "service_lock_report_count",
            "valid_service_lock_report_count",
            "ready_service_lock_report_count",
            "closeout_receipt_count",
            "ready_closeout_receipt_count",
            "final_hold_count",
            "active_final_hold_count",
        ):
            if counts.get(field) != summary_counts.get(field):
                errors.append(f"counts.{field} must match service lock report summary counts")

    operator_actions = handoff.get("operator_actions")
    if not isinstance(operator_actions, list) or len(operator_actions) < 5:
        errors.append("operator_actions must include at least five actions")
    else:
        action_text = "\n".join(str(item) for item in operator_actions)
        if "Keep service operation disabled" not in action_text:
            errors.append("operator_actions must keep service operation disabled")
        if "Do not deploy AWS resources" not in action_text:
            errors.append("operator_actions must explicitly prohibit AWS deployment")
        if "Do not enable scheduled jobs" not in action_text:
            errors.append("operator_actions must explicitly prohibit scheduled jobs")
        if "Do not call provider APIs" not in action_text:
            errors.append("operator_actions must explicitly prohibit provider calls")
        if "Do not execute training" not in action_text:
            errors.append("operator_actions must explicitly prohibit training execution")
        if "Resume only after" not in action_text:
            errors.append("operator_actions must include resume prerequisites")

    boundary = _as_dict(handoff.get("handoff_boundary"))
    if boundary.get("reads_local_service_lock_report_summary") is not True:
        errors.append("handoff_boundary.reads_local_service_lock_report_summary must be true")
    if boundary.get("writes_local_handoff_files") is not True:
        errors.append("handoff_boundary.writes_local_handoff_files must be true")
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
        prefix="handoff_boundary",
        errors=errors,
    )

    for finding in _scan_forbidden_true(handoff):
        errors.append(f"training_no_cost_operator_handoff: {finding}")

    return {
        "report_type": "report_quality_training_no_cost_operator_handoff_validation",
        "ok": not errors,
        "require_ready": require_ready,
        "operator_handoff_manifest_path": str(resolved_handoff),
        "schema_version": handoff.get("schema_version"),
        "operator_handoff_ready": state.get("ready") is True,
        "service_operation_locked": state.get("service_operation_locked") is True,
        "resume_blocked": state.get("resume_blocked") is True,
        "aws_cost_boundary": "no_cost_increase"
        if state.get("aws_cost_increase_allowed") is False
        else "cost_increase_possible",
        "summary_validation_ok": summary_validation.get("ok") if summary_validation else None,
        "service_lock_report_count": report_count,
        "ready_service_lock_report_count": counts.get("ready_service_lock_report_count"),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a no-cost operator handoff manifest.")
    parser.add_argument(
        "operator_handoff_manifest",
        type=Path,
        help="Path to *-training-no-cost-operator-handoff-manifest.json.",
    )
    parser.add_argument("--allow-not-ready", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_training_no_cost_operator_handoff(
        args.operator_handoff_manifest,
        require_ready=not args.allow_not_ready,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS report quality training no-cost operator handoff validated")
        print(f"operator_handoff_ready={str(result['operator_handoff_ready']).lower()}")
        print(f"service_operation_locked={str(result['service_operation_locked']).lower()}")
        print(f"resume_blocked={str(result['resume_blocked']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print("training_boundary=not_authorized")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL report quality training no-cost operator handoff validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
