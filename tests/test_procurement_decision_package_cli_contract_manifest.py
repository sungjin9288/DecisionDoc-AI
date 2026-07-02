from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import procurement_decision_package_service as validator_contract


JsonObject = dict[str, object]
ValidatorScriptRunWithStdout = tuple[subprocess.CompletedProcess[str], JsonObject]
ValidatorScriptRunWithResultFile = tuple[subprocess.CompletedProcess[str], JsonObject, JsonObject]

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    ROOT
    / validator_contract.CLI_CONTRACT_MANIFEST_CASE_SCRIPTS[
        "cli_contract_manifest_validator"
    ]
)
DEFAULT_MANIFEST_PATH = ROOT / validator_contract.LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH
DEFAULT_VALIDATION_RESULT_PATH = (
    DEFAULT_MANIFEST_PATH.parent
    / validator_contract.CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME
)
UNREVIEWED_MANIFEST_METADATA_VALUE = "quiet drift"
UNREVIEWED_CASE_METADATA_VALUE = "quiet drift"
RESULT_PATH_WITHOUT_WRITE_RESULT_ERROR_TYPE = "ValueError"
RESULT_PATH_WITHOUT_WRITE_RESULT_ERROR_MESSAGE = "--result-path requires --write-result"
BROKEN_MANIFEST_FIXTURE_NAME = "broken_manifest.json"
MISSING_MANIFEST_FAILURE_NAME = "missing_manifest.json"
MISSING_MANIFEST_FAILURE_ERROR_TYPE = "FileNotFoundError"
TRACEBACK_FIELD_FIXTURE_NAME = "traceback"
SHA256_HEX_DIGEST_LENGTH = 64
EXPECTED_CONTRACT_VERSION = validator_contract.CLI_CONTRACT_MANIFEST_CONTRACT_VERSION
EXPECTED_WORKFLOW = validator_contract.CLI_CONTRACT_MANIFEST_WORKFLOW
EXPECTED_CONTRACT_STATUS = validator_contract.CLI_CONTRACT_MANIFEST_CONTRACT_STATUS
EXPECTED_CLI_CONTRACT_COUNT = len(validator_contract.CLI_CONTRACT_MANIFEST_CASE_ORDER)
EXPECTED_CLI_SCRIPT_COUNT = len(validator_contract.CLI_CONTRACT_MANIFEST_CASE_SCRIPTS)
EXCLUDED_PROVIDER_API_ACTION = validator_contract.PROVIDER_API_EXECUTION_ACTION


