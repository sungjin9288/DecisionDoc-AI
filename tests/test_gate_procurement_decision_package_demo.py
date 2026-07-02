from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    DECISION_PACKAGE_NAME,
    DECISION_SUMMARY_NAME,
    DEMO_RECOMMENDATION,
    DEMO_RECEIPT_NAME,
    DEMO_RESULT_NAME,
    EXTERNAL_RUNTIME_ACTION_ORDER,
    GATE_NAME,
    GATE_RESULT_NAME,
    INCLUDED_ARTIFACT_ORDER,
    gate_demo_output,
    run_demo,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["evidence_gate"]
UNKNOWN_ARTIFACT_NAME = "unreviewed_artifact.json"
GATE_FAILURE_ERROR_TYPE = "ValueError"
MISSING_RECEIPT_ERROR_MARKER = "demo evidence receipt file is missing"
RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR = "--result-path requires --write-result"
DEMO_DATA_DIR_NAME = "data"
DEMO_OUTPUT_DIR_NAME = "out"
CUSTOM_GATE_RESULT_DIR_NAME = "gate-results"
IGNORED_GATE_RESULT_NAME = "ignored_gate.json"
FAILED_GATE_RESULT_NAME = "failed_gate.json"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _artifact_path(out_dir: Path, artifact_name: str) -> Path:
    return out_dir / artifact_name


def _demo_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DEMO_RESULT_NAME)


def _demo_receipt_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DEMO_RECEIPT_NAME)


def _gate_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, GATE_RESULT_NAME)


def _custom_gate_result_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / CUSTOM_GATE_RESULT_DIR_NAME / file_name


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(cli_run.stdout)


def _run_gate_cli(
    *args: object,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    cli_run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            *(str(arg) for arg in args),
        ],
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


def _run_seeded_demo(tmp_path: Path) -> Path:
    out_dir = tmp_path / DEMO_OUTPUT_DIR_NAME
    run_demo(data_dir=tmp_path / DEMO_DATA_DIR_NAME, out_dir=out_dir)
    return out_dir


def test_accepts_self_checked_demo_package(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    gate_output = gate_demo_output(out_dir)

    assert gate_output["gate"] == GATE_NAME
    assert gate_output["status"] == "passed"
    assert gate_output["recommendation"] == DEMO_RECOMMENDATION
    assert gate_output["operational_approval"] is False
    assert gate_output["demo_result_checked"] is True
    assert gate_output["artifact_inventory_checked"] is True
    assert gate_output["demo_receipt_checked"] is True
    assert gate_output["demo_result_path"] == str(_demo_result_path(out_dir))
    assert gate_output["demo_receipt_path"] == str(_demo_receipt_path(out_dir))
    assert gate_output["excluded_external_actions"] == EXTERNAL_RUNTIME_ACTION_ORDER
    assert gate_output["artifacts"] == INCLUDED_ARTIFACT_ORDER


def test_rejects_missing_receipt(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    _demo_receipt_path(out_dir).unlink()

    with pytest.raises(
        ValueError,
        match="demo evidence receipt file is missing|demo evidence receipt is missing",
    ):
        gate_demo_output(out_dir)


def test_rejects_missing_demo_result_artifact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifacts"] = [
        artifact for artifact in demo_result["artifacts"] if artifact != DECISION_SUMMARY_NAME
    ]
    _write_json(demo_result_path, demo_result)

    with pytest.raises(
        ValueError,
        match=f"demo_run_result.artifacts missing package artifacts: {DECISION_SUMMARY_NAME}",
    ):
        gate_demo_output(out_dir)


def test_rejects_duplicate_demo_result_artifact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifacts"].append(DECISION_PACKAGE_NAME)
    _write_json(demo_result_path, demo_result)

    with pytest.raises(
        ValueError,
        match="demo_run_result.artifacts must not contain duplicate values",
    ):
        gate_demo_output(out_dir)


def test_rejects_unknown_demo_result_artifact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifacts"].append(UNKNOWN_ARTIFACT_NAME)
    _write_json(demo_result_path, demo_result)

    with pytest.raises(
        ValueError,
        match=(
            "demo_run_result.artifacts includes unknown package artifacts: "
            f"{UNKNOWN_ARTIFACT_NAME}"
        ),
    ):
        gate_demo_output(out_dir)


def test_rejects_non_string_demo_result_artifact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifacts"].append(False)
    _write_json(demo_result_path, demo_result)

    expected_index = len(demo_result["artifacts"]) - 1
    with pytest.raises(
        ValueError,
        match=rf"demo_run_result.artifacts\[{expected_index}\] must be a non-empty string",
    ):
        gate_demo_output(out_dir)


def test_rejects_demo_result_artifact_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    artifacts = demo_result["artifacts"]
    artifacts[0], artifacts[1] = artifacts[1], artifacts[0]
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="demo_run_result.artifacts must match the expected order"):
        gate_demo_output(out_dir)


