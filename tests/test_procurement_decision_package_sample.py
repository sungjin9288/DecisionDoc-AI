from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_CASE_SCRIPTS,
    DECISION_PACKAGE_NAME,
    DEMO_RECOMMENDATION,
    EXCLUDED_ACTION_ORDER,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    LOCAL_DEMO_EXPECTED_PACKAGE_PATH,
    LOCAL_DEMO_SCENARIO_ID,
    LOCAL_DEMO_SAMPLE_INPUT_PATH,
    PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
    PROPOSAL_HANDOFF_NAME,
    load_json,
    validate_expected_package,
    validate_sample_input,
    validate_sample_pair,
)


JsonObject = dict[str, object]
ValidatorCliRun = tuple[subprocess.CompletedProcess[str], JsonObject]

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_INPUT_NAME = LOCAL_DEMO_SAMPLE_INPUT_PATH.name
EXPECTED_PACKAGE_NAME = LOCAL_DEMO_EXPECTED_PACKAGE_PATH.name
SAMPLE_INPUT_PATH = ROOT / LOCAL_DEMO_SAMPLE_INPUT_PATH
EXPECTED_PACKAGE_PATH = ROOT / LOCAL_DEMO_EXPECTED_PACKAGE_PATH
VALIDATOR_SCRIPT_PATH = ROOT / CLI_CONTRACT_MANIFEST_CASE_SCRIPTS["sample_validator"]
UNKNOWN_ARTIFACT_NAME = "unreviewed_artifact.json"
MISSING_SAMPLE_INPUT_NAME = "missing_sample_input.json"
MISSING_SAMPLE_INPUT_ERROR_TYPE = "FileNotFoundError"


def _copy_text(source: Path, destination: Path) -> None:
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _sample_input_path(base_dir: Path) -> Path:
    return base_dir / SAMPLE_INPUT_NAME


def _expected_package_path(base_dir: Path) -> Path:
    return base_dir / EXPECTED_PACKAGE_NAME


def _sample_input() -> JsonObject:
    return load_json(SAMPLE_INPUT_PATH)


def _expected_package() -> JsonObject:
    return load_json(EXPECTED_PACKAGE_PATH)


def _sample_pair() -> tuple[JsonObject, JsonObject]:
    return _sample_input(), _expected_package()


def _mutable_expected_package_pair() -> tuple[JsonObject, JsonObject]:
    sample_input, expected_package = _sample_pair()
    return sample_input, copy.deepcopy(expected_package)


def _load_stdout_json(cli_run: subprocess.CompletedProcess[str]) -> JsonObject:
    return json.loads(cli_run.stdout)


