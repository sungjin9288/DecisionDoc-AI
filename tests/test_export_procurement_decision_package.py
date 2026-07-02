from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionUpsert,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)
from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    DECISION_PACKAGE_NAME,
    DEMO_RECOMMENDATION,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    EXPORT_MANIFEST_NAME,
    PENDING_SIGNOFF_NAME,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    export_project_decision_package,
)
from app.storage.procurement_store import ProcurementDecisionStore


ROOT = Path(__file__).resolve().parents[1]
EXPORT_SCRIPT_PATH = ROOT / CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["project_export"]
EXPORT_FIXTURE_TENANT_ID = "tenant-a"
EXPORT_FIXTURE_PROJECT_ID = "project-a"
MISSING_EXPORT_PROJECT_ID = "missing-project"
MISSING_EXPORT_PROJECT_ERROR_TYPE = "KeyError"
EXPORT_REVIEWER_OWNER = "reviewer-a"
EXPORT_OUTPUT_DIR_NAME = "package"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_path(out_dir: Path, artifact_name: str) -> Path:
    return out_dir / artifact_name


def _export_output_dir(tmp_path: Path) -> Path:
    return tmp_path / EXPORT_OUTPUT_DIR_NAME


def _load_artifact_json(out_dir: Path, artifact_name: str) -> dict[str, object]:
    return _load_json(_artifact_path(out_dir, artifact_name))


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(cli_run.stdout)


def _run_export_cli(*args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    cli_run = subprocess.run(
        [sys.executable, str(EXPORT_SCRIPT_PATH), *args],
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


def _seed_recommended_record(tmp_path: Path) -> str:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))
    record = store.upsert(
        ProcurementDecisionUpsert(
            project_id=EXPORT_FIXTURE_PROJECT_ID,
            tenant_id=EXPORT_FIXTURE_TENANT_ID,
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="bid-001",
                title="Public workflow modernization",
                issuer="Sample Agency",
            ),
            score_breakdown=[
                ProcurementScoreBreakdownItem(
                    key="domain_fit",
                    label="Domain fit",
                    score=72.0,
                    weight=0.2,
                    weighted_score=14.4,
                    summary="Relevant workflow experience exists.",
                    evidence=["workflow reference"],
                )
            ],
            soft_fit_score=72.0,
            soft_fit_status="scored",
            missing_data=["security plan owner"],
            checklist_items=[
                ProcurementChecklistItem(
                    category="security_plan",
                    title="Assign security plan owner",
                    status="action_needed",
                    severity="high",
                    remediation_note="Assign owner before proposal drafting.",
                )
            ],
            recommendation=ProcurementRecommendation(
                value=DEMO_RECOMMENDATION,
                summary="Conditional go pending security owner assignment.",
                evidence=["Weighted fit score: 72.00"],
                missing_data=["security plan owner"],
                remediation_notes=["Assign security plan owner."],
            ),
        )
    )
    return record.decision_id


def test_export_writes_artifacts(tmp_path: Path) -> None:
    decision_id = _seed_recommended_record(tmp_path)
    out_dir = _export_output_dir(tmp_path)

    export_result = export_project_decision_package(
        data_dir=tmp_path,
        tenant_id=EXPORT_FIXTURE_TENANT_ID,
        project_id=EXPORT_FIXTURE_PROJECT_ID,
        out_dir=out_dir,
        reviewer_owner=EXPORT_REVIEWER_OWNER,
    )

    assert export_result["decision_id"] == decision_id
    assert export_result["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert export_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert _artifact_path(out_dir, DECISION_PACKAGE_NAME).exists()
    assert _artifact_path(out_dir, EXPORT_MANIFEST_NAME).exists()

    decision_package = _load_artifact_json(out_dir, DECISION_PACKAGE_NAME)
    pending_signoff = _load_artifact_json(out_dir, PENDING_SIGNOFF_NAME)

    assert decision_package["package"]["recommendation"] == DEMO_RECOMMENDATION
    assert (
        decision_package["package"]["reviewer_handoff"]["requested_reviewer"]
        == EXPORT_REVIEWER_OWNER
    )
    assert pending_signoff["operational_approval"] is False


def test_export_rejects_missing_record(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="procurement decision record not found"):
        export_project_decision_package(
            data_dir=tmp_path,
            tenant_id=EXPORT_FIXTURE_TENANT_ID,
            project_id=MISSING_EXPORT_PROJECT_ID,
            out_dir=_export_output_dir(tmp_path),
        )


def test_export_cli_returns_success_json(tmp_path: Path) -> None:
    decision_id = _seed_recommended_record(tmp_path)
    out_dir = _export_output_dir(tmp_path)

    cli_run, export_cli_result = _run_export_cli(
        "--data-dir",
        str(tmp_path),
        "--tenant-id",
        EXPORT_FIXTURE_TENANT_ID,
        "--project-id",
        EXPORT_FIXTURE_PROJECT_ID,
        "--out-dir",
        str(out_dir),
    )

    _assert_cli_completed(cli_run, exit_code=0)
    assert export_cli_result["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert export_cli_result["tenant_id"] == EXPORT_FIXTURE_TENANT_ID
    assert export_cli_result["project_id"] == EXPORT_FIXTURE_PROJECT_ID
    assert export_cli_result["decision_id"] == decision_id
    assert _artifact_path(out_dir, DECISION_PACKAGE_NAME).exists()


def test_export_cli_returns_failure_json_no_traceback(tmp_path: Path) -> None:
    out_dir = _export_output_dir(tmp_path)

    cli_run, export_failure_result = _run_export_cli(
        "--data-dir",
        str(tmp_path),
        "--tenant-id",
        EXPORT_FIXTURE_TENANT_ID,
        "--project-id",
        MISSING_EXPORT_PROJECT_ID,
        "--out-dir",
        str(out_dir),
    )

    _assert_cli_completed(cli_run, exit_code=1)
    assert export_failure_result["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert export_failure_result["status"] == "failed"
    assert export_failure_result["tenant_id"] == EXPORT_FIXTURE_TENANT_ID
    assert export_failure_result["project_id"] == MISSING_EXPORT_PROJECT_ID
    assert export_failure_result["output_dir"] == str(out_dir)
    assert export_failure_result["error_type"] == MISSING_EXPORT_PROJECT_ERROR_TYPE
