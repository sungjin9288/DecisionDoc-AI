from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    DEMO_PROJECT_ID,
    DEMO_RECEIPT_NAME,
    DEMO_RECOMMENDATION,
    DEMO_RESULT_NAME,
    DEMO_TENANT_ID,
    EVIDENCE_FILE_FIELDS,
    GATE_RESULT_NAME,
    SMOKE_NAME,
    SMOKE_CHECK_RESULT_NAME,
    SMOKE_RESULT_NAME,
    build_evidence_files,
    build_smoke_failure_result,
    smoke_demo_gate,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["smoke_wrapper"]
SMOKE_DATA_DIR_NAME = "data"
SMOKE_OUTPUT_DIR_NAME = "out"
EVIDENCE_OUTPUT_DIR_LABEL = "out"
DATA_DIR_FILE_NAME = "data-file"
FILE_INSTEAD_OF_DIRECTORY_TEXT = "not a directory\n"
SMOKE_FAILURE_ERROR_TYPE = "ValueError"
PERSISTED_SMOKE_REQUIRES_GATE_ERROR = "persisted smoke result requires persisted gate result"
GATE_RESULT_PATH_REQUIRES_WRITE_ERROR = (
    "--gate-result-path requires persisted gate result writing"
)
SMOKE_RESULT_PATH_REQUIRES_WRITE_ERROR = (
    "--smoke-result-path requires persisted smoke result writing"
)
SMOKE_CHECK_RESULT_PATH_REQUIRES_WRITE_ERROR = (
    "--smoke-check-result-path requires persisted smoke check result writing"
)
CUSTOM_GATE_RESULT_DIR_NAME = "gate"
CUSTOM_SMOKE_RESULT_DIR_NAME = "smoke"
CUSTOM_CHECK_RESULT_DIR_NAME = "checks"
HANDOFF_RESULT_DIR_NAME = "handoff"
FAILED_RESULT_NAME = "failed.json"
CUSTOM_GATE_RESULT_NAME = "result.json"
CUSTOM_SMOKE_CHECK_RESULT_NAME = "smoke_check.json"
HANDOFF_GATE_RESULT_NAME = "gate_result.json"
HANDOFF_SMOKE_RESULT_NAME = "smoke_result.json"
HANDOFF_SMOKE_CHECK_RESULT_NAME = "smoke_check_result.json"

EXPECTED_EVIDENCE_FILE_FIELDS = [
    "demo_result",
    "demo_receipt",
    "gate_result",
    "smoke_result",
    "smoke_check_result",
]


def _assert_evidence_files(
    evidence_files: dict[str, object],
    *,
    demo_result: object | None = None,
    demo_receipt: object | None = None,
    gate_result: object | None = None,
    smoke_result: object | None = None,
    smoke_check_result: object | None = None,
) -> None:
    assert list(evidence_files) == EXPECTED_EVIDENCE_FILE_FIELDS
    assert evidence_files == {
        "demo_result": demo_result,
        "demo_receipt": demo_receipt,
        "gate_result": gate_result,
        "smoke_result": smoke_result,
        "smoke_check_result": smoke_check_result,
    }


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _evidence_path(artifact_name: str) -> str:
    return f"{EVIDENCE_OUTPUT_DIR_LABEL}/{artifact_name}"


def _artifact_path(out_dir: Path, artifact_name: str) -> Path:
    return out_dir / artifact_name


def _demo_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DEMO_RESULT_NAME)


def _demo_receipt_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DEMO_RECEIPT_NAME)


def _gate_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, GATE_RESULT_NAME)


def _smoke_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, SMOKE_RESULT_NAME)


def _smoke_check_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, SMOKE_CHECK_RESULT_NAME)


def _custom_gate_result_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / CUSTOM_GATE_RESULT_DIR_NAME / file_name


def _custom_smoke_result_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / CUSTOM_SMOKE_RESULT_DIR_NAME / file_name


def _custom_smoke_check_result_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / CUSTOM_CHECK_RESULT_DIR_NAME / file_name


def _handoff_gate_result_path(tmp_path: Path) -> Path:
    return tmp_path / HANDOFF_RESULT_DIR_NAME / HANDOFF_GATE_RESULT_NAME


def _handoff_smoke_result_path(tmp_path: Path) -> Path:
    return tmp_path / HANDOFF_RESULT_DIR_NAME / HANDOFF_SMOKE_RESULT_NAME


