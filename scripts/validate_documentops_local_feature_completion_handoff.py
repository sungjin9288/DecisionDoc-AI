#!/usr/bin/env python3
"""Validate the DocumentOps local feature completion handoff package."""
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

from scripts.validate_documentops_local_feature_completion import (  # noqa: E402
    validate_documentops_local_feature_completion,
)


DEFAULT_HANDOFF_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/phase48_local_feature_completion_handoff/local_feature_completion_handoff.json"
)
PHASE47_COMPLETION_PATH = (
    "docs/specs/hermes_decisiondoc_agent/phase47_local_feature_completion/local_feature_completion.json"
)
EXPECTED_REPORT_TYPE = "document_ops_phase48_local_feature_completion_handoff"
EXPECTED_VALIDATION_REPORT_TYPE = "document_ops_phase48_local_feature_completion_handoff_validation"
EXPECTED_STATUS = "local_feature_completion_handoff_ready_no_aws_no_training_authorization"
REQUIRED_RECIPIENTS = {
    "release_owner",
    "operator",
    "product_pm_reviewer",
    "ml_ai_owner",
    "compliance_security_reviewer",
}
REQUIRED_ACTION_IDS = {
    "read_phase47_completion",
    "run_phase47_validator",
    "confirm_no_cost_boundary",
    "preserve_service_freeze",
}
REQUIRED_TRUE_FIELDS = (
    "local_completion_handoff_recorded",
    "source_completion_valid",
    "operator_handoff_ready",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_FALSE_FIELDS = (
    "service_resume_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_dataset_upload_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
)
FORBIDDEN_TRUE_KEYS = set(REQUIRED_FALSE_FIELDS) | {
    "service_operation_allowed",
    "provider_api_calls_allowed",
    "external_upload_allowed",
    "training_execution_allowed",
    "model_promotion_allowed",
    "model_training_started",
    "external_dataset_uploaded",
    "provider_job_created",
    "provider_job_polled",
    "model_promoted",
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


def _resolve_repo_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


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


def validate_documentops_local_feature_completion_handoff(
    handoff_path: Path = DEFAULT_HANDOFF_PATH,
) -> dict[str, Any]:
    resolved_handoff = handoff_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        handoff = _load_json(resolved_handoff)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "handoff_path": str(resolved_handoff),
            "errors": [str(exc)],
            "warnings": [],
        }

    if handoff.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if handoff.get("phase") != 48:
        errors.append("phase must be 48")
    if handoff.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")
    if handoff.get("handoff_scope") != "operator_handoff_for_local_freeze_safe_completion":
        errors.append("handoff_scope must be operator_handoff_for_local_freeze_safe_completion")
    if handoff.get("recommended_decision") != "keep_service_frozen":
        errors.append("recommended_decision must be keep_service_frozen")

    source = _as_dict(handoff.get("source_completion"))
    source_path_value = source.get("path")
    if source_path_value != PHASE47_COMPLETION_PATH:
        errors.append("source_completion.path must reference the Phase 47 local feature completion JSON")
        source_path = _resolve_repo_path(PHASE47_COMPLETION_PATH)
    else:
        source_path = _resolve_repo_path(source_path_value)

    if not source_path.exists():
        errors.append(f"source_completion.path must exist: {source_path}")
    else:
        expected_source_sha = source.get("sha256")
        actual_source_sha = _sha256_file(source_path)
        if expected_source_sha != actual_source_sha:
            errors.append("source_completion.sha256 must match the Phase 47 local feature completion JSON")

        source_result = validate_documentops_local_feature_completion(source_path)
        if source_result.get("ok") is not True:
            errors.append("source_completion must pass Phase 47 validation")
            for error in source_result.get("errors", []):
                errors.append(f"source_completion: {error}")

    if source.get("validator") != "scripts/validate_documentops_local_feature_completion.py":
        errors.append("source_completion.validator must be scripts/validate_documentops_local_feature_completion.py")
    if source.get("validator_result") != "pass":
        errors.append("source_completion.validator_result must be pass")
    if source.get("service_operation_state") != "freeze_preserved":
        errors.append("source_completion.service_operation_state must be freeze_preserved")

    recipients = set(_as_list(handoff.get("handoff_recipients")))
    missing_recipients = REQUIRED_RECIPIENTS - recipients
    if missing_recipients:
        errors.append(f"handoff_recipients missing required roles {sorted(missing_recipients)}")

    actions = [_as_dict(action) for action in _as_list(handoff.get("handoff_actions"))]
    action_ids = {action.get("id") for action in actions}
    if action_ids != REQUIRED_ACTION_IDS:
        errors.append(f"handoff_actions ids must be {sorted(REQUIRED_ACTION_IDS)}")
    for action in actions:
        action_id = action.get("id", "<unknown>")
        if action.get("required") is not True:
            errors.append(f"handoff_actions.{action_id}.required must be true")
        if action.get("side_effect") is not False:
            errors.append(f"handoff_actions.{action_id}.side_effect must be false")

    boundary = _as_dict(handoff.get("handoff_boundary"))
    for field in REQUIRED_TRUE_FIELDS:
        if boundary.get(field) is not True:
            errors.append(f"handoff_boundary.{field} must be true")
    for field in REQUIRED_FALSE_FIELDS:
        if boundary.get(field) is not False:
            errors.append(f"handoff_boundary.{field} must be false")
    if boundary.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("handoff_boundary.aws_cost_boundary must be no_cost_increase")
    if boundary.get("training_boundary") != "not_authorized":
        errors.append("handoff_boundary.training_boundary must be not_authorized")

    for finding in _scan_forbidden_true(handoff):
        errors.append(f"documentops_local_feature_completion_handoff: {finding}")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "handoff_path": str(resolved_handoff),
        "local_feature_completion_handoff_valid": not errors,
        "handoff_action_count": len(actions),
        "service_operation_state": "freeze_preserved",
        "aws_cost_boundary": boundary.get("aws_cost_boundary", ""),
        "training_boundary": boundary.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the DocumentOps local feature completion handoff package.")
    parser.add_argument(
        "handoff",
        nargs="?",
        type=Path,
        default=DEFAULT_HANDOFF_PATH,
        help="Path to phase48 local_feature_completion_handoff.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_documentops_local_feature_completion_handoff(args.handoff)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS documentops local feature completion handoff validated")
        print(
            "local_feature_completion_handoff_valid="
            f"{str(result['local_feature_completion_handoff_valid']).lower()}"
        )
        print(f"handoff_action_count={result['handoff_action_count']}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL documentops local feature completion handoff validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
