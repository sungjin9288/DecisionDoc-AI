from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services import procurement_decision_package_service as checker


ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT_PATH = ROOT / checker.CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["smoke_wrapper"]
CHECK_SCRIPT_PATH = ROOT / checker.CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["smoke_checker"]
MISSING_SMOKE_RESULT_NAME = "missing.json"
MISSING_SMOKE_RESULT_ERROR_TYPE = "FileNotFoundError"
CHECK_RESULT_PATH_ERROR_TYPE = "ValueError"
RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR = "--result-path requires --write-result"
SMOKE_DATA_DIR_NAME = "data"
SMOKE_OUTPUT_DIR_NAME = "out"
RESULT_PATH_MISSING_SMOKE_RESULT_NAME = "missing_smoke_result.json"
CUSTOM_CHECK_RESULT_DIR_NAME = "checks"
IGNORED_CHECK_RESULT_NAME = "ignored_check.json"
SUCCESSFUL_CHECK_RESULT_NAME = "successful_check.json"
FAILED_CHECK_RESULT_NAME = "failed_check.json"
MISSING_RECEIPT_NAME = "missing_receipt.md"
STALE_GATE_RESULT_NAME = "other_gate_result.json"
UNKNOWN_EVIDENCE_NAME = "unreviewed.json"
STALE_DEMO_RESULT_NAME = "other_demo_run_result.json"
STALE_SMOKE_CHECK_RESULT_NAME = "other_smoke_check_result.json"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: dict[str, object]) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _output_path(out_dir: Path, artifact_name: str) -> Path:
    return out_dir / artifact_name


def _demo_result_path(out_dir: Path) -> Path:
    return _output_path(out_dir, checker.DEMO_RESULT_NAME)


def _decision_summary_path(out_dir: Path) -> Path:
    return _output_path(out_dir, checker.DECISION_SUMMARY_NAME)


def _gate_result_path(out_dir: Path) -> Path:
    return _output_path(out_dir, checker.GATE_RESULT_NAME)


def _smoke_result_path(out_dir: Path) -> Path:
    return _output_path(out_dir, checker.SMOKE_RESULT_NAME)


def _smoke_check_result_path(out_dir: Path) -> Path:
    return _output_path(out_dir, checker.SMOKE_CHECK_RESULT_NAME)


def _custom_smoke_check_result_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / CUSTOM_CHECK_RESULT_DIR_NAME / file_name


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(cli_run.stdout)