def _validate_contract_manifest(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> JsonObject:
    return validator_contract.validate_cli_contract_manifest(manifest_path, repo_root=ROOT)


def _assert_contract_manifest_rejected(manifest_path: Path, expected_error_pattern: str) -> None:
    with pytest.raises(ValueError, match=expected_error_pattern):
        _validate_contract_manifest(manifest_path)


def _load_result_file_json(json_path: Path) -> JsonObject:
    return json.loads(json_path.read_text(encoding="utf-8"))


def _read_optional_text(path: Path) -> str | None:
    if not path.exists():
        return None

    return path.read_text(encoding="utf-8")


def _write_manifest(manifest_path: Path, contract_manifest: JsonObject) -> None:
    manifest_path.write_text(
        json.dumps(contract_manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def _restore_file(path: Path, original_text: str | None) -> None:
    if original_text is None:
        path.unlink(missing_ok=True)
        return

    path.write_text(original_text, encoding="utf-8")


def _write_broken_manifest(tmp_path: Path, broken_manifest: JsonObject) -> Path:
    manifest_path = tmp_path / BROKEN_MANIFEST_FIXTURE_NAME
    _write_manifest(manifest_path, broken_manifest)
    return manifest_path


def _copy_default_contract_manifest() -> JsonObject:
    return copy.deepcopy(validator_contract.load_json(DEFAULT_MANIFEST_PATH))


def _required_fields_by_case(
    contract_manifest: JsonObject,
    contract_field_name: str,
) -> JsonObject:
    return {
        cli_contract["case_name"]: cli_contract[contract_field_name]
        for cli_contract in contract_manifest["cli_contracts"]
    }


def _contract_case_names(contract_manifest: JsonObject) -> list[str]:
    return [
        cli_contract["case_name"]
        for cli_contract in contract_manifest["cli_contracts"]
    ]


def _contract_scripts(contract_manifest: JsonObject) -> list[str]:
    return [
        cli_contract["script"]
        for cli_contract in contract_manifest["cli_contracts"]
    ]


def _expected_required_fields_by_case(
    expected_required_fields_by_case: dict[str, tuple[str, ...]],
) -> dict[str, list[str]]:
    return {
        case_name: list(expected_required_fields)
        for case_name, expected_required_fields in expected_required_fields_by_case.items()
    }


def _manifest_validation_result_path(tmp_path: Path) -> Path:
    return tmp_path / validator_contract.CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME


def _load_validator_stdout_json(validator_run: subprocess.CompletedProcess[str]) -> JsonObject:
    return json.loads(validator_run.stdout)


def _run_validator_script(
    *validator_args: object,
) -> ValidatorScriptRunWithStdout:
    validator_run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            *(str(validator_arg) for validator_arg in validator_args),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    return validator_run, _load_validator_stdout_json(validator_run)


def _run_validator_script_with_result_file(
    manifest_validation_result_path: Path,
    *validator_args: object,
) -> ValidatorScriptRunWithResultFile:
    validator_run, stdout_manifest_validation = _run_validator_script(
        *validator_args,
        "--write-result",
        "--result-path",
        manifest_validation_result_path,
    )
    file_manifest_validation = _load_result_file_json(manifest_validation_result_path)
    return validator_run, stdout_manifest_validation, file_manifest_validation


def _assert_cli_completed(
    validator_run: subprocess.CompletedProcess[str],
    *,
    exit_code: int,
    cli_payload: object,
) -> None:
    assert validator_run.returncode == exit_code, cli_payload
    assert validator_run.stderr == "", cli_payload


def _assert_written_manifest_validation_matches_stdout(
    file_manifest_validation: JsonObject,
    stdout_manifest_validation: JsonObject,
) -> None:
    assert file_manifest_validation == stdout_manifest_validation, {
        "file_manifest_validation": file_manifest_validation,
        "stdout_manifest_validation": stdout_manifest_validation,
    }


def _assert_manifest_validation_fields(
    manifest_validation_payload: JsonObject,
    expected_manifest_validation_fields: tuple[str, ...],
) -> None:
    assert list(manifest_validation_payload) == list(
        expected_manifest_validation_fields
    ), manifest_validation_payload


def _assert_success_manifest_validation(manifest_validation_result: JsonObject) -> None:
    _assert_manifest_validation_fields(
        manifest_validation_result,
        validator_contract.CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
    )
    excluded_external_actions = manifest_validation_result["external_actions_excluded"]

    assert manifest_validation_result["status"] == "passed", manifest_validation_result
    assert (
        manifest_validation_result["manifest_path"]
        == str(validator_contract.LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH)
    ), manifest_validation_result
    assert (
        manifest_validation_result["contract_version"] == EXPECTED_CONTRACT_VERSION
    ), manifest_validation_result
    assert (
        manifest_validation_result["workflow"] == EXPECTED_WORKFLOW
    ), manifest_validation_result
    assert (
        manifest_validation_result["contract_status"] == EXPECTED_CONTRACT_STATUS
    ), manifest_validation_result
    assert (
        manifest_validation_result["contract_count"] == EXPECTED_CLI_CONTRACT_COUNT
    ), manifest_validation_result
    assert (
        manifest_validation_result["script_count"] == EXPECTED_CLI_SCRIPT_COUNT
    ), manifest_validation_result
    assert (
        len(manifest_validation_result["manifest_sha256"]) == SHA256_HEX_DIGEST_LENGTH
    ), manifest_validation_result
    assert (
        manifest_validation_result["manifest_size_bytes"] > 0
    ), manifest_validation_result
    assert (
        EXCLUDED_PROVIDER_API_ACTION in excluded_external_actions
    ), manifest_validation_result
    assert (
        len(manifest_validation_result["cli_contract_fingerprint"]) == SHA256_HEX_DIGEST_LENGTH
    ), manifest_validation_result


def _assert_manifest_validation_failure(
    manifest_validation_failure: JsonObject,
    *,
    error_type: str,
) -> None:
    _assert_manifest_validation_fields(
        manifest_validation_failure,
        validator_contract.CLI_CONTRACT_MANIFEST_VALIDATION_FAILURE_FIELDS,
    )
    assert manifest_validation_failure["status"] == "failed", manifest_validation_failure
    assert (
        manifest_validation_failure["contract_version"] == EXPECTED_CONTRACT_VERSION
    ), manifest_validation_failure
    assert (
        manifest_validation_failure["error_type"] == error_type
    ), manifest_validation_failure


def _assert_missing_manifest_failure_result(
    manifest_validation_failure: JsonObject,
    manifest_path: Path,
) -> None:
    _assert_manifest_validation_failure(
        manifest_validation_failure,
        error_type=MISSING_MANIFEST_FAILURE_ERROR_TYPE,
    )
    assert (
        manifest_validation_failure["manifest_path"] == str(manifest_path)
    ), manifest_validation_failure


def _assert_default_manifest_projection(
    manifest_validation_result: JsonObject,
    default_manifest: JsonObject,
) -> None:
    success_fields_by_case = _required_fields_by_case(
        default_manifest,
        "success_required_fields",
    )
    failure_fields_by_case = _required_fields_by_case(
        default_manifest,
        "failure_required_fields",
    )

    _assert_success_manifest_validation(manifest_validation_result)
    assert manifest_validation_result["case_names"] == _contract_case_names(
        default_manifest
    )
    assert manifest_validation_result["scripts"] == _contract_scripts(default_manifest)
    assert (
        manifest_validation_result["success_required_fields_by_case"]
        == success_fields_by_case
    )
    assert (
        manifest_validation_result["failure_required_fields_by_case"]
        == failure_fields_by_case
    )
    assert list(manifest_validation_result["success_required_fields_by_case"]) == list(
        validator_contract.CLI_CONTRACT_MANIFEST_CASE_ORDER
    )
    assert list(manifest_validation_result["failure_required_fields_by_case"]) == list(
        validator_contract.CLI_CONTRACT_MANIFEST_CASE_ORDER
    )
    assert success_fields_by_case == _expected_required_fields_by_case(
        validator_contract.CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE
    )
    assert failure_fields_by_case == _expected_required_fields_by_case(
        validator_contract.CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE
    )


def test_accepts_default_manifest() -> None:
    manifest_validation_result = _validate_contract_manifest()
    default_manifest = validator_contract.load_json(DEFAULT_MANIFEST_PATH)

    _assert_default_manifest_projection(manifest_validation_result, default_manifest)


def test_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["unreviewed_manifest_metadata"] = UNREVIEWED_MANIFEST_METADATA_VALUE
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "manifest includes unknown fields: unreviewed_manifest_metadata",
    )


def test_rejects_missing_top_level_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest.pop("stdout_json_contract")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "manifest missing fields: stdout_json_contract",
    )


def test_rejects_top_level_field_order_drift(tmp_path: Path) -> None:
    default_manifest = validator_contract.load_json(DEFAULT_MANIFEST_PATH)
    broken_manifest = {
        "contract_version": default_manifest["contract_version"],
        "schema_purpose": default_manifest["schema_purpose"],
        "workflow": default_manifest["workflow"],
        "contract_status": default_manifest["contract_status"],
        "stdout_json_contract": default_manifest["stdout_json_contract"],
        "external_actions_excluded": default_manifest["external_actions_excluded"],
        "cli_contracts": default_manifest["cli_contracts"],
    }
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "manifest fields must match the expected order",
    )


