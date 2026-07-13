from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.procurement_decision_package_service import (
    AUDIT_MANIFEST_NAME,
    BID_SUBMISSION_ACTION,
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    DECISION_PACKAGE_NAME,
    DECISION_SUMMARY_NAME,
    DEMO_RECEIPT_NAME,
    DEMO_RECOMMENDATION,
    DEMO_RESULT_NAME,
    EVIDENCE_SUMMARY_NAME,
    EXCLUDED_ACTION_ORDER,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    EXPORT_MANIFEST_NAME,
    INCLUDED_ARTIFACT_ORDER,
    NON_AUTHORIZATION_MARKER,
    PENDING_SIGNOFF_NAME,
    PROCUREMENT_REVIEW_NAME,
    PROPOSAL_HANDOFF_NAME,
    REVIEWER_HANDOFF_NAME,
    SIGNOFF_SUMMARY_NAME,
    VALIDATION_SUMMARY_NAME,
    build_package_artifact_check_result as check_package_artifacts,
    run_demo,
)


ROOT = Path(__file__).resolve().parents[1]
CHECK_SCRIPT_PATH = ROOT / CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["artifact_checker"]
UNKNOWN_ARTIFACT_NAME = "unreviewed_artifact.json"
MISSING_OUTPUT_DIR_NAME = "missing-out"
MISSING_OUTPUT_DIR_ERROR_TYPE = "FileNotFoundError"
STALE_SHA256 = "0" * 64
DEMO_DATA_DIR_NAME = "data"
DEMO_OUTPUT_DIR_NAME = "out"
STALE_DEMO_RESULT_NAME = "other.json"
STALE_DEMO_RECEIPT_NAME = "other.md"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(_read_text(path))


def _write_json(path: Path, value: dict[str, object]) -> None:
    _write_text(path, json.dumps(value))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _append_text(path: Path, value: str) -> None:
    _write_text(path, _read_text(path) + value)


def _replace_text(path: Path, old: str, new: str) -> None:
    _write_text(path, _read_text(path).replace(old, new))


def _artifact_path(out_dir: Path, artifact_name: str) -> Path:
    return out_dir / artifact_name


def _decision_package_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DECISION_PACKAGE_NAME)


def _decision_summary_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DECISION_SUMMARY_NAME)


def _evidence_summary_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, EVIDENCE_SUMMARY_NAME)


def _pending_signoff_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, PENDING_SIGNOFF_NAME)


def _signoff_summary_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, SIGNOFF_SUMMARY_NAME)


def _reviewer_handoff_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, REVIEWER_HANDOFF_NAME)


def _validation_summary_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, VALIDATION_SUMMARY_NAME)


def _proposal_handoff_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, PROPOSAL_HANDOFF_NAME)


def _audit_manifest_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, AUDIT_MANIFEST_NAME)


def _export_manifest_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, EXPORT_MANIFEST_NAME)


def _demo_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DEMO_RESULT_NAME)


def _demo_receipt_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, DEMO_RECEIPT_NAME)


def _stale_demo_result_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, STALE_DEMO_RESULT_NAME)


def _stale_demo_receipt_path(out_dir: Path) -> Path:
    return _artifact_path(out_dir, STALE_DEMO_RECEIPT_NAME)


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return json.loads(cli_run.stdout)


def _run_checker_cli(
    output_dir: Path,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    cli_run = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT_PATH), str(output_dir)],
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


