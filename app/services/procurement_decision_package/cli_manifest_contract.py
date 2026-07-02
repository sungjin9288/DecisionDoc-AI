"""Validating a CLI contract manifest file against the expected contract shape.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.services.procurement_decision_package.constants import (
    CLI_CONTRACT_MANIFEST_CASE_NAMES,
    CLI_CONTRACT_MANIFEST_CASE_ORDER,
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    CLI_CONTRACT_MANIFEST_CLI_CONTRACT_FIELDS,
    CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE,
    CLI_CONTRACT_MANIFEST_FIELDS,
    CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS,
    CLI_CONTRACT_MANIFEST_GLOBAL_SUCCESS_FORBIDDEN_FIELDS,
    CLI_CONTRACT_MANIFEST_IDENTITY_VALUES,
    CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
    CLI_CONTRACT_MANIFEST_STDOUT_CONTRACT_FIELDS,
    CLI_CONTRACT_MANIFEST_STDOUT_FAILURE_FIELDS,
    CLI_CONTRACT_MANIFEST_STDOUT_SUCCESS_FIELDS,
    CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE,
    CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
    EXCLUDED_ACTION_ORDER,
)
from app.services.procurement_decision_package.field_validators import (
    _require_non_empty_string_field,
)
from app.services.procurement_decision_package.json_helpers import (
    _field_path,
    _list_item_path,
    _missing_values,
    _project_fields,
    _require_exact_mapping_fields,
    _require_exact_ordered_values,
    _require_mapping,
    _require_non_empty_list,
    _require_non_empty_string_list,
    _require_unique_values,
    _shared_values,
    _unknown_values,
    load_json,
)
from app.services.procurement_decision_package.sample_validation import display_path

def validate_cli_contract_manifest(
    manifest_path: Path,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = load_json(manifest_path)
    _require_exact_mapping_fields(
        manifest,
        CLI_CONTRACT_MANIFEST_FIELDS,
        "manifest",
    )
    _validate_cli_contract_manifest_identity(manifest)
    _validate_cli_contract_manifest_stdout_contract(manifest)
    excluded_external_actions = _validate_cli_contract_manifest_excluded_actions(
        manifest
    )
    contracts, case_names, scripts = _validate_cli_contract_manifest_contracts(
        manifest,
        repo_root=repo_root,
    )

    return _build_cli_contract_manifest_validation_result(
        manifest_path=manifest_path,
        manifest_bytes=manifest_bytes,
        manifest=manifest,
        contracts=contracts,
        case_names=case_names,
        scripts=scripts,
        excluded_external_actions=excluded_external_actions,
        display_base_dir=repo_root,
    )


def _build_cli_contract_manifest_validation_result(
    *,
    manifest_path: Path,
    manifest_bytes: bytes,
    manifest: dict[str, Any],
    contracts: list[dict[str, Any]],
    case_names: list[str],
    scripts: list[str],
    excluded_external_actions: list[str],
    display_base_dir: Path | None = None,
) -> dict[str, Any]:
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    success_required_fields_by_case = _cli_contract_required_fields_by_case(
        contracts,
        "success_required_fields",
    )
    failure_required_fields_by_case = _cli_contract_required_fields_by_case(
        contracts,
        "failure_required_fields",
    )
    cli_contract_fingerprint = build_cli_contract_manifest_fingerprint(
        contracts,
        excluded_external_actions,
    )

    return _project_fields(
        {
            "schema_purpose": CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
            "status": "passed",
            "contract_version": manifest["contract_version"],
            "manifest_path": display_path(
                manifest_path,
                base_dir=display_base_dir,
            ),
            "manifest_sha256": manifest_sha256,
            "manifest_size_bytes": len(manifest_bytes),
            "workflow": manifest["workflow"],
            "contract_status": manifest["contract_status"],
            "contract_count": len(contracts),
            "script_count": len(scripts),
            "case_names": case_names,
            "scripts": scripts,
            "external_actions_excluded": excluded_external_actions,
            "success_required_fields_by_case": success_required_fields_by_case,
            "failure_required_fields_by_case": failure_required_fields_by_case,
            "cli_contract_fingerprint": cli_contract_fingerprint,
        },
        CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
    )


def _cli_contract_required_fields_by_case(
    contracts: Sequence[dict[str, Any]],
    field_name: str,
) -> dict[str, list[str]]:
    return {
        contract["case_name"]: contract[field_name]
        for contract in contracts
    }


def _validate_cli_contract_manifest_identity(
    manifest: dict[str, Any],
) -> None:
    manifest_field_path = "manifest"
    for field, expected_value in CLI_CONTRACT_MANIFEST_IDENTITY_VALUES:
        _require_cli_contract_value(
            manifest,
            field,
            expected_value,
            manifest_field_path,
        )


def _validate_cli_contract_manifest_excluded_actions(
    manifest: dict[str, Any],
) -> list[str]:
    excluded_external_actions_path = "manifest.external_actions_excluded"
    excluded_external_actions = _require_non_empty_string_list(
        manifest.get("external_actions_excluded"),
        excluded_external_actions_path,
    )
    _require_unique_values(
        excluded_external_actions,
        excluded_external_actions_path,
    )
    _require_exact_ordered_values(
        excluded_external_actions,
        EXCLUDED_ACTION_ORDER,
        path=excluded_external_actions_path,
    )

    return excluded_external_actions


def _validate_cli_contract_manifest_contracts(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    contracts_path = "manifest.cli_contracts"
    manifest_contract_entries = _require_non_empty_list(
        manifest.get("cli_contracts"),
        contracts_path,
    )
    contracts: list[dict[str, Any]] = []
    case_names: list[str] = []
    scripts: list[str] = []

    for index, contract_entry in enumerate(manifest_contract_entries):
        contract_path = _list_item_path(contracts_path, index)
        contract, case_name, script = _validate_cli_contract_manifest_entry(
            contract_entry,
            contract_path=contract_path,
            repo_root=repo_root,
        )
        contracts.append(contract)
        case_names.append(case_name)
        scripts.append(script)

    _validate_cli_contract_manifest_contract_collection(
        case_names=case_names,
        scripts=scripts,
    )

    return contracts, case_names, scripts


def _validate_cli_contract_manifest_entry(
    contract_entry: Any,
    *,
    contract_path: str,
    repo_root: Path,
) -> tuple[dict[str, Any], str, str]:
    contract = _require_mapping(contract_entry, contract_path)
    _require_exact_mapping_fields(
        contract,
        CLI_CONTRACT_MANIFEST_CLI_CONTRACT_FIELDS,
        contract_path,
    )
    case_name = _require_non_empty_string_field(
        contract,
        "case_name",
        path=contract_path,
    )
    script = _require_non_empty_string_field(
        contract,
        "script",
        path=contract_path,
    )
    _validate_cli_contract_manifest_contract_script(
        case_name=case_name,
        script=script,
        contract_path=contract_path,
        repo_root=repo_root,
    )
    _validate_cli_contract_manifest_success_fields(
        contract,
        case_name=case_name,
        contract_path=contract_path,
    )
    _validate_cli_contract_manifest_failure_fields(
        contract,
        case_name=case_name,
        contract_path=contract_path,
    )

    return contract, case_name, script


def _validate_cli_contract_manifest_contract_collection(
    *,
    case_names: Sequence[str],
    scripts: Sequence[str],
) -> None:
    _require_unique_values(
        case_names,
        "manifest.cli_contracts.case_name",
        message="manifest.cli_contracts case_name values must be unique",
    )
    _require_unique_values(
        scripts,
        "manifest.cli_contracts.script",
        message="manifest.cli_contracts script values must be unique",
    )

    missing_cases = _missing_values(CLI_CONTRACT_MANIFEST_CASE_NAMES, case_names)
    unknown_cases = _unknown_values(
        case_names,
        CLI_CONTRACT_MANIFEST_CASE_NAMES,
    )
    if missing_cases or unknown_cases:
        detail_text = _cli_contract_case_set_mismatch_detail(
            missing_cases,
            unknown_cases,
        )
        raise ValueError(
            f"manifest.cli_contracts case_name set mismatch: {detail_text}"
        )
    if list(case_names) != list(CLI_CONTRACT_MANIFEST_CASE_ORDER):
        raise ValueError(
            "manifest.cli_contracts case_name values must match the expected order"
        )


def _cli_contract_case_set_mismatch_detail(
    missing_cases: Sequence[str],
    unknown_cases: Sequence[str],
) -> str:
    details: list[str] = []
    if missing_cases:
        details.append(f"missing: {', '.join(missing_cases)}")
    if unknown_cases:
        details.append(f"extra: {', '.join(unknown_cases)}")

    return "; ".join(details)


def _validate_cli_contract_manifest_contract_script(
    *,
    case_name: str,
    script: str,
    contract_path: str,
    repo_root: Path,
) -> None:
    script_field_path = _field_path(contract_path, "script")
    script_path = Path(script)
    is_repo_scripts_path = (
        not script_path.is_absolute()
        and script_path.parts[:1] == ("scripts",)
    )
    if not is_repo_scripts_path:
        raise ValueError(
            f"{script_field_path} must be a repo-relative scripts/ path"
        )
    if not (repo_root / script_path).is_file():
        raise ValueError(f"{script_field_path} file is missing: {script}")

    expected_case_script = CLI_CONTRACT_MANIFEST_CASE_SCRIPTS.get(case_name)
    if expected_case_script is not None and script != expected_case_script:
        raise ValueError(
            f"{script_field_path} must be {expected_case_script!r} "
            f"for case_name {case_name!r}"
        )


def _validate_cli_contract_manifest_success_fields(
    contract: dict[str, Any],
    *,
    case_name: str,
    contract_path: str,
) -> list[str]:
    success_fields, fields_path = _require_cli_contract_manifest_case_fields(
        contract,
        case_name=case_name,
        contract_path=contract_path,
        field_name="success_required_fields",
        expected_fields_by_case=CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE,
    )
    if "status" not in success_fields:
        raise ValueError(f"{fields_path} must include status")
    forbidden_fields = _shared_values(
        success_fields,
        CLI_CONTRACT_MANIFEST_GLOBAL_SUCCESS_FORBIDDEN_FIELDS,
    )
    if forbidden_fields:
        raise ValueError(
            f"{fields_path} includes forbidden fields: "
            f"{', '.join(forbidden_fields)}"
        )

    return success_fields


def _require_cli_contract_manifest_case_fields(
    contract: dict[str, Any],
    *,
    case_name: str,
    contract_path: str,
    field_name: str,
    expected_fields_by_case: dict[str, Sequence[str]],
) -> tuple[list[str], str]:
    fields = _require_cli_contract_exact_case_fields(
        contract.get(field_name),
        expected_fields_by_case,
        case_name=case_name,
        field_name=field_name,
        path=contract_path,
    )
    fields_path = _field_path(contract_path, field_name)

    return fields, fields_path


def _validate_cli_contract_manifest_failure_fields(
    contract: dict[str, Any],
    *,
    case_name: str,
    contract_path: str,
) -> list[str]:
    failure_fields, fields_path = _require_cli_contract_manifest_case_fields(
        contract,
        case_name=case_name,
        contract_path=contract_path,
        field_name="failure_required_fields",
        expected_fields_by_case=CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE,
    )
    missing_fields = _missing_values(
        CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS,
        failure_fields,
    )
    if missing_fields:
        raise ValueError(
            f"{fields_path} missing values: {', '.join(missing_fields)}"
        )

    return failure_fields


def build_cli_contract_manifest_fingerprint(
    contracts: list[dict[str, Any]],
    excluded_external_actions: list[str],
) -> str:
    fingerprint_payload = _build_cli_contract_manifest_fingerprint_payload(
        contracts,
        excluded_external_actions,
    )
    canonical_payload = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _build_cli_contract_manifest_fingerprint_payload(
    contracts: list[dict[str, Any]],
    excluded_external_actions: list[str],
) -> dict[str, Any]:
    return {
        "stdout_json_contract": _build_cli_contract_stdout_fingerprint_payload(),
        "external_actions_excluded": excluded_external_actions,
        "cli_contracts": [
            _build_cli_contract_entry_fingerprint_payload(contract)
            for contract in contracts
        ],
    }


def _build_cli_contract_stdout_fingerprint_payload() -> dict[str, Any]:
    return {
        "success": _build_cli_contract_stdout_success_fingerprint_payload(),
        "handled_failure": _build_cli_contract_stdout_failure_fingerprint_payload(),
    }


def _build_cli_contract_stdout_success_fingerprint_payload() -> dict[str, Any]:
    return {
        "exit_code": 0,
        "status": "passed",
        "forbidden_fields": list(
            CLI_CONTRACT_MANIFEST_GLOBAL_SUCCESS_FORBIDDEN_FIELDS
        ),
    }


def _build_cli_contract_stdout_failure_fingerprint_payload() -> dict[str, Any]:
    return {
        "exit_code": 1,
        "status": "failed",
        "required_fields": list(
            CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS
        ),
    }


def _build_cli_contract_entry_fingerprint_payload(
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "case_name": contract["case_name"],
        "script": contract["script"],
        "success_required_fields": contract["success_required_fields"],
        "failure_required_fields": contract["failure_required_fields"],
    }


def _validate_cli_contract_manifest_stdout_contract(
    manifest: dict[str, Any],
) -> None:
    stdout_contract_path = "manifest.stdout_json_contract"
    stdout_contract = _require_mapping(
        manifest.get("stdout_json_contract"),
        stdout_contract_path,
    )
    _require_exact_mapping_fields(
        stdout_contract,
        CLI_CONTRACT_MANIFEST_STDOUT_CONTRACT_FIELDS,
        stdout_contract_path,
    )
    success, success_path = _require_stdout_contract_section(
        stdout_contract,
        "success",
    )
    handled_failure, handled_failure_path = _require_stdout_contract_section(
        stdout_contract,
        "handled_failure",
    )
    _validate_cli_contract_manifest_stdout_success(success, success_path)
    _validate_cli_contract_manifest_stdout_failure(
        handled_failure,
        handled_failure_path,
    )


def _require_stdout_contract_section(
    stdout_contract: dict[str, Any],
    field: str,
) -> tuple[dict[str, Any], str]:
    section_path = _stdout_contract_field_path(field)
    section = _require_mapping(stdout_contract.get(field), section_path)

    return section, section_path


def _validate_cli_contract_manifest_stdout_success(
    success: dict[str, Any],
    success_path: str,
) -> None:
    _require_exact_mapping_fields(
        success,
        CLI_CONTRACT_MANIFEST_STDOUT_SUCCESS_FIELDS,
        success_path,
    )
    _require_stdout_contract_outcome(
        success,
        exit_code=0,
        status="passed",
        path=success_path,
    )
    _require_cli_contract_exact_string_list(
        success.get("forbidden_fields"),
        CLI_CONTRACT_MANIFEST_GLOBAL_SUCCESS_FORBIDDEN_FIELDS,
        _field_path(success_path, "forbidden_fields"),
    )


def _validate_cli_contract_manifest_stdout_failure(
    handled_failure: dict[str, Any],
    handled_failure_path: str,
) -> None:
    _require_exact_mapping_fields(
        handled_failure,
        CLI_CONTRACT_MANIFEST_STDOUT_FAILURE_FIELDS,
        handled_failure_path,
    )
    _require_stdout_contract_outcome(
        handled_failure,
        exit_code=1,
        status="failed",
        path=handled_failure_path,
    )
    _require_cli_contract_exact_string_list(
        handled_failure.get("required_fields"),
        CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS,
        _field_path(handled_failure_path, "required_fields"),
    )


def _stdout_contract_field_path(field: str) -> str:
    return f"manifest.stdout_json_contract.{field}"


def _require_stdout_contract_outcome(
    section: dict[str, Any],
    *,
    exit_code: int,
    status: str,
    path: str,
) -> None:
    _require_cli_contract_value(section, "exit_code", exit_code, path)
    _require_cli_contract_value(section, "status", status, path)


def _require_cli_contract_exact_string_list(
    value: Any,
    expected_values: Sequence[str],
    path: str,
) -> list[str]:
    string_items = _require_non_empty_string_list(value, path)
    _require_unique_values(string_items, path)

    _require_exact_ordered_values(
        string_items,
        expected_values,
        path=path,
    )
    return string_items


def _require_cli_contract_exact_case_fields(
    value: Any,
    expected_fields_by_case: dict[str, Sequence[str]],
    *,
    case_name: str,
    field_name: str,
    path: str,
) -> list[str]:
    field_path = _field_path(path, field_name)
    expected_case_fields = expected_fields_by_case.get(case_name)
    if expected_case_fields is None:
        raise ValueError(
            f"{field_path} has no exact field contract for case_name {case_name!r}"
        )

    return _require_cli_contract_exact_string_list(
        value,
        expected_case_fields,
        field_path,
    )


def _require_cli_contract_value(
    mapping: dict[str, Any],
    key: str,
    contract_value: Any,
    path: str,
) -> None:
    field_path = _field_path(path, key)

    if mapping.get(key) != contract_value:
        raise ValueError(f"{field_path} must be {contract_value!r}")