def test_rejects_unknown_stdout_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["stdout_json_contract"]["unreviewed_section"] = {}
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "stdout_json_contract includes unknown fields: unreviewed_section",
    )


def test_rejects_stdout_field_order_drift(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    original_stdout_json_contract = broken_manifest["stdout_json_contract"]
    broken_manifest["stdout_json_contract"] = {
        "handled_failure": original_stdout_json_contract["handled_failure"],
        "success": original_stdout_json_contract["success"],
    }
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "stdout_json_contract fields must match the expected order",
    )


def test_rejects_missing_stdout_success(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["stdout_json_contract"]["success"].pop("forbidden_fields")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "stdout_json_contract.success missing fields: forbidden_fields",
    )


def test_rejects_unknown_stdout_failure(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["stdout_json_contract"]["handled_failure"]["traceback_policy"] = "never"
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "handled_failure includes unknown fields: traceback_policy",
    )


def test_rejects_missing_stdout_failure(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["stdout_json_contract"]["handled_failure"].pop("required_fields")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "handled_failure missing fields: required_fields",
    )


def test_rejects_case_field_order_drift(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    cli_contract = broken_manifest["cli_contracts"][0]
    broken_manifest["cli_contracts"][0] = {
        "script": cli_contract["script"],
        "case_name": cli_contract["case_name"],
        "success_required_fields": cli_contract["success_required_fields"],
        "failure_required_fields": cli_contract["failure_required_fields"],
    }
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        r"cli_contracts\[0\] fields must match the expected order",
    )


def test_rejects_unknown_cli_contract_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0]["unreviewed_case_metadata"] = UNREVIEWED_CASE_METADATA_VALUE
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        r"cli_contracts\[0\] includes unknown fields: unreviewed_case_metadata",
    )


