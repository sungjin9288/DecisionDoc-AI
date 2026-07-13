from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services import procurement_decision_package_service as contract


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / contract.LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH
MISSING_SAMPLE_INPUT_NAME = "missing_sample_input.json"
DATA_DIR_FILE_NAME = "data-file"
FILE_INSTEAD_OF_DIRECTORY_TEXT = "not a directory\n"
SAMPLE_OUTPUT_DIR_NAME = "sample-out"
MISSING_ARTIFACTS_DIR_NAME = "missing-artifacts"
DEMO_OUTPUT_DIR_NAME = "demo-out"
EXPORT_DATA_DIR_NAME = "data"
EXPORT_OUTPUT_DIR_NAME = "export-out"
MISSING_GATE_OUTPUT_DIR_NAME = "missing-gate-output"
SMOKE_OUTPUT_DIR_NAME = "smoke-out"
MISSING_SMOKE_RESULT_NAME = "missing_smoke_result.json"
MISSING_CLI_CONTRACT_MANIFEST_NAME = "missing_cli_contract_manifest.json"
MISSING_MANIFEST_VALIDATION_RESULT_NAME = "missing_manifest_validation_result.json"
MISSING_PROJECT_EXPORT_TENANT_ID = "tenant-a"
MISSING_PROJECT_EXPORT_PROJECT_ID = "missing-project"
NON_EMPTY_FAILURE_FIELDS_BY_CASE = {
    "sample_validator": ("expected_package",),
    "sample_builder": ("schema_purpose",),
    "demo_runner": ("schema_purpose",),
}


def _load_contract_manifest() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema_purpose"] == contract.CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE, manifest
    return manifest


def _script_path(case_name: str) -> str:
    return str(ROOT / contract.CLI_CONTRACT_MANIFEST_CASE_SCRIPTS[case_name])


def _cli_case(case_name: str, *args: str) -> tuple[str, tuple[str, ...]]:
    return case_name, args


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(cli_run.stdout)


