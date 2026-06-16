#!/usr/bin/env python3
"""Validate the DocumentOps validated handoff sign-off closure index."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.create_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_pending_signoff import (  # noqa: E402
    build_pending_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff,
)
from scripts.summarize_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoffs import (  # noqa: E402
    build_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary,
)
from scripts.validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff import (  # noqa: E402
    validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff,
)
from scripts.validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff import (  # noqa: E402
    validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff,
)
from scripts.validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary import (  # noqa: E402
    validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary,
)


DEFAULT_INDEX_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/"
    "phase89_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_index/"
    "validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_index.json"
)
EXPECTED_REPORT_TYPE = (
    "document_ops_phase89_local_feature_completion_validated_closure_handoff_signoff_"
    "closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_"
    "closure_receipt_validated_handoff_signoff_closure_index"
)
EXPECTED_VALIDATION_REPORT_TYPE = (
    "document_ops_phase89_local_feature_completion_validated_closure_handoff_signoff_"
    "closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_"
    "closure_receipt_validated_handoff_signoff_closure_index_validation"
)
EXPECTED_STATUS = (
    "validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_"
    "validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_index_ready_no_aws_no_training_authorization"
)
EXPECTED_ARTIFACTS = {
    "phase84_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff": {
        "phase": 84,
        "path": (
            "docs/specs/hermes_decisiondoc_agent/"
            "phase84_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff/"
            "validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff.json"
        ),
        "validator": (
            "scripts/validate_documentops_local_feature_completion_validated_closure_handoff_signoff_"
            "closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_"
            "closure_receipt_validated_handoff.py"
        ),
    },
    "phase85_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff_signoff_template": {
        "phase": 85,
        "path": (
            "docs/specs/hermes_decisiondoc_agent/"
            "phase85_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff/"
            "validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_template.json"
        ),
        "validator": (
            "scripts/validate_documentops_local_feature_completion_validated_closure_handoff_signoff_"
            "closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_"
            "closure_receipt_validated_handoff_signoff.py"
        ),
    },
    "phase86_pending_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff_signoff_generation_contract": {
        "phase": 86,
        "path": (
            "docs/specs/hermes_decisiondoc_agent/"
            "phase86_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_pending_signoff/"
            "pending_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_generation_contract.json"
        ),
        "validator": (
            "scripts/create_documentops_local_feature_completion_validated_closure_handoff_signoff_"
            "closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_"
            "closure_receipt_validated_handoff_pending_signoff.py"
        ),
    },
    "phase87_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff_signoff_summary_contract": {
        "phase": 87,
        "path": (
            "docs/specs/hermes_decisiondoc_agent/"
            "phase87_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary/"
            "validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary_contract.json"
        ),
        "validator": (
            "scripts/summarize_documentops_local_feature_completion_validated_closure_handoff_signoff_"
            "closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_"
            "closure_receipt_validated_handoff_signoffs.py"
        ),
    },
    "phase88_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff_signoff_summary_validation_contract": {
        "phase": 88,
        "path": (
            "docs/specs/hermes_decisiondoc_agent/"
            "phase88_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary_validation/"
            "validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary_validation_contract.json"
        ),
        "validator": (
            "scripts/validate_documentops_local_feature_completion_validated_closure_handoff_signoff_"
            "closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_"
            "closure_receipt_validated_handoff_signoff_summary.py"
        ),
    },
}
REQUIRED_TRUE_BOUNDARY_FIELDS = (
    "local_read_only_closure_validation",
    "temporary_local_probe_files_allowed",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_FALSE_BOUNDARY_FIELDS = (
    "actual_reviewer_approval_recorded_by_validator",
    "service_resume_authorized",
    "production_ui_called",
    "production_uat_reexecuted",
    "production_download_open_verification_authorized",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "aws_deploy_started",
    "aws_resource_created",
    "scheduled_job_enabled",
    "cloudwatch_polling_started",
    "provider_api_calls_authorized",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "external_dataset_uploaded",
    "training_execution_started",
    "model_candidate_emitted",
    "model_promoted",
)
FORBIDDEN_TRUE_KEYS = set(REQUIRED_FALSE_BOUNDARY_FIELDS) | {
    "aws_deploy_authorized",
    "aws_resource_creation_authorized",
    "scheduled_job_authorized",
    "cloudwatch_polling_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "external_dataset_upload_authorized",
    "training_execution_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
    "actual_reviewer_approval_recorded",
    "actual_reviewer_approval_recorded_by_template",
    "actual_reviewer_approval_recorded_by_summary",
    "actual_operation_resume_approved",
    "service_operation_allowed",
    "service_operation_authorized",
    "provider_api_calls_allowed",
    "external_upload_allowed",
    "training_execution_allowed",
    "model_promotion_allowed",
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


def _repo_path(path_value: str) -> Path:
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_source_artifacts(index: dict[str, Any], errors: list[str]) -> int:
    artifacts = [_as_dict(item) for item in _as_list(index.get("source_artifacts"))]
    artifacts_by_id = {artifact.get("id"): artifact for artifact in artifacts if isinstance(artifact.get("id"), str)}
    if set(artifacts_by_id) != set(EXPECTED_ARTIFACTS):
        errors.append(f"source_artifacts ids must be {sorted(EXPECTED_ARTIFACTS)}")

    for artifact_id, expected in EXPECTED_ARTIFACTS.items():
        artifact = artifacts_by_id.get(artifact_id, {})
        expected_path = expected["path"]
        expected_validator = expected["validator"]
        if artifact.get("phase") != expected["phase"]:
            errors.append(f"source_artifacts.{artifact_id}.phase must be {expected['phase']}")
        if artifact.get("path") != expected_path:
            errors.append(f"source_artifacts.{artifact_id}.path must be {expected_path}")
            continue
        artifact_path = _repo_path(expected_path)
        if not artifact_path.exists():
            errors.append(f"source_artifacts.{artifact_id}.path must exist: {expected_path}")
            continue
        if artifact.get("sha256") != _sha256_file(artifact_path):
            errors.append(f"source_artifacts.{artifact_id}.sha256 must match {expected_path}")
        if artifact.get("validator") != expected_validator:
            errors.append(f"source_artifacts.{artifact_id}.validator must be {expected_validator}")
        validator_path = _repo_path(expected_validator)
        if not validator_path.exists():
            errors.append(f"source_artifacts.{artifact_id}.validator must exist: {expected_validator}")
    return len(artifacts)


def _run_closure_probe() -> dict[str, Any]:
    phase84_result = (
        validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff()
    )
    template_path = _repo_path(
        EXPECTED_ARTIFACTS[
            "phase85_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff_signoff_template"
        ]["path"]
    )
    phase85_template_result = (
        validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff(
            _load_json(template_path)
        )
    )

    with tempfile.TemporaryDirectory(prefix="decisiondoc_phase89_closure_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        pending_signoff = build_pending_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff(
            signoff_id=(
                "documentops_local_feature_completion_validated_closure_receipt_validated_handoff_"
                "signoff_closure_receipt_validated_handoff_summary_handoff_signoff_phase89probe"
            ),
            created_at="2026-06-01T00:00:00+09:00",
        )
        pending_path = tmp_path / "phase89_pending_signoff.json"
        _write_json(pending_path, pending_signoff)
        phase86_pending_result = (
            validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff(
                pending_signoff
            )
        )

        summary = build_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary(
            [pending_path],
            generated_at="2026-06-01T00:00:00+09:00",
        )
        summary_path = tmp_path / "phase89_pending_summary.json"
        _write_json(summary_path, summary)
        phase88_summary_result = (
            validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_summary(
                summary_path
            )
        )

    return {
        "phase84_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff": phase84_result,
        "phase85_signoff_template": phase85_template_result,
        "phase86_temporary_pending_signoff": phase86_pending_result,
        "phase87_temporary_pending_summary": {
            "ok": summary.get("ok") is True,
            "completion_ready": summary.get("completion_ready") is True,
            "readiness_status": _as_dict(summary.get("readiness")).get("status", ""),
            "signoff_count": _as_dict(summary.get("counts")).get("signoff_count", 0),
            "errors": [],
        },
        "phase88_temporary_summary_validation": phase88_summary_result,
    }


def validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_index(
    index_path: Path = DEFAULT_INDEX_PATH,
) -> dict[str, Any]:
    resolved_index = index_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        index = _load_json(resolved_index)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "index_path": str(resolved_index),
            "errors": [str(exc)],
            "warnings": [],
        }

    if index.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if index.get("phase") != 89:
        errors.append("phase must be 89")
    if index.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")
    if index.get("closure_scope") != "local_read_only_phase84_to_phase88_validated_handoff_signoff_closure_validation":
        errors.append("closure_scope must be local_read_only_phase84_to_phase88_validated_handoff_signoff_closure_validation")
    if index.get("recommended_decision") != "keep_service_frozen":
        errors.append("recommended_decision must be keep_service_frozen")

    artifact_count = _validate_source_artifacts(index, errors)

    closure_validator = _as_dict(index.get("closure_validator"))
    if closure_validator.get("path") != (
        "scripts/validate_documentops_local_feature_completion_validated_closure_handoff_signoff_"
        "closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_"
        "closure_receipt_validated_handoff_signoff_closure_index.py"
    ):
        errors.append("closure_validator.path must reference this validator")
    for field in (
        "checks_source_artifact_hashes",
        "runs_phase84_validator",
        "validates_phase85_template",
        "generates_temporary_phase86_pending_signoff",
        "builds_temporary_phase87_summary",
        "runs_phase88_summary_validator",
    ):
        if closure_validator.get(field) is not True:
            errors.append(f"closure_validator.{field} must be true")
    if closure_validator.get("writes_repo_files") is not False:
        errors.append("closure_validator.writes_repo_files must be false")

    policy = _as_dict(index.get("closure_policy"))
    for field in (
        "pending_summary_can_validate_as_non_approval_evidence",
        "actual_reviewer_approval_still_required_for_completion",
        "phase89_is_not_service_resume_approval",
        "boundary_breaks_fail_validation",
        "artifact_hash_mismatch_fails_validation",
    ):
        if policy.get(field) is not True:
            errors.append(f"closure_policy.{field} must be true")

    boundary = _as_dict(index.get("closure_boundary"))
    for field in REQUIRED_TRUE_BOUNDARY_FIELDS:
        if boundary.get(field) is not True:
            errors.append(f"closure_boundary.{field} must be true")
    for field in REQUIRED_FALSE_BOUNDARY_FIELDS:
        if boundary.get(field) is not False:
            errors.append(f"closure_boundary.{field} must be false")
    if boundary.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("closure_boundary.aws_cost_boundary must be no_cost_increase")
    if boundary.get("training_boundary") != "not_authorized":
        errors.append("closure_boundary.training_boundary must be not_authorized")

    for finding in _scan_forbidden_true(index):
        errors.append(f"documentops_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff_signoff_closure_index: {finding}")

    probe_results = _run_closure_probe() if not errors else {}
    for name, result in probe_results.items():
        if result.get("ok") is not True:
            errors.append(f"{name} probe must pass")
            for error in result.get("errors", []):
                errors.append(f"{name}: {error}")

    phase87_probe = _as_dict(probe_results.get("phase87_temporary_pending_summary"))
    phase88_probe = _as_dict(probe_results.get("phase88_temporary_summary_validation"))
    expected_pending_status = (
        "pending_validated_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_summary_handoff_signoff_"
        "review_no_training_authorization"
    )
    if phase87_probe and phase87_probe.get("readiness_status") != expected_pending_status:
        errors.append("phase87_temporary_pending_summary.readiness_status must be pending non-approval evidence")
    if phase87_probe and phase87_probe.get("completion_ready") is not False:
        errors.append("phase87_temporary_pending_summary.completion_ready must be false")
    if phase88_probe and phase88_probe.get("completion_ready") is not False:
        errors.append("phase88_temporary_summary_validation.completion_ready must be false")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "index_path": str(resolved_index),
        "closure_index_valid": not errors,
        "source_artifact_count": artifact_count,
        "probe_count": len(probe_results),
        "temporary_summary_readiness": phase87_probe.get("readiness_status", ""),
        "service_operation_state": "freeze_preserved",
        "recommended_decision": index.get("recommended_decision", ""),
        "aws_cost_boundary": boundary.get("aws_cost_boundary", ""),
        "training_boundary": boundary.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the DocumentOps validated handoff sign-off closure index."
    )
    parser.add_argument(
        "index",
        nargs="?",
        type=Path,
        default=DEFAULT_INDEX_PATH,
        help="Path to phase89 validated handoff sign-off closure index JSON.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = (
        validate_documentops_local_feature_completion_validated_closure_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_receipt_validated_handoff_signoff_closure_index(
            args.index
        )
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print(
            "PASS documentops local feature completion validated closure handoff signoff "
            "closure receipt validated handoff signoff closure receipt validated handoff signoff "
            "closure receipt validated handoff signoff closure index validated"
        )
        print(f"closure_index_valid={str(result['closure_index_valid']).lower()}")
        print(f"source_artifact_count={result['source_artifact_count']}")
        print(f"probe_count={result['probe_count']}")
        print(f"temporary_summary_readiness={result['temporary_summary_readiness']}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"recommended_decision={result['recommended_decision']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print(
            "FAIL documentops local feature completion validated closure handoff signoff "
            "closure receipt validated handoff signoff closure receipt validated handoff signoff "
            "closure receipt validated handoff signoff closure index validation failed"
        )
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
