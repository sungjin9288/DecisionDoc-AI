#!/usr/bin/env python3
"""Validate a DocumentOps Phase 249 validated handoff sign-off summary."""
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

from scripts.validate_documentops_phase246_validated_closure_receipt_summary_handoff_signoff import (  # noqa: E402
    validate_documentops_phase246_validated_closure_receipt_summary_handoff_signoff,
)


EXPECTED_REPORT_TYPE = (
    "document_ops_phase249_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_summary"
)
EXPECTED_VALIDATION_REPORT_TYPE = (
    "document_ops_phase250_local_feature_completion_validated_closure_receipt_summary_handoff_signoff_summary_validation"
)
EXPECTED_SCHEMA = "decisiondoc_documentops_phase247_validated_closure_receipt_summary_handoff_signoff_summary.v1"
READY_STATUS = "all_phase246_validated_closure_receipt_summary_handoff_signoffs_accepted_no_cost_boundary_preserved"
PENDING_STATUS = "pending_phase246_validated_closure_receipt_summary_handoff_signoff_review_no_training_authorization"
FORBIDDEN_TRUE_KEYS = {
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_template",
    "actual_reviewer_approval_recorded_by_summary",
    "actual_reviewer_approval_recorded_by_validator",
    "actual_reviewer_approval_recorded_by_signoff",
    "actual_operation_resume_approved",
    "service_operation_allowed",
    "service_operation_authorized",
    "service_resume_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "production_download_open_verification_authorized",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "provider_api_calls_allowed",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_upload_allowed",
    "external_dataset_upload_authorized",
    "training_execution_allowed",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_allowed",
    "model_promotion_authorized",
    "aws_deploy_started",
    "aws_resource_created",
    "scheduled_job_enabled",
    "cloudwatch_polling_started",
    "provider_job_created",
    "provider_job_polled",
    "external_dataset_uploaded",
    "training_execution_started",
    "model_candidate_emitted",
    "model_training_started",
    "model_promoted",
}
PASS_MESSAGE = "PASS documentops phase250 validated closure receipt summary handoff sign-off summary validated"
FAIL_MESSAGE = "FAIL documentops phase250 validated closure receipt summary handoff sign-off summary validation failed"


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


