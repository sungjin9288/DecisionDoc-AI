from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import procurement_decision_package_service as checker_contract


JsonObject = dict[str, object]
CliScriptRunWithStdout = tuple[subprocess.CompletedProcess[str], JsonObject]
CliScriptRunWithResultFile = tuple[subprocess.CompletedProcess[str], JsonObject, JsonObject]

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_SCRIPT = (
    ROOT
    / checker_contract.CLI_CONTRACT_MANIFEST_CASE_SCRIPTS[
        "cli_contract_manifest_validator"
    ]
)
CHECKER_SCRIPT = (
    ROOT
    / checker_contract.CLI_CONTRACT_MANIFEST_CASE_SCRIPTS[
        "cli_contract_manifest_result_checker"
    ]
)
DEFAULT_MANIFEST_PATH = ROOT / checker_contract.LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH
VALIDATION_RESULT_NAME = checker_contract.CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME
CHECK_RESULT_NAME = checker_contract.CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME
DEFAULT_VALIDATION_RESULT_PATH = DEFAULT_MANIFEST_PATH.parent / VALIDATION_RESULT_NAME
FIELD_MAP_DRIFT_CASE = "sample_validator"
STALE_SUCCESS_FIELDS = ("status",)
STALE_FAILURE_FIELDS = checker_contract.CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS
SHA256_HEX_LENGTH = 64
STALE_SHA256 = "0" * SHA256_HEX_LENGTH
STALE_CONTRACT_VERSION = "0.0.0"
UNREVIEWED_METADATA_VALUE = "quiet drift"
CHECK_RESULT_PATH_ERROR_TYPE = "ValueError"
RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR = "--result-path requires --write-result"
MISSING_VALIDATION_RESULT_NAME = "missing_validation_result.json"
MISSING_VALIDATION_RESULT_ERROR_TYPE = "FileNotFoundError"
EXPECTED_CHECK_FIELDS = checker_contract.CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FIELDS
EXPECTED_CHECK_FAILURE_FIELDS = (
    checker_contract.CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FAILURE_FIELDS
)
MIRRORED_VALIDATION_RESULT_FIELDS = (
    "contract_version",
    "manifest_sha256",
    "manifest_size_bytes",
    "case_names",
    "scripts",
    "external_actions_excluded",
    "success_required_fields_by_case",
    "failure_required_fields_by_case",
    "cli_contract_fingerprint",
)


def _write_current_manifest_validation_result(manifest_validation_result_path: Path) -> JsonObject:
    validator_run, manifest_validation_result = _run_validator_script(
        "--write-result",
        "--result-path",
        manifest_validation_result_path,
    )
    _assert_cli_completed(
        validator_run,
        exit_code=0,
        context=manifest_validation_result,
    )
    return manifest_validation_result


def _write_default_manifest_validation_result(tmp_path: Path) -> tuple[Path, JsonObject]:
    manifest_validation_result_path = _manifest_validation_result_path(tmp_path)
    return (
        manifest_validation_result_path,
        _write_current_manifest_validation_result(manifest_validation_result_path),
    )


def _write_manifest_validation_result_with_field(
    tmp_path: Path,
    validation_result_field: str,
    validation_result_value: object,
) -> Path:
    manifest_validation_result_path, manifest_validation_result = (
        _write_default_manifest_validation_result(tmp_path)
    )
    manifest_validation_result[validation_result_field] = validation_result_value
    _write_json(manifest_validation_result_path, manifest_validation_result)
    return manifest_validation_result_path


def _write_manifest_validation_result_without_field(
    tmp_path: Path,
    validation_result_field: str,
) -> Path:
    manifest_validation_result_path, manifest_validation_result = (
        _write_default_manifest_validation_result(tmp_path)
    )
    manifest_validation_result.pop(validation_result_field)
    _write_json(manifest_validation_result_path, manifest_validation_result)
    return manifest_validation_result_path


def _write_manifest_validation_result_with_case_fields(
    tmp_path: Path,
    case_field_map_name: str,
    case_fields: tuple[str, ...],
) -> Path:
    manifest_validation_result_path, manifest_validation_result = (
        _write_default_manifest_validation_result(tmp_path)
    )
    manifest_validation_result[case_field_map_name][FIELD_MAP_DRIFT_CASE] = list(case_fields)
    _write_json(manifest_validation_result_path, manifest_validation_result)
    return manifest_validation_result_path