def _run_smoke_demo_gate(tmp_path: Path, out_dir: Path) -> Path:
    cli_run = subprocess.run(
        [
            sys.executable,
            str(SMOKE_SCRIPT_PATH),
            "--data-dir",
            str(tmp_path / SMOKE_DATA_DIR_NAME),
            "--out-dir",
            str(out_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    _assert_cli_completed(cli_run, exit_code=0)
    return _smoke_result_path(out_dir)


def _run_smoke_demo(tmp_path: Path) -> tuple[Path, Path]:
    out_dir = tmp_path / SMOKE_OUTPUT_DIR_NAME
    smoke_result_path = _run_smoke_demo_gate(tmp_path, out_dir)
    return out_dir, smoke_result_path


def _run_checker_cli(
    *args: object,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    cli_run = subprocess.run(
        [
            sys.executable,
            str(CHECK_SCRIPT_PATH),
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


def test_accepts_persisted_smoke_summary(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)

    smoke_check_result = checker.check_smoke_result(smoke_result_path)

    assert smoke_check_result["status"] == "passed"
    assert smoke_check_result["output_dir"] == str(out_dir)
    assert smoke_check_result["clean_output"] is True
    assert smoke_check_result["smoke_check_result_path"] == str(
        _smoke_check_result_path(out_dir)
    )
    assert smoke_check_result["smoke_check_result_written"] is True
    assert smoke_check_result["demo_tenant_id"] == checker.DEMO_TENANT_ID
    assert smoke_check_result["demo_project_id"] == checker.DEMO_PROJECT_ID
    assert isinstance(smoke_check_result["seeded_decision_id"], str)
    assert smoke_check_result["seeded_decision_id"]
    assert smoke_check_result["recommendation"] == checker.DEMO_RECOMMENDATION
    assert smoke_check_result["operational_approval"] is False
    assert smoke_check_result["smoke_result_checked"] is True
    assert (
        checker.PROVIDER_API_EXECUTION_ACTION
        in smoke_check_result["excluded_external_actions"]
    )
    assert smoke_check_result["evidence_files"]["smoke_result"] == str(smoke_result_path)
    assert smoke_check_result["evidence_files"]["smoke_check_result"] == str(
        _smoke_check_result_path(out_dir)
    )


def test_rejects_failed_status(tmp_path: Path) -> None:
    smoke_result_path = _smoke_result_path(tmp_path)
    _write_json(
        smoke_result_path,
        {
            "smoke": checker.SMOKE_NAME,
            "status": "failed",
            "operational_approval": False,
        },
    )

    with pytest.raises(ValueError, match="status must be passed"):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_missing_evidence_file(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    missing_receipt_path = str(_output_path(out_dir, MISSING_RECEIPT_NAME))
    smoke_result["demo_receipt_path"] = missing_receipt_path
    smoke_result["evidence_files"]["demo_receipt"] = missing_receipt_path
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(ValueError, match="evidence_files.demo_receipt file is missing"):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_top_level_evidence_path_mismatch(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["gate_result_path"] = str(_output_path(out_dir, STALE_GATE_RESULT_NAME))
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(
        ValueError,
        match=(
            "demo_smoke_result.gate_result_path must match "
            "demo_smoke_result.evidence_files.gate_result"
        ),
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_missing_evidence_file_key(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["evidence_files"].pop("demo_receipt")
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(ValueError, match="evidence_files missing fields: demo_receipt"):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_unknown_evidence_file_key(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["evidence_files"]["unreviewed_evidence"] = str(
        _output_path(out_dir, UNKNOWN_EVIDENCE_NAME)
    )
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(
        ValueError,
        match="evidence_files includes unknown fields: unreviewed_evidence",
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_evidence_file_key_order_drift(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    evidence_files = smoke_result["evidence_files"]
    smoke_result["evidence_files"] = {
        "demo_receipt": evidence_files["demo_receipt"],
        "demo_result": evidence_files["demo_result"],
        "gate_result": evidence_files["gate_result"],
        "smoke_result": evidence_files["smoke_result"],
        "smoke_check_result": evidence_files["smoke_check_result"],
    }
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(ValueError, match="evidence_files must match the expected order"):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_stale_package_artifact_inventory(tmp_path: Path) -> None:
    out_dir, _ = _run_smoke_demo(tmp_path)
    decision_summary_path = _decision_summary_path(out_dir)
    decision_summary_path.write_text(
        decision_summary_path.read_text(encoding="utf-8")
        + "\nlocal drift after smoke\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match=f"artifact inventory sha256 mismatch: {checker.DECISION_SUMMARY_NAME}",
    ):
        checker.check_smoke_result(_smoke_result_path(out_dir))


def test_rejects_checked_summary_without_artifact_flag(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result.pop("package_artifacts_checked")
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(
        ValueError,
        match="package_artifacts_checked must be true when smoke_result_checked is true",
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_unchecked_persisted_summary(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["smoke_result_checked"] = False
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(ValueError, match="demo_smoke_result.smoke_result_checked must be true"):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_gate_result_mismatch(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    gate_result_path = _gate_result_path(out_dir)
    gate_result = _load_json(gate_result_path)
    gate_result["recommendation"] = "GO"
    _write_json(gate_result_path, gate_result)

    with pytest.raises(ValueError, match="recommendation must match"):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_gate_result_evidence_path_mismatch(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    gate_result_path = _gate_result_path(out_dir)
    gate_result = _load_json(gate_result_path)
    gate_result["demo_result_path"] = str(_output_path(out_dir, STALE_DEMO_RESULT_NAME))
    _write_json(gate_result_path, gate_result)

    with pytest.raises(
        ValueError,
        match="demo_gate_result.demo_result_path must match demo_smoke_result.demo_result_path",
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_demo_result_mismatch(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifact_check"]["artifact_inventory_checked"] = False
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="artifact_inventory_checked must match demo_run_result"):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_demo_run_metadata_mismatch(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["clean_output"] = False
    _write_json(demo_result_path, demo_result)

    with pytest.raises(
        ValueError,
        match="demo_run_result.clean_output must match demo_smoke_result.clean_output",
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_demo_identity_mismatch(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["demo_project_id"] = "other-demo-project"
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(
        ValueError,
        match="demo_run_result.demo_project_id must match demo_smoke_result.demo_project_id",
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_missing_recorded_smoke_check_result(tmp_path: Path) -> None:
    out_dir, _ = _run_smoke_demo(tmp_path)
    _smoke_check_result_path(out_dir).unlink()

    with pytest.raises(ValueError, match="evidence_files.smoke_check_result file is missing"):
        checker.check_smoke_result(_smoke_result_path(out_dir))


def test_rejects_smoke_check_evidence_path_mismatch(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["evidence_files"]["smoke_check_result"] = str(
        _output_path(out_dir, STALE_SMOKE_CHECK_RESULT_NAME)
    )
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(
        ValueError,
        match=(
            "demo_smoke_result.smoke_check_result_path must match "
            "demo_smoke_result.evidence_files.smoke_check_result"
        ),
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_stale_recorded_smoke_check_result(tmp_path: Path) -> None:
    out_dir, _ = _run_smoke_demo(tmp_path)
    smoke_check_result_path = _smoke_check_result_path(out_dir)
    smoke_check_result = _load_json(smoke_check_result_path)
    smoke_check_result["demo_project_id"] = "stale-demo-project"
    _write_json(smoke_check_result_path, smoke_check_result)

    with pytest.raises(
        ValueError,
        match="demo_smoke_check_result must match the current smoke check result",
    ):
        checker.check_smoke_result(_smoke_result_path(out_dir))


def test_rejects_missing_external_action(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["excluded_external_actions"] = [
        action
        for action in smoke_result["excluded_external_actions"]
        if action != checker.PROVIDER_API_EXECUTION_ACTION
    ]
    _write_json(smoke_result_path, smoke_result)

    expected_error = f"missing external actions: {checker.PROVIDER_API_EXECUTION_ACTION}"
    with pytest.raises(ValueError, match=expected_error):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_non_string_external_action(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["excluded_external_actions"].append(False)
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(
        ValueError,
        match=r"excluded_external_actions\[6\] must be a non-empty string",
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_duplicate_external_action(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    smoke_result["excluded_external_actions"].append(
        checker.PROVIDER_API_EXECUTION_ACTION
    )
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(
        ValueError,
        match="excluded_external_actions must not contain duplicate values",
    ):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_external_action_order_drift(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_result = _load_json(smoke_result_path)
    external_actions = smoke_result["excluded_external_actions"]
    external_actions[0], external_actions[1] = (
        external_actions[1],
        external_actions[0],
    )
    _write_json(smoke_result_path, smoke_result)

    with pytest.raises(ValueError, match="excluded_external_actions must match the expected order"):
        checker.check_smoke_result(smoke_result_path)


def test_rejects_gate_external_action_order_drift(tmp_path: Path) -> None:
    out_dir, _ = _run_smoke_demo(tmp_path)
    gate_result_path = _gate_result_path(out_dir)
    gate_result = _load_json(gate_result_path)
    external_actions = gate_result["excluded_external_actions"]
    external_actions[0], external_actions[1] = (
        external_actions[1],
        external_actions[0],
    )
    _write_json(gate_result_path, gate_result)

    with pytest.raises(
        ValueError,
        match="demo_gate_result.excluded_external_actions must match the expected order",
    ):
        checker.check_smoke_result(_smoke_result_path(out_dir))


def test_rejects_unknown_gate_external_action(tmp_path: Path) -> None:
    out_dir, _ = _run_smoke_demo(tmp_path)
    gate_result_path = _gate_result_path(out_dir)
    gate_result = _load_json(gate_result_path)
    gate_result["excluded_external_actions"].append("unreviewed_runtime_action")
    _write_json(gate_result_path, gate_result)

    with pytest.raises(
        ValueError,
        match=(
            "demo_gate_result.excluded_external_actions includes unknown external "
            "actions: unreviewed_runtime_action"
        ),
    ):
        checker.check_smoke_result(_smoke_result_path(out_dir))


def test_checker_cli_returns_json_for_missing_file(tmp_path: Path) -> None:
    missing_smoke_result_path = tmp_path / MISSING_SMOKE_RESULT_NAME

    cli_run, missing_smoke_failure_result = _run_checker_cli(missing_smoke_result_path)

    _assert_cli_completed(cli_run, exit_code=1)
    assert missing_smoke_failure_result["status"] == "failed"
    assert missing_smoke_failure_result["error_type"] == MISSING_SMOKE_RESULT_ERROR_TYPE


def test_checker_cli_can_persist_success_result(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)

    cli_run, stdout_smoke_check_result = _run_checker_cli(
        smoke_result_path,
        "--write-result",
    )
    file_smoke_check_result = _load_json(_smoke_check_result_path(out_dir))

    _assert_cli_completed(cli_run, exit_code=0)
    assert stdout_smoke_check_result["status"] == "passed"
    assert file_smoke_check_result == stdout_smoke_check_result
    assert file_smoke_check_result["demo_project_id"] == checker.DEMO_PROJECT_ID
    assert file_smoke_check_result["output_dir"] == str(out_dir)


def test_checker_cli_rejects_result_path_without_write_result(tmp_path: Path) -> None:
    smoke_result_path = tmp_path / RESULT_PATH_MISSING_SMOKE_RESULT_NAME
    smoke_check_result_path = _custom_smoke_check_result_path(
        tmp_path,
        IGNORED_CHECK_RESULT_NAME,
    )

    cli_run, smoke_check_result_path_failure = _run_checker_cli(
        smoke_result_path,
        "--result-path",
        smoke_check_result_path,
    )

    _assert_cli_completed(cli_run, exit_code=1)
    assert smoke_check_result_path_failure["status"] == "failed"
    assert smoke_check_result_path_failure["error_type"] == CHECK_RESULT_PATH_ERROR_TYPE
    assert (
        RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR
        in smoke_check_result_path_failure["error"]
    )
    assert not smoke_check_result_path.exists()


def test_checker_cli_can_persist_success_result_to_custom_path(tmp_path: Path) -> None:
    out_dir, smoke_result_path = _run_smoke_demo(tmp_path)
    smoke_check_result_path = _custom_smoke_check_result_path(
        tmp_path,
        SUCCESSFUL_CHECK_RESULT_NAME,
    )
    canonical_smoke_check_result_path = _smoke_check_result_path(out_dir)
    canonical_smoke_check_result_before = _load_json(canonical_smoke_check_result_path)

    cli_run, stdout_smoke_check_result = _run_checker_cli(
        smoke_result_path,
        "--write-result",
        "--result-path",
        smoke_check_result_path,
    )
    custom_file_smoke_check_result = _load_json(smoke_check_result_path)
    canonical_smoke_check_result_after = _load_json(canonical_smoke_check_result_path)

    _assert_cli_completed(cli_run, exit_code=0)
    assert stdout_smoke_check_result["status"] == "passed"
    assert custom_file_smoke_check_result == stdout_smoke_check_result
    assert canonical_smoke_check_result_after == canonical_smoke_check_result_before
    assert custom_file_smoke_check_result == canonical_smoke_check_result_after
    assert custom_file_smoke_check_result["smoke_check_result_path"] == str(
        canonical_smoke_check_result_path
    )
    assert custom_file_smoke_check_result["evidence_files"]["smoke_check_result"] == str(
        canonical_smoke_check_result_path
    )


def test_checker_cli_can_persist_failure_result_to_custom_path(tmp_path: Path) -> None:
    missing_smoke_result_path = tmp_path / MISSING_SMOKE_RESULT_NAME
    smoke_check_result_path = _custom_smoke_check_result_path(tmp_path, FAILED_CHECK_RESULT_NAME)

    cli_run, stdout_smoke_check_failure = _run_checker_cli(
        missing_smoke_result_path,
        "--write-result",
        "--result-path",
        smoke_check_result_path,
    )
    file_smoke_check_failure = _load_json(smoke_check_result_path)

    _assert_cli_completed(cli_run, exit_code=1)
    assert stdout_smoke_check_failure["status"] == "failed"
    assert stdout_smoke_check_failure["error_type"] == MISSING_SMOKE_RESULT_ERROR_TYPE
    assert file_smoke_check_failure == stdout_smoke_check_failure