def validate_documentops_phase249_validated_closure_receipt_summary_handoff_signoff_summary(
    summary_path: Path,
    *,
    require_complete: bool = False,
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
            "require_complete": require_complete,
            "summary_path": str(resolved_summary),
            "errors": [str(exc)],
            "warnings": [],
        }

    if summary.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if summary.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA}")
    if summary.get("read_only") is not True:
        errors.append("read_only must be true")
    if summary.get("ok") is not True:
        errors.append("summary.ok must be true")

    readiness = _as_dict(summary.get("readiness"))
    readiness_status = readiness.get("status")
    if readiness_status not in {READY_STATUS, PENDING_STATUS}:
        errors.append(f"readiness.status must be {READY_STATUS} or {PENDING_STATUS}")
    if require_complete and readiness_status != READY_STATUS:
        errors.append(f"readiness.status must be {READY_STATUS} when --require-complete is used")
    if require_complete and summary.get("completion_ready") is not True:
        errors.append("completion_ready must be true when --require-complete is used")
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
            "aws_cost_increase_allowed",
            "provider_api_calls_authorized",
            "external_dataset_upload_authorized",
            "training_execution_authorized",
            "model_promotion_authorized",
        ),
        prefix="readiness",
        errors=errors,
    )

    counts = _as_dict(summary.get("counts"))
    signoff_count = counts.get("signoff_count")
    if not isinstance(signoff_count, int) or signoff_count < 1:
        errors.append("counts.signoff_count must be at least 1")
        signoff_count = 0
    for field in (
        "valid_signoff_count",
        "invalid_signoff_count",
        "pending_signoff_count",
        "completed_signoff_count",
        "accepted_signoff_count",
        "boundary_break_count",
        "load_error_count",
    ):
        if not isinstance(counts.get(field), int):
            errors.append(f"counts.{field} must be an integer")
    signoffs = [_as_dict(item) for item in _as_list(summary.get("signoffs"))]
    if len(signoffs) != signoff_count:
        errors.append("signoffs length must match counts.signoff_count")

    actual_valid_count = 0
    actual_completed_count = 0
    actual_accepted_count = 0
    actual_pending_count = 0
    actual_boundary_break_count = 0
    effective_require_complete = require_complete or summary.get("require_complete") is True
    for index, signoff in enumerate(signoffs, start=1):
        prefix = f"signoffs[{index}]"
        validation = _as_dict(signoff.get("validation"))
        if validation.get("ok") is True:
            actual_valid_count += 1
        if signoff.get("completed") is True:
            actual_completed_count += 1
        if signoff.get("accepted") is True:
            actual_accepted_count += 1
        if signoff.get("decision") == "pending":
            actual_pending_count += 1
        boundary_breaks = _as_list(signoff.get("boundary_breaks"))
        if boundary_breaks:
            actual_boundary_break_count += 1
            errors.append(f"{prefix}.boundary_breaks must be empty")

        signoff_path = _resolve_path(signoff.get("path"))
        if signoff_path is None:
            errors.append(f"{prefix}.path must be non-empty")
            continue
        if not signoff_path.exists():
            errors.append(f"{prefix}.path must exist: {signoff_path}")
            continue
        if signoff.get("sha256") != _sha256_file(signoff_path):
            errors.append(f"{prefix}.sha256 must match linked Phase 247 sign-off file")
        try:
            signoff_payload = _load_json(signoff_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{prefix}.path could not be loaded: {exc}")
            continue
        current_validation = validate_documentops_phase246_validated_closure_receipt_summary_handoff_signoff(
            signoff_payload,
            require_complete=effective_require_complete,
        )
        if validation.get("ok") is not (current_validation.get("ok") is True):
            errors.append(f"{prefix}.validation.ok must match current Phase 247 validation")
        if validation.get("completed") is not (current_validation.get("completed") is True):
            errors.append(f"{prefix}.validation.completed must match current Phase 247 validation")
        if validation.get("source_handoff_validation_ok") != current_validation.get("source_handoff_validation_ok"):
            errors.append(f"{prefix}.validation.source_handoff_validation_ok must match current Phase 247 validation")
        if current_validation.get("ok") is not True:
            for error in current_validation.get("errors", []):
                errors.append(f"{prefix}.current_validation: {error}")
        side_effect_boundary = _as_dict(signoff.get("side_effect_boundary"))
        _require_false_fields(
            side_effect_boundary,
            (
                "service_resume_authorized",
                "production_ui_called",
                "aws_runtime_called",
                "aws_cost_increase_allowed",
                "provider_api_calls_authorized",
                "external_dataset_upload_authorized",
                "training_execution_authorized",
                "model_promotion_authorized",
                "generation_training_execution_started",
                "generation_model_promoted",
            ),
            prefix=f"{prefix}.side_effect_boundary",
            errors=errors,
        )

    if counts.get("valid_signoff_count") != actual_valid_count:
        errors.append("counts.valid_signoff_count must match signoffs")
    if counts.get("completed_signoff_count") != actual_completed_count:
        errors.append("counts.completed_signoff_count must match signoffs")
    if counts.get("accepted_signoff_count") != actual_accepted_count:
        errors.append("counts.accepted_signoff_count must match signoffs")
    if counts.get("pending_signoff_count") != actual_pending_count:
        errors.append("counts.pending_signoff_count must match signoffs")
    if counts.get("boundary_break_count") != actual_boundary_break_count:
        errors.append("counts.boundary_break_count must match signoffs")
    if counts.get("invalid_signoff_count") != signoff_count - actual_valid_count:
        errors.append("counts.invalid_signoff_count must match signoffs")
    if counts.get("load_error_count") != 0:
        errors.append("counts.load_error_count must be 0")
    if _as_list(summary.get("load_errors")):
        errors.append("load_errors must be empty")
    if require_complete:
        if actual_completed_count != signoff_count:
            errors.append("all signoffs must be completed when --require-complete is used")
        if actual_accepted_count != signoff_count:
            errors.append("all signoffs must be accepted when --require-complete is used")

    boundary = _as_dict(summary.get("side_effect_boundary"))
    if boundary.get("reads_local_signoff_records") is not True:
        errors.append("side_effect_boundary.reads_local_signoff_records must be true")
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
            "external_dataset_upload_authorized",
            "training_execution_started",
            "model_promoted",
        ),
        prefix="side_effect_boundary",
        errors=errors,
    )

    for finding in _scan_forbidden_true(summary):
        errors.append(f"documentops_phase249_validated_closure_receipt_summary_handoff_signoff_summary: {finding}")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "require_complete": require_complete,
        "summary_path": str(resolved_summary),
        "signoff_summary_valid": not errors,
        "completion_ready": summary.get("completion_ready") is True,
        "readiness_status": readiness_status or "",
        "signoff_count": signoff_count,
        "service_operation_state": "freeze_preserved",
        "aws_cost_boundary": readiness.get("aws_cost_boundary", ""),
        "training_boundary": readiness.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a DocumentOps Phase 249 validated handoff sign-off summary."
    )
    parser.add_argument("summary", type=Path, help="Path to Phase 249 sign-off summary JSON.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_documentops_phase249_validated_closure_receipt_summary_handoff_signoff_summary(
        args.summary,
        require_complete=bool(args.require_complete),
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(PASS_MESSAGE)
        print(f"signoff_summary_valid={str(result['signoff_summary_valid']).lower()}")
        print(f"completion_ready={str(result['completion_ready']).lower()}")
        print(f"readiness_status={result['readiness_status']}")
        print(f"signoff_count={result['signoff_count']}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print(FAIL_MESSAGE)
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
