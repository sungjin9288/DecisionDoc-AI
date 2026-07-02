"""Checking a recorded demo-smoke result against the current demo/gate state.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.procurement_decision_package.constants import (
    EVIDENCE_FILE_FIELDS,
    EXTERNAL_RUNTIME_ACTION_ORDER,
    GATE_NAME,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    SMOKE_CHECK_CONTEXT_FIELDS,
    SMOKE_CHECK_DECISION_FIELDS,
    SMOKE_CHECK_NAME,
    SMOKE_DEMO_ARTIFACT_CHECK_FIELDS,
    SMOKE_DEMO_CONTEXT_FIELDS,
    SMOKE_DEMO_IDENTITY_FIELDS,
    SMOKE_DEMO_RESULT_MATCH_FIELDS,
    SMOKE_EVIDENCE_PATH_FIELDS,
    SMOKE_NAME,
    SMOKE_PACKAGE_ARTIFACT_MATCH_FIELDS,
    SMOKE_REQUIRED_FALSE_FIELDS,
    SMOKE_REQUIRED_TRUE_FIELDS,
    _SmokeEvidenceContext,
    _SmokeEvidencePaths,
)
from app.services.procurement_decision_package.cli_manifest_check import (
    _require_passed_status,
)
from app.services.procurement_decision_package.demo_run import (
    build_evidence_files,
    build_package_artifact_check_result,
)
from app.services.procurement_decision_package.field_validators import (
    _require_string_list,
)
from app.services.procurement_decision_package.json_helpers import (
    _exception_fields,
    _field_path,
    _project_optional_fields,
    _require_boolean_fields,
    _require_exact_ordered_values,
    _require_mapping,
    _require_matching_field,
    _require_matching_fields,
    _require_path_string,
    _require_unique_values,
    load_json,
)

def _require_existing_file_path(path_value: Any, path_name: str) -> Path:
    path_text = _require_path_string(path_value, path_name)
    path = Path(path_text)
    if not path.is_file():
        raise ValueError(f"{path_name} file is missing: {path}")
    return path


def _require_existing_dir(path_value: Any, path_name: str) -> Path:
    path_text = _require_path_string(path_value, path_name)
    path = Path(path_text)
    if not path.is_dir():
        raise ValueError(f"{path_name} directory is missing: {path}")
    return path


def _require_smoke_evidence_file_paths(
    evidence_files: dict[str, Any],
) -> _SmokeEvidencePaths:
    demo_result_path = _require_smoke_evidence_file_path(
        evidence_files,
        "demo_result",
    )
    demo_receipt_path = _require_smoke_evidence_file_path(
        evidence_files,
        "demo_receipt",
    )
    gate_result_path = _require_smoke_evidence_file_path(
        evidence_files,
        "gate_result",
    )
    smoke_result_recorded_path = _require_smoke_evidence_file_path(
        evidence_files,
        "smoke_result",
    )

    return _SmokeEvidencePaths(
        demo_result_path=demo_result_path,
        demo_receipt_path=demo_receipt_path,
        gate_result_path=gate_result_path,
        smoke_result_recorded_path=smoke_result_recorded_path,
    )


def _require_smoke_evidence_file_path(
    evidence_files: dict[str, Any],
    evidence_file_field: str,
) -> Path:
    return _require_existing_file_path(
        evidence_files.get(evidence_file_field),
        f"evidence_files.{evidence_file_field}",
    )


def _require_checked_smoke_result_path(
    recorded_smoke_result_path: Path,
    checked_smoke_result_path: Path,
) -> None:
    if str(recorded_smoke_result_path) != str(checked_smoke_result_path):
        raise ValueError(
            "evidence_files.smoke_result must match "
            "the checked smoke result file"
        )


def _require_recorded_smoke_check_result(
    smoke_result: dict[str, Any],
    evidence_files: dict[str, Any],
    current_smoke_check_result: dict[str, object],
) -> None:
    smoke_check_result_written = smoke_result.get("smoke_check_result_written")
    if smoke_check_result_written is not True:
        raise ValueError(
            f"{_field_path('demo_smoke_result', 'smoke_check_result_written')} "
            "must be true"
        )

    smoke_check_result_path = _require_existing_file_path(
        evidence_files.get("smoke_check_result"),
        "evidence_files.smoke_check_result",
    )

    recorded_smoke_check_result_payload = load_json(smoke_check_result_path)
    if recorded_smoke_check_result_payload != current_smoke_check_result:
        raise ValueError(
            "demo_smoke_check_result must match "
            "the current smoke check result"
        )


def _require_gate_result_paths(
    gate_result: dict[str, Any],
    smoke_result: dict[str, Any],
    *,
    demo_result_path: Path,
    demo_receipt_path: Path,
) -> None:
    expected_smoke_demo_paths = {
        "demo_result_path": str(demo_result_path),
        "demo_receipt_path": str(demo_receipt_path),
    }

    _require_matching_field(
        gate_result,
        smoke_result,
        "output_dir",
        left_label="demo_gate_result",
        right_label="demo_smoke_result",
    )
    _require_matching_fields(
        gate_result,
        expected_smoke_demo_paths,
        ("demo_result_path", "demo_receipt_path"),
        left_label="demo_gate_result",
        right_label="demo_smoke_result",
    )


def _require_excluded_external_actions(value: Any, path: str) -> list[str]:
    excluded_external_actions = _require_string_list(value, path)
    _require_unique_values(excluded_external_actions, path)
    _require_excluded_external_action_order(
        excluded_external_actions,
        path=path,
    )
    return excluded_external_actions


def _require_excluded_external_action_order(
    recorded_excluded_external_actions: list[str],
    *,
    path: str,
) -> None:
    expected_external_actions = EXTERNAL_RUNTIME_ACTION_ORDER

    _require_exact_ordered_values(
        recorded_excluded_external_actions,
        expected_external_actions,
        path=path,
        missing_label="external actions",
        unknown_label="external actions",
    )


def _require_matching_excluded_external_actions(
    recorded_smoke_result_actions: list[str],
    comparison_actions_value: Any,
    *,
    comparison_path: str,
    comparison_label: str,
) -> None:
    comparison_actions = _require_excluded_external_actions(
        comparison_actions_value,
        comparison_path,
    )
    if recorded_smoke_result_actions != comparison_actions:
        smoke_result_actions_path = _field_path(
            "demo_smoke_result",
            "excluded_external_actions",
        )
        comparison_actions_path = _field_path(
            comparison_label,
            "excluded_external_actions",
        )
        raise ValueError(
            f"{smoke_result_actions_path} must match {comparison_actions_path}"
        )


def _require_smoke_result_check_state(
    smoke_result: dict[str, Any],
    *,
    require_smoke_result_checked: bool,
) -> None:
    _require_boolean_fields(
        smoke_result,
        SMOKE_REQUIRED_FALSE_FIELDS,
        expected=False,
        path="demo_smoke_result",
    )
    _require_boolean_fields(
        smoke_result,
        SMOKE_REQUIRED_TRUE_FIELDS,
        expected=True,
        path="demo_smoke_result",
    )
    smoke_result_checked = smoke_result.get("smoke_result_checked")
    if require_smoke_result_checked and smoke_result_checked is not True:
        raise ValueError(
            f"{_field_path('demo_smoke_result', 'smoke_result_checked')} "
            "must be true"
        )
    _require_smoke_result_checked_after_artifact_check(smoke_result)


def _require_smoke_result_checked_after_artifact_check(
    smoke_result: dict[str, Any],
) -> None:
    smoke_result_checked = smoke_result.get("smoke_result_checked")
    package_artifacts_checked = smoke_result.get("package_artifacts_checked")
    smoke_result_is_checked = smoke_result_checked is True
    artifact_check_is_missing = package_artifacts_checked is not True

    if smoke_result_is_checked and artifact_check_is_missing:
        raise ValueError(
            "package_artifacts_checked must be true "
            "when smoke_result_checked is true "
            f"({_field_path('demo_smoke_result', 'package_artifacts_checked')} "
            "depends on "
            f"{_field_path('demo_smoke_result', 'smoke_result_checked')})"
        )


def _build_smoke_check_result(
    *,
    smoke_result_path: Path,
    smoke_result: dict[str, Any],
    evidence_context: _SmokeEvidenceContext,
    excluded_external_actions: list[str],
) -> dict[str, object]:
    smoke_check_result_path_value = smoke_result.get("smoke_check_result_path")
    evidence_files = build_evidence_files(
        demo_result_path=evidence_context.demo_result_path,
        demo_receipt_path=evidence_context.demo_receipt_path,
        gate_result_path=evidence_context.gate_result_path,
        smoke_result_path=evidence_context.smoke_result_recorded_path,
        smoke_check_result_path=smoke_check_result_path_value,
    )
    smoke_context = _project_optional_fields(
        smoke_result,
        SMOKE_CHECK_CONTEXT_FIELDS,
    )
    smoke_decision = _project_optional_fields(
        smoke_result,
        SMOKE_CHECK_DECISION_FIELDS,
    )

    return {
        "status": "passed",
        "check": SMOKE_CHECK_NAME,
        "smoke_result_path": str(smoke_result_path),
        "output_dir": smoke_result.get("output_dir"),
        "package_artifacts_checked": True,
        "smoke_result_checked": True,
        "evidence_files": evidence_files,
        "smoke_check_result_path": smoke_check_result_path_value,
        **smoke_context,
        "excluded_external_actions": excluded_external_actions,
        **smoke_decision,
        "operational_approval": False,
        "clean_output": smoke_result.get("clean_output"),
    }


def check_smoke_result(
    smoke_result_path: Path,
    *,
    require_recorded_smoke_check: bool = True,
    require_recorded_smoke_check_result: bool = True,
) -> dict[str, object]:
    if not smoke_result_path.is_file():
        raise FileNotFoundError(f"smoke result file is missing: {smoke_result_path}")

    smoke_result = load_json(smoke_result_path)
    smoke_name = smoke_result.get("smoke")
    if smoke_name != SMOKE_NAME:
        raise ValueError(
            f"{_field_path('demo_smoke_result', 'smoke')} must be {SMOKE_NAME}"
        )
    _require_passed_status(smoke_result, "demo_smoke_result")
    _require_smoke_result_check_state(
        smoke_result,
        require_smoke_result_checked=require_recorded_smoke_check,
    )
    excluded_external_actions = _require_excluded_external_actions(
        smoke_result.get("excluded_external_actions"),
        "demo_smoke_result.excluded_external_actions",
    )
    evidence_context = _require_smoke_evidence_context(smoke_result, smoke_result_path)
    current_artifact_check_result = build_package_artifact_check_result(
        evidence_context.output_dir
    )
    _require_matching_fields(
        smoke_result,
        current_artifact_check_result,
        SMOKE_PACKAGE_ARTIFACT_MATCH_FIELDS,
        right_label="package_artifact_check",
    )
    demo_result = load_json(evidence_context.demo_result_path)
    schema_purpose = demo_result.get("schema_purpose")
    if schema_purpose != PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE:
        raise ValueError(
            "demo_run_result.schema_purpose must be procurement_decision_package"
        )
    _require_demo_result_matches_smoke_result(demo_result, smoke_result)
    demo_artifact_check_value = demo_result.get("artifact_check")
    demo_artifact_check = _require_mapping(
        demo_artifact_check_value,
        "demo_run_result.artifact_check",
    )
    _require_matching_fields(
        smoke_result,
        demo_artifact_check,
        SMOKE_DEMO_ARTIFACT_CHECK_FIELDS,
        right_label="demo_run_result.artifact_check",
    )
    _require_gate_result_for_smoke(
        smoke_result,
        evidence_context.gate_result_path,
        demo_result_path=evidence_context.demo_result_path,
        demo_receipt_path=evidence_context.demo_receipt_path,
        excluded_external_actions=excluded_external_actions,
    )
    smoke_check_result = _build_smoke_check_result(
        smoke_result_path=smoke_result_path,
        smoke_result=smoke_result,
        evidence_context=evidence_context,
        excluded_external_actions=excluded_external_actions,
    )
    if require_recorded_smoke_check_result:
        _require_recorded_smoke_check_result(
            smoke_result,
            evidence_context.evidence_files,
            smoke_check_result,
        )
    return smoke_check_result


def _require_smoke_evidence_context(
    smoke_result: dict[str, Any],
    smoke_result_path: Path,
) -> _SmokeEvidenceContext:
    output_dir_value = smoke_result.get("output_dir")
    output_dir = _require_existing_dir(
        output_dir_value,
        "demo_smoke_result.output_dir",
    )
    evidence_files_value = smoke_result.get("evidence_files")
    evidence_files = _require_mapping(
        evidence_files_value,
        "demo_smoke_result.evidence_files",
    )
    recorded_evidence_file_fields = list(evidence_files)

    _require_exact_ordered_values(
        recorded_evidence_file_fields,
        EVIDENCE_FILE_FIELDS,
        path="demo_smoke_result.evidence_files",
        missing_label="fields",
        unknown_label="fields",
    )
    for smoke_result_field, evidence_file_field in SMOKE_EVIDENCE_PATH_FIELDS:
        if smoke_result.get(smoke_result_field) != evidence_files.get(
            evidence_file_field
        ):
            smoke_result_field_path = _field_path(
                "demo_smoke_result",
                smoke_result_field,
            )
            evidence_file_field_path = _field_path(
                "demo_smoke_result.evidence_files",
                evidence_file_field,
            )
            raise ValueError(
                f"{smoke_result_field_path} must match "
                f"{evidence_file_field_path}"
            )
    required_evidence_paths = _require_smoke_evidence_file_paths(evidence_files)
    _require_checked_smoke_result_path(
        required_evidence_paths.smoke_result_recorded_path,
        smoke_result_path,
    )
    return _SmokeEvidenceContext(
        output_dir=output_dir,
        evidence_files=evidence_files,
        demo_result_path=required_evidence_paths.demo_result_path,
        demo_receipt_path=required_evidence_paths.demo_receipt_path,
        gate_result_path=required_evidence_paths.gate_result_path,
        smoke_result_recorded_path=required_evidence_paths.smoke_result_recorded_path,
    )


def _require_demo_result_matches_smoke_result(
    demo_result: dict[str, Any],
    smoke_result: dict[str, Any],
) -> None:
    _require_matching_fields(
        demo_result,
        smoke_result,
        SMOKE_DEMO_CONTEXT_FIELDS,
        left_label="demo_run_result",
        right_label="demo_smoke_result",
    )
    _require_matching_fields(
        demo_result,
        smoke_result,
        SMOKE_DEMO_IDENTITY_FIELDS,
        left_label="demo_run_result",
        right_label="demo_smoke_result",
    )
    _require_matching_fields(
        smoke_result,
        demo_result,
        SMOKE_DEMO_RESULT_MATCH_FIELDS,
        right_label="demo_run_result",
    )


def _require_gate_result_for_smoke(
    smoke_result: dict[str, Any],
    gate_result_path: Path,
    *,
    demo_result_path: Path,
    demo_receipt_path: Path,
    excluded_external_actions: list[str],
) -> None:
    gate_result = load_json(gate_result_path)
    gate_name = gate_result.get("gate")
    if gate_name != GATE_NAME:
        raise ValueError(
            f"{_field_path('demo_gate_result', 'gate')} must be {GATE_NAME}"
        )
    _require_passed_status(gate_result, "demo_gate_result")
    _require_gate_result_paths(
        gate_result,
        smoke_result,
        demo_result_path=demo_result_path,
        demo_receipt_path=demo_receipt_path,
    )
    gate_excluded_external_actions = gate_result.get("excluded_external_actions")
    _require_matching_excluded_external_actions(
        excluded_external_actions,
        gate_excluded_external_actions,
        comparison_path="demo_gate_result.excluded_external_actions",
        comparison_label="demo_gate_result",
    )
    _require_matching_fields(
        smoke_result,
        gate_result,
        SMOKE_PACKAGE_ARTIFACT_MATCH_FIELDS,
        right_label="demo_gate_result",
    )


def build_smoke_check_failure_result(
    smoke_result_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "check": SMOKE_CHECK_NAME,
        "status": "failed",
        "smoke_result_path": str(smoke_result_path),
        **_exception_fields(exc),
    }