def _handoff_smoke_check_result_path(tmp_path: Path) -> Path:
    return tmp_path / HANDOFF_RESULT_DIR_NAME / HANDOFF_SMOKE_CHECK_RESULT_NAME


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(cli_run.stdout)


def _run_smoke_cli(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    cli_run = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return cli_run, _load_stdout_json(cli_run)


def _assert_cli_completed(
    cli_run: subprocess.CompletedProcess[str],
    *,
    exit_code: int = 0,
) -> None:
    assert cli_run.returncode == exit_code
    assert cli_run.stderr == ""


def _smoke_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / SMOKE_DATA_DIR_NAME, tmp_path / SMOKE_OUTPUT_DIR_NAME


def test_build_evidence_files_uses_smoke_checker_contract_order() -> None:
    demo_result_path = _evidence_path(DEMO_RESULT_NAME)
    demo_receipt_path = _evidence_path(DEMO_RECEIPT_NAME)
    gate_result_path = _evidence_path(GATE_RESULT_NAME)
    smoke_result_path = _evidence_path(SMOKE_RESULT_NAME)
    smoke_check_result_path = _evidence_path(SMOKE_CHECK_RESULT_NAME)
    evidence_files = build_evidence_files(
        demo_result_path=demo_result_path,
        demo_receipt_path=demo_receipt_path,
        gate_result_path=gate_result_path,
        smoke_result_path=smoke_result_path,
        smoke_check_result_path=smoke_check_result_path,
    )
    empty_evidence_files = build_evidence_files()

    assert list(EVIDENCE_FILE_FIELDS) == EXPECTED_EVIDENCE_FILE_FIELDS
    _assert_evidence_files(
        evidence_files,
        demo_result=demo_result_path,
        demo_receipt=demo_receipt_path,
        gate_result=gate_result_path,
        smoke_result=smoke_result_path,
        smoke_check_result=smoke_check_result_path,
    )
    _assert_evidence_files(empty_evidence_files)


def test_build_failure_payload_preserves_evidence_file_contract_order(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)
    gate_result_path = _custom_gate_result_path(tmp_path, FAILED_RESULT_NAME)
    smoke_result_path = _custom_smoke_result_path(tmp_path, FAILED_RESULT_NAME)
    smoke_check_result_path = _custom_smoke_check_result_path(tmp_path, FAILED_RESULT_NAME)

    smoke_failure_result = build_smoke_failure_result(
        data_dir=data_dir,
        out_dir=out_dir,
        clean_output=True,
        gate_result_path=gate_result_path,
        gate_result_written=True,
        smoke_result_path=smoke_result_path,
        smoke_result_written=False,
        smoke_check_result_path=smoke_check_result_path,
        smoke_check_result_written=False,
        exc=RuntimeError("demo failed"),
    )

    _assert_evidence_files(
        smoke_failure_result["evidence_files"],
        gate_result=str(gate_result_path),
        smoke_result=str(smoke_result_path),
        smoke_check_result=str(smoke_check_result_path),
    )


def test_smoke_demo_gate_runs_demo_and_persists_gate_result(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)

    smoke_gate_result = smoke_demo_gate(data_dir=data_dir, out_dir=out_dir)
    persisted_gate_result = _load_json(_gate_result_path(out_dir))

    assert smoke_gate_result["smoke"] == SMOKE_NAME
    assert smoke_gate_result["status"] == "passed"
    assert smoke_gate_result["clean_output"] is True
    assert smoke_gate_result["demo_tenant_id"] == DEMO_TENANT_ID
    assert smoke_gate_result["demo_project_id"] == DEMO_PROJECT_ID
    assert isinstance(smoke_gate_result["seeded_decision_id"], str)
    assert smoke_gate_result["seeded_decision_id"]
    assert smoke_gate_result["recommendation"] == DEMO_RECOMMENDATION
    assert smoke_gate_result["operational_approval"] is False
    assert smoke_gate_result["demo_result_checked"] is True
    assert smoke_gate_result["artifact_inventory_checked"] is True
    assert smoke_gate_result["demo_receipt_checked"] is True
    assert smoke_gate_result["gate_result_path"] == str(_gate_result_path(out_dir))
    assert smoke_gate_result["gate_result_written"] is True
    assert smoke_gate_result["smoke_result_path"] is None
    assert smoke_gate_result["smoke_result_written"] is False
    assert smoke_gate_result["smoke_check_result_path"] is None
    assert smoke_gate_result["smoke_check_result_written"] is False
    assert smoke_gate_result["package_artifacts_checked"] is False
    assert smoke_gate_result["smoke_result_checked"] is False
    _assert_evidence_files(
        smoke_gate_result["evidence_files"],
        demo_result=str(_demo_result_path(out_dir)),
        demo_receipt=str(_demo_receipt_path(out_dir)),
        gate_result=str(_gate_result_path(out_dir)),
    )
    assert persisted_gate_result["status"] == "passed"


def test_smoke_demo_gate_can_skip_gate_result_write(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)

    smoke_gate_result = smoke_demo_gate(
        data_dir=data_dir,
        out_dir=out_dir,
        write_gate_result=False,
    )

    assert smoke_gate_result["status"] == "passed"
    assert smoke_gate_result["gate_result_path"] is None
    assert smoke_gate_result["gate_result_written"] is False
    assert smoke_gate_result["smoke_result_written"] is False
    assert smoke_gate_result["smoke_check_result_written"] is False
    assert smoke_gate_result["package_artifacts_checked"] is False
    assert smoke_gate_result["smoke_result_checked"] is False
    assert smoke_gate_result["evidence_files"]["gate_result"] is None
    assert list(smoke_gate_result["evidence_files"]) == EXPECTED_EVIDENCE_FILE_FIELDS
    assert not _gate_result_path(out_dir).exists()


def test_smoke_cli_returns_json_and_writes_custom_gate_result(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)
    gate_result_path = _custom_gate_result_path(tmp_path, CUSTOM_GATE_RESULT_NAME)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--gate-result-path",
        str(gate_result_path),
    )
    persisted_gate_result = _load_json(gate_result_path)
    persisted_smoke_result = _load_json(_smoke_result_path(out_dir))
    persisted_smoke_check_result = _load_json(_smoke_check_result_path(out_dir))

    _assert_cli_completed(cli_run)
    assert smoke_cli_result["status"] == "passed"
    assert smoke_cli_result["demo_tenant_id"] == DEMO_TENANT_ID
    assert smoke_cli_result["demo_project_id"] == DEMO_PROJECT_ID
    assert isinstance(smoke_cli_result["seeded_decision_id"], str)
    assert smoke_cli_result["seeded_decision_id"]
    assert smoke_cli_result["gate_result_path"] == str(gate_result_path)
    assert smoke_cli_result["gate_result_written"] is True
    assert smoke_cli_result["smoke_result_path"] == str(_smoke_result_path(out_dir))
    assert smoke_cli_result["smoke_result_written"] is True
    assert smoke_cli_result["smoke_check_result_path"] == str(_smoke_check_result_path(out_dir))
    assert smoke_cli_result["smoke_check_result_written"] is True
    assert smoke_cli_result["package_artifacts_checked"] is True
    assert smoke_cli_result["smoke_result_checked"] is True
    _assert_evidence_files(
        smoke_cli_result["evidence_files"],
        demo_result=str(_demo_result_path(out_dir)),
        demo_receipt=str(_demo_receipt_path(out_dir)),
        gate_result=str(gate_result_path),
        smoke_result=str(_smoke_result_path(out_dir)),
        smoke_check_result=str(_smoke_check_result_path(out_dir)),
    )
    assert persisted_gate_result["status"] == "passed"
    assert persisted_smoke_result["status"] == "passed"
    assert persisted_smoke_result["demo_tenant_id"] == DEMO_TENANT_ID
    assert persisted_smoke_result["demo_project_id"] == DEMO_PROJECT_ID
    assert persisted_smoke_result["seeded_decision_id"] == smoke_cli_result["seeded_decision_id"]
    assert persisted_smoke_result["gate_result_path"] == str(gate_result_path)
    assert persisted_smoke_result["smoke_result_written"] is True
    assert persisted_smoke_result["smoke_check_result_path"] == str(
        _smoke_check_result_path(out_dir)
    )
    assert persisted_smoke_result["smoke_check_result_written"] is True
    assert persisted_smoke_result["package_artifacts_checked"] is True
    assert persisted_smoke_result["smoke_result_checked"] is True
    _assert_evidence_files(
        persisted_smoke_result["evidence_files"],
        demo_result=str(_demo_result_path(out_dir)),
        demo_receipt=str(_demo_receipt_path(out_dir)),
        gate_result=str(gate_result_path),
        smoke_result=str(_smoke_result_path(out_dir)),
        smoke_check_result=str(_smoke_check_result_path(out_dir)),
    )
    assert persisted_smoke_check_result["status"] == "passed"
    assert persisted_smoke_check_result["smoke_result_checked"] is True
    assert persisted_smoke_check_result["demo_project_id"] == DEMO_PROJECT_ID
    assert persisted_smoke_check_result["smoke_result_path"] == str(_smoke_result_path(out_dir))
    assert persisted_smoke_check_result["evidence_files"]["smoke_check_result"] == str(
        _smoke_check_result_path(out_dir)
    )
    assert list(persisted_smoke_check_result["evidence_files"]) == EXPECTED_EVIDENCE_FILE_FIELDS