def test_gate_cli_returns_json_for_success(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    cli_run, gate_cli_result = _run_gate_cli(out_dir)

    _assert_cli_completed(cli_run, exit_code=0)
    assert gate_cli_result["status"] == "passed"
    assert gate_cli_result["demo_receipt_checked"] is True


def test_gate_cli_returns_json_for_failure_no_traceback(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    _demo_receipt_path(out_dir).unlink()
    cli_run, gate_failure_result = _run_gate_cli(out_dir)

    _assert_cli_completed(cli_run, exit_code=1)
    assert gate_failure_result["status"] == "failed"
    assert gate_failure_result["error_type"] == GATE_FAILURE_ERROR_TYPE
    assert MISSING_RECEIPT_ERROR_MARKER in gate_failure_result["error"]


def test_gate_cli_can_write_success_result_file(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    gate_result_path = _gate_result_path(out_dir)
    cli_run, gate_cli_result = _run_gate_cli(out_dir, "--write-result")
    gate_file_result = _load_json(gate_result_path)

    _assert_cli_completed(cli_run, exit_code=0)
    assert gate_cli_result["status"] == "passed"
    assert gate_file_result["status"] == "passed"
    assert gate_file_result["demo_receipt_checked"] is True
    assert gate_file_result["demo_result_path"] == str(_demo_result_path(out_dir))


def test_gate_cli_rejects_result_path_without_write_result(tmp_path: Path) -> None:
    out_dir = tmp_path / DEMO_OUTPUT_DIR_NAME
    gate_result_path = _custom_gate_result_path(tmp_path, IGNORED_GATE_RESULT_NAME)

    cli_run, gate_cli_result = _run_gate_cli(
        out_dir,
        "--result-path",
        gate_result_path,
    )

    _assert_cli_completed(cli_run, exit_code=1)
    assert gate_cli_result["status"] == "failed"
    assert gate_cli_result["error_type"] == GATE_FAILURE_ERROR_TYPE
    assert RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR in gate_cli_result["error"]
    assert not gate_result_path.exists()


def test_gate_cli_can_write_failure_result_file_to_custom_path(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    gate_result_path = _custom_gate_result_path(tmp_path, FAILED_GATE_RESULT_NAME)
    _demo_receipt_path(out_dir).unlink()
    cli_run, gate_cli_result = _run_gate_cli(
        out_dir,
        "--write-result",
        "--result-path",
        gate_result_path,
    )
    gate_file_result = _load_json(gate_result_path)

    _assert_cli_completed(cli_run, exit_code=1)
    assert gate_cli_result["status"] == "failed"
    assert gate_file_result["status"] == "failed"
    assert gate_file_result["error_type"] == GATE_FAILURE_ERROR_TYPE
    assert MISSING_RECEIPT_ERROR_MARKER in gate_file_result["error"]
