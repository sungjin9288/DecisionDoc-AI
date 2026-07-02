from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.services.procurement_decision_package_service import (
    AUDIT_MANIFEST_NAME,
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    DECISION_PACKAGE_NAME,
    DEMO_PROJECT_ID,
    DEMO_RECEIPT_NAME,
    DEMO_RECOMMENDATION,
    DEMO_RESULT_NAME,
    DEMO_TENANT_ID,
    EXCLUDED_ACTION_ORDER,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    INCLUDED_ARTIFACT_ORDER,
    NON_APPROVAL_MARKER,
    NON_AUTHORIZATION_MARKER,
    PENDING_SIGNOFF_NAME,
    PROPOSAL_HANDOFF_NAME,
    PROPOSAL_HANDOFF_SCOPE,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    SCOPED_REVIEW_MARKER,
    SIGNOFF_SUMMARY_REQUIRED_MARKERS,
    SIGNOFF_SUMMARY_NAME,
    VALIDATION_SUMMARY_NAME,
    run_demo,
)


ROOT = Path(__file__).resolve().parents[1]
RUN_DEMO_SCRIPT_PATH = ROOT / CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["demo_runner"]
DEMO_DATA_DIR_NAME = "data"
DEMO_OUTPUT_DIR_NAME = "out"
DEMO_REVIEWER_OWNER = "reviewer-a"
DATA_DIR_FILE_NAME = "data-file"
FILE_INSTEAD_OF_DIRECTORY_TEXT = "not a directory\n"
DATA_DIR_FILE_ERROR_TYPES = {"FileExistsError", "NotADirectoryError"}
STALE_ARTIFACT_NAME = "stale_artifact.txt"
STALE_ARTIFACT_TEXT = "stale\n"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_path(out_dir: Path, artifact_name: str) -> Path:
    return out_dir / artifact_name


def _load_artifact_json(out_dir: Path, artifact_name: str) -> dict[str, object]:
    return _load_json(_artifact_path(out_dir, artifact_name))


def _load_artifact_text(out_dir: Path, artifact_name: str) -> str:
    return _artifact_path(out_dir, artifact_name).read_text(encoding="utf-8")


def _decision_package_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DECISION_PACKAGE_NAME)


def _demo_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DEMO_RESULT_NAME)


def _demo_receipt_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DEMO_RECEIPT_NAME)


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(cli_run.stdout)