def _write_manifest_validation_result_with_reversed_case_order(
    tmp_path: Path,
    case_field_map_name: str,
) -> Path:
    manifest_validation_result_path, manifest_validation_result = (
        _write_default_manifest_validation_result(tmp_path)
    )
    case_fields_by_case = manifest_validation_result[case_field_map_name]
    manifest_validation_result[case_field_map_name] = {
        case_name: case_fields_by_case[case_name]
        for case_name in reversed(manifest_validation_result["case_names"])
    }
    _write_json(manifest_validation_result_path, manifest_validation_result)
    return manifest_validation_result_path


def _write_manifest_validation_result_with_reordered_fields(tmp_path: Path) -> Path:
    manifest_validation_result_path, manifest_validation_result = (
        _write_default_manifest_validation_result(tmp_path)
    )
    reordered_validation_result = {
        "contract_version": manifest_validation_result["contract_version"],
        "schema_purpose": manifest_validation_result["schema_purpose"],
    }
    reordered_validation_result.update(
        {
            validation_field: validation_value
            for validation_field, validation_value in manifest_validation_result.items()
            if validation_field not in reordered_validation_result
        }
    )
    _write_json(manifest_validation_result_path, reordered_validation_result)
    return manifest_validation_result_path


def _manifest_validation_result_path(tmp_path: Path) -> Path:
    return tmp_path / VALIDATION_RESULT_NAME


def _manifest_check_result_path(tmp_path: Path) -> Path:
    return tmp_path / CHECK_RESULT_NAME


def _load_json(path: Path) -> JsonObject:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_text(path: Path) -> str | None:
    if not path.exists():
        return None

    return path.read_text(encoding="utf-8")


def _write_json(path: Path, json_payload: JsonObject) -> None:
    path.write_text(
        json.dumps(json_payload, indent=2) + "\n",
        encoding="utf-8",
    )


def _restore_file(path: Path, original_text: str | None) -> None:
    if original_text is None:
        path.unlink(missing_ok=True)
        return

    path.write_text(original_text, encoding="utf-8")


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> JsonObject:
    return json.loads(cli_run.stdout)