def test_rejects_missing_cli_contract_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0].pop("script")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        r"cli_contracts\[0\] missing fields: script",
    )


def test_rejects_missing_script(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0]["script"] = "scripts/missing_contract_cli.py"
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "script file is missing",
    )


def test_rejects_missing_failure_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0]["failure_required_fields"].remove("error_type")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "error_type",
    )


def test_rejects_missing_success_evidence(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0]["success_required_fields"].remove("authorization_boundary")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "success_required_fields missing values: authorization_boundary",
    )


def test_rejects_missing_failure_context(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0]["failure_required_fields"].remove("expected_package")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "failure_required_fields missing values: expected_package",
    )


def test_rejects_unknown_case_success_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0]["success_required_fields"].append(
        "unreviewed_success_field"
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "success_required_fields includes unknown values: unreviewed_success_field",
    )


def test_rejects_success_case_field_order(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    cli_success_required_fields = broken_manifest["cli_contracts"][0][
        "success_required_fields"
    ]
    cli_success_required_fields[0], cli_success_required_fields[1] = (
        cli_success_required_fields[1],
        cli_success_required_fields[0],
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "success_required_fields must match the expected order",
    )


def test_rejects_unknown_case_failure_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0]["failure_required_fields"].append(
        "unreviewed_failure_field"
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "failure_required_fields includes unknown values: unreviewed_failure_field",
    )


