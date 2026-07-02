"""Checking a recorded CLI-contract-manifest validation result against the
current manifest state on disk.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from app.services.procurement_decision_package.constants import (
    CLI_CONTRACT_MANIFEST_CASE_MAP_FIELDS,
    CLI_CONTRACT_MANIFEST_CONTRACT_VERSION,
    CLI_CONTRACT_MANIFEST_CURRENT_VALIDATION_FIELDS,
    CLI_CONTRACT_MANIFEST_CURRENT_VALIDATION_MATCH_FIELDS,
    CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FAILURE_FIELDS,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FIELDS,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
    CLI_CONTRACT_MANIFEST_VALIDATION_FAILURE_FIELDS,
    CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
)
from app.services.procurement_decision_package.field_validators import (
    _require_non_empty_string_field,
)
from app.services.procurement_decision_package.json_helpers import (
    _exception_fields,
    _field_path,
    _project_fields,
    _require_exact_mapping_fields,
    _require_matching_fields,
    load_json,
)
from app.services.procurement_decision_package.sample_validation import display_path

def _require_passed_status(mapping: dict[str, Any], path: str) -> None:
    status_path = _field_path(path, "status")

    if mapping.get("status") != "passed":
        raise ValueError(f"{status_path} must be passed")


def _validation_result_field_path(field: str) -> str:
    return f"validation_result.{field}"


def check_cli_contract_manifest_validation_result(
    validation_result_path: Path,
    *,
    expected_schema_purpose: str,
    validate_current_manifest: Callable[[Path], dict[str, Any]],
    display_base_dir: Path | None = None,
) -> dict[str, object]:
    if not validation_result_path.is_file():
        raise FileNotFoundError(
            "manifest validation result file is missing: "
            f"{validation_result_path}"
        )

    recorded_validation_result = load_json(validation_result_path)
    _require_exact_mapping_fields(
        recorded_validation_result,
        CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
        "validation_result",
    )
    _validate_cli_validation_result_identity(
        recorded_validation_result,
        expected_schema_purpose=expected_schema_purpose,
    )
    manifest_path, current_manifest_validation = _load_current_manifest_validation(
        recorded_validation_result,
        validate_current_manifest=validate_current_manifest,
    )
    _validate_cli_validation_result_matches_current_manifest(
        recorded_validation_result,
        current_manifest_validation,
    )

    return _build_cli_manifest_validation_check_result(
        validation_result_path=validation_result_path,
        manifest_path=manifest_path,
        current_manifest_validation=current_manifest_validation,
        display_base_dir=display_base_dir,
    )


def _validate_cli_validation_result_identity(
    recorded_validation_result: dict[str, Any],
    *,
    expected_schema_purpose: str,
) -> None:
    schema_purpose_path = _validation_result_field_path("schema_purpose")
    if (
        recorded_validation_result.get("schema_purpose")
        != expected_schema_purpose
    ):
        raise ValueError(
            f"{schema_purpose_path} must be {expected_schema_purpose}"
        )

    _require_passed_status(recorded_validation_result, "validation_result")


def _load_current_manifest_validation(
    recorded_validation_result: dict[str, Any],
    *,
    validate_current_manifest: Callable[[Path], dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    manifest_path = _cli_manifest_path_from_validation_result(
        recorded_validation_result
    )
    current_manifest_validation = validate_current_manifest(manifest_path)

    return manifest_path, current_manifest_validation


def _validate_cli_validation_result_matches_current_manifest(
    recorded_validation_result: dict[str, Any],
    current_manifest_validation: dict[str, Any],
) -> None:
    current_manifest_case_names = current_manifest_validation["case_names"]
    _validate_cli_validation_result_case_maps(
        recorded_validation_result,
        current_manifest_case_names=current_manifest_case_names,
    )
    _require_matching_fields(
        recorded_validation_result,
        current_manifest_validation,
        CLI_CONTRACT_MANIFEST_CURRENT_VALIDATION_MATCH_FIELDS,
        left_label="validation_result",
        right_label="current_manifest_validation",
    )


def _cli_manifest_path_from_validation_result(
    recorded_validation_result: dict[str, Any],
) -> Path:
    manifest_path = _require_non_empty_string_field(
        recorded_validation_result,
        "manifest_path",
        path="validation_result",
    )

    return Path(manifest_path)


def _build_cli_manifest_validation_check_result(
    *,
    validation_result_path: Path,
    manifest_path: Path,
    current_manifest_validation: dict[str, Any],
    display_base_dir: Path | None = None,
) -> dict[str, Any]:
    current_manifest_check_fields = _project_fields(
        current_manifest_validation,
        CLI_CONTRACT_MANIFEST_CURRENT_VALIDATION_FIELDS,
    )

    return _project_fields(
        {
            "check": CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
            "status": "passed",
            "validation_result_path": display_path(
                validation_result_path,
                base_dir=display_base_dir,
            ),
            "manifest_path": display_path(
                manifest_path,
                base_dir=display_base_dir,
            ),
            **current_manifest_check_fields,
            "validation_result_checked": True,
        },
        CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FIELDS,
    )


def _validate_cli_validation_result_case_maps(
    recorded_validation_result: dict[str, Any],
    *,
    current_manifest_case_names: Sequence[str],
) -> None:
    current_manifest_case_order = list(current_manifest_case_names)
    case_names_path = _validation_result_field_path("case_names")

    for case_map_field in CLI_CONTRACT_MANIFEST_CASE_MAP_FIELDS:
        recorded_case_map = recorded_validation_result.get(case_map_field)
        case_map_path = _validation_result_field_path(case_map_field)

        if not isinstance(recorded_case_map, dict):
            raise ValueError(f"{case_map_path} must be an object")
        if list(recorded_case_map) != current_manifest_case_order:
            raise ValueError(
                f"{case_map_path} case order must match "
                f"{case_names_path}"
            )


def build_cli_contract_manifest_validation_check_failure_result(
    validation_result_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return _project_fields(
        {
            "status": "failed",
            "check": CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
            "validation_result_path": str(validation_result_path),
            **_exception_fields(exc),
        },
        CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FAILURE_FIELDS,
    )


def build_cli_contract_manifest_validation_failure_result(
    *,
    manifest_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return _project_fields(
        {
            "schema_purpose": CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
            "contract_version": CLI_CONTRACT_MANIFEST_CONTRACT_VERSION,
            "status": "failed",
            "manifest_path": str(manifest_path),
            **_exception_fields(exc),
        },
        CLI_CONTRACT_MANIFEST_VALIDATION_FAILURE_FIELDS,
    )