def test_accepts_seeded_demo_output(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    artifact_check_result = check_package_artifacts(out_dir)

    assert artifact_check_result["status"] == "passed"
    assert artifact_check_result["recommendation"] == DEMO_RECOMMENDATION
    assert artifact_check_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert artifact_check_result["operational_approval"] is False
    assert artifact_check_result["demo_result_checked"] is True
    assert artifact_check_result["artifact_inventory_checked"] is True
    assert artifact_check_result["demo_receipt_checked"] is True


def test_rejects_procurement_review_without_boundary(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    review_path = _artifact_path(out_dir, PROCUREMENT_REVIEW_NAME)
    _replace_text(review_path, NON_AUTHORIZATION_MARKER, "boundary removed")

    with pytest.raises(ValueError, match="missing review markers"):
        check_package_artifacts(out_dir)


def test_rejects_scripted_procurement_review(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    review_path = _artifact_path(out_dir, PROCUREMENT_REVIEW_NAME)
    _append_text(review_path, "<script></script>")

    with pytest.raises(ValueError, match="must remain script-free"):
        check_package_artifacts(out_dir)


def test_rejects_top_level_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    _write_json(
        decision_package_path,
        {
            "schema_purpose": package_doc["schema_purpose"],
            "scenario_id": package_doc["scenario_id"],
            "updated_at": package_doc["updated_at"],
            "package": package_doc["package"],
        },
    )

    with pytest.raises(ValueError, match="decision_package fields must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_empty_decision_package_updated_at(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    package_doc["updated_at"] = ""
    _write_json(decision_package_path, package_doc)

    with pytest.raises(ValueError, match="decision_package.updated_at"):
        check_package_artifacts(out_dir)


def test_rejects_decision_package_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    package = package_doc["package"]
    package_doc["package"] = {
        "recommendation": package["recommendation"],
        "package_id": package["package_id"],
        "recommendation_reason": package["recommendation_reason"],
        "opportunity_ref": package["opportunity_ref"],
        "hard_filters": package["hard_filters"],
        "soft_fit_score": package["soft_fit_score"],
        "evidence_summary": package["evidence_summary"],
        "bid_readiness_checklist": package["bid_readiness_checklist"],
        "validation_summary": package["validation_summary"],
        "reviewer_handoff": package["reviewer_handoff"],
        "proposal_handoff": package["proposal_handoff"],
        "pending_signoff": package["pending_signoff"],
        "audit_manifest": package["audit_manifest"],
        "export_manifest": package["export_manifest"],
    }
    _write_json(decision_package_path, package_doc)

    with pytest.raises(
        ValueError,
        match="decision_package.package fields must match the expected order",
    ):
        check_package_artifacts(out_dir)


def test_rejects_opportunity_ref_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    opportunity_ref = package_doc["package"]["opportunity_ref"]
    package_doc["package"]["opportunity_ref"] = {
        "title": opportunity_ref["title"],
        "opportunity_id": opportunity_ref["opportunity_id"],
        "source_type": opportunity_ref["source_type"],
    }
    _write_json(decision_package_path, package_doc)

    with pytest.raises(ValueError, match="opportunity_ref fields must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_empty_opportunity_ref_title(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    package_doc["package"]["opportunity_ref"]["title"] = ""
    _write_json(decision_package_path, package_doc)

    with pytest.raises(ValueError, match="opportunity_ref.title"):
        check_package_artifacts(out_dir)


def test_rejects_empty_opportunity_ref_source_type(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    package_doc["package"]["opportunity_ref"]["source_type"] = ""
    _write_json(decision_package_path, package_doc)

    with pytest.raises(ValueError, match="opportunity_ref.source_type"):
        check_package_artifacts(out_dir)


def test_rejects_hard_filter_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    hard_filter = package_doc["package"]["hard_filters"][0]
    package_doc["package"]["hard_filters"][0] = {
        "status": hard_filter["status"],
        "filter_id": hard_filter["filter_id"],
        "reason": hard_filter["reason"],
    }
    _write_json(decision_package_path, package_doc)

    with pytest.raises(ValueError, match=r"hard_filters\[0\] fields must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_unreviewed_hard_filter_status(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    package_doc["package"]["hard_filters"][0]["status"] = "approved"
    _write_json(decision_package_path, package_doc)

    with pytest.raises(ValueError, match=r"hard_filters\[0\].status"):
        check_package_artifacts(out_dir)


def test_rejects_soft_fit_factor_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    factor = package_doc["package"]["soft_fit_score"]["factors"][0]
    package_doc["package"]["soft_fit_score"]["factors"][0] = {
        "score": factor["score"],
        "name": factor["name"],
        "evidence_ids": factor["evidence_ids"],
    }
    _write_json(decision_package_path, package_doc)

    with pytest.raises(
        ValueError,
        match=r"soft_fit_score.factors\[0\] fields must match the expected order",
    ):
        check_package_artifacts(out_dir)


def test_rejects_bool_soft_fit_score(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    package_doc["package"]["soft_fit_score"]["score"] = True
    _write_json(decision_package_path, package_doc)

    with pytest.raises(ValueError, match="soft_fit_score.score must be an integer from 0 to 100"):
        check_package_artifacts(out_dir)


def test_rejects_evidence_summary_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    evidence = package_doc["package"]["evidence_summary"][0]
    package_doc["package"]["evidence_summary"][0] = {
        "type": evidence["type"],
        "evidence_id": evidence["evidence_id"],
        "source": evidence["source"],
        "summary": evidence["summary"],
    }
    _write_json(decision_package_path, package_doc)

    with pytest.raises(
        ValueError,
        match=r"evidence_summary\[0\] fields must match the expected order",
    ):
        check_package_artifacts(out_dir)


def test_rejects_checklist_field_order(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    checklist_item = package_doc["package"]["bid_readiness_checklist"][0]
    package_doc["package"]["bid_readiness_checklist"][0] = {
        "label": checklist_item["label"],
        "item_id": checklist_item["item_id"],
        "owner": checklist_item["owner"],
        "status": checklist_item["status"],
        "required_before": checklist_item["required_before"],
    }
    _write_json(decision_package_path, package_doc)

    with pytest.raises(
        ValueError,
        match=r"bid_readiness_checklist\[0\] fields must match the expected order",
    ):
        check_package_artifacts(out_dir)


def test_rejects_unreviewed_bid_readiness_status(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_package_path = _decision_package_path(out_dir)
    package_doc = _load_json(decision_package_path)
    package_doc["package"]["bid_readiness_checklist"][0]["status"] = "action_needed"
    _write_json(decision_package_path, package_doc)

    with pytest.raises(ValueError, match=r"bid_readiness_checklist\[0\].status"):
        check_package_artifacts(out_dir)


def test_checker_cli_returns_success_json(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    cli_run, artifact_check_cli_result = _run_checker_cli(out_dir)

    _assert_cli_completed(cli_run, exit_code=0)
    assert artifact_check_cli_result["status"] == "passed"
    assert artifact_check_cli_result["output_dir"] == str(out_dir)
    assert artifact_check_cli_result["operational_approval"] is False


def test_checker_cli_returns_failure_json_no_traceback(tmp_path: Path) -> None:
    out_dir = tmp_path / MISSING_OUTPUT_DIR_NAME

    cli_run, artifact_check_failure_result = _run_checker_cli(out_dir)

    _assert_cli_completed(cli_run, exit_code=1)
    assert artifact_check_failure_result["status"] == "failed"
    assert artifact_check_failure_result["output_dir"] == str(out_dir)
    assert artifact_check_failure_result["error_type"] == MISSING_OUTPUT_DIR_ERROR_TYPE


def test_rejects_operational_approval(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    pending_signoff_path = _pending_signoff_path(out_dir)
    pending_signoff = _load_json(pending_signoff_path)
    pending_signoff["operational_approval"] = True
    _write_json(pending_signoff_path, pending_signoff)

    with pytest.raises(ValueError, match="operational_approval"):
        check_package_artifacts(out_dir)


def test_rejects_pending_signoff_scope_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    pending_signoff_path = _pending_signoff_path(out_dir)
    pending_signoff = _load_json(pending_signoff_path)
    pending_signoff["signoff_scope"] = "operational_approval"
    _write_json(pending_signoff_path, pending_signoff)

    with pytest.raises(ValueError, match="pending_signoff.signoff_scope"):
        check_package_artifacts(out_dir)


def test_rejects_pending_signoff_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    pending_signoff_path = _pending_signoff_path(out_dir)
    pending_signoff = _load_json(pending_signoff_path)
    _write_json(
        pending_signoff_path,
        {
            "reviewer": pending_signoff["reviewer"],
            "status": pending_signoff["status"],
            "signoff_scope": pending_signoff["signoff_scope"],
            "operational_approval": pending_signoff["operational_approval"],
        },
    )

    with pytest.raises(ValueError, match="pending_signoff fields must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_signoff_summary_without_boundary(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    signoff_summary_path = _signoff_summary_path(out_dir)
    _replace_text(
        signoff_summary_path,
        "Operational approval: `false`",
        "Operational approval: `true`",
    )

    with pytest.raises(ValueError, match="signoff_summary.md missing sign-off markers"):
        check_package_artifacts(out_dir)


def test_rejects_reviewer_handoff_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    reviewer_handoff_path = _reviewer_handoff_path(out_dir)
    reviewer_handoff = _load_json(reviewer_handoff_path)
    _write_json(
        reviewer_handoff_path,
        {
            "requested_decision": reviewer_handoff["requested_decision"],
            "requested_reviewer": reviewer_handoff["requested_reviewer"],
            "review_prompt": reviewer_handoff["review_prompt"],
            "non_authorization_note": reviewer_handoff["non_authorization_note"],
        },
    )

    with pytest.raises(ValueError, match="reviewer_handoff fields must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_reviewer_handoff_without_boundary(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    reviewer_handoff_path = _reviewer_handoff_path(out_dir)
    reviewer_handoff = _load_json(reviewer_handoff_path)
    reviewer_handoff["non_authorization_note"] = "Review is complete."
    _write_json(reviewer_handoff_path, reviewer_handoff)

    with pytest.raises(ValueError, match="reviewer_handoff.non_authorization_note"):
        check_package_artifacts(out_dir)


def test_rejects_stale_reviewer_handoff(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    reviewer_handoff_path = _reviewer_handoff_path(out_dir)
    reviewer_handoff = _load_json(reviewer_handoff_path)
    reviewer_handoff["requested_reviewer"] = "alternate-reviewer"
    _write_json(reviewer_handoff_path, reviewer_handoff)

    with pytest.raises(
        ValueError,
        match="reviewer_handoff.json must match decision_package.package.reviewer_handoff",
    ):
        check_package_artifacts(out_dir)


def test_rejects_stale_operator_summary(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    validation_summary_path = _validation_summary_path(out_dir)
    validation_summary = _load_json(validation_summary_path)
    validation_summary["operator_summary"] = "Review pending."
    _write_json(validation_summary_path, validation_summary)

    with pytest.raises(ValueError, match="operator_summary"):
        check_package_artifacts(out_dir)


def test_rejects_unscoped_next_review_action(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    validation_summary_path = _validation_summary_path(out_dir)
    validation_summary = _load_json(validation_summary_path)
    validation_summary["next_review_action"] = "Approve the package."
    _write_json(validation_summary_path, validation_summary)

    with pytest.raises(ValueError, match="next_review_action"):
        check_package_artifacts(out_dir)


def test_rejects_validation_summary_order(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    validation_summary_path = _validation_summary_path(out_dir)
    validation_summary = _load_json(validation_summary_path)
    _write_json(
        validation_summary_path,
        {
            "boundary_status": validation_summary["boundary_status"],
            "schema_status": validation_summary["schema_status"],
            "operator_summary": validation_summary["operator_summary"],
            "next_review_action": validation_summary["next_review_action"],
            "unresolved_gaps": validation_summary["unresolved_gaps"],
        },
    )

    with pytest.raises(ValueError, match="validation_summary fields must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_proposal_handoff_scope_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    proposal_handoff_path = _proposal_handoff_path(out_dir)
    proposal_handoff = _load_json(proposal_handoff_path)
    proposal_handoff["handoff_scope"] = BID_SUBMISSION_ACTION
    _write_json(proposal_handoff_path, proposal_handoff)

    with pytest.raises(ValueError, match="proposal_handoff.handoff_scope"):
        check_package_artifacts(out_dir)


def test_rejects_proposal_handoff_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    proposal_handoff_path = _proposal_handoff_path(out_dir)
    proposal_handoff = _load_json(proposal_handoff_path)
    _write_json(
        proposal_handoff_path,
        {
            "source_package_id": proposal_handoff["source_package_id"],
            "handoff_scope": proposal_handoff["handoff_scope"],
            "recommendation": proposal_handoff["recommendation"],
            "drafting_status": proposal_handoff["drafting_status"],
            "required_inputs": proposal_handoff["required_inputs"],
            "blocked_until": proposal_handoff["blocked_until"],
            "allowed_next_steps": proposal_handoff["allowed_next_steps"],
            "excluded_actions": proposal_handoff["excluded_actions"],
            "non_authorization_note": proposal_handoff["non_authorization_note"],
        },
    )

    with pytest.raises(ValueError, match="proposal_handoff fields must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_proposal_next_step_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    proposal_handoff_path = _proposal_handoff_path(out_dir)
    proposal_handoff = _load_json(proposal_handoff_path)
    proposal_handoff["allowed_next_steps"].append("submit bid")
    _write_json(proposal_handoff_path, proposal_handoff)

    with pytest.raises(
        ValueError,
        match="proposal_handoff.allowed_next_steps includes unknown values: submit bid",
    ):
        check_package_artifacts(out_dir)


def test_rejects_proposal_blocked_until_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    proposal_handoff_path = _proposal_handoff_path(out_dir)
    proposal_handoff = _load_json(proposal_handoff_path)
    proposal_handoff["blocked_until"].append("extra-review")
    _write_json(proposal_handoff_path, proposal_handoff)

    with pytest.raises(
        ValueError,
        match="proposal_handoff.blocked_until must match required_inputs",
    ):
        check_package_artifacts(out_dir)


def test_rejects_audit_manifest_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    audit_manifest_path = _audit_manifest_path(out_dir)
    audit_manifest = _load_json(audit_manifest_path)
    _write_json(
        audit_manifest_path,
        {
            "packet_status": audit_manifest["packet_status"],
            "schema_purpose": audit_manifest["schema_purpose"],
            "package_id": audit_manifest["package_id"],
            "recommendation": audit_manifest["recommendation"],
            "included_artifacts": audit_manifest["included_artifacts"],
            "decision_artifacts": audit_manifest["decision_artifacts"],
            "evidence_artifacts": audit_manifest["evidence_artifacts"],
            "validation_artifacts": audit_manifest["validation_artifacts"],
            "handoff_artifacts": audit_manifest["handoff_artifacts"],
            "signoff_artifacts": audit_manifest["signoff_artifacts"],
            "excluded_actions": audit_manifest["excluded_actions"],
            "non_authorization_note": audit_manifest["non_authorization_note"],
        },
    )

    with pytest.raises(ValueError, match="audit_manifest fields must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_audit_manifest_stale_package_id(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    audit_manifest_path = _audit_manifest_path(out_dir)
    audit_manifest = _load_json(audit_manifest_path)
    audit_manifest["package_id"] = "stale-package"
    _write_json(audit_manifest_path, audit_manifest)

    with pytest.raises(ValueError, match="audit_manifest.package_id"):
        check_package_artifacts(out_dir)


def test_rejects_audit_manifest_group_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    audit_manifest_path = _audit_manifest_path(out_dir)
    audit_manifest = _load_json(audit_manifest_path)
    audit_manifest["signoff_artifacts"].remove(SIGNOFF_SUMMARY_NAME)
    _write_json(audit_manifest_path, audit_manifest)

    with pytest.raises(
        ValueError,
        match="audit_manifest.signoff_artifacts missing required values: signoff_summary.md",
    ):
        check_package_artifacts(out_dir)


def test_rejects_missing_artifact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    _export_manifest_path(out_dir).unlink()

    with pytest.raises(ValueError, match="missing package artifacts"):
        check_package_artifacts(out_dir)


def test_rejects_missing_export_artifact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    export_manifest["included_artifacts"].remove(DECISION_SUMMARY_NAME)
    _write_json(export_manifest_path, export_manifest)

    with pytest.raises(
        ValueError,
        match=(
            "export_manifest.included_artifacts missing required values: "
            f"{DECISION_SUMMARY_NAME}"
        ),
    ):
        check_package_artifacts(out_dir)


def test_rejects_duplicate_export_artifact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    export_manifest["included_artifacts"].append(DECISION_SUMMARY_NAME)
    _write_json(export_manifest_path, export_manifest)

    with pytest.raises(
        ValueError,
        match="export_manifest.included_artifacts must not contain duplicate values",
    ):
        check_package_artifacts(out_dir)


def test_rejects_unknown_export_artifact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    export_manifest["included_artifacts"].append(UNKNOWN_ARTIFACT_NAME)
    _write_json(export_manifest_path, export_manifest)

    with pytest.raises(
        ValueError,
        match=(
            "export_manifest.included_artifacts includes unknown values: "
            f"{UNKNOWN_ARTIFACT_NAME}"
        ),
    ):
        check_package_artifacts(out_dir)


def test_rejects_export_artifact_order(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    included_artifacts = export_manifest["included_artifacts"]
    included_artifacts[0], included_artifacts[1] = (
        included_artifacts[1],
        included_artifacts[0],
    )
    _write_json(export_manifest_path, export_manifest)

    with pytest.raises(
        ValueError,
        match="export_manifest.included_artifacts must match the expected order",
    ):
        check_package_artifacts(out_dir)


def test_rejects_non_string_excluded_action(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    export_manifest["excluded_actions"].append(False)
    _write_json(export_manifest_path, export_manifest)

    with pytest.raises(
        ValueError,
        match=r"export_manifest.excluded_actions\[9\] must be a non-empty string",
    ):
        check_package_artifacts(out_dir)


def test_rejects_duplicate_excluded_action(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    export_manifest["excluded_actions"].append(EXCLUDED_ACTION_ORDER[0])
    _write_json(export_manifest_path, export_manifest)

    with pytest.raises(
        ValueError,
        match="export_manifest.excluded_actions must not contain duplicate values",
    ):
        check_package_artifacts(out_dir)


def test_rejects_unknown_excluded_action(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    export_manifest["excluded_actions"].append("unreviewed_external_action")
    _write_json(export_manifest_path, export_manifest)

    with pytest.raises(
        ValueError,
        match=(
            "export_manifest.excluded_actions includes unknown values: "
            "unreviewed_external_action"
        ),
    ):
        check_package_artifacts(out_dir)


def test_rejects_excluded_action_order(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    excluded_actions = export_manifest["excluded_actions"]
    excluded_actions[0], excluded_actions[1] = (
        excluded_actions[1],
        excluded_actions[0],
    )
    _write_json(export_manifest_path, export_manifest)

    with pytest.raises(
        ValueError,
        match="export_manifest.excluded_actions must match the expected order",
    ):
        check_package_artifacts(out_dir)


def test_rejects_export_manifest_field_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    export_manifest_path = _export_manifest_path(out_dir)
    export_manifest = _load_json(export_manifest_path)
    _write_json(
        export_manifest_path,
        {
            "excluded_actions": export_manifest["excluded_actions"],
            "included_artifacts": export_manifest["included_artifacts"],
        },
    )

    with pytest.raises(
        ValueError,
        match="export_manifest fields must match the expected order",
    ):
        check_package_artifacts(out_dir)


def test_rejects_missing_source_fact(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    evidence_summary_path = _evidence_summary_path(out_dir)
    _replace_text(evidence_summary_path, "source_fact", "source fact")

    with pytest.raises(ValueError, match="missing evidence type markers: source_fact"):
        check_package_artifacts(out_dir)


def test_rejects_missing_evidence_gap(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    evidence_summary_path = _evidence_summary_path(out_dir)
    _replace_text(evidence_summary_path, "missing_evidence", "missing evidence")

    with pytest.raises(ValueError, match="missing evidence type markers: missing_evidence"):
        check_package_artifacts(out_dir)


def test_rejects_stale_demo_result_path(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["demo_result_path"] = str(_stale_demo_result_path(out_dir))
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="demo_result_path"):
        check_package_artifacts(out_dir)


def test_rejects_stale_demo_result_self_check_flag(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifact_check"]["demo_result_checked"] = False
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="demo_result_checked"):
        check_package_artifacts(out_dir)


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
        check_package_artifacts(out_dir)


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
        check_package_artifacts(out_dir)


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
        check_package_artifacts(out_dir)


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
        check_package_artifacts(out_dir)


def test_rejects_demo_result_artifact_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    artifacts = demo_result["artifacts"]
    artifacts[0], artifacts[1] = artifacts[1], artifacts[0]
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="demo_run_result.artifacts must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_artifact_inventory_mismatch(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    decision_summary_path = _decision_summary_path(out_dir)
    _append_text(decision_summary_path, "\nLocal tamper.\n")

    with pytest.raises(ValueError, match="artifact inventory sha256 mismatch"):
        check_package_artifacts(out_dir)


def test_rejects_invalid_artifact_inventory_sha256(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifact_inventory"][DECISION_SUMMARY_NAME]["sha256"] = 123
    _write_json(demo_result_path, demo_result)

    with pytest.raises(
        ValueError,
        match=f"artifact_inventory.{DECISION_SUMMARY_NAME}.sha256",
    ):
        check_package_artifacts(out_dir)


def test_rejects_non_hex_artifact_inventory_sha256(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifact_inventory"][DECISION_SUMMARY_NAME]["sha256"] = "z" * 64
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="sha256 must be a 64-character hex string"):
        check_package_artifacts(out_dir)


def test_rejects_invalid_artifact_inventory_size(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifact_inventory"][DECISION_SUMMARY_NAME]["size_bytes"] = "large"
    _write_json(demo_result_path, demo_result)

    with pytest.raises(
        ValueError,
        match=f"artifact_inventory.{DECISION_SUMMARY_NAME}.size_bytes",
    ):
        check_package_artifacts(out_dir)


def test_rejects_bool_artifact_inventory_size(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifact_inventory"][DECISION_SUMMARY_NAME]["size_bytes"] = True
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="size_bytes must be a non-negative integer"):
        check_package_artifacts(out_dir)


def test_rejects_unknown_artifact_inventory_key(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifact_inventory"][UNKNOWN_ARTIFACT_NAME] = {
        "sha256": STALE_SHA256,
        "size_bytes": 0,
    }
    _write_json(demo_result_path, demo_result)

    with pytest.raises(
        ValueError,
        match=f"artifact_inventory includes unknown artifacts: {UNKNOWN_ARTIFACT_NAME}",
    ):
        check_package_artifacts(out_dir)


def test_rejects_missing_artifact_inventory_key(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["artifact_inventory"].pop(DECISION_SUMMARY_NAME)
    _write_json(demo_result_path, demo_result)

    with pytest.raises(
        ValueError,
        match=f"artifact_inventory missing artifacts: {DECISION_SUMMARY_NAME}",
    ):
        check_package_artifacts(out_dir)


def test_rejects_artifact_inventory_key_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    artifact_inventory = demo_result["artifact_inventory"]
    reordered_artifacts = list(INCLUDED_ARTIFACT_ORDER)
    reordered_artifacts[0], reordered_artifacts[1] = reordered_artifacts[1], reordered_artifacts[0]
    demo_result["artifact_inventory"] = {
        artifact_name: artifact_inventory[artifact_name]
        for artifact_name in reordered_artifacts
    }
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="artifact_inventory must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_stale_demo_receipt_path(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result_path = _demo_result_path(out_dir)
    demo_result = _load_json(demo_result_path)
    demo_result["demo_receipt_path"] = str(_stale_demo_receipt_path(out_dir))
    _write_json(demo_result_path, demo_result)

    with pytest.raises(ValueError, match="demo_receipt_path"):
        check_package_artifacts(out_dir)


def test_rejects_demo_receipt_missing_boundary(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    receipt_path = _demo_receipt_path(out_dir)
    _replace_text(receipt_path, NON_AUTHORIZATION_MARKER, "omits boundary")

    with pytest.raises(ValueError, match="demo evidence receipt missing markers"):
        check_package_artifacts(out_dir)


def test_rejects_stale_receipt_summary(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    validation_summary = _load_json(_validation_summary_path(out_dir))
    receipt_path = _demo_receipt_path(out_dir)
    _replace_text(receipt_path, validation_summary["operator_summary"], "Stale validation summary.")

    with pytest.raises(ValueError, match="validation summary field: operator_summary"):
        check_package_artifacts(out_dir)


def test_rejects_missing_receipt_inventory_row(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    receipt_path = _demo_receipt_path(out_dir)
    _replace_text(receipt_path, DECISION_PACKAGE_NAME, "decision package json")

    with pytest.raises(
        ValueError,
        match=f"missing artifact inventory row: {DECISION_PACKAGE_NAME}",
    ):
        check_package_artifacts(out_dir)


def test_rejects_receipt_row_order_drift(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result = _load_json(_demo_result_path(out_dir))
    expected_artifacts = list(demo_result["artifact_inventory"])
    receipt_path = _demo_receipt_path(out_dir)
    receipt_lines = _read_text(receipt_path).splitlines()
    table_start = receipt_lines.index("| Artifact | Size bytes | SHA256 |") + 2
    receipt_lines[table_start], receipt_lines[table_start + 1] = (
        receipt_lines[table_start + 1],
        receipt_lines[table_start],
    )
    _write_text(receipt_path, "\n".join(receipt_lines))

    assert expected_artifacts[:2] == [DECISION_PACKAGE_NAME, PROCUREMENT_REVIEW_NAME]
    with pytest.raises(ValueError, match="artifact inventory rows must match the expected order"):
        check_package_artifacts(out_dir)


def test_rejects_stale_receipt_fingerprint(tmp_path: Path) -> None:
    out_dir = _run_seeded_demo(tmp_path)
    demo_result = _load_json(_demo_result_path(out_dir))
    decision_summary_sha = demo_result["artifact_inventory"][DECISION_SUMMARY_NAME]["sha256"]
    receipt_path = _demo_receipt_path(out_dir)
    _replace_text(receipt_path, decision_summary_sha, STALE_SHA256)

    with pytest.raises(
        ValueError,
        match=f"missing artifact inventory row: {DECISION_SUMMARY_NAME}",
    ):
        check_package_artifacts(out_dir)
