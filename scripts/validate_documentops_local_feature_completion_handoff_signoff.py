#!/usr/bin/env python3
"""Validate a DocumentOps local feature completion handoff sign-off record."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_documentops_local_feature_completion_handoff import (  # noqa: E402
    validate_documentops_local_feature_completion_handoff,
)


EXPECTED_SCHEMA = "decisiondoc_documentops_local_feature_completion_handoff_signoff.v1"
EXPECTED_VALIDATION_REPORT_TYPE = "document_ops_phase49_local_feature_completion_handoff_signoff_validation"
PHASE48_HANDOFF_PATH = (
    "docs/specs/hermes_decisiondoc_agent/"
    "phase48_local_feature_completion_handoff/local_feature_completion_handoff.json"
)
SIGNOFF_ID_PATTERN = re.compile(r"documentops_local_feature_completion_handoff_signoff_[A-Za-z0-9_-]{8,96}")
VALID_DECISIONS = {"pending", "accepted", "changes_requested", "rejected"}
COMPLETED_DECISIONS = {"accepted", "changes_requested", "rejected"}
REQUIRED_ACKS = (
    "phase48_handoff_reviewed",
    "phase47_completion_chain_reviewed",
    "operator_actions_understood",
    "service_freeze_acknowledged",
    "resume_block_acknowledged",
    "aws_no_cost_boundary_acknowledged",
    "no_production_ui_reexecution_acknowledged",
    "no_provider_calls_acknowledged",
    "no_dataset_upload_acknowledged",
    "no_training_execution_acknowledged",
    "no_model_promotion_acknowledged",
    "separate_approval_required_acknowledged",
)
REQUIRED_TRUE_BOUNDARY_FIELDS = (
    "evidence_only_signoff",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_FALSE_BOUNDARY_FIELDS = (
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
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_dataset_upload_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
)
FORBIDDEN_TRUE_KEYS = set(REQUIRED_FALSE_BOUNDARY_FIELDS) | {
    "actual_operation_resume_approved",
    "service_operation_allowed",
    "service_operation_authorized",
    "provider_api_calls_allowed",
    "external_upload_allowed",
    "training_execution_allowed",
    "model_promotion_allowed",
    "aws_runtime_enabled",
    "aws_cost_increase_authorized",
    "external_dataset_uploaded",
    "provider_job_created",
    "provider_job_polled",
    "model_training_started",
    "training_execution_started",
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


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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


def validate_documentops_local_feature_completion_handoff_signoff(
    payload: dict[str, Any],
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        errors.append(f"schema_version must be {EXPECTED_SCHEMA}")
    if payload.get("phase") != 49:
        errors.append("phase must be 49")
    if payload.get("signoff_scope") != "evidence_only_review_of_phase48_local_feature_completion_handoff":
        errors.append("signoff_scope must be evidence_only_review_of_phase48_local_feature_completion_handoff")

    signoff_id = payload.get("signoff_id")
    if not _non_empty_string(signoff_id):
        errors.append("signoff_id must be non-empty")
    elif not SIGNOFF_ID_PATTERN.fullmatch(str(signoff_id)):
        errors.append(
            "signoff_id must match "
            "documentops_local_feature_completion_handoff_signoff_[A-Za-z0-9_-]{8,96}"
        )

    decision = payload.get("decision")
    if decision not in VALID_DECISIONS:
        errors.append(f"decision must be one of {sorted(VALID_DECISIONS)}")
    completed = decision in COMPLETED_DECISIONS
    if require_complete and not completed:
        errors.append("signoff decision must be completed when --require-complete is used")
    if completed and str(signoff_id).endswith("_TEMPLATE"):
        errors.append("completed signoff must use a non-template signoff_id")
    if (completed or require_complete) and not _non_empty_string(payload.get("created_at")):
        errors.append("completed signoff requires created_at")

    source = _as_dict(payload.get("source_handoff"))
    source_path_value = source.get("path")
    source_validation: dict[str, Any] = {}
    if source_path_value != PHASE48_HANDOFF_PATH:
        errors.append("source_handoff.path must reference the Phase 48 handoff JSON")
        source_path = _resolve_repo_path(PHASE48_HANDOFF_PATH)
    else:
        source_path = _resolve_repo_path(source_path_value)

    if not source_path.exists():
        errors.append(f"source_handoff.path must exist: {source_path}")
    else:
        if source.get("sha256") != _sha256_file(source_path):
            errors.append("source_handoff.sha256 must match the Phase 48 handoff JSON")
        source_validation = validate_documentops_local_feature_completion_handoff(source_path)
        if source_validation.get("ok") is not True:
            errors.append("source_handoff must pass Phase 48 validation")
            for error in source_validation.get("errors", []):
                errors.append(f"source_handoff: {error}")

    if source.get("validator") != "scripts/validate_documentops_local_feature_completion_handoff.py":
        errors.append("source_handoff.validator must be scripts/validate_documentops_local_feature_completion_handoff.py")
    if source.get("validator_result") != "pass":
        errors.append("source_handoff.validator_result must be pass")
    if source.get("service_operation_state") != "freeze_preserved":
        errors.append("source_handoff.service_operation_state must be freeze_preserved")

    reviewer = _as_dict(payload.get("reviewer"))
    if completed or require_complete:
        for field in ("name", "title_or_team", "reviewed_at"):
            if not _non_empty_string(reviewer.get(field)):
                errors.append(f"completed signoff requires reviewer.{field}")

    evidence_reviewed = _as_list(payload.get("evidence_reviewed"))
    if completed and not evidence_reviewed:
        errors.append("completed signoff requires evidence_reviewed")

    findings = _as_dict(payload.get("findings"))
    if decision == "accepted" and not _non_empty_string(findings.get("summary")):
        errors.append("accepted signoff requires findings.summary")
    if decision in {"changes_requested", "rejected"} and not _as_list(findings.get("changes_requested")):
        errors.append(f"{decision} signoff requires findings.changes_requested")

    acknowledgements = _as_dict(payload.get("acknowledgements"))
    if completed:
        for key in REQUIRED_ACKS:
            if acknowledgements.get(key) is not True:
                errors.append(f"completed signoff requires acknowledgements.{key}=true")

    boundary = _as_dict(payload.get("signoff_boundary"))
    for field in REQUIRED_TRUE_BOUNDARY_FIELDS:
        if boundary.get(field) is not True:
            errors.append(f"signoff_boundary.{field} must be true")
    for field in REQUIRED_FALSE_BOUNDARY_FIELDS:
        if boundary.get(field) is not False:
            errors.append(f"signoff_boundary.{field} must be false")
    if boundary.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("signoff_boundary.aws_cost_boundary must be no_cost_increase")
    if boundary.get("training_boundary") != "not_authorized":
        errors.append("signoff_boundary.training_boundary must be not_authorized")

    for finding in _scan_forbidden_true(payload):
        errors.append(f"documentops_local_feature_completion_handoff_signoff: {finding}")

    if completed and not errors:
        warnings.append(
            "completed DocumentOps handoff signoff records evidence review only; "
            "it does not authorize service resume, AWS cost, provider calls, training, or model promotion"
        )

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "completed": completed and not errors,
        "require_complete": require_complete,
        "decision": decision,
        "signoff_id": payload.get("signoff_id"),
        "source_handoff_validation_ok": source_validation.get("ok") if source_validation else None,
        "service_operation_state": "freeze_preserved",
        "aws_cost_boundary": boundary.get("aws_cost_boundary", ""),
        "training_boundary": boundary.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a DocumentOps local feature completion handoff sign-off record.")
    parser.add_argument("signoff", type=Path, help="Path to Phase 49 handoff sign-off JSON.")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        payload = _load_json(args.signoff)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "completed": False,
            "require_complete": bool(args.require_complete),
            "errors": [str(exc)],
            "warnings": [],
        }
    else:
        result = validate_documentops_local_feature_completion_handoff_signoff(
            payload,
            require_complete=bool(args.require_complete),
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS documentops local feature completion handoff signoff validated")
        print(f"completed={str(result['completed']).lower()}")
        print(f"decision={result.get('decision')}")
        print(f"source_handoff_validation_ok={str(result.get('source_handoff_validation_ok')).lower()}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL documentops local feature completion handoff signoff validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