def _run_script(script_path: Path, *args: object) -> CliScriptRunWithStdout:
    script_run = subprocess.run(
        [
            sys.executable,
            str(script_path),
            *(str(arg) for arg in args),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    return script_run, _load_stdout_json(script_run)


def _validate_current_manifest(manifest_path: Path) -> JsonObject:
    return checker_contract.validate_cli_contract_manifest(manifest_path, repo_root=ROOT)


def _check_manifest_validation_result(manifest_validation_result_path: Path) -> JsonObject:
    return checker_contract.check_cli_contract_manifest_validation_result(
        manifest_validation_result_path,
        expected_schema_purpose=checker_contract.CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
        validate_current_manifest=_validate_current_manifest,
    )


def _run_checker_script(
    *args: object,
) -> CliScriptRunWithStdout:
    return _run_script(CHECKER_SCRIPT, *args)


def _run_checker_script_with_result_file(
    manifest_check_result_path: Path,
    *args: object,
) -> CliScriptRunWithResultFile:
    checker_run, stdout_manifest_check = _run_checker_script(
        *args,
        "--write-result",
        "--result-path",
        manifest_check_result_path,
    )
    return checker_run, stdout_manifest_check, _load_json(manifest_check_result_path)


def _run_validator_script(
    *args: object,
) -> CliScriptRunWithStdout:
    return _run_script(VALIDATOR_SCRIPT, *args)


def _assert_cli_completed(
    cli_run: subprocess.CompletedProcess[str],
    *,
    exit_code: int,
    context: object,
) -> None:
    assert cli_run.returncode == exit_code, context
    assert cli_run.stderr == "", context


def _assert_written_manifest_check_matches_stdout(
    file_manifest_check: JsonObject,
    stdout_manifest_check: JsonObject,
) -> None:
    assert file_manifest_check == stdout_manifest_check, {
        "file_manifest_check": file_manifest_check,
        "stdout_manifest_check": stdout_manifest_check,
    }


def _assert_manifest_check_fields(
    manifest_check_payload: JsonObject,
    expected_manifest_check_fields: tuple[str, ...],
) -> None:
    assert list(manifest_check_payload) == list(
        expected_manifest_check_fields
    ), manifest_check_payload


def _assert_manifest_check_matches_validation(
    manifest_check_result: JsonObject,
    manifest_validation_result: JsonObject,
    manifest_validation_result_path: Path,
) -> None:
    _assert_manifest_check_fields(
        manifest_check_result,
        EXPECTED_CHECK_FIELDS,
    )
    assert manifest_check_result["status"] == "passed", manifest_check_result
    assert manifest_check_result["validation_result_path"] == str(
        manifest_validation_result_path
    ), manifest_check_result
    for mirrored_field in MIRRORED_VALIDATION_RESULT_FIELDS:
        assert (
            manifest_check_result[mirrored_field]
            == manifest_validation_result[mirrored_field]
        ), manifest_check_result
    assert (
        manifest_check_result["validation_result_checked"] is True
    ), manifest_check_result


def _assert_written_manifest_check_matches_validation(
    stdout_manifest_check: JsonObject,
    file_manifest_check: JsonObject,
    manifest_validation_result: JsonObject,
    manifest_validation_result_path: Path,
) -> None:
    _assert_manifest_check_matches_validation(
        stdout_manifest_check,
        manifest_validation_result,
        manifest_validation_result_path,
    )
    _assert_manifest_check_matches_validation(
        file_manifest_check,
        manifest_validation_result,
        manifest_validation_result_path,
    )
    _assert_written_manifest_check_matches_stdout(
        file_manifest_check,
        stdout_manifest_check,
    )


def _assert_manifest_check_failure(
    manifest_check_failure: JsonObject,
    *,
    error_type: str,
) -> None:
    _assert_manifest_check_fields(
        manifest_check_failure,
        EXPECTED_CHECK_FAILURE_FIELDS,
    )
    assert manifest_check_failure["status"] == "failed", manifest_check_failure
    assert manifest_check_failure["error_type"] == error_type, manifest_check_failure


def _assert_validation_result_rejected(manifest_validation_result_path: Path, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        _check_manifest_validation_result(manifest_validation_result_path)


def test_accepts_current_manifest_validation(
    tmp_path: Path,
) -> None:
    (
        manifest_validation_result_path,
        manifest_validation_result,
    ) = _write_default_manifest_validation_result(tmp_path)

    manifest_check_result = _check_manifest_validation_result(manifest_validation_result_path)

    _assert_manifest_check_matches_validation(
        manifest_check_result,
        manifest_validation_result,
        manifest_validation_result_path,
    )


def test_default_manifest_validation_result_path_stays_next_to_manifest() -> None:
    assert (
        DEFAULT_VALIDATION_RESULT_PATH
        == DEFAULT_MANIFEST_PATH.parent / VALIDATION_RESULT_NAME
    )


def test_rejects_stale_fingerprint(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_with_field(
        tmp_path,
        "manifest_sha256",
        STALE_SHA256,
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "manifest_sha256",
    )


def test_rejects_stale_contract_version(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_with_field(
        tmp_path,
        "contract_version",
        STALE_CONTRACT_VERSION,
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "contract_version",
    )


def test_rejects_stale_cli_fingerprint(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_with_field(
        tmp_path,
        "cli_contract_fingerprint",
        STALE_SHA256,
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "cli_contract_fingerprint",
    )


def test_rejects_unknown_field(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_with_field(
        tmp_path,
        "unreviewed_metadata",
        UNREVIEWED_METADATA_VALUE,
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "validation_result includes unknown fields: unreviewed_metadata",
    )


def test_rejects_missing_field(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_without_field(
        tmp_path,
        "scripts",
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "validation_result missing fields: scripts",
    )


def test_rejects_field_order_drift(tmp_path: Path) -> None:
    manifest_validation_result_path = (
        _write_manifest_validation_result_with_reordered_fields(tmp_path)
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "validation_result fields must match the expected order",
    )


def test_rejects_stale_success_field_map(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_with_case_fields(
        tmp_path,
        "success_required_fields_by_case",
        STALE_SUCCESS_FIELDS,
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "success_required_fields_by_case",
    )


def test_rejects_success_case_order_drift(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_with_reversed_case_order(
        tmp_path,
        "success_required_fields_by_case",
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "success_required_fields_by_case case order",
    )


def test_rejects_stale_failure_field_map(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_with_case_fields(
        tmp_path,
        "failure_required_fields_by_case",
        STALE_FAILURE_FIELDS,
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "failure_required_fields_by_case",
    )


def test_rejects_failure_case_order_drift(tmp_path: Path) -> None:
    manifest_validation_result_path = _write_manifest_validation_result_with_reversed_case_order(
        tmp_path,
        "failure_required_fields_by_case",
    )

    _assert_validation_result_rejected(
        manifest_validation_result_path,
        "failure_required_fields_by_case case order",
    )


def test_checker_cli_returns_success_json(tmp_path: Path) -> None:
    manifest_validation_result_path, manifest_validation_result = (
        _write_default_manifest_validation_result(tmp_path)
    )

    checker_run, manifest_check_result = _run_checker_script(
        manifest_validation_result_path
    )

    _assert_cli_completed(
        checker_run,
        exit_code=0,
        context=manifest_check_result,
    )
    _assert_manifest_check_matches_validation(
        manifest_check_result,
        manifest_validation_result,
        manifest_validation_result_path,
    )


def test_checker_cli_writes_success_result(tmp_path: Path) -> None:
    manifest_validation_result_path, manifest_validation_result = (
        _write_default_manifest_validation_result(tmp_path)
    )
    manifest_check_result_path = _manifest_check_result_path(tmp_path)

    (
        checker_run,
        stdout_manifest_check,
        file_manifest_check,
    ) = _run_checker_script_with_result_file(
        manifest_check_result_path,
        manifest_validation_result_path,
    )

    _assert_cli_completed(
        checker_run,
        exit_code=0,
        context=stdout_manifest_check,
    )
    _assert_written_manifest_check_matches_validation(
        stdout_manifest_check,
        file_manifest_check,
        manifest_validation_result,
        manifest_validation_result_path,
    )


def test_checker_cli_writes_default_result_with_repo_relative_paths() -> None:
    default_check_result_path = DEFAULT_MANIFEST_PATH.parent / CHECK_RESULT_NAME
    original_check_result_text = _read_optional_text(default_check_result_path)

    try:
        checker_run, stdout_manifest_check = _run_checker_script("--write-result")
        file_manifest_check = _load_json(default_check_result_path)

        _assert_cli_completed(
            checker_run,
            exit_code=0,
            context=stdout_manifest_check,
        )
        _assert_written_manifest_check_matches_stdout(
            file_manifest_check,
            stdout_manifest_check,
        )
        assert stdout_manifest_check["manifest_path"] == str(
            checker_contract.LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH
        )
        assert stdout_manifest_check["validation_result_path"] == str(
            checker_contract.LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH.parent
            / VALIDATION_RESULT_NAME
        )
    finally:
        _restore_file(default_check_result_path, original_check_result_text)

    assert _read_optional_text(default_check_result_path) == original_check_result_text


def test_checker_cli_rejects_result_path_without_write(tmp_path: Path) -> None:
    manifest_validation_result_path, _ = (
        _write_default_manifest_validation_result(tmp_path)
    )
    manifest_check_result_path = _manifest_check_result_path(tmp_path)

    checker_run, manifest_check_failure = _run_checker_script(
        manifest_validation_result_path,
        "--result-path",
        manifest_check_result_path,
    )

    _assert_cli_completed(
        checker_run,
        exit_code=1,
        context=manifest_check_failure,
    )
    _assert_manifest_check_failure(
        manifest_check_failure,
        error_type=CHECK_RESULT_PATH_ERROR_TYPE,
    )
    assert RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR in manifest_check_failure["error"]
    assert not manifest_check_result_path.exists()


def test_checker_cli_returns_failure_json_no_traceback(tmp_path: Path) -> None:
    manifest_validation_result_path = tmp_path / MISSING_VALIDATION_RESULT_NAME

    checker_run, manifest_check_failure = _run_checker_script(
        manifest_validation_result_path
    )

    _assert_cli_completed(
        checker_run,
        exit_code=1,
        context=manifest_check_failure,
    )
    _assert_manifest_check_failure(
        manifest_check_failure,
        error_type=MISSING_VALIDATION_RESULT_ERROR_TYPE,
    )
    assert manifest_check_failure["validation_result_path"] == str(
        manifest_validation_result_path
    )