def test_smoke_cli_can_write_custom_smoke_check_result(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)
    smoke_check_result_path = _custom_smoke_check_result_path(
        tmp_path,
        CUSTOM_SMOKE_CHECK_RESULT_NAME,
    )

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--smoke-check-result-path",
        str(smoke_check_result_path),
    )
    persisted_smoke_result = _load_json(_smoke_result_path(out_dir))
    persisted_smoke_check_result = _load_json(smoke_check_result_path)

    _assert_cli_completed(cli_run)
    assert smoke_cli_result["smoke_check_result_path"] == str(smoke_check_result_path)
    assert smoke_cli_result["smoke_check_result_written"] is True
    assert smoke_cli_result["evidence_files"]["smoke_check_result"] == str(smoke_check_result_path)
    assert persisted_smoke_result["smoke_check_result_path"] == str(smoke_check_result_path)
    assert persisted_smoke_result["smoke_check_result_written"] is True
    assert persisted_smoke_result["evidence_files"]["smoke_check_result"] == str(
        smoke_check_result_path
    )
    assert persisted_smoke_check_result["status"] == "passed"
    assert persisted_smoke_check_result["smoke_result_path"] == str(_smoke_result_path(out_dir))


def test_smoke_cli_can_write_custom_smoke_result(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)
    smoke_result_path = _handoff_smoke_result_path(tmp_path)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--smoke-result-path",
        str(smoke_result_path),
    )
    persisted_smoke_result = _load_json(smoke_result_path)
    persisted_smoke_check_result = _load_json(_smoke_check_result_path(out_dir))

    _assert_cli_completed(cli_run)
    assert not _smoke_result_path(out_dir).exists()
    assert smoke_cli_result["smoke_result_path"] == str(smoke_result_path)
    assert smoke_cli_result["smoke_result_written"] is True
    assert smoke_cli_result["smoke_check_result_path"] == str(_smoke_check_result_path(out_dir))
    assert smoke_cli_result["smoke_check_result_written"] is True
    assert smoke_cli_result["package_artifacts_checked"] is True
    assert smoke_cli_result["smoke_result_checked"] is True
    assert smoke_cli_result["evidence_files"]["smoke_result"] == str(smoke_result_path)
    assert persisted_smoke_result == smoke_cli_result
    assert persisted_smoke_check_result["status"] == "passed"
    assert persisted_smoke_check_result["smoke_result_path"] == str(smoke_result_path)
    assert persisted_smoke_check_result["evidence_files"]["smoke_result"] == str(smoke_result_path)
    assert persisted_smoke_check_result["evidence_files"]["smoke_check_result"] == str(
        _smoke_check_result_path(out_dir)
    )