def _run_demo_cli(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    cli_run = subprocess.run(
        [sys.executable, str(RUN_DEMO_SCRIPT_PATH), *args],
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


def _demo_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / DEMO_DATA_DIR_NAME, tmp_path / DEMO_OUTPUT_DIR_NAME


def test_run_demo_writes_validated_evidence_package(tmp_path: Path) -> None:
    data_dir, out_dir = _demo_paths(tmp_path)

    demo_run_result = run_demo(
        data_dir=data_dir,
        out_dir=out_dir,
        reviewer_owner=DEMO_REVIEWER_OWNER,
    )

    assert demo_run_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert demo_run_result["recommendation"] == DEMO_RECOMMENDATION
    assert demo_run_result["demo_tenant_id"] == DEMO_TENANT_ID
    assert demo_run_result["demo_project_id"] == DEMO_PROJECT_ID
    assert demo_run_result["seeded_decision_id"] == demo_run_result["decision_id"]
    assert demo_run_result["clean_output"] is False
    assert demo_run_result["artifact_check"]["status"] == "passed"
    assert demo_run_result["artifact_check"]["operational_approval"] is False
    assert demo_run_result["artifact_check"]["demo_result_checked"] is True
    assert demo_run_result["artifact_check"]["artifact_inventory_checked"] is True
    assert demo_run_result["artifact_check"]["demo_receipt_checked"] is True
    assert _demo_result_path(out_dir).exists()
    assert _demo_receipt_path(out_dir).exists()

    decision_package = _load_artifact_json(out_dir, DECISION_PACKAGE_NAME)
    validation_summary = _load_artifact_json(out_dir, VALIDATION_SUMMARY_NAME)
    proposal_handoff = _load_artifact_json(out_dir, PROPOSAL_HANDOFF_NAME)
    audit_manifest = _load_artifact_json(out_dir, AUDIT_MANIFEST_NAME)
    pending_signoff = _load_artifact_json(out_dir, PENDING_SIGNOFF_NAME)
    signoff_summary = _load_artifact_text(out_dir, SIGNOFF_SUMMARY_NAME)
    persisted_demo_result = _load_json(_demo_result_path(out_dir))
    demo_receipt_text = _demo_receipt_path(out_dir).read_text(encoding="utf-8")

    assert decision_package["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert (
        decision_package["package"]["reviewer_handoff"]["requested_reviewer"]
        == DEMO_REVIEWER_OWNER
    )
    assert (
        EXCLUDED_ACTION_ORDER[0]
        in decision_package["package"]["export_manifest"]["excluded_actions"]
    )
    assert NON_APPROVAL_MARKER in validation_summary["operator_summary"]
    assert SCOPED_REVIEW_MARKER in validation_summary["next_review_action"]
    assert proposal_handoff["handoff_scope"] == PROPOSAL_HANDOFF_SCOPE
    assert proposal_handoff["source_package_id"] == decision_package["package"]["package_id"]
    assert EXCLUDED_ACTION_ORDER[0] in proposal_handoff["excluded_actions"]
    assert audit_manifest["package_id"] == decision_package["package"]["package_id"]
    assert audit_manifest["recommendation"] == decision_package["package"]["recommendation"]
    assert audit_manifest["included_artifacts"] == INCLUDED_ARTIFACT_ORDER
    assert pending_signoff["operational_approval"] is False
    for marker in SIGNOFF_SUMMARY_REQUIRED_MARKERS:
        assert marker in signoff_summary
    assert demo_run_result["artifacts"] == INCLUDED_ARTIFACT_ORDER
    assert list(persisted_demo_result["artifact_inventory"]) == INCLUDED_ARTIFACT_ORDER
    assert persisted_demo_result["artifact_inventory"][DECISION_PACKAGE_NAME]["size_bytes"] > 0
    assert len(persisted_demo_result["artifact_inventory"][DECISION_PACKAGE_NAME]["sha256"]) == 64
    assert persisted_demo_result["artifact_check"]["status"] == "passed"
    assert persisted_demo_result["artifact_check"]["demo_result_checked"] is True
    assert persisted_demo_result["artifact_check"]["artifact_inventory_checked"] is True
    assert persisted_demo_result["artifact_check"]["demo_receipt_checked"] is True
    assert persisted_demo_result["demo_result_path"] == str(_demo_result_path(out_dir))
    assert persisted_demo_result["demo_receipt_path"] == str(_demo_receipt_path(out_dir))
    assert NON_AUTHORIZATION_MARKER in demo_receipt_text
    assert "demo_receipt_checked: true" in demo_receipt_text
    assert f"operator_summary: {validation_summary['operator_summary']}" in demo_receipt_text
    assert f"next_review_action: {validation_summary['next_review_action']}" in demo_receipt_text
    assert DECISION_PACKAGE_NAME in demo_receipt_text
    expected_receipt_rows = []
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        inventory_entry = persisted_demo_result["artifact_inventory"][artifact_name]
        expected_receipt_rows.append(
            f"| {artifact_name} | {inventory_entry['size_bytes']} | "
            f"{inventory_entry['sha256']} |"
        )
    demo_receipt_lines = demo_receipt_text.splitlines()
    artifact_table_start = demo_receipt_lines.index("| Artifact | Size bytes | SHA256 |") + 2
    assert (
        demo_receipt_lines[
            artifact_table_start : artifact_table_start + len(INCLUDED_ARTIFACT_ORDER)
        ]
        == expected_receipt_rows
    )


def test_run_demo_cleans_existing_output(tmp_path: Path) -> None:
    data_dir, out_dir = _demo_paths(tmp_path)
    out_dir.mkdir()
    stale_file = out_dir / STALE_ARTIFACT_NAME
    stale_file.write_text(STALE_ARTIFACT_TEXT, encoding="utf-8")

    demo_run_result = run_demo(
        data_dir=data_dir,
        out_dir=out_dir,
        reviewer_owner=DEMO_REVIEWER_OWNER,
        clean_output=True,
    )

    assert demo_run_result["clean_output"] is True
    assert demo_run_result["artifact_check"]["status"] == "passed"
    assert demo_run_result["artifact_check"]["demo_result_checked"] is True
    assert demo_run_result["artifact_check"]["artifact_inventory_checked"] is True
    assert demo_run_result["artifact_check"]["demo_receipt_checked"] is True
    assert not stale_file.exists()
    assert _decision_package_path(out_dir).exists()
    assert _demo_result_path(out_dir).exists()
    assert _demo_receipt_path(out_dir).exists()


def test_run_demo_cli_returns_success_json(tmp_path: Path) -> None:
    data_dir, out_dir = _demo_paths(tmp_path)

    cli_run, demo_cli_result = _run_demo_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
    )
    persisted_demo_result = _load_json(_demo_result_path(out_dir))

    _assert_cli_completed(cli_run, exit_code=0)
    assert demo_cli_result["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert demo_cli_result["demo_tenant_id"] == DEMO_TENANT_ID
    assert demo_cli_result["demo_project_id"] == DEMO_PROJECT_ID
    assert demo_cli_result["artifact_check"]["status"] == "passed"
    assert demo_cli_result["artifacts"] == INCLUDED_ARTIFACT_ORDER
    assert list(demo_cli_result["artifact_inventory"]) == INCLUDED_ARTIFACT_ORDER
    assert persisted_demo_result["artifacts"] == INCLUDED_ARTIFACT_ORDER
    assert list(persisted_demo_result["artifact_inventory"]) == INCLUDED_ARTIFACT_ORDER
    assert demo_cli_result["artifact_inventory"] == persisted_demo_result["artifact_inventory"]
    assert _demo_result_path(out_dir).exists()


def test_run_demo_cli_returns_failure_json_no_traceback(tmp_path: Path) -> None:
    data_dir = tmp_path / DATA_DIR_FILE_NAME
    data_dir.write_text(FILE_INSTEAD_OF_DIRECTORY_TEXT, encoding="utf-8")
    out_dir = tmp_path / DEMO_OUTPUT_DIR_NAME

    cli_run, demo_failure_result = _run_demo_cli(
        "--data-dir",
        str(data_dir),
        "--out-dir",
        str(out_dir),
    )

    _assert_cli_completed(cli_run, exit_code=1)
    assert demo_failure_result["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert demo_failure_result["status"] == "failed"
    assert demo_failure_result["data_dir"] == str(data_dir)
    assert demo_failure_result["output_dir"] == str(out_dir)
    assert demo_failure_result["error_type"] in DATA_DIR_FILE_ERROR_TYPES
