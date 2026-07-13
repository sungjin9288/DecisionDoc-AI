from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    DECISION_PACKAGE_NAME,
    DECISION_SUMMARY_NAME,
    DEMO_RECOMMENDATION,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE,
    LOCAL_DEMO_EXPECTED_PACKAGE_PATH,
    LOCAL_DEMO_SAMPLE_INPUT_PATH,
    NON_AUTHORIZATION_MARKER,
    PENDING_SIGNOFF_NAME,
    PROCUREMENT_REVIEW_NAME,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    build_and_write,
    build_decision_package,
    load_json,
    write_package_artifacts,
)


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_INPUT_PATH = ROOT / LOCAL_DEMO_SAMPLE_INPUT_PATH
EXPECTED_PACKAGE_PATH = ROOT / LOCAL_DEMO_EXPECTED_PACKAGE_PATH
BUILDER_SCRIPT_PATH = ROOT / CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["sample_builder"]
BUILDER_OUTPUT_DIR_NAME = "out"
MISSING_SAMPLE_INPUT_NAME = "missing_sample_input.json"
MISSING_SAMPLE_INPUT_ERROR_TYPE = "FileNotFoundError"


def _sample_input() -> dict[str, object]:
    return load_json(SAMPLE_INPUT_PATH)


def _expected_package() -> dict[str, object]:
    return load_json(EXPECTED_PACKAGE_PATH)


def _artifact_path(output_dir: Path, artifact_name: str) -> Path:
    return output_dir / artifact_name


def _builder_output_dir(tmp_path: Path) -> Path:
    return tmp_path / BUILDER_OUTPUT_DIR_NAME


def _decision_package_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, DECISION_PACKAGE_NAME)


def _decision_summary_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, DECISION_SUMMARY_NAME)


def _pending_signoff_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, PENDING_SIGNOFF_NAME)


def _procurement_review_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, PROCUREMENT_REVIEW_NAME)


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(cli_run.stdout)


def _run_builder_cli(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    cli_run = subprocess.run(
        [sys.executable, str(BUILDER_SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return cli_run, _load_stdout_json(cli_run)


def _assert_cli_completed(
    cli_run: subprocess.CompletedProcess[str],
    *,
    exit_code: int,
) -> None:
    assert cli_run.returncode == exit_code
    assert cli_run.stderr == ""


def test_build_decision_package_matches_expected_fixture() -> None:
    sample_input = _sample_input()
    expected_package = _expected_package()

    decision_package = build_decision_package(sample_input)

    assert decision_package == expected_package


def test_write_package_artifacts_creates_reviewable_local_package(tmp_path: Path) -> None:
    sample_input = _sample_input()
    decision_package = build_decision_package(sample_input)

    package_artifacts = write_package_artifacts(decision_package, tmp_path)

    assert package_artifacts["schema_purpose"] == EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert package_artifacts["recommendation"] == DEMO_RECOMMENDATION
    assert package_artifacts["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    for artifact_name in decision_package["package"]["export_manifest"]["included_artifacts"]:
        assert _artifact_path(tmp_path, artifact_name).exists(), artifact_name

    decision_summary = _decision_summary_path(tmp_path).read_text(encoding="utf-8")
    procurement_review = _procurement_review_path(tmp_path).read_text(encoding="utf-8")
    pending_signoff = load_json(_pending_signoff_path(tmp_path))

    assert NON_AUTHORIZATION_MARKER in decision_summary
    assert 'data-procurement-review-workspace' in procurement_review
    assert DEMO_RECOMMENDATION in procurement_review
    assert NON_AUTHORIZATION_MARKER in procurement_review
    assert pending_signoff["operational_approval"] is False


def test_build_and_write_validates_and_writes_package(tmp_path: Path) -> None:
    build_result = build_and_write(sample_input_path=SAMPLE_INPUT_PATH, output_dir=tmp_path)

    assert build_result["schema_purpose"] == EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert build_result["status"] == "passed"
    assert build_result["output_dir"] == str(tmp_path)
    assert build_result["recommendation"] == DEMO_RECOMMENDATION
    assert _decision_package_path(tmp_path).exists()


def test_builder_cli_returns_success_json(tmp_path: Path) -> None:
    out_dir = _builder_output_dir(tmp_path)

    cli_run, builder_cli_result = _run_builder_cli("--out-dir", str(out_dir))

    _assert_cli_completed(cli_run, exit_code=0)
    assert builder_cli_result["schema_purpose"] == EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert builder_cli_result["status"] == "passed"
    assert builder_cli_result["output_dir"] == str(out_dir)
    assert builder_cli_result["recommendation"] == DEMO_RECOMMENDATION
    assert builder_cli_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert _decision_package_path(out_dir).exists()


def test_builder_cli_returns_failure_json_no_traceback(tmp_path: Path) -> None:
    sample_input_path = tmp_path / MISSING_SAMPLE_INPUT_NAME
    out_dir = _builder_output_dir(tmp_path)

    cli_run, builder_failure_result = _run_builder_cli(
        "--sample-input",
        str(sample_input_path),
        "--out-dir",
        str(out_dir),
    )

    _assert_cli_completed(cli_run, exit_code=1)
    assert builder_failure_result["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert builder_failure_result["status"] == "failed"
    assert builder_failure_result["sample_input"] == str(sample_input_path)
    assert builder_failure_result["output_dir"] == str(out_dir)
    assert builder_failure_result["error_type"] == MISSING_SAMPLE_INPUT_ERROR_TYPE