def test_smoke_cli_can_skip_smoke_check_result_write(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--no-write-smoke-check-result",
    )
    persisted_smoke_result = _load_json(_smoke_result_path(out_dir))

    _assert_cli_completed(cli_run)
    assert smoke_cli_result["smoke_check_result_path"] is None
    assert smoke_cli_result["smoke_check_result_written"] is False
    assert smoke_cli_result["evidence_files"]["smoke_check_result"] is None
    assert persisted_smoke_result["smoke_check_result_path"] is None
    assert persisted_smoke_result["smoke_check_result_written"] is False
    assert persisted_smoke_result["evidence_files"]["smoke_check_result"] is None
    assert not _smoke_check_result_path(out_dir).exists()


def test_smoke_cli_rejects_persisted_smoke_without_persisted_gate_result(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--no-write-gate-result",
    )
    persisted_smoke_result = _load_json(_smoke_result_path(out_dir))

    _assert_cli_completed(cli_run, exit_code=1)
    assert smoke_cli_result["status"] == "failed"
    assert smoke_cli_result["error_type"] == SMOKE_FAILURE_ERROR_TYPE
    assert PERSISTED_SMOKE_REQUIRES_GATE_ERROR in smoke_cli_result["error"]
    assert smoke_cli_result["gate_result_path"] is None
    assert smoke_cli_result["gate_result_written"] is False
    assert smoke_cli_result["smoke_result_path"] == str(_smoke_result_path(out_dir))
    assert smoke_cli_result["smoke_result_written"] is True
    assert smoke_cli_result["smoke_check_result_path"] == str(_smoke_check_result_path(out_dir))
    assert smoke_cli_result["smoke_check_result_written"] is False
    assert smoke_cli_result["evidence_files"]["gate_result"] is None
    assert smoke_cli_result["evidence_files"]["smoke_result"] == str(_smoke_result_path(out_dir))
    assert smoke_cli_result["evidence_files"]["smoke_check_result"] == str(
        _smoke_check_result_path(out_dir)
    )
    assert persisted_smoke_result == smoke_cli_result
    assert not _gate_result_path(out_dir).exists()
    assert not _smoke_check_result_path(out_dir).exists()


