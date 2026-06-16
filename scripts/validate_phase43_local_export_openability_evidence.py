#!/usr/bin/env python3
"""Validate Phase 43 local no-cost export openability evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


EXPECTED_REPORT_TYPE = "document_ops_phase43_local_export_openability_evidence"
EXPECTED_STATUS = "local_export_openability_passed_no_aws_no_training_authorization"
EXPECTED_VALIDATION_REPORT_TYPE = "document_ops_phase43_local_export_openability_evidence_validation"
FORBIDDEN_TRUE_KEYS = {
    "production_ui_called",
    "production_uat_reexecuted",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "external_dataset_uploaded",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "training_execution_started",
    "model_candidate_emitted",
    "model_promoted",
    "server_side_generated_reviewer_approval",
}
REQUIRED_RESTRICTED_FALSE_KEYS = {
    "production_ui_called",
    "aws_runtime_called",
    "aws_cost_increase_allowed",
    "external_dataset_uploaded",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "provider_job_polled",
    "training_execution_started",
    "model_candidate_emitted",
    "model_promoted",
    "server_side_generated_reviewer_approval",
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


def _require_true_fields(mapping: dict[str, Any], fields: Sequence[str], *, prefix: str, errors: list[str]) -> None:
    for field in fields:
        if mapping.get(field) is not True:
            errors.append(f"{prefix}.{field} must be true")


def _validate_generation_export(
    exports: dict[str, Any],
    name: str,
    *,
    endpoint: str,
    content_type: str,
    extension: str,
    errors: list[str],
) -> dict[str, Any]:
    export = _as_dict(exports.get(name))
    validation = _as_dict(export.get("validation"))
    prefix = f"generation_exports.{name}"
    if export.get("endpoint") != endpoint:
        errors.append(f"{prefix}.endpoint must be {endpoint}")
    if export.get("status") != 200:
        errors.append(f"{prefix}.status must be 200")
    if not isinstance(export.get("bytes"), int) or export.get("bytes", 0) <= 0:
        errors.append(f"{prefix}.bytes must be positive")
    if export.get("content_type") != content_type:
        errors.append(f"{prefix}.content_type must be {content_type}")
    if "attachment" not in str(export.get("content_disposition", "")).lower():
        errors.append(f"{prefix}.content_disposition must be an attachment")
    if extension not in str(export.get("filename", "")).lower():
        errors.append(f"{prefix}.filename must include {extension}")
    if export.get("opened") is not True:
        errors.append(f"{prefix}.opened must be true")
    if validation.get("valid_magic") is not True:
        errors.append(f"{prefix}.validation.valid_magic must be true")
    return validation


def validate_phase43_local_export_openability_evidence(evidence_path: Path) -> dict[str, Any]:
    resolved_evidence = evidence_path.expanduser().resolve()
    errors: list[str] = []
    warnings: list[str] = []
    try:
        evidence = _load_json(resolved_evidence)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
            "ok": False,
            "evidence_path": str(resolved_evidence),
            "errors": [str(exc)],
            "warnings": [],
        }

    if evidence.get("report_type") != EXPECTED_REPORT_TYPE:
        errors.append(f"report_type must be {EXPECTED_REPORT_TYPE}")
    if evidence.get("phase") != 43:
        errors.append("phase must be 43")
    if evidence.get("status") != EXPECTED_STATUS:
        errors.append(f"status must be {EXPECTED_STATUS}")

    target = _as_dict(evidence.get("target"))
    if target.get("runtime") != "FastAPI TestClient":
        errors.append("target.runtime must be FastAPI TestClient")
    if target.get("provider") != "mock":
        errors.append("target.provider must be mock")
    if target.get("data_dir") != "temporary_local_directory":
        errors.append("target.data_dir must be temporary_local_directory")
    _require_false_fields(
        target,
        ("production_uat_reexecuted", "aws_runtime_called"),
        prefix="target",
        errors=errors,
    )

    checkpoints = _as_dict(evidence.get("checkpoint_summary"))
    if checkpoints.get("status") != "passed":
        errors.append("checkpoint_summary.status must be passed")
    _require_true_fields(
        checkpoints,
        (
            "pdf_opened",
            "pptx_opened",
            "hwp_opened",
            "report_workflow_pptx_opened",
            "report_workflow_snapshot_exported",
        ),
        prefix="checkpoint_summary",
        errors=errors,
    )
    _require_false_fields(
        checkpoints,
        ("native_os_download_verified", "production_browser_uat_reexecuted"),
        prefix="checkpoint_summary",
        errors=errors,
    )
    if checkpoints.get("aws_cost_boundary") != "no_cost_increase":
        errors.append("checkpoint_summary.aws_cost_boundary must be no_cost_increase")
    if checkpoints.get("training_boundary") != "not_authorized":
        errors.append("checkpoint_summary.training_boundary must be not_authorized")

    exports = _as_dict(evidence.get("generation_exports"))
    pdf_validation = _validate_generation_export(
        exports,
        "pdf",
        endpoint="/generate/pdf",
        content_type="application/pdf",
        extension=".pdf",
        errors=errors,
    )
    if pdf_validation.get("valid_eof") is not True:
        errors.append("generation_exports.pdf.validation.valid_eof must be true")
    if pdf_validation.get("locally_openable") is not True:
        errors.append("generation_exports.pdf.validation.locally_openable must be true")

    pptx_validation = _validate_generation_export(
        exports,
        "pptx",
        endpoint="/generate/pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        extension=".pptx",
        errors=errors,
    )
    _require_true_fields(
        pptx_validation,
        ("valid_zip", "required_entries_present", "opened_with_python_pptx"),
        prefix="generation_exports.pptx.validation",
        errors=errors,
    )
    if not isinstance(pptx_validation.get("slide_count"), int) or pptx_validation.get("slide_count", 0) < 1:
        errors.append("generation_exports.pptx.validation.slide_count must be at least 1")
    if "ppt/slides/slide1.xml" not in _as_list(pptx_validation.get("slide_entries")):
        errors.append("generation_exports.pptx.validation.slide_entries must include ppt/slides/slide1.xml")

    hwp_validation = _validate_generation_export(
        exports,
        "hwp",
        endpoint="/generate/hwp",
        content_type="application/hwp+zip",
        extension=".hwpx",
        errors=errors,
    )
    _require_true_fields(
        hwp_validation,
        ("valid_zip", "required_entries_present", "mimetype_matches"),
        prefix="generation_exports.hwp.validation",
        errors=errors,
    )
    if not isinstance(hwp_validation.get("entry_count"), int) or hwp_validation.get("entry_count", 0) < 3:
        errors.append("generation_exports.hwp.validation.entry_count must be at least 3")

    workflow = _as_dict(evidence.get("report_workflow_export"))
    for field in (
        "create_status",
        "planning_generate_status",
        "planning_approve_status",
        "slides_generate_status",
        "final_submit_status",
        "pm_approve_status",
        "executive_approve_status",
        "pptx_export_status",
        "snapshot_export_status",
    ):
        if workflow.get(field) != 200:
            errors.append(f"report_workflow_export.{field} must be 200")
    if not _as_list(workflow.get("slide_approval_statuses")):
        errors.append("report_workflow_export.slide_approval_statuses must not be empty")
    if any(status != 200 for status in _as_list(workflow.get("slide_approval_statuses"))):
        errors.append("report_workflow_export.slide_approval_statuses must all be 200")
    if workflow.get("final_status") != "final_approved":
        errors.append("report_workflow_export.final_status must be final_approved")
    if workflow.get("learning_opt_in") is not False:
        errors.append("report_workflow_export.learning_opt_in must be false")
    if workflow.get("opened") is not True:
        errors.append("report_workflow_export.opened must be true")
    if not isinstance(workflow.get("pptx_export_bytes"), int) or workflow.get("pptx_export_bytes", 0) <= 0:
        errors.append("report_workflow_export.pptx_export_bytes must be positive")
    if workflow.get("snapshot_export_version") != "decisiondoc_report_workflow_snapshot.v1":
        errors.append("report_workflow_export.snapshot_export_version must be decisiondoc_report_workflow_snapshot.v1")
    workflow_pptx_validation = _as_dict(workflow.get("pptx_validation"))
    _require_true_fields(
        workflow_pptx_validation,
        ("valid_magic", "valid_zip", "required_entries_present", "opened_with_python_pptx"),
        prefix="report_workflow_export.pptx_validation",
        errors=errors,
    )
    if not isinstance(workflow_pptx_validation.get("slide_count"), int) or workflow_pptx_validation.get("slide_count", 0) < 1:
        errors.append("report_workflow_export.pptx_validation.slide_count must be at least 1")

    allowed = _as_dict(evidence.get("allowed_local_side_effects"))
    _require_true_fields(
        allowed,
        (
            "local_fastapi_testclient_called",
            "local_temp_data_dir_used",
            "mock_provider_generation_used",
            "local_evidence_files_written",
        ),
        prefix="allowed_local_side_effects",
        errors=errors,
    )
    restricted = _as_dict(evidence.get("restricted_side_effect_boundary"))
    _require_false_fields(
        restricted,
        tuple(REQUIRED_RESTRICTED_FALSE_KEYS),
        prefix="restricted_side_effect_boundary",
        errors=errors,
    )
    for finding in _scan_forbidden_true(evidence):
        errors.append(f"phase43_local_export_openability_evidence: {finding}")

    return {
        "report_type": EXPECTED_VALIDATION_REPORT_TYPE,
        "ok": not errors,
        "evidence_path": str(resolved_evidence),
        "local_export_openability_valid": not errors,
        "pdf_opened": checkpoints.get("pdf_opened") is True,
        "pptx_opened": checkpoints.get("pptx_opened") is True,
        "hwp_opened": checkpoints.get("hwp_opened") is True,
        "report_workflow_pptx_opened": checkpoints.get("report_workflow_pptx_opened") is True,
        "aws_cost_boundary": checkpoints.get("aws_cost_boundary", ""),
        "training_boundary": checkpoints.get("training_boundary", ""),
        "errors": errors,
        "warnings": warnings,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Phase 43 local no-cost export openability evidence.")
    parser.add_argument("evidence", type=Path, help="Path to local_export_openability_evidence.json.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation result.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = validate_phase43_local_export_openability_evidence(args.evidence)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    elif result["ok"]:
        print("PASS phase43 local export openability evidence validated")
        print(f"local_export_openability_valid={str(result['local_export_openability_valid']).lower()}")
        print(f"pdf_opened={str(result['pdf_opened']).lower()}")
        print(f"pptx_opened={str(result['pptx_opened']).lower()}")
        print(f"hwp_opened={str(result['hwp_opened']).lower()}")
        print(f"report_workflow_pptx_opened={str(result['report_workflow_pptx_opened']).lower()}")
        print(f"aws_cost_boundary={result['aws_cost_boundary']}")
        print(f"training_boundary={result['training_boundary']}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    else:
        print("FAIL phase43 local export openability evidence validation failed")
        for error in result["errors"]:
            print(f"ERROR {error}")
        for warning in result["warnings"]:
            print(f"WARN {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
