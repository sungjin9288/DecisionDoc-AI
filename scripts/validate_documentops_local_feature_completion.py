#!/usr/bin/env python3
"""Validate the DocumentOps local feature completion package."""
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

from scripts.validate_hermes_no_cost_freeze_closeout_summary import (  # noqa: E402
    validate_hermes_no_cost_freeze_closeout_summary,
)


DEFAULT_COMPLETION_PATH = (
    REPO_ROOT
    / "docs/specs/hermes_decisiondoc_agent/phase47_local_feature_completion/local_feature_completion.json"
)
EXPECTED_REPORT_TYPE = "document_ops_phase47_local_feature_completion"
EXPECTED_VALIDATION_REPORT_TYPE = "document_ops_phase47_local_feature_completion_validation"
EXPECTED_STATUS = "local_feature_completion_validated_no_aws_no_training_authorization"
EXPECTED_FEATURE_IDS = {
    "documentops_develop_quality_agent",
    "report_workflow_develop_quality_preview",
    "report_quality_learning_gate",
    "review_packet_evidence_chain",
    "hermes_no_cost_freeze_closeout",
}
REQUIRED_ARTIFACTS = {
    "develop_document_improver_skill": {
        "path": "app/agents/skills/develop-document-improver.md",
        "fragments": ("develop_quality_improvement", "develop-document-improver"),
    },
    "documentops_agent": {
        "path": "app/agents/document_ops_agent.py",
        "fragments": ("develop_quality_improvement", "critique", "revision_tasks"),
    },
    "report_workflow_router": {
        "path": "app/routers/report_workflows.py",
        "fragments": ("/develop-quality/preview", "preview_develop_quality_improvement"),
    },
    "report_workflow_service": {
        "path": "app/services/report_workflow_service.py",
        "fragments": ("preview_develop_quality_improvement", "_build_develop_quality_payload"),
    },
    "report_workflow_ui": {
        "path": "app/static/index.html",
        "fragments": ("runReportWorkflowDevelopPreview", "Review packet JSON"),
    },
    "correction_artifact_validator": {
        "path": "docs/specs/report_quality_learning/validate_correction_artifact.py",
        "fragments": ("validate_correction_artifact", "ready_for_learning"),
    },
    "review_packet_validator": {
        "path": "docs/specs/report_quality_learning/validate_review_packet.py",
        "fragments": ("Validate a client-side report quality review packet", "preview_artifact"),
    },
    "review_packet_evidence_builder": {
        "path": "scripts/build_report_quality_review_packet_evidence.py",
        "fragments": ("review packet evidence", "provider_fine_tune_api_call_authorized"),
    },
    "review_packet_evidence_validator": {
        "path": "scripts/validate_report_quality_review_packet_evidence.py",
        "fragments": ("review packet evidence", "FORBIDDEN_TRUE_KEYS"),
    },
    "phase46_closeout_summary_json": {
        "path": "docs/specs/hermes_decisiondoc_agent/phase46_no_cost_freeze_closeout_summary/no_cost_freeze_closeout_summary.json",
        "fragments": ("document_ops_phase46_no_cost_freeze_closeout_summary", "keep_service_frozen"),
    },
    "phase46_closeout_summary_validator": {
        "path": "scripts/validate_hermes_no_cost_freeze_closeout_summary.py",
        "fragments": ("validate_hermes_no_cost_freeze_closeout_summary", "closeout_summary_valid"),
    },
    "documentops_agent_tests": {
        "path": "tests/agents/test_document_ops_agent.py",
        "fragments": ("test_document_ops_agent_runs_develop_quality_improvement_with_mock_provider",),
    },
    "report_workflow_api_tests": {
        "path": "tests/test_report_workflows_api.py",
        "fragments": ("test_report_workflow_develop_quality_preview_runs_document_ops_agent",),
    },
    "report_quality_learning_tests": {
        "path": "tests/test_report_quality_learning.py",
        "fragments": ("test_completed_correction_artifact_is_learning_ready",),
    },
    "infrastructure_tests": {
        "path": "tests/test_infrastructure.py",
        "fragments": ("test_phase46_no_cost_freeze_closeout_summary_records_receipt_chain",),
    },
}
REQUIRED_TRUE_FIELDS = (
    "local_completion_recorded",
    "develop_quality_agent_ready",
    "report_workflow_develop_preview_ready",
    "report_quality_learning_gate_ready",
    "review_packet_evidence_chain_ready",
    "phase46_freeze_summary_valid",
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else REPO_ROOT / path


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


def validate_documentops_local_feature_completion(
    completion_path: Path = DEFAULT_COMPLETION_PATH,
) -> dict[str, Any]:
    resolved_completion = completion_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        completion = _load_json(resolved_completion)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "completion_path": str(resolved_completion),
            "errors": [str(exc)],
            "warnings": [],
        }

    if completion.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if completion.get("phase") != 47:
        errors.append("phase must be 47")
    if completion.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")
    if completion.get("recommended_decision") != "keep_service_frozen":
        errors.append("recommended_decision must be keep_service_frozen")

    features = [_as_dict(item) for item in _as_list(completion.get("features"))]
    feature_ids = {feature.get("id") for feature in features}
    if feature_ids != EXPECTED_FEATURE_IDS:
        errors.append(f"features ids must be {sorted(EXPECTED_FEATURE_IDS)}")
    for feature in features:
        if feature.get("status") != "ready_local_no_cost":
            errors.append(f"features.{feature.get('id')}.status must be ready_local_no_cost")

    artifacts = [_as_dict(item) for item in _as_list(completion.get("linked_artifacts"))]
    artifacts_by_id = {artifact.get("id"): artifact for artifact in artifacts if isinstance(artifact.get("id"), str)}
    missing_artifacts = set(REQUIRED_ARTIFACTS) - set(artifacts_by_id)
    if missing_artifacts:
        errors.append(f"linked_artifacts missing required ids {sorted(missing_artifacts)}")

    for artifact_id, expected in REQUIRED_ARTIFACTS.items():
        artifact = artifacts_by_id.get(artifact_id, {})
        expected_path = expected["path"]
        if artifact.get("path") != expected_path:
            errors.append(f"linked_artifacts.{artifact_id}.path must be {expected_path}")
            continue
        path = _resolve_repo_path(expected_path)
        if not path.exists():
            errors.append(f"linked_artifacts.{artifact_id}.path must exist: {expected_path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for fragment in expected["fragments"]:
            if fragment not in text:
                errors.append(f"linked_artifacts.{artifact_id}.path must include {fragment}")
        expected_sha = artifact.get("sha256")
        if expected_sha is not None and expected_sha != _sha256_file(path):
            errors.append(f"linked_artifacts.{artifact_id}.sha256 must match {expected_path}")

    phase46 = _as_dict(completion.get("phase46_closeout_summary"))
    phase46_path = phase46.get("path")
    if phase46_path != REQUIRED_ARTIFACTS["phase46_closeout_summary_json"]["path"]:
        errors.append("phase46_closeout_summary.path must reference the Phase 46 summary JSON")
    else:
        resolved_phase46 = _resolve_repo_path(phase46_path)
        if phase46.get("sha256") != _sha256_file(resolved_phase46):
            errors.append("phase46_closeout_summary.sha256 must match the Phase 46 summary JSON")
        phase46_result = validate_hermes_no_cost_freeze_closeout_summary(resolved_phase46)
        if phase46_result.get("ok") is not True:
            errors.append("phase46_closeout_summary must pass Phase 46 validation")
            for error in phase46_result.get("errors", []):
                errors.append(f"phase46_closeout_summary: {error}")
        if phase46.get("validator_result") != "pass":
            errors.append("phase46_closeout_summary.validator_result must be pass")
        if phase46.get("service_operation_state") != "freeze_preserved":
            errors.append("phase46_closeout_summary.service_operation_state must be freeze_preserved")

    boundary = _as_dict(completion.get("completion_boundary"))
    for field in REQUIRED_TRUE_FIELDS:
        if boundary.get(field) is not True:
            errors.append(f"completion_boundary.{field} must be true")
    for field in REQUIRED_FALSE_FIELDS:
        if boundary.get(field) is not False:
            errors.append(f"completion_boundary.{field} must be false")
    if boundary.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("completion_boundary.aws_cost_boundary must be no_cost_increase")
    if boundary.get("training_boundary") != "not_authorized":
        errors.append("completion_boundary.training_boundary must be not_authorized")

    for finding in _scan_forbidden_true(completion):
        errors.append(f"documentops_local_feature_completion: {finding}")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "completion_path": str(resolved_completion),
        "local_feature_completion_valid": not errors,
        "feature_count": len(features),
        "service_operation_state": "freeze_preserved",
        "aws_cost_boundary": boundary.get("aws_cost_boundary", ""),
        "training_boundary": boundary.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the DocumentOps local feature completion package.")
    parser.add_argument(
        "completion",
        nargs="?",
        type=Path,
        default=DEFAULT_COMPLETION_PATH,
        help="Path to phase47 local_feature_completion.json.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_documentops_local_feature_completion(args.completion)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS documentops local feature completion validated")
        print(f"local_feature_completion_valid={str(result['local_feature_completion_valid']).lower()}")
        print(f"feature_count={result['feature_count']}")
        print(f"service_operation_state={result['service_operation_state']}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL documentops local feature completion validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