def test_smoke_cli_can_run_without_persisted_gate_or_smoke_results(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--no-write-gate-result",
        "--no-write-smoke-result",
    )

    _assert_cli_completed(cli_run)
    assert smoke_cli_result["status"] == "passed"
    assert smoke_cli_result["gate_result_path"] is None
    assert smoke_cli_result["gate_result_written"] is False
    assert smoke_cli_result["smoke_result_path"] is None
    assert smoke_cli_result["smoke_result_written"] is False
    assert smoke_cli_result["smoke_check_result_path"] is None
    assert smoke_cli_result["smoke_check_result_written"] is False
    assert smoke_cli_result["package_artifacts_checked"] is False
    assert smoke_cli_result["smoke_result_checked"] is False
    assert smoke_cli_result["evidence_files"]["gate_result"] is None
    assert smoke_cli_result["evidence_files"]["smoke_result"] is None
    assert smoke_cli_result["evidence_files"]["smoke_check_result"] is None
    assert _demo_result_path(out_dir).exists()
    assert not _gate_result_path(out_dir).exists()
    assert not _smoke_result_path(out_dir).exists()
    assert not _smoke_check_result_path(out_dir).exists()


def test_smoke_cli_rejects_gate_result_path_without_write(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)
    gate_result_path = _handoff_gate_result_path(tmp_path)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--no-write-gate-result",
        "--gate-result-path",
        str(gate_result_path),
    )

    _assert_cli_completed(cli_run, exit_code=1)
    assert smoke_cli_result["status"] == "failed"
    assert smoke_cli_result["error_type"] == SMOKE_FAILURE_ERROR_TYPE
    assert GATE_RESULT_PATH_REQUIRES_WRITE_ERROR in smoke_cli_result["error"]
    assert smoke_cli_result["gate_result_path"] is None
    assert smoke_cli_result["gate_result_written"] is False
    assert smoke_cli_result["smoke_result_path"] is None
    assert smoke_cli_result["smoke_result_written"] is False
    assert smoke_cli_result["smoke_check_result_path"] is None
    assert smoke_cli_result["smoke_check_result_written"] is False
    assert not gate_result_path.exists()
    assert not _demo_result_path(out_dir).exists()


def test_smoke_cli_rejects_smoke_result_path_without_write(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)
    smoke_result_path = _handoff_smoke_result_path(tmp_path)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--no-write-smoke-result",
        "--smoke-result-path",
        str(smoke_result_path),
    )

    _assert_cli_completed(cli_run, exit_code=1)
    assert smoke_cli_result["status"] == "failed"
    assert smoke_cli_result["error_type"] == SMOKE_FAILURE_ERROR_TYPE
    assert SMOKE_RESULT_PATH_REQUIRES_WRITE_ERROR in smoke_cli_result["error"]
    assert smoke_cli_result["gate_result_written"] is False
    assert smoke_cli_result["smoke_result_path"] is None
    assert smoke_cli_result["smoke_result_written"] is False
    assert smoke_cli_result["smoke_check_result_path"] is None
    assert smoke_cli_result["smoke_check_result_written"] is False
    assert not smoke_result_path.exists()
    assert not _demo_result_path(out_dir).exists()