def _run_cli_json(
    case_name: str,
    *args: str,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    cli_run = subprocess.run(
        [sys.executable, _script_path(case_name), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    failure_payload = _load_stdout_json(cli_run)

    return cli_run, failure_payload


def _assert_failure_fields(
    *,
    case_name: str,
    failure_payload: dict[str, Any],
    contracts: dict[str, dict[str, Any]],
) -> None:
    expected_failure_fields = contracts[case_name]["failure_required_fields"]
    actual_failure_fields = list(failure_payload)
    assert actual_failure_fields == expected_failure_fields, {
        "case_name": case_name,
        "expected": expected_failure_fields,
        "actual": actual_failure_fields,
        "failure_payload": failure_payload,
    }


def _assert_cli_completed(
    cli_run: subprocess.CompletedProcess[str],
    *,
    exit_code: int,
    context: object,
) -> None:
    assert cli_run.returncode == exit_code, context
    assert cli_run.stderr == "", context


def _assert_handled_failure(
    *,
    case_name: str,
    failure_payload: dict[str, Any],
    cli_run: subprocess.CompletedProcess[str],
    contracts: dict[str, dict[str, Any]],
    failure_contract: dict[str, Any],
) -> None:
    _assert_cli_completed(
        cli_run,
        exit_code=failure_contract["exit_code"],
        context=failure_payload,
    )
    assert failure_payload["status"] == failure_contract["status"], failure_payload
    for required_field in failure_contract["required_fields"]:
        assert failure_payload[required_field], {
            "case_name": case_name,
            "field": required_field,
            "failure_payload": failure_payload,
        }
    _assert_failure_fields(
        case_name=case_name,
        failure_payload=failure_payload,
        contracts=contracts,
    )


def test_local_evidence_clis_return_json_failures_no_tracebacks(tmp_path: Path) -> None:
    manifest = _load_contract_manifest()
    contracts = {
        contract_case["case_name"]: contract_case
        for contract_case in manifest["cli_contracts"]
    }
    failure_contract = manifest["stdout_json_contract"]["handled_failure"]
    data_file = tmp_path / DATA_DIR_FILE_NAME
    data_file.write_text(FILE_INSTEAD_OF_DIRECTORY_TEXT, encoding="utf-8")
    missing_sample_input = tmp_path / MISSING_SAMPLE_INPUT_NAME
    sample_out = tmp_path / SAMPLE_OUTPUT_DIR_NAME
    missing_artifacts = tmp_path / MISSING_ARTIFACTS_DIR_NAME
    missing_packet_path = tmp_path / "missing-packet.zip"
    missing_review_receipt = tmp_path / "missing-review-receipt.json"
    demo_out = tmp_path / DEMO_OUTPUT_DIR_NAME
    export_data_dir = tmp_path / EXPORT_DATA_DIR_NAME
    export_out = tmp_path / EXPORT_OUTPUT_DIR_NAME
    missing_gate_output = tmp_path / MISSING_GATE_OUTPUT_DIR_NAME
    smoke_out = tmp_path / SMOKE_OUTPUT_DIR_NAME
    missing_smoke_result = tmp_path / MISSING_SMOKE_RESULT_NAME
    missing_contract_manifest = tmp_path / MISSING_CLI_CONTRACT_MANIFEST_NAME
    missing_validation_result = tmp_path / MISSING_MANIFEST_VALIDATION_RESULT_NAME

    cases = [
        _cli_case(
            "sample_validator",
            "--sample-input",
            str(missing_sample_input),
        ),
        _cli_case(
            "sample_builder",
            "--sample-input",
            str(missing_sample_input),
            "--out-dir",
            str(sample_out),
        ),
        _cli_case(
            "artifact_checker",
            str(missing_artifacts),
        ),
        _cli_case(
            "packet_manager",
            "create",
            str(missing_artifacts),
            "--packet",
            str(missing_packet_path),
        ),
        _cli_case(
            "review_receipt_manager",
            "init",
            str(missing_packet_path),
            "--receipt",
            str(missing_review_receipt),
        ),
        _cli_case(
            "demo_runner",
            "--data-dir",
            str(data_file),
            "--out-dir",
            str(demo_out),
        ),
        _cli_case(
            "project_export",
            "--data-dir",
            str(export_data_dir),
            "--tenant-id",
            MISSING_PROJECT_EXPORT_TENANT_ID,
            "--project-id",
            MISSING_PROJECT_EXPORT_PROJECT_ID,
            "--out-dir",
            str(export_out),
        ),
        _cli_case(
            "evidence_gate",
            str(missing_gate_output),
        ),
        _cli_case(
            "smoke_wrapper",
            "--data-dir",
            str(data_file),
            "--out-dir",
            str(smoke_out),
        ),
        _cli_case(
            "smoke_checker",
            str(missing_smoke_result),
        ),
        _cli_case(
            "cli_contract_manifest_validator",
            "--manifest",
            str(missing_contract_manifest),
        ),
        _cli_case(
            "cli_contract_manifest_result_checker",
            str(missing_validation_result),
        ),
    ]
    case_order = tuple(case_name for case_name, _ in cases)
    assert tuple(contracts) == case_order == contract.CLI_CONTRACT_MANIFEST_CASE_ORDER

    for case_name, args in cases:
        cli_run, failure_payload = _run_cli_json(case_name, *args)

        _assert_handled_failure(
            case_name=case_name,
            failure_payload=failure_payload,
            cli_run=cli_run,
            contracts=contracts,
            failure_contract=failure_contract,
        )
        for non_empty_field in NON_EMPTY_FAILURE_FIELDS_BY_CASE.get(case_name, ()):
            assert failure_payload[non_empty_field], {
                "case_name": case_name,
                "field": non_empty_field,
                "failure_payload": failure_payload,
            }