def test_rejects_failure_case_field_order(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    cli_failure_required_fields = broken_manifest["cli_contracts"][0][
        "failure_required_fields"
    ]
    cli_failure_required_fields[0], cli_failure_required_fields[1] = (
        cli_failure_required_fields[1],
        cli_failure_required_fields[0],
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "failure_required_fields must match the expected order",
    )


def test_rejects_case_order_drift(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    cli_contract_entries = broken_manifest["cli_contracts"]
    cli_contract_entries[0], cli_contract_entries[1] = (
        cli_contract_entries[1],
        cli_contract_entries[0],
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "case_name values must match the expected order",
    )


def test_rejects_case_script_mismatch(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    cli_contract_entries = broken_manifest["cli_contracts"]
    cli_contract_entries[0]["script"], cli_contract_entries[1]["script"] = (
        cli_contract_entries[1]["script"],
        cli_contract_entries[0]["script"],
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)
    expected_sample_validator_script = (
        validator_contract.CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["sample_validator"]
    )

    _assert_contract_manifest_rejected(
        manifest_path,
        f"script must be '{expected_sample_validator_script}'",
    )


def test_rejects_unknown_success_forbidden(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["stdout_json_contract"]["success"]["forbidden_fields"].append(
        TRACEBACK_FIELD_FIXTURE_NAME
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "success.forbidden_fields includes unknown values: traceback",
    )


def test_rejects_success_forbidden_order(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    stdout_success_forbidden_fields = (
        broken_manifest["stdout_json_contract"]["success"]["forbidden_fields"]
    )
    stdout_success_forbidden_fields[0], stdout_success_forbidden_fields[1] = (
        stdout_success_forbidden_fields[1],
        stdout_success_forbidden_fields[0],
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "success.forbidden_fields must match the expected order",
    )


def test_rejects_unknown_failure_required(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["stdout_json_contract"]["handled_failure"]["required_fields"].append(
        TRACEBACK_FIELD_FIXTURE_NAME
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "handled_failure.required_fields includes unknown values: traceback",
    )


def test_rejects_failure_required_order(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    stdout_failure_required_fields = (
        broken_manifest["stdout_json_contract"]["handled_failure"]["required_fields"]
    )
    stdout_failure_required_fields[0], stdout_failure_required_fields[1] = (
        stdout_failure_required_fields[1],
        stdout_failure_required_fields[0],
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "handled_failure.required_fields must match the expected order",
    )


def test_rejects_duplicate_success_field(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["cli_contracts"][0]["success_required_fields"].append("status")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "success_required_fields must not contain duplicate values",
    )


def test_rejects_duplicate_excluded_action(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["external_actions_excluded"].append(
        validator_contract.PROVIDER_API_EXECUTION_ACTION
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "external_actions_excluded must not contain duplicate values",
    )


def test_rejects_unknown_excluded_action(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    broken_manifest["external_actions_excluded"].append("unreviewed_runtime_action")
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "external_actions_excluded includes unknown values: unreviewed_runtime_action",
    )


def test_rejects_excluded_action_order_drift(tmp_path: Path) -> None:
    broken_manifest = _copy_default_contract_manifest()
    excluded_external_actions = broken_manifest["external_actions_excluded"]
    excluded_external_actions[0], excluded_external_actions[1] = (
        excluded_external_actions[1],
        excluded_external_actions[0],
    )
    manifest_path = _write_broken_manifest(tmp_path, broken_manifest)

    _assert_contract_manifest_rejected(
        manifest_path,
        "external_actions_excluded must match the expected order",
    )


def test_validator_cli_returns_success_json() -> None:
    validator_run, manifest_validation_result = _run_validator_script()

    _assert_cli_completed(
        validator_run,
        exit_code=0,
        cli_payload=manifest_validation_result,
    )
    _assert_success_manifest_validation(manifest_validation_result)


def test_validator_cli_writes_success_result(tmp_path: Path) -> None:
    manifest_validation_result_path = _manifest_validation_result_path(tmp_path)

    (
        validator_run,
        stdout_manifest_validation,
        file_manifest_validation,
    ) = _run_validator_script_with_result_file(
        manifest_validation_result_path
    )

    _assert_cli_completed(
        validator_run,
        exit_code=0,
        cli_payload=stdout_manifest_validation,
    )
    _assert_success_manifest_validation(stdout_manifest_validation)
    _assert_success_manifest_validation(file_manifest_validation)
    _assert_written_manifest_validation_matches_stdout(
        file_manifest_validation,
        stdout_manifest_validation,
    )


def test_validator_cli_writes_default_result_with_repo_relative_path() -> None:
    original_result_text = _read_optional_text(DEFAULT_VALIDATION_RESULT_PATH)

    try:
        validator_run, stdout_manifest_validation = _run_validator_script(
            "--write-result"
        )
        file_manifest_validation = _load_result_file_json(
            DEFAULT_VALIDATION_RESULT_PATH
        )

        _assert_cli_completed(
            validator_run,
            exit_code=0,
            cli_payload=stdout_manifest_validation,
        )
        _assert_success_manifest_validation(stdout_manifest_validation)
        _assert_success_manifest_validation(file_manifest_validation)
        _assert_written_manifest_validation_matches_stdout(
            file_manifest_validation,
            stdout_manifest_validation,
        )
    finally:
        _restore_file(DEFAULT_VALIDATION_RESULT_PATH, original_result_text)

    assert _read_optional_text(DEFAULT_VALIDATION_RESULT_PATH) == original_result_text


def test_validator_cli_rejects_result_path_without_write(tmp_path: Path) -> None:
    manifest_validation_result_path = _manifest_validation_result_path(tmp_path)

    validator_run, manifest_validation_failure = _run_validator_script(
        "--result-path",
        manifest_validation_result_path,
    )

    _assert_cli_completed(
        validator_run,
        exit_code=1,
        cli_payload=manifest_validation_failure,
    )
    _assert_manifest_validation_failure(
        manifest_validation_failure,
        error_type=RESULT_PATH_WITHOUT_WRITE_RESULT_ERROR_TYPE,
    )
    assert (
        RESULT_PATH_WITHOUT_WRITE_RESULT_ERROR_MESSAGE
        in manifest_validation_failure["error"]
    )
    assert not manifest_validation_result_path.exists()


def test_validator_cli_returns_failure_json_no_traceback(tmp_path: Path) -> None:
    manifest_path = tmp_path / MISSING_MANIFEST_FAILURE_NAME

    validator_run, manifest_validation_failure = _run_validator_script(
        "--manifest",
        manifest_path,
    )

    _assert_cli_completed(
        validator_run,
        exit_code=1,
        cli_payload=manifest_validation_failure,
    )
    _assert_missing_manifest_failure_result(manifest_validation_failure, manifest_path)


def test_validator_cli_writes_failure_result(tmp_path: Path) -> None:
    manifest_path = tmp_path / MISSING_MANIFEST_FAILURE_NAME
    manifest_validation_result_path = _manifest_validation_result_path(tmp_path)

    (
        validator_run,
        stdout_manifest_validation,
        file_manifest_validation,
    ) = _run_validator_script_with_result_file(
        manifest_validation_result_path,
        "--manifest",
        manifest_path,
    )

    _assert_cli_completed(
        validator_run,
        exit_code=1,
        cli_payload=stdout_manifest_validation,
    )
    _assert_missing_manifest_failure_result(stdout_manifest_validation, manifest_path)
    _assert_missing_manifest_failure_result(file_manifest_validation, manifest_path)
    _assert_written_manifest_validation_matches_stdout(
        file_manifest_validation,
        stdout_manifest_validation,
    )
