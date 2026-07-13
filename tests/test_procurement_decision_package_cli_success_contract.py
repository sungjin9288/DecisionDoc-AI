from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_CASE_ORDER,
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
    DEMO_PROJECT_ID,
    DEMO_RECOMMENDATION,
    DEMO_TENANT_ID,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    EXTERNAL_RUNTIME_ACTION_ORDER,
    GATE_NAME,
    LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH,
    LOCAL_DEMO_SCENARIO_ID,
    PACKET_SCHEMA_VERSION,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    REVIEW_RECEIPT_PENDING,
    SMOKE_CHECK_NAME,
    SMOKE_NAME,
    SMOKE_RESULT_NAME,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH
SAMPLE_OUTPUT_DIR_NAME = "sample-out"
DEMO_DATA_DIR_NAME = "demo-data"
DEMO_OUTPUT_DIR_NAME = "demo-out"
EXPORT_OUTPUT_DIR_NAME = "export-out"
SMOKE_DATA_DIR_NAME = "smoke-data"
SMOKE_OUTPUT_DIR_NAME = "smoke-out"
CUSTOM_MANIFEST_VALIDATION_RESULT_NAME = "cli-contract-manifest-validation-result.json"
SHA256_HEX_DIGEST_LENGTH = 64
MIRRORED_MANIFEST_VALIDATION_FIELDS = (
    "case_names",
    "scripts",
    "external_actions_excluded",
    "success_required_fields_by_case",
    "failure_required_fields_by_case",
    "cli_contract_fingerprint",
)


def _load_contract_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema_purpose"] == CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE, manifest
    return manifest


def _script_path(case_name: str) -> str:
    return str(ROOT / CLI_CONTRACT_MANIFEST_CASE_SCRIPTS[case_name])


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(cli_run.stdout)


def _assert_cli_completed(
    cli_run: subprocess.CompletedProcess[str],
    *,
    exit_code: int,
    context: object,
) -> None:
    assert cli_run.returncode == exit_code, context
    assert cli_run.stderr == "", context