def _run_validator_cli(*args: str) -> ValidatorCliRun:
    cli_run = subprocess.run(
        [sys.executable, str(VALIDATOR_SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return cli_run, _load_stdout_json(cli_run)


def _assert_cli_completed(
    cli_run: subprocess.CompletedProcess[str],
    *,
    exit_code: int,
    context: object,
) -> None:
    assert cli_run.returncode == exit_code, context
    assert cli_run.stderr == "", context


def _assert_success_sample_validation(sample_validation_result: JsonObject) -> None:
    assert (
        sample_validation_result["schema_purpose"]
        == PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE
    )
    assert sample_validation_result["status"] == "passed"
    assert sample_validation_result["scenario_id"] == LOCAL_DEMO_SCENARIO_ID
    assert sample_validation_result["recommendation"] == DEMO_RECOMMENDATION
    assert sample_validation_result["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY


def _assert_failure_sample_validation(
    sample_validation_result: JsonObject,
    *,
    sample_input_path: Path,
    error_type: str,
) -> None:
    assert (
        sample_validation_result["schema_purpose"]
        == PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE
    )
    assert sample_validation_result["status"] == "failed"
    assert sample_validation_result["sample_input"] == str(sample_input_path)
    assert sample_validation_result["expected_package"] == str(EXPECTED_PACKAGE_PATH)
    assert sample_validation_result["error_type"] == error_type
    assert sample_validation_result["error"]


def test_validate_sample_pair_accepts_local_demo_fixture() -> None:
    sample_validation_result = validate_sample_pair(
        sample_input_path=SAMPLE_INPUT_PATH,
        expected_package_path=EXPECTED_PACKAGE_PATH,
        display_base_dir=ROOT,
    )

    _assert_success_sample_validation(sample_validation_result)


def test_validate_sample_pair_accepts_fixture_copies_outside_repo(tmp_path: Path) -> None:
    sample_input_path = _sample_input_path(tmp_path)
    expected_package_path = _expected_package_path(tmp_path)
    _copy_text(SAMPLE_INPUT_PATH, sample_input_path)
    _copy_text(EXPECTED_PACKAGE_PATH, expected_package_path)

    sample_validation_result = validate_sample_pair(
        sample_input_path=sample_input_path,
        expected_package_path=expected_package_path,
        display_base_dir=ROOT,
    )

    assert sample_validation_result["status"] == "passed"
    assert sample_validation_result["sample_input"] == str(sample_input_path)
    assert sample_validation_result["expected_package"] == str(expected_package_path)


def test_validate_expected_package_rejects_missing_authorization_boundary() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    excluded_actions = broken_package["package"]["export_manifest"]["excluded_actions"]
    excluded_actions.remove(EXCLUDED_ACTION_ORDER[0])

    with pytest.raises(ValueError, match=EXCLUDED_ACTION_ORDER[0]):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_top_level_field_order_drift() -> None:
    sample_input, expected_package = _sample_pair()
    broken_package = {
        "schema_purpose": expected_package["schema_purpose"],
        "scenario_id": expected_package["scenario_id"],
        "updated_at": expected_package["updated_at"],
        "package": expected_package["package"],
    }

    with pytest.raises(ValueError, match="expected_package fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_updated_at_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["updated_at"] = "2026-06-24"

    with pytest.raises(ValueError, match="updated_at must match"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_package_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    package_section = broken_package["package"]
    broken_package["package"] = {
        "recommendation": package_section["recommendation"],
        "package_id": package_section["package_id"],
        "recommendation_reason": package_section["recommendation_reason"],
        "opportunity_ref": package_section["opportunity_ref"],
        "hard_filters": package_section["hard_filters"],
        "soft_fit_score": package_section["soft_fit_score"],
        "evidence_summary": package_section["evidence_summary"],
        "bid_readiness_checklist": package_section["bid_readiness_checklist"],
        "validation_summary": package_section["validation_summary"],
        "reviewer_handoff": package_section["reviewer_handoff"],
        "proposal_handoff": package_section["proposal_handoff"],
        "pending_signoff": package_section["pending_signoff"],
        "audit_manifest": package_section["audit_manifest"],
        "export_manifest": package_section["export_manifest"],
    }

    with pytest.raises(
        ValueError,
        match="expected_package.package fields must match the expected order",
    ):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_opportunity_ref_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    opportunity_ref = broken_package["package"]["opportunity_ref"]
    broken_package["package"]["opportunity_ref"] = {
        "title": opportunity_ref["title"],
        "opportunity_id": opportunity_ref["opportunity_id"],
        "source_type": opportunity_ref["source_type"],
    }

    with pytest.raises(ValueError, match="opportunity_ref fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_opportunity_ref_title_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["opportunity_ref"]["title"] = "Stale opportunity title"

    with pytest.raises(ValueError, match="opportunity_ref.title must match sample input"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_opportunity_ref_source_type_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["opportunity_ref"]["source_type"] = "stale_source"

    with pytest.raises(ValueError, match="opportunity_ref.source_type must match sample input"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_hard_filter_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    hard_filter = broken_package["package"]["hard_filters"][0]
    broken_package["package"]["hard_filters"][0] = {
        "status": hard_filter["status"],
        "filter_id": hard_filter["filter_id"],
        "reason": hard_filter["reason"],
    }

    with pytest.raises(ValueError, match=r"hard_filters\[0\] fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_unreviewed_hard_filter_status() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["hard_filters"][0]["status"] = "approved"

    with pytest.raises(ValueError, match=r"hard_filters\[0\].status"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_soft_fit_factor_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    factor = broken_package["package"]["soft_fit_score"]["factors"][0]
    broken_package["package"]["soft_fit_score"]["factors"][0] = {
        "score": factor["score"],
        "name": factor["name"],
        "evidence_ids": factor["evidence_ids"],
    }

    with pytest.raises(
        ValueError,
        match=r"soft_fit_score.factors\[0\] fields must match the expected order",
    ):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_bool_soft_fit_score() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["soft_fit_score"]["score"] = True

    with pytest.raises(ValueError, match="soft_fit_score.score must be an integer from 0 to 100"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_evidence_summary_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    evidence = broken_package["package"]["evidence_summary"][0]
    broken_package["package"]["evidence_summary"][0] = {
        "type": evidence["type"],
        "evidence_id": evidence["evidence_id"],
        "source": evidence["source"],
        "summary": evidence["summary"],
    }

    with pytest.raises(
        ValueError,
        match=r"evidence_summary\[0\] fields must match the expected order",
    ):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_bid_readiness_checklist_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    checklist_item = broken_package["package"]["bid_readiness_checklist"][0]
    broken_package["package"]["bid_readiness_checklist"][0] = {
        "label": checklist_item["label"],
        "item_id": checklist_item["item_id"],
        "owner": checklist_item["owner"],
        "status": checklist_item["status"],
        "required_before": checklist_item["required_before"],
    }

    with pytest.raises(
        ValueError,
        match=r"bid_readiness_checklist\[0\] fields must match the expected order",
    ):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_unreviewed_bid_readiness_status() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["bid_readiness_checklist"][0]["status"] = "action_needed"

    with pytest.raises(ValueError, match=r"bid_readiness_checklist\[0\].status"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_sample_input_rejects_non_string_required_capability() -> None:
    sample_input = _sample_input()
    broken_input = copy.deepcopy(sample_input)
    broken_input["opportunity"]["required_capabilities"].append(False)

    with pytest.raises(ValueError, match=r"required_capabilities\[4\] must be a non-empty string"):
        validate_sample_input(broken_input)


def test_validate_expected_package_rejects_non_string_excluded_action() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["export_manifest"]["excluded_actions"].append(False)

    with pytest.raises(ValueError, match=r"excluded_actions\[9\] must be a non-empty string"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_duplicate_included_artifact() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["export_manifest"]["included_artifacts"].append(DECISION_PACKAGE_NAME)

    with pytest.raises(ValueError, match="included_artifacts must not contain duplicate values"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_unknown_included_artifact() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["export_manifest"]["included_artifacts"].append(UNKNOWN_ARTIFACT_NAME)

    with pytest.raises(
        ValueError,
        match=f"included_artifacts includes unknown values: {UNKNOWN_ARTIFACT_NAME}",
    ):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_included_artifact_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    included_artifacts = broken_package["package"]["export_manifest"]["included_artifacts"]
    included_artifacts[0], included_artifacts[1] = included_artifacts[1], included_artifacts[0]

    with pytest.raises(ValueError, match="included_artifacts must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_duplicate_excluded_action() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    excluded_actions = broken_package["package"]["export_manifest"]["excluded_actions"]
    excluded_actions.append(EXCLUDED_ACTION_ORDER[0])

    with pytest.raises(ValueError, match="excluded_actions must not contain duplicate values"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_unknown_excluded_action() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    excluded_actions = broken_package["package"]["export_manifest"]["excluded_actions"]
    excluded_actions.append("unreviewed_runtime_action")

    with pytest.raises(
        ValueError,
        match="excluded_actions includes unknown values: unreviewed_runtime_action",
    ):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_excluded_action_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    excluded_actions = broken_package["package"]["export_manifest"]["excluded_actions"]
    excluded_actions[0], excluded_actions[1] = excluded_actions[1], excluded_actions[0]

    with pytest.raises(ValueError, match="excluded_actions must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_export_manifest_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    export_manifest = broken_package["package"]["export_manifest"]
    broken_package["package"]["export_manifest"] = {
        "excluded_actions": export_manifest["excluded_actions"],
        "included_artifacts": export_manifest["included_artifacts"],
    }

    with pytest.raises(ValueError, match="export_manifest fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_operational_approval() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["pending_signoff"]["operational_approval"] = True

    with pytest.raises(ValueError, match="operational_approval"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_pending_signoff_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    pending_signoff = broken_package["package"]["pending_signoff"]
    broken_package["package"]["pending_signoff"] = {
        "reviewer": pending_signoff["reviewer"],
        "status": pending_signoff["status"],
        "signoff_scope": pending_signoff["signoff_scope"],
        "operational_approval": pending_signoff["operational_approval"],
    }

    with pytest.raises(ValueError, match="pending_signoff fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_missing_operator_summary() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["validation_summary"].pop("operator_summary")

    with pytest.raises(ValueError, match="operator_summary"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_unscoped_next_review_action() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["validation_summary"]["next_review_action"] = "Ask for approval."

    with pytest.raises(ValueError, match="next_review_action"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_validation_summary_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    validation_summary = broken_package["package"]["validation_summary"]
    broken_package["package"]["validation_summary"] = {
        "boundary_status": validation_summary["boundary_status"],
        "schema_status": validation_summary["schema_status"],
        "operator_summary": validation_summary["operator_summary"],
        "next_review_action": validation_summary["next_review_action"],
        "unresolved_gaps": validation_summary["unresolved_gaps"],
    }

    with pytest.raises(ValueError, match="validation_summary fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_reviewer_handoff_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    reviewer_handoff = broken_package["package"]["reviewer_handoff"]
    broken_package["package"]["reviewer_handoff"] = {
        "requested_decision": reviewer_handoff["requested_decision"],
        "requested_reviewer": reviewer_handoff["requested_reviewer"],
        "review_prompt": reviewer_handoff["review_prompt"],
        "non_authorization_note": reviewer_handoff["non_authorization_note"],
    }

    with pytest.raises(ValueError, match="reviewer_handoff fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_empty_reviewer_handoff_prompt() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["reviewer_handoff"]["review_prompt"] = ""

    with pytest.raises(ValueError, match="reviewer_handoff.review_prompt"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_missing_proposal_handoff() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"].pop("proposal_handoff")

    with pytest.raises(ValueError, match="proposal_handoff"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_proposal_handoff_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    proposal_handoff = broken_package["package"]["proposal_handoff"]
    broken_package["package"]["proposal_handoff"] = {
        "source_package_id": proposal_handoff["source_package_id"],
        "handoff_scope": proposal_handoff["handoff_scope"],
        "recommendation": proposal_handoff["recommendation"],
        "drafting_status": proposal_handoff["drafting_status"],
        "required_inputs": proposal_handoff["required_inputs"],
        "blocked_until": proposal_handoff["blocked_until"],
        "allowed_next_steps": proposal_handoff["allowed_next_steps"],
        "excluded_actions": proposal_handoff["excluded_actions"],
        "non_authorization_note": proposal_handoff["non_authorization_note"],
    }

    with pytest.raises(ValueError, match="proposal_handoff fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_proposal_handoff_allowed_next_step_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["proposal_handoff"]["allowed_next_steps"].append("submit bid")

    with pytest.raises(ValueError, match="allowed_next_steps includes unknown values"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_proposal_handoff_blocked_until_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["proposal_handoff"]["blocked_until"].append("extra-review")

    with pytest.raises(ValueError, match="blocked_until must match required_inputs"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_missing_audit_manifest() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"].pop("audit_manifest")

    with pytest.raises(ValueError, match="audit_manifest"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_audit_manifest_field_order_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    audit_manifest = broken_package["package"]["audit_manifest"]
    broken_package["package"]["audit_manifest"] = {
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
    }

    with pytest.raises(ValueError, match="audit_manifest fields must match the expected order"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_expected_package_rejects_audit_manifest_group_drift() -> None:
    sample_input, broken_package = _mutable_expected_package_pair()
    broken_package["package"]["audit_manifest"]["handoff_artifacts"].remove(PROPOSAL_HANDOFF_NAME)

    with pytest.raises(ValueError, match="audit_manifest.handoff_artifacts"):
        validate_expected_package(broken_package, sample_input=sample_input)


def test_validate_sample_cli_returns_success_json() -> None:
    cli_run, sample_validation_result = _run_validator_cli()

    _assert_cli_completed(cli_run, exit_code=0, context=sample_validation_result)
    _assert_success_sample_validation(sample_validation_result)


def test_validate_sample_cli_returns_failure_json_no_traceback(tmp_path: Path) -> None:
    sample_input_path = tmp_path / MISSING_SAMPLE_INPUT_NAME

    cli_run, sample_validation_failure = _run_validator_cli(
        "--sample-input",
        str(sample_input_path),
    )

    _assert_cli_completed(cli_run, exit_code=1, context=sample_validation_failure)
    _assert_failure_sample_validation(
        sample_validation_failure,
        sample_input_path=sample_input_path,
        error_type=MISSING_SAMPLE_INPUT_ERROR_TYPE,
    )
