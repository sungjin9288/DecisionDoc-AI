#!/usr/bin/env python3
"""Validate the Phase 20/46 release handoff manifest without side effects."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


EXPECTED_REPORT_TYPE = "document_ops_phase29_reviewer_signoff_handoff_refresh"
EXPECTED_VALIDATION_REPORT_TYPE = "document_ops_phase20_release_handoff_manifest_validation"
EXPECTED_STATUS = "no_cost_freeze_closeout_summary_validated_no_aws_no_training_authorization"
EXPECTED_PHASE43_EVIDENCE_STATUS = "local_export_openability_passed_no_aws_no_training_authorization"
REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_REVIEWERS = {
    "product_pm_reviewer",
    "ml_ai_owner",
    "compliance_security_reviewer",
    "release_owner",
}
REQUIRED_RELEASE_TRUE_FIELDS = (
    "reviewer_signoff_ready",
    "human_reviewer_use_ready",
    "actual_reviewer_approval_recorded",
    "production_smoke_completed",
    "production_browser_uat_completed",
    "local_export_openability_completed",
    "phase43_validator_completed",
    "phase20_handoff_manifest_validator_completed",
    "phase44_no_cost_freeze_gate_completed",
    "phase45_no_cost_freeze_closeout_receipt_completed",
    "phase46_no_cost_freeze_closeout_summary_completed",
)
REQUIRED_RELEASE_FALSE_FIELDS = (
    "training_execution_authorized",
    "external_dataset_upload_authorized",
    "server_side_export_artifact_write_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
)
REQUIRED_PHASE43_TRUE_FIELDS = (
    "local_fastapi_testclient_called",
    "mock_provider_generation_used",
    "pdf_opened",
    "pptx_opened",
    "hwp_opened",
    "report_workflow_pptx_opened",
    "report_workflow_snapshot_exported",
    "validator_passed",
)
REQUIRED_PHASE43_FALSE_FIELDS = (
    "training_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "server_side_generated_approval_record",
    "model_promotion_authorized",
    "production_ui_called",
    "aws_runtime_called",
    "native_os_download_verified",
    "production_uat_reexecuted",
)
REQUIRED_PHASE43_SUMMARY_TRUE_FIELDS = (
    "phase43_pdf_opened",
    "phase43_pptx_opened",
    "phase43_hwp_opened",
    "phase43_report_workflow_pptx_opened",
    "phase43_report_workflow_snapshot_exported",
    "phase43_validator_passed",
)
REQUIRED_PHASE43_SUMMARY_FALSE_FIELDS = (
    "phase43_production_uat_reexecuted",
    "phase43_aws_runtime_called",
)
REQUIRED_PHASE44_TRUE_FIELDS = (
    "release_handoff_validator_passed",
    "local_export_openability_validator_passed",
    "service_freeze_recommended",
    "resume_requires_separate_approval",
)
REQUIRED_PHASE44_FALSE_FIELDS = (
    "production_ui_called",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "training_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "model_promotion_authorized",
)
REQUIRED_PHASE45_TRUE_FIELDS = (
    "closeout_receipt_recorded",
    "closeout_receipt_validator_passed",
    "no_cost_freeze_gate_validated",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_PHASE45_FALSE_FIELDS = (
    "service_resume_authorized",
    "production_ui_called",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "training_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "model_promotion_authorized",
)
REQUIRED_PHASE46_TRUE_FIELDS = (
    "closeout_summary_recorded",
    "closeout_summary_validator_passed",
    "all_closeout_receipts_valid",
    "all_closeout_receipts_confirm_freeze",
    "service_freeze_preserved",
    "resume_requires_separate_approval",
)
REQUIRED_PHASE46_FALSE_FIELDS = (
    "service_resume_authorized",
    "production_ui_called",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "training_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_called",
    "provider_job_creation_authorized",
    "model_promotion_authorized",
)
REQUIRED_ARTIFACT_IDS = {
    "status",
    "phase29_release_handoff_index",
    "phase29_handoff_manifest",
    "phase20_release_handoff_manifest_validator",
    "phase44_no_cost_freeze_gate_guide",
    "phase44_no_cost_freeze_gate_checker",
    "phase45_no_cost_freeze_closeout_receipt_report",
    "phase45_no_cost_freeze_closeout_receipt_json",
    "phase45_no_cost_freeze_closeout_receipt_validator",
    "phase46_no_cost_freeze_closeout_summary_report",
    "phase46_no_cost_freeze_closeout_summary_json",
    "phase46_no_cost_freeze_closeout_summary_validator",
    "phase40_production_signoff_completion_evidence_json",
    "phase41_production_post_deploy_smoke_evidence_json",
    "phase42_production_browser_uat_evidence_report",
    "phase42_production_browser_uat_evidence_json",
    "phase43_local_export_openability_evidence_report",
    "phase43_local_export_openability_evidence_json",
    "phase43_local_export_openability_generator",
    "phase43_local_export_openability_validator",
}
EXPECTED_ARTIFACT_RESULTS = {
    "phase20_release_handoff_manifest_validator": "pass",
    "phase44_no_cost_freeze_gate_checker": "pass",
    "phase45_no_cost_freeze_closeout_receipt_json": "pass_no_cost_freeze_closeout_receipt",
    "phase45_no_cost_freeze_closeout_receipt_validator": "pass",
    "phase46_no_cost_freeze_closeout_summary_json": "pass_no_cost_freeze_closeout_summary",
    "phase46_no_cost_freeze_closeout_summary_validator": "pass",
    "phase40_production_signoff_completion_evidence_json": "pass",
    "phase41_production_post_deploy_smoke_evidence_json": "pass",
    "phase42_production_browser_uat_evidence_json": "pass_with_download_runtime_limitation",
    "phase43_local_export_openability_evidence_json": "pass_no_cost_openability",
    "phase43_local_export_openability_validator": "pass",
}
REQUIRED_VERIFICATION_FRAGMENTS = (
    "python3 scripts/create_phase43_local_export_openability_evidence.py",
    "python3 -m json.tool docs/specs/hermes_decisiondoc_agent/phase43_local_export_openability_evidence/local_export_openability_evidence.json",
    "python3 scripts/validate_phase43_local_export_openability_evidence.py docs/specs/hermes_decisiondoc_agent/phase43_local_export_openability_evidence/local_export_openability_evidence.json",
    "pytest -q tests/test_infrastructure.py::test_phase43_local_export_openability_evidence_records_no_cost_export_checks",
    "python3 scripts/validate_phase20_release_handoff_manifest.py docs/specs/hermes_decisiondoc_agent/phase20_release_handoff/handoff_manifest.json",
    "pytest -q tests/test_infrastructure.py::test_phase20_release_handoff_manifest_validator_accepts_phase43_handoff_and_rejects_boundary_break",
    "python3 scripts/check_hermes_no_cost_freeze_gate.py",
    "pytest -q tests/test_infrastructure.py::test_phase44_no_cost_freeze_gate_composes_handoff_and_export_validators_without_side_effects",
    "python3 scripts/validate_hermes_no_cost_freeze_closeout_receipt.py",
    "test_phase45_no_cost_freeze_closeout_receipt_validator_accepts_receipt_and_rejects_boundary_break",
    "python3 scripts/validate_hermes_no_cost_freeze_closeout_summary.py",
    "test_phase46_no_cost_freeze_closeout_summary_validator_accepts_summary_and_rejects_boundary_break",
)
FORBIDDEN_TRUE_KEYS = {
    "training_execution_allowed",
    "provider_api_calls_allowed",
    "external_upload_allowed",
    "server_file_written",
    "provider_job_started",
    "model_candidate_emitted",
    "model_promotion_allowed",
    "model_training_started",
    "external_dataset_uploaded",
    "server_side_export_artifact_written",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "model_promoted",
    "production_ui_called",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "production_uat_reexecuted",
    "service_resume_authorized",
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


def _require_true_fields(mapping: dict[str, Any], fields: Sequence[str], *, prefix: str, errors: list[str]) -> None:
    for field in fields:
        if mapping.get(field) is not True:
            errors.append(f"{prefix}.{field} must be true")


def _require_false_fields(mapping: dict[str, Any], fields: Sequence[str], *, prefix: str, errors: list[str]) -> None:
    for field in fields:
        if mapping.get(field) is not False:
            errors.append(f"{prefix}.{field} must be false")


def _require_all_false(mapping: dict[str, Any], *, prefix: str, errors: list[str]) -> None:
    if not mapping:
        errors.append(f"{prefix} must be a non-empty object")
        return
    for field, value in mapping.items():
        if value is not False:
            errors.append(f"{prefix}.{field} must be false")


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


def _artifact_path(artifact: dict[str, Any]) -> Path:
    raw_path = artifact.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return Path("")
    path = Path(raw_path)
    return path if path.is_absolute() else REPO_ROOT / path


def _require_verification_fragment(
    references: Sequence[Any],
    fragment: str,
    *,
    errors: list[str],
) -> None:
    if not any(fragment in str(reference) for reference in references):
        errors.append(f"verification_references must include {fragment}")


def validate_phase20_release_handoff_manifest(manifest_path: Path) -> dict[str, Any]:
    resolved_manifest = manifest_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        manifest = _load_json(resolved_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "manifest_path": str(resolved_manifest),
            "errors": [str(exc)],
            "warnings": [],
        }

    if manifest.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if manifest.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")
    if "Phase 43 local export openability evidence and validator" not in str(manifest.get("scope", "")):
        errors.append("scope must include Phase 43 local export openability evidence and validator")
    if manifest.get("recommended_decision") != EXPECTED_STATUS:
        errors.append(f"recommended_decision must be {EXPECTED_STATUS}")
    next_step = str(manifest.get("next_step", ""))
    if "manual Chrome/Safari" not in next_step:
        errors.append("next_step must mention manual Chrome/Safari")
    if "normal production UI/export costs" not in next_step:
        errors.append("next_step must mention normal production UI/export costs")

    release_boundary = _as_dict(manifest.get("release_boundary"))
    _require_true_fields(
        release_boundary,
        REQUIRED_RELEASE_TRUE_FIELDS,
        prefix="release_boundary",
        errors=errors,
    )
    _require_false_fields(
        release_boundary,
        REQUIRED_RELEASE_FALSE_FIELDS,
        prefix="release_boundary",
        errors=errors,
    )

    reviewers = set(_as_list(manifest.get("required_reviewers")))
    missing_reviewers = REQUIRED_REVIEWERS - reviewers
    if missing_reviewers:
        errors.append(f"required_reviewers missing {sorted(missing_reviewers)}")

    reviewer_steps = _as_list(manifest.get("reviewer_use_steps"))
    if not reviewer_steps:
        errors.append("reviewer_use_steps must not be empty")
    for index, step in enumerate(reviewer_steps):
        if _as_dict(step).get("side_effect") is not False:
            errors.append(f"reviewer_use_steps[{index}].side_effect must be false")

    artifacts = [_as_dict(item) for item in _as_list(manifest.get("artifacts"))]
    artifacts_by_id = {artifact.get("id"): artifact for artifact in artifacts if isinstance(artifact.get("id"), str)}
    missing_artifacts = REQUIRED_ARTIFACT_IDS - set(artifacts_by_id)
    if missing_artifacts:
        errors.append(f"artifacts missing required ids {sorted(missing_artifacts)}")
    for artifact_id in REQUIRED_ARTIFACT_IDS & set(artifacts_by_id):
        artifact = artifacts_by_id[artifact_id]
        if artifact.get("required_for_signoff") is not True:
            errors.append(f"artifacts.{artifact_id}.required_for_signoff must be true")
        path = _artifact_path(artifact)
        if not path.exists():
            errors.append(f"artifacts.{artifact_id}.path must exist: {artifact.get('path')}")
    for artifact_id, expected_result in EXPECTED_ARTIFACT_RESULTS.items():
        artifact = artifacts_by_id.get(artifact_id, {})
        if artifact.get("result") != expected_result:
            errors.append(f"artifacts.{artifact_id}.result must be {expected_result}")

    phase_coverage = _as_dict(manifest.get("phase_coverage"))
    phase43 = _as_dict(phase_coverage.get("phase43"))
    if phase43.get("result") != "pass_no_cost_openability_validated":
        errors.append("phase_coverage.phase43.result must be pass_no_cost_openability_validated")
    _require_true_fields(
        phase43,
        REQUIRED_PHASE43_TRUE_FIELDS,
        prefix="phase_coverage.phase43",
        errors=errors,
    )
    _require_false_fields(
        phase43,
        REQUIRED_PHASE43_FALSE_FIELDS,
        prefix="phase_coverage.phase43",
        errors=errors,
    )
    phase44 = _as_dict(phase_coverage.get("phase44"))
    if phase44.get("result") != "pass_no_cost_freeze_gate":
        errors.append("phase_coverage.phase44.result must be pass_no_cost_freeze_gate")
    _require_true_fields(
        phase44,
        REQUIRED_PHASE44_TRUE_FIELDS,
        prefix="phase_coverage.phase44",
        errors=errors,
    )
    _require_false_fields(
        phase44,
        REQUIRED_PHASE44_FALSE_FIELDS,
        prefix="phase_coverage.phase44",
        errors=errors,
    )
    phase45 = _as_dict(phase_coverage.get("phase45"))
    if phase45.get("result") != "pass_no_cost_freeze_closeout_receipt":
        errors.append("phase_coverage.phase45.result must be pass_no_cost_freeze_closeout_receipt")
    _require_true_fields(
        phase45,
        REQUIRED_PHASE45_TRUE_FIELDS,
        prefix="phase_coverage.phase45",
        errors=errors,
    )
    _require_false_fields(
        phase45,
        REQUIRED_PHASE45_FALSE_FIELDS,
        prefix="phase_coverage.phase45",
        errors=errors,
    )
    phase46 = _as_dict(phase_coverage.get("phase46"))
    if phase46.get("result") != "pass_no_cost_freeze_closeout_summary":
        errors.append("phase_coverage.phase46.result must be pass_no_cost_freeze_closeout_summary")
    _require_true_fields(
        phase46,
        REQUIRED_PHASE46_TRUE_FIELDS,
        prefix="phase_coverage.phase46",
        errors=errors,
    )
    _require_false_fields(
        phase46,
        REQUIRED_PHASE46_FALSE_FIELDS,
        prefix="phase_coverage.phase46",
        errors=errors,
    )

    observed = _as_dict(manifest.get("observed_browser_qa_summary"))
    if observed.get("phase43_result") != "pass_no_cost_openability_validated":
        errors.append("observed_browser_qa_summary.phase43_result must be pass_no_cost_openability_validated")
    if observed.get("phase44_result") != "pass_no_cost_freeze_gate":
        errors.append("observed_browser_qa_summary.phase44_result must be pass_no_cost_freeze_gate")
    if observed.get("phase45_result") != "pass_no_cost_freeze_closeout_receipt":
        errors.append("observed_browser_qa_summary.phase45_result must be pass_no_cost_freeze_closeout_receipt")
    if observed.get("phase46_result") != "pass_no_cost_freeze_closeout_summary":
        errors.append("observed_browser_qa_summary.phase46_result must be pass_no_cost_freeze_closeout_summary")
    _require_true_fields(
        observed,
        REQUIRED_PHASE43_SUMMARY_TRUE_FIELDS,
        prefix="observed_browser_qa_summary",
        errors=errors,
    )
    _require_true_fields(
        observed,
        (
            "phase44_no_cost_freeze_gate_passed",
            "phase44_service_freeze_recommended",
            "phase45_closeout_receipt_recorded",
            "phase45_closeout_receipt_validator_passed",
            "phase46_closeout_summary_recorded",
            "phase46_closeout_summary_validator_passed",
        ),
        prefix="observed_browser_qa_summary",
        errors=errors,
    )
    _require_false_fields(
        observed,
        (
            *REQUIRED_PHASE43_SUMMARY_FALSE_FIELDS,
            "phase44_production_ui_called",
            "phase44_aws_runtime_called",
            "phase45_service_resume_authorized",
            "phase45_aws_runtime_called",
            "phase46_service_resume_authorized",
            "phase46_aws_runtime_called",
        ),
        prefix="observed_browser_qa_summary",
        errors=errors,
    )

    staging = _as_dict(manifest.get("staging_readiness_summary"))
    _require_true_fields(
        staging,
        (
            "phase43_local_export_openability_passed",
            "phase44_no_cost_freeze_gate_passed",
            "phase44_service_freeze_recommended",
            "phase45_closeout_receipt_recorded",
            "phase45_closeout_receipt_validator_passed",
            "phase46_closeout_summary_recorded",
            "phase46_closeout_summary_validator_passed",
            *REQUIRED_PHASE43_SUMMARY_TRUE_FIELDS,
        ),
        prefix="staging_readiness_summary",
        errors=errors,
    )
    _require_false_fields(
        staging,
        (
            *REQUIRED_PHASE43_SUMMARY_FALSE_FIELDS,
            "phase44_production_ui_called",
            "phase44_aws_runtime_called",
            "phase45_service_resume_authorized",
            "phase45_aws_runtime_called",
            "phase46_service_resume_authorized",
            "phase46_aws_runtime_called",
        ),
        prefix="staging_readiness_summary",
        errors=errors,
    )

    _require_all_false(_as_dict(manifest.get("guard_flags")), prefix="guard_flags", errors=errors)
    _require_all_false(_as_dict(manifest.get("side_effect_boundary")), prefix="side_effect_boundary", errors=errors)

    verification_references = _as_list(manifest.get("verification_references"))
    for fragment in REQUIRED_VERIFICATION_FRAGMENTS:
        _require_verification_fragment(verification_references, fragment, errors=errors)

    phase43_evidence_artifact = artifacts_by_id.get("phase43_local_export_openability_evidence_json")
    if phase43_evidence_artifact:
        evidence_path = _artifact_path(phase43_evidence_artifact)
        try:
            evidence = _load_json(evidence_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"phase43 evidence JSON must be readable: {exc}")
        else:
            if evidence.get("status") != EXPECTED_PHASE43_EVIDENCE_STATUS:
                errors.append(f"phase43 evidence status must be {EXPECTED_PHASE43_EVIDENCE_STATUS}")

    for finding in _scan_forbidden_true(manifest):
        errors.append(f"phase20_release_handoff_manifest: {finding}")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "manifest_path": str(resolved_manifest),
        "release_handoff_valid": not errors,
        "phase43_handoff_included": "phase43" in phase_coverage
        and "phase43_local_export_openability_evidence_json" in artifacts_by_id,
        "local_export_openability_validated": phase43.get("result") == "pass_no_cost_openability_validated",
        "aws_cost_boundary": "no_cost_increase",
        "training_boundary": "not_authorized",
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the Phase 20/46 release handoff manifest.")
    parser.add_argument("manifest", type=Path, help="Path to phase20_release_handoff/handoff_manifest.json.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_phase20_release_handoff_manifest(args.manifest)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS phase20 release handoff manifest validated")
        print(f"release_handoff_valid={str(result['release_handoff_valid']).lower()}")
        print(f"phase43_handoff_included={str(result['phase43_handoff_included']).lower()}")
        print(f"local_export_openability_validated={str(result['local_export_openability_validated']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL phase20 release handoff manifest validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