def _run_success_json(
    case_name: str,
    *args: str,
    success_contract: dict[str, Any],
) -> dict[str, Any]:
    cli_run = subprocess.run(
        [sys.executable, _script_path(case_name), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    success_payload = _load_stdout_json(cli_run)

    _assert_cli_completed(
        cli_run,
        exit_code=success_contract["exit_code"],
        context=success_payload,
    )
    assert success_payload["status"] == success_contract["status"], success_payload
    for forbidden_field in success_contract["forbidden_fields"]:
        assert forbidden_field not in success_payload, {
            "field": forbidden_field,
            "success_payload": success_payload,
        }
    return success_payload


def _assert_success_fields(
    *,
    case_name: str,
    success_payload: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
) -> None:
    expected_success_fields = contracts[case_name]["success_required_fields"]
    actual_success_fields = list(success_payload)
    assert actual_success_fields == expected_success_fields, {
        "case_name": case_name,
        "expected": expected_success_fields,
        "actual": actual_success_fields,
        "success_payload": success_payload,
    }


def _run_success_case(
    case_name: str,
    *args: str,
    success_contract: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    success_payload = _run_success_json(
        case_name,
        *args,
        success_contract=success_contract,
    )
    _assert_success_fields(
        case_name=case_name,
        success_payload=success_payload,
        contracts=contracts,
    )

    return success_payload


def test_local_evidence_clis_return_success_json_with_passed_status(tmp_path: Path) -> None:
    manifest = _load_contract_manifest()
    contracts = {
        contract_case["case_name"]: contract_case
        for contract_case in manifest["cli_contracts"]
    }
    success_contract = manifest["stdout_json_contract"]["success"]
    case_order = list(CLI_CONTRACT_MANIFEST_CASE_ORDER)
    assert list(contracts) == case_order
    demo_excluded_actions = list(EXTERNAL_RUNTIME_ACTION_ORDER)

    sample_out = tmp_path / SAMPLE_OUTPUT_DIR_NAME
    demo_data = tmp_path / DEMO_DATA_DIR_NAME
    demo_out = tmp_path / DEMO_OUTPUT_DIR_NAME
    export_out = tmp_path / EXPORT_OUTPUT_DIR_NAME
    smoke_data = tmp_path / SMOKE_DATA_DIR_NAME
    smoke_out = tmp_path / SMOKE_OUTPUT_DIR_NAME
    manifest_validation_result_path = tmp_path / CUSTOM_MANIFEST_VALIDATION_RESULT_NAME
    packet_path = tmp_path / "procurement-review-packet.zip"
    review_receipt_path = tmp_path / "procurement-review-receipt.json"

    validator_result = _run_success_case(
        "sample_validator",
        success_contract=success_contract,
        contracts=contracts,
    )
    assert validator_result["scenario_id"] == LOCAL_DEMO_SCENARIO_ID
    assert validator_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY

    builder_result = _run_success_case(
        "sample_builder",
        "--out-dir",
        str(sample_out),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert builder_result["output_dir"] == str(sample_out)
    assert builder_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY

    artifact_check_result = _run_success_case(
        "artifact_checker",
        str(sample_out),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert artifact_check_result["output_dir"] == str(sample_out)
    assert artifact_check_result["operational_approval"] is False
    assert artifact_check_result["demo_result_checked"] is False
    assert artifact_check_result["artifact_inventory_checked"] is False
    assert artifact_check_result["demo_receipt_checked"] is False

    packet_result = _run_success_case(
        "packet_manager",
        "create",
        str(sample_out),
        "--packet",
        str(packet_path),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert packet_result["operation"] == "create"
    assert packet_result["source_dir"] == str(sample_out)
    assert packet_result["packet_path"] == str(packet_path)
    assert packet_result["schema_version"] == PACKET_SCHEMA_VERSION
    assert packet_result["artifact_count"] == len(builder_result["artifacts"])
    assert packet_result["entry_count"] == len(builder_result["artifacts"]) + 1
    assert packet_result["operational_approval"] is False
    assert packet_result["packet_verified"] is True

    review_receipt_result = _run_success_case(
        "review_receipt_manager",
        "init",
        str(packet_path),
        "--receipt",
        str(review_receipt_path),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert review_receipt_result["operation"] == "init"
    assert review_receipt_result["packet_path"] == str(packet_path)
    assert review_receipt_result["receipt_path"] == str(review_receipt_path)
    assert review_receipt_result["review_status"] == REVIEW_RECEIPT_PENDING
    assert review_receipt_result["packet_sha256"] == packet_result["packet_sha256"]
    assert review_receipt_result["reviewer"] == "executive-reviewer"
    assert review_receipt_result["decision"] is None
    assert review_receipt_result["reviewed_at"] is None
    assert review_receipt_result["operational_approval"] is False
    assert review_receipt_result["receipt_valid"] is True

    demo_result = _run_success_case(
        "demo_runner",
        "--data-dir",
        str(demo_data),
        "--out-dir",
        str(demo_out),
        "--clean-output",
        success_contract=success_contract,
        contracts=contracts,
    )
    assert demo_result["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert demo_result["demo_tenant_id"] == DEMO_TENANT_ID
    assert demo_result["demo_project_id"] == DEMO_PROJECT_ID
    assert demo_result["tenant_id"] == DEMO_TENANT_ID
    assert demo_result["project_id"] == DEMO_PROJECT_ID
    assert demo_result["decision_id"] == demo_result["seeded_decision_id"]
    assert demo_result["recommendation"] == DEMO_RECOMMENDATION
    assert demo_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert demo_result["clean_output"] is True
    assert demo_result["artifacts"] == builder_result["artifacts"]
    assert list(demo_result["artifact_inventory"]) == demo_result["artifacts"]
    assert demo_result["artifact_check"]["status"] == "passed"

    export_result = _run_success_case(
        "project_export",
        "--data-dir",
        str(demo_data),
        "--tenant-id",
        DEMO_TENANT_ID,
        "--project-id",
        DEMO_PROJECT_ID,
        "--out-dir",
        str(export_out),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert export_result["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert export_result["tenant_id"] == DEMO_TENANT_ID
    assert export_result["project_id"] == DEMO_PROJECT_ID

    gate_result = _run_success_case(
        "evidence_gate",
        str(demo_out),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert gate_result["gate"] == GATE_NAME
    assert gate_result["operational_approval"] is False
    assert gate_result["recommendation"] == DEMO_RECOMMENDATION
    assert gate_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert gate_result["artifacts"] == demo_result["artifacts"]
    assert gate_result["excluded_external_actions"] == demo_excluded_actions
    assert gate_result["demo_result_checked"] is True
    assert gate_result["artifact_inventory_checked"] is True
    assert gate_result["demo_receipt_checked"] is True

    smoke_result = _run_success_case(
        "smoke_wrapper",
        "--data-dir",
        str(smoke_data),
        "--out-dir",
        str(smoke_out),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert smoke_result["smoke"] == SMOKE_NAME
    assert smoke_result["gate_result_written"] is True
    assert smoke_result["smoke_result_written"] is True
    assert smoke_result["smoke_check_result_written"] is True
    assert smoke_result["data_dir"] == str(smoke_data)
    assert smoke_result["demo_tenant_id"] == DEMO_TENANT_ID
    assert smoke_result["demo_project_id"] == DEMO_PROJECT_ID
    assert smoke_result["recommendation"] == DEMO_RECOMMENDATION
    assert smoke_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert smoke_result["operational_approval"] is False
    assert smoke_result["clean_output"] is True
    assert smoke_result["package_artifacts_checked"] is True
    assert smoke_result["smoke_result_checked"] is True
    assert smoke_result["demo_result_checked"] is True
    assert smoke_result["artifact_inventory_checked"] is True
    assert smoke_result["demo_receipt_checked"] is True
    assert smoke_result["artifact_count"] == len(demo_result["artifacts"])
    assert smoke_result["excluded_external_actions"] == demo_excluded_actions

    smoke_check_result = _run_success_case(
        "smoke_checker",
        str(smoke_out / SMOKE_RESULT_NAME),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert smoke_check_result["check"] == SMOKE_CHECK_NAME
    assert smoke_check_result["package_artifacts_checked"] is True
    assert smoke_check_result["smoke_result_checked"] is True
    assert smoke_check_result["smoke_check_result_written"] is True
    assert smoke_check_result["demo_tenant_id"] == DEMO_TENANT_ID
    assert smoke_check_result["demo_project_id"] == DEMO_PROJECT_ID
    assert smoke_check_result["seeded_decision_id"] == smoke_result["seeded_decision_id"]
    assert smoke_check_result["artifact_count"] == len(demo_result["artifacts"])
    assert smoke_check_result["excluded_external_actions"] == demo_excluded_actions
    assert smoke_check_result["recommendation"] == DEMO_RECOMMENDATION
    assert smoke_check_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert smoke_check_result["operational_approval"] is False
    assert smoke_check_result["clean_output"] is True

    manifest_validation_result = _run_success_case(
        "cli_contract_manifest_validator",
        "--write-result",
        "--result-path",
        str(manifest_validation_result_path),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert manifest_validation_result["contract_count"] == len(case_order)
    assert manifest_validation_result["script_count"] == len(case_order)
    assert manifest_validation_result["case_names"] == case_order
    assert list(manifest_validation_result["success_required_fields_by_case"]) == case_order
    assert list(manifest_validation_result["failure_required_fields_by_case"]) == case_order
    assert (
        len(manifest_validation_result["cli_contract_fingerprint"])
        == SHA256_HEX_DIGEST_LENGTH
    )

    manifest_result_check = _run_success_case(
        "cli_contract_manifest_result_checker",
        str(manifest_validation_result_path),
        success_contract=success_contract,
        contracts=contracts,
    )
    assert manifest_result_check["check"] == CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME
    for mirrored_field in MIRRORED_MANIFEST_VALIDATION_FIELDS:
        assert (
            manifest_result_check[mirrored_field]
            == manifest_validation_result[mirrored_field]
        ), {
            "field": mirrored_field,
            "manifest_result_check": manifest_result_check,
            "manifest_validation_result": manifest_validation_result,
        }
    assert manifest_result_check["validation_result_checked"] is True