def test_smoke_cli_rejects_check_result_path_without_write(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)
    smoke_check_result_path = _handoff_smoke_check_result_path(tmp_path)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--no-write-smoke-check-result",
        "--smoke-check-result-path",
        str(smoke_check_result_path),
    )
    persisted_smoke_result = _load_json(_smoke_result_path(out_dir))

    _assert_cli_completed(cli_run, exit_code=1)
    assert smoke_cli_result["status"] == "failed"
    assert smoke_cli_result["error_type"] == SMOKE_FAILURE_ERROR_TYPE
    assert SMOKE_CHECK_RESULT_PATH_REQUIRES_WRITE_ERROR in smoke_cli_result["error"]
    assert smoke_cli_result["gate_result_written"] is False
    assert smoke_cli_result["smoke_result_path"] == str(_smoke_result_path(out_dir))
    assert smoke_cli_result["smoke_result_written"] is True
    assert smoke_cli_result["smoke_check_result_path"] is None
    assert smoke_cli_result["smoke_check_result_written"] is False
    assert persisted_smoke_result == smoke_cli_result
    assert not smoke_check_result_path.exists()
    assert not _demo_result_path(out_dir).exists()


def test_smoke_cli_returns_failure_json_no_traceback(tmp_path: Path) -> None:
    data_dir = tmp_path / DATA_DIR_FILE_NAME
    data_dir.write_text(FILE_INSTEAD_OF_DIRECTORY_TEXT, encoding="utf-8")
    out_dir = tmp_path / SMOKE_OUTPUT_DIR_NAME
    gate_result_path = _custom_gate_result_path(tmp_path, FAILED_RESULT_NAME)
    smoke_result_path = _custom_smoke_result_path(tmp_path, FAILED_RESULT_NAME)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--gate-result-path",
        str(gate_result_path),
        "--smoke-result-path",
        str(smoke_result_path),
    )
    persisted_gate_result = _load_json(gate_result_path)
    persisted_smoke_result = _load_json(smoke_result_path)

    _assert_cli_completed(cli_run, exit_code=1)
    assert smoke_cli_result["status"] == "failed"
    assert persisted_gate_result["status"] == "failed"
    assert persisted_smoke_result["status"] == "failed"
    assert smoke_cli_result["gate_result_written"] is True
    assert smoke_cli_result["smoke_result_written"] is True
    assert smoke_cli_result["smoke_check_result_written"] is False
    assert smoke_cli_result["package_artifacts_checked"] is False
    assert smoke_cli_result["smoke_result_checked"] is False
    assert persisted_gate_result["error_type"] == smoke_cli_result["error_type"]
    assert persisted_gate_result["gate_result_path"] == str(gate_result_path)
    assert persisted_gate_result["smoke_result_written"] is True
    assert persisted_gate_result["smoke_check_result_written"] is False
    assert persisted_gate_result["package_artifacts_checked"] is False
    assert persisted_gate_result["smoke_result_checked"] is False
    assert persisted_gate_result["evidence_files"]["gate_result"] == str(gate_result_path)
    assert persisted_gate_result["evidence_files"]["smoke_result"] == str(smoke_result_path)
    assert persisted_smoke_result["smoke_result_path"] == str(smoke_result_path)
    assert persisted_smoke_result["smoke_result_written"] is True
    assert persisted_smoke_result["smoke_check_result_written"] is False
    assert persisted_smoke_result["package_artifacts_checked"] is False
    assert persisted_smoke_result["smoke_result_checked"] is False
    assert persisted_smoke_result["evidence_files"]["smoke_result"] == str(smoke_result_path)


def test_smoke_cli_can_skip_smoke_result_write(tmp_path: Path) -> None:
    data_dir, out_dir = _smoke_paths(tmp_path)

    cli_run, smoke_cli_result = _run_smoke_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
        "--no-write-smoke-result",
    )

    _assert_cli_completed(cli_run)
    assert smoke_cli_result["status"] == "passed"
    assert smoke_cli_result["smoke_result_path"] is None
    assert smoke_cli_result["smoke_result_written"] is False
    assert smoke_cli_result["smoke_check_result_path"] is None
    assert smoke_cli_result["smoke_check_result_written"] is False
    assert smoke_cli_result["package_artifacts_checked"] is False
    assert smoke_cli_result["smoke_result_checked"] is False
    assert smoke_cli_result["evidence_files"]["smoke_result"] is None
    assert smoke_cli_result["evidence_files"]["smoke_check_result"] is None
    assert not _smoke_result_path(out_dir).exists()
    assert not _smoke_check_result_path(out_dir).exists()
