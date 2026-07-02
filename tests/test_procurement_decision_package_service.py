from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)
from app.services.procurement_decision_package_service import (
    AUDIT_MANIFEST_ARTIFACT_GROUPS,
    AUDIT_MANIFEST_FIELD_ORDER,
    AUDIT_MANIFEST_NAME,
    AUDIT_MANIFEST_PACKET_STATUS,
    AUDIT_MANIFEST_SCHEMA_PURPOSE,
    ARTIFACT_INVENTORY_TABLE_HEADER,
    BID_READINESS_CHECKLIST_FIELD_ORDER,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FAILURE_FIELDS,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
    CLI_CONTRACT_MANIFEST_VALIDATION_FAILURE_FIELDS,
    CLI_CONTRACT_MANIFEST_CONTRACT_VERSION,
    CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE,
    CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
    CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE,
    DECISION_PACKAGE_NAME,
    DECISION_PACKAGE_FIELD_ORDER,
    DECISION_PACKAGE_TOP_LEVEL_FIELD_ORDER,
    DECISION_SUMMARY_NAME,
    DEMO_RECEIPT_NAME,
    DEMO_RESULT_NAME,
    DEMO_PROJECT_ID,
    DEMO_TENANT_ID,
    EVIDENCE_SUMMARY_NAME,
    EVIDENCE_SUMMARY_FIELD_ORDER,
    EXCLUDED_ACTION_ORDER,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    EXPORT_MANIFEST_FIELD_ORDER,
    EXPORT_MANIFEST_NAME,
    EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE,
    GATE_NAME,
    HARD_FILTER_FIELD_ORDER,
    INCLUDED_ARTIFACT_ORDER,
    JSON_ARTIFACT_PACKAGE_FIELDS,
    DEMO_RECOMMENDATION,
    LOCAL_DEMO_EXPECTED_PACKAGE_PATH,
    LOCAL_DEMO_SCENARIO_ID,
    LOCAL_DEMO_SAMPLE_INPUT_PATH,
    NON_APPROVAL_MARKER,
    NON_AUTHORIZATION_NOTE,
    NON_AUTHORIZATION_MARKER,
    OPPORTUNITY_REF_FIELD_ORDER,
    PENDING_SIGNOFF_NAME,
    PENDING_SIGNOFF_FIELD_ORDER,
    PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    PROPOSAL_ALLOWED_NEXT_STEPS,
    PROPOSAL_HANDOFF_FIELD_ORDER,
    PROPOSAL_HANDOFF_SCOPE,
    PROPOSAL_HANDOFF_NAME,
    REVIEWER_HANDOFF_FIELD_ORDER,
    REVIEWER_HANDOFF_NAME,
    SCOPED_REVIEW_MARKER,
    SIGNOFF_SCOPE,
    SIGNOFF_SUMMARY_REQUIRED_MARKERS,
    SIGNOFF_SUMMARY_NAME,
    SMOKE_CHECK_NAME,
    SMOKE_NAME,
    SOFT_FIT_FACTOR_FIELD_ORDER,
    SOFT_FIT_SCORE_FIELD_ORDER,
    VALIDATION_SUMMARY_FIELD_ORDER,
    VALIDATION_SUMMARY_NAME,
    build_audit_manifest,
    build_artifact_inventory,
    build_artifact_inventory_rows,
    build_cli_contract_manifest_validation_failure_result,
    build_cli_contract_manifest_validation_check_failure_result,
    build_demo_run_failure_result,
    build_demo_run_result,
    build_export_package_failure_result,
    build_gate_failure_result,
    build_package_artifact_check_failure_result,
    build_package_artifact_check_result,
    build_decision_package,
    build_decision_package_from_record,
    build_export_manifest,
    build_pending_signoff,
    build_proposal_handoff,
    build_reviewer_handoff,
    build_sample_builder_failure_result,
    build_sample_validation_failure_result,
    build_smoke_failure_result,
    build_smoke_check_failure_result,
    load_json,
    render_demo_evidence_receipt,
    seed_demo_decision_record,
    validate_demo_input,
    validate_artifact_inventory_matches_files,
    validate_artifact_list,
    validate_demo_evidence_receipt_file,
    validate_demo_evidence_receipt_text,
    validate_demo_evidence_files,
    validate_demo_run_result,
    validate_evidence_summary_text,
    validate_json_artifact_matches_package,
    validate_local_package_artifacts,
    validate_markdown_artifact_files,
    validate_package_document,
    validate_package_artifact_files,
    validate_package_document_for_path,
    validate_package_section_for_path,
    validate_expected_package_for_sample,
    validate_sample_pair,
    write_json_atomic,
    write_demo_evidence_state,
    write_validated_demo_evidence,
    write_package_artifacts,
    write_text_atomic,
)
from app.storage.procurement_store import ProcurementDecisionStore


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_INPUT_PATH = ROOT / LOCAL_DEMO_SAMPLE_INPUT_PATH
EXPECTED_PACKAGE_PATH = ROOT / LOCAL_DEMO_EXPECTED_PACKAGE_PATH
UNKNOWN_ARTIFACT_NAME = "unreviewed_artifact.json"
MISSING_SAMPLE_INPUT_NAME = "missing_sample_input.json"
MISSING_EXPECTED_PACKAGE_NAME = "expected_decision_package.json"
DEMO_DATA_DIR_NAME = "data"
DEMO_OUTPUT_DIR_NAME = "out"
FIXTURE_TENANT_ID = "tenant-a"
FIXTURE_PROJECT_ID = "project-a"
FIXTURE_REVIEWER = "reviewer-a"
DEMO_FIXTURE_TENANT_ID = "demo-tenant"
DEMO_FIXTURE_PROJECT_ID = "demo-project"
HELPER_PACKAGE_ID = "package-a"
STALE_PACKAGE_ID = "stale-package"
CUSTOM_GATE_RESULT_DIR_NAME = "gate"
CUSTOM_SMOKE_RESULT_DIR_NAME = "smoke"
CUSTOM_CHECK_RESULT_DIR_NAME = "checks"
FAILED_RESULT_NAME = "failed.json"
MISSING_SMOKE_RESULT_NAME = "missing_smoke_result.json"
MISSING_OUTPUT_DIR_NAME = "missing-out"
MISSING_VALIDATION_RESULT_NAME = "missing_validation_result.json"
MISSING_MANIFEST_NAME = "missing_manifest.json"
STALE_DEMO_RECEIPT_NAME = "other.md"
STALE_OUTPUT_DIR_NAME = "other"
ATOMIC_WRITE_DIR_NAME = "nested"
ATOMIC_JSON_RESULT_NAME = "result.json"
ATOMIC_TEXT_RECEIPT_NAME = "receipt.md"
PACKAGE_OUTPUT_DIR_NAME = "package"
STALE_ARTIFACT_NAME = "stale_artifact.txt"
STALE_ARTIFACT_TEXT = "stale\n"


def _read_artifact_json(output_dir: Path, artifact_name: str) -> dict[str, object]:
    return _read_json(output_dir / artifact_name)


def _read_artifact_text(output_dir: Path, artifact_name: str) -> str:
    return _read_text(output_dir / artifact_name)


def _artifact_path(output_dir: Path, artifact_name: str) -> Path:
    return output_dir / artifact_name


def _decision_package_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, DECISION_PACKAGE_NAME)


def _decision_summary_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, DECISION_SUMMARY_NAME)


def _evidence_summary_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, EVIDENCE_SUMMARY_NAME)


def _signoff_summary_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, SIGNOFF_SUMMARY_NAME)


def _reviewer_handoff_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, REVIEWER_HANDOFF_NAME)


def _export_manifest_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, EXPORT_MANIFEST_NAME)


def _demo_result_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, DEMO_RESULT_NAME)


def _demo_receipt_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, DEMO_RECEIPT_NAME)


def _demo_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / DEMO_DATA_DIR_NAME, tmp_path / DEMO_OUTPUT_DIR_NAME


def _custom_gate_result_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / CUSTOM_GATE_RESULT_DIR_NAME / file_name


def _custom_smoke_result_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / CUSTOM_SMOKE_RESULT_DIR_NAME / file_name


def _custom_smoke_check_result_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / CUSTOM_CHECK_RESULT_DIR_NAME / file_name


def _atomic_write_path(tmp_path: Path, file_name: str) -> Path:
    return tmp_path / ATOMIC_WRITE_DIR_NAME / file_name


def _package_output_dir(tmp_path: Path) -> Path:
    return tmp_path / PACKAGE_OUTPUT_DIR_NAME


def _validation_summary_path(output_dir: Path) -> Path:
    return _artifact_path(output_dir, VALIDATION_SUMMARY_NAME)


def _read_json(path: Path) -> dict[str, object]:
    return json.loads(_read_text(path))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def _write_artifact_placeholders(
    output_dir: Path,
    *,
    missing_artifact: str | None = None,
    content: str | None = None,
) -> None:
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        if artifact_name == missing_artifact:
            continue
        placeholder = content if content is not None else f"{artifact_name}\n"
        _write_text(output_dir / artifact_name, placeholder)


def _review_only_validation_summary() -> dict[str, str]:
    return {
        "operator_summary": f"This package is {NON_APPROVAL_MARKER}.",
        "next_review_action": f"Review {SCOPED_REVIEW_MARKER}.",
    }


def test_build_decision_package_matches_expected_fixture() -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    expected_package = load_json(EXPECTED_PACKAGE_PATH)

    decision_package = build_decision_package(sample_input)

    assert decision_package == expected_package
    assert list(decision_package) == DECISION_PACKAGE_TOP_LEVEL_FIELD_ORDER
    assert list(decision_package["package"]) == DECISION_PACKAGE_FIELD_ORDER
    assert list(decision_package["package"]["opportunity_ref"]) == OPPORTUNITY_REF_FIELD_ORDER
    assert all(
        list(hard_filter) == HARD_FILTER_FIELD_ORDER
        for hard_filter in decision_package["package"]["hard_filters"]
    )
    assert list(decision_package["package"]["soft_fit_score"]) == SOFT_FIT_SCORE_FIELD_ORDER
    assert all(
        list(soft_fit_factor) == SOFT_FIT_FACTOR_FIELD_ORDER
        for soft_fit_factor in decision_package["package"]["soft_fit_score"]["factors"]
    )
    assert all(
        list(evidence_summary) == EVIDENCE_SUMMARY_FIELD_ORDER
        for evidence_summary in decision_package["package"]["evidence_summary"]
    )
    assert all(
        list(checklist_item) == BID_READINESS_CHECKLIST_FIELD_ORDER
        for checklist_item in decision_package["package"]["bid_readiness_checklist"]
    )


def test_validate_sample_pair_preserves_success_contract_and_display_paths() -> None:
    sample_validation_result = validate_sample_pair(
        sample_input_path=SAMPLE_INPUT_PATH,
        expected_package_path=EXPECTED_PACKAGE_PATH,
        display_base_dir=ROOT,
    )

    assert sample_validation_result == {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
        "status": "passed",
        "sample_input": str(LOCAL_DEMO_SAMPLE_INPUT_PATH),
        "expected_package": str(LOCAL_DEMO_EXPECTED_PACKAGE_PATH),
        "scenario_id": LOCAL_DEMO_SCENARIO_ID,
        "recommendation": DEMO_RECOMMENDATION,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
    }


def test_seed_demo_decision_record_persists_package_ready_fixture(tmp_path: Path) -> None:
    decision_id = seed_demo_decision_record(data_dir=tmp_path)

    record = ProcurementDecisionStore(base_dir=str(tmp_path)).get(
        DEMO_PROJECT_ID,
        tenant_id=DEMO_TENANT_ID,
    )
    assert record is not None
    assert record.decision_id == decision_id
    assert record.tenant_id == DEMO_TENANT_ID
    assert record.project_id == DEMO_PROJECT_ID
    assert record.recommendation is not None
    assert record.recommendation.value.value == DEMO_RECOMMENDATION
    assert record.opportunity is not None
    assert record.opportunity.source_kind == "local_demo"
    assert record.missing_data == [
        "security plan owner",
        "operator training staffing owner",
    ]

    package = build_decision_package_from_record(record)

    assert package["schema_purpose"] == PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert package["package"]["recommendation"] == DEMO_RECOMMENDATION
    assert package["package"]["pending_signoff"]["operational_approval"] is False
    assert package["package"]["export_manifest"]["excluded_actions"] == EXCLUDED_ACTION_ORDER


def test_write_package_artifacts_creates_reviewable_local_package(tmp_path: Path) -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    stale_file = tmp_path / STALE_ARTIFACT_NAME
    _write_text(stale_file, STALE_ARTIFACT_TEXT)

    package_artifacts = write_package_artifacts(package_doc, tmp_path)

    assert package_artifacts["schema_purpose"] == EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE
    assert package_artifacts["recommendation"] == DEMO_RECOMMENDATION
    assert package_artifacts["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY
    assert package_artifacts["artifacts"] == INCLUDED_ARTIFACT_ORDER
    assert stale_file.exists()
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        assert (tmp_path / artifact_name).exists(), artifact_name

    decision_summary = _read_artifact_text(tmp_path, DECISION_SUMMARY_NAME)
    pending_signoff = _read_artifact_json(tmp_path, PENDING_SIGNOFF_NAME)
    reviewer_handoff = _read_artifact_json(tmp_path, REVIEWER_HANDOFF_NAME)
    proposal_handoff = _read_artifact_json(tmp_path, PROPOSAL_HANDOFF_NAME)
    validation_summary = _read_artifact_json(tmp_path, VALIDATION_SUMMARY_NAME)
    signoff_summary = _read_artifact_text(tmp_path, SIGNOFF_SUMMARY_NAME)
    audit_manifest = _read_artifact_json(tmp_path, AUDIT_MANIFEST_NAME)
    export_manifest = _read_artifact_json(tmp_path, EXPORT_MANIFEST_NAME)

    for artifact_name, package_field in JSON_ARTIFACT_PACKAGE_FIELDS.items():
        artifact = _read_artifact_json(tmp_path, artifact_name)
        assert artifact == package_doc["package"][package_field]

    assert NON_AUTHORIZATION_MARKER in decision_summary
    assert list(reviewer_handoff) == REVIEWER_HANDOFF_FIELD_ORDER
    assert reviewer_handoff["non_authorization_note"] == NON_AUTHORIZATION_NOTE
    assert proposal_handoff["handoff_scope"] == PROPOSAL_HANDOFF_SCOPE
    assert proposal_handoff["source_package_id"] == package_doc["package"]["package_id"]
    assert proposal_handoff["excluded_actions"] == EXCLUDED_ACTION_ORDER
    assert list(pending_signoff) == PENDING_SIGNOFF_FIELD_ORDER
    assert pending_signoff["operational_approval"] is False
    assert pending_signoff["signoff_scope"] == SIGNOFF_SCOPE
    for marker in SIGNOFF_SUMMARY_REQUIRED_MARKERS:
        assert marker in signoff_summary
    assert list(audit_manifest) == AUDIT_MANIFEST_FIELD_ORDER
    assert audit_manifest["package_id"] == package_doc["package"]["package_id"]
    assert audit_manifest["recommendation"] == package_doc["package"]["recommendation"]
    assert audit_manifest["included_artifacts"] == INCLUDED_ARTIFACT_ORDER
    assert audit_manifest["excluded_actions"] == EXCLUDED_ACTION_ORDER
    assert list(export_manifest) == EXPORT_MANIFEST_FIELD_ORDER
    assert list(validation_summary) == VALIDATION_SUMMARY_FIELD_ORDER
    assert NON_APPROVAL_MARKER in validation_summary["operator_summary"]
    assert SCOPED_REVIEW_MARKER in validation_summary["next_review_action"]
    assert export_manifest["included_artifacts"] == INCLUDED_ARTIFACT_ORDER
    assert export_manifest["excluded_actions"] == EXCLUDED_ACTION_ORDER


def test_json_artifact_package_fields_follow_artifact_order() -> None:
    expected_json_artifacts = [
        artifact_name
        for artifact_name in INCLUDED_ARTIFACT_ORDER
        if artifact_name.endswith(".json") and artifact_name != DECISION_PACKAGE_NAME
    ]

    assert list(JSON_ARTIFACT_PACKAGE_FIELDS) == expected_json_artifacts
    assert list(JSON_ARTIFACT_PACKAGE_FIELDS.values()) == [
        "validation_summary",
        "reviewer_handoff",
        "proposal_handoff",
        "pending_signoff",
        "audit_manifest",
        "export_manifest",
    ]


def test_artifact_inventory_helpers_use_artifact_order(tmp_path: Path) -> None:
    _write_artifact_placeholders(tmp_path)

    artifact_inventory = build_artifact_inventory(tmp_path)

    assert list(artifact_inventory) == INCLUDED_ARTIFACT_ORDER
    assert artifact_inventory[DECISION_PACKAGE_NAME]["size_bytes"] == len(
        f"{DECISION_PACKAGE_NAME}\n"
    )
    assert len(str(artifact_inventory[DECISION_PACKAGE_NAME]["sha256"])) == 64
    assert validate_artifact_inventory_matches_files(
        artifact_inventory,
        output_dir=tmp_path,
        path="artifact_inventory",
    ) == artifact_inventory


def test_validate_artifact_list_rejects_unknown_artifact() -> None:
    artifacts = [*INCLUDED_ARTIFACT_ORDER, UNKNOWN_ARTIFACT_NAME]

    with pytest.raises(
        ValueError,
        match=(
            "demo_run_result.artifacts includes unknown package artifacts: "
            f"{UNKNOWN_ARTIFACT_NAME}"
        ),
    ):
        validate_artifact_list(artifacts, path="demo_run_result.artifacts")


def test_validate_demo_evidence_receipt_text_rejects_stale_inventory_row(tmp_path: Path) -> None:
    _write_artifact_placeholders(tmp_path)
    artifact_inventory = build_artifact_inventory(tmp_path)
    validation_summary = _review_only_validation_summary()
    receipt_text = "\n".join(
        [
            "# Receipt",
            NON_AUTHORIZATION_MARKER,
            "operational_approval: false",
            "demo_result_checked: true",
            "artifact_inventory_checked: true",
            f"operator_summary: {validation_summary['operator_summary']}",
            f"next_review_action: {validation_summary['next_review_action']}",
            "## Artifact Inventory",
            ARTIFACT_INVENTORY_TABLE_HEADER,
            "|---|---:|---|",
            *build_artifact_inventory_rows(artifact_inventory, path="artifact_inventory"),
        ]
    )

    stale_receipt_text = receipt_text.replace(DECISION_PACKAGE_NAME, "decision package json")

    with pytest.raises(
        ValueError,
        match=(
            "demo evidence receipt missing artifact inventory row: "
            f"{DECISION_PACKAGE_NAME}"
        ),
    ):
        validate_demo_evidence_receipt_text(
            stale_receipt_text,
            artifact_inventory=artifact_inventory,
            validation_summary=validation_summary,
            inventory_path="artifact_inventory",
        )


def test_render_demo_evidence_receipt_includes_summary_and_inventory(tmp_path: Path) -> None:
    _write_artifact_placeholders(tmp_path)
    validation_summary = _review_only_validation_summary()
    write_json_atomic(_validation_summary_path(tmp_path), validation_summary)
    artifact_inventory = build_artifact_inventory(tmp_path)

    receipt_text = render_demo_evidence_receipt(
        {
            "artifact_check": {
                "status": "passed",
                "operational_approval": False,
                "demo_result_checked": True,
                "artifact_inventory_checked": True,
                "demo_receipt_checked": False,
            },
            "artifact_inventory": artifact_inventory,
            "output_dir": str(tmp_path),
            "recommendation": DEMO_RECOMMENDATION,
            "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        }
    )

    assert f"operator_summary: {validation_summary['operator_summary']}" in receipt_text
    assert f"next_review_action: {validation_summary['next_review_action']}" in receipt_text
    for artifact_inventory_row in build_artifact_inventory_rows(
        artifact_inventory,
        path="artifact_inventory",
    ):
        assert artifact_inventory_row in receipt_text


def test_build_demo_run_result_preserves_demo_contract_fields(tmp_path: Path) -> None:
    _write_artifact_placeholders(tmp_path)
    export_result = {
        "status": "passed",
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "output_dir": str(tmp_path),
        "artifacts": list(INCLUDED_ARTIFACT_ORDER),
        "tenant_id": FIXTURE_TENANT_ID,
        "project_id": FIXTURE_PROJECT_ID,
        "decision_id": "decision-a",
        "recommendation": DEMO_RECOMMENDATION,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
    }
    artifact_check = {
        "status": "passed",
        "operational_approval": False,
        "demo_result_checked": False,
        "artifact_inventory_checked": False,
        "demo_receipt_checked": False,
    }

    demo_result = build_demo_run_result(
        export_result,
        output_dir=tmp_path,
        artifact_check=artifact_check,
        seeded_decision_id="decision-a",
        demo_tenant_id=DEMO_FIXTURE_TENANT_ID,
        demo_project_id=DEMO_FIXTURE_PROJECT_ID,
        clean_output=True,
    )

    assert demo_result["demo_result_path"] == str(_demo_result_path(tmp_path))
    assert demo_result["demo_receipt_path"] == str(_demo_receipt_path(tmp_path))
    assert demo_result["artifact_check"] == artifact_check
    assert demo_result["artifact_inventory"] == build_artifact_inventory(tmp_path)
    assert demo_result["clean_output"] is True
    assert list(demo_result) == list(CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE["demo_runner"])


def test_build_demo_run_failure_result_preserves_cli_contract_fields(tmp_path: Path) -> None:
    data_dir, output_dir = _demo_paths(tmp_path)
    error = RuntimeError("demo failed")

    demo_failure_result = build_demo_run_failure_result(
        data_dir=data_dir,
        out_dir=output_dir,
        clean_output=True,
        exc=error,
    )

    assert demo_failure_result == {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "status": "failed",
        "data_dir": str(data_dir),
        "output_dir": str(output_dir),
        "clean_output": True,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(demo_failure_result) == list(
        CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE["demo_runner"]
    )


def test_build_smoke_failure_result_preserves_cli_contract_fields(tmp_path: Path) -> None:
    data_dir, output_dir = _demo_paths(tmp_path)
    gate_result_path = _custom_gate_result_path(tmp_path, FAILED_RESULT_NAME)
    smoke_result_path = _custom_smoke_result_path(tmp_path, FAILED_RESULT_NAME)
    smoke_check_result_path = _custom_smoke_check_result_path(tmp_path, FAILED_RESULT_NAME)
    error = RuntimeError("smoke failed")

    smoke_failure_result = build_smoke_failure_result(
        data_dir=data_dir,
        out_dir=output_dir,
        clean_output=True,
        gate_result_path=gate_result_path,
        gate_result_written=True,
        smoke_result_path=smoke_result_path,
        smoke_result_written=False,
        smoke_check_result_path=smoke_check_result_path,
        smoke_check_result_written=False,
        exc=error,
    )

    assert smoke_failure_result == {
        "status": "failed",
        "smoke": SMOKE_NAME,
        "data_dir": str(data_dir),
        "output_dir": str(output_dir),
        "clean_output": True,
        "gate_result_path": str(gate_result_path),
        "smoke_result_path": str(smoke_result_path),
        "smoke_check_result_path": str(smoke_check_result_path),
        "evidence_files": {
            "demo_result": None,
            "demo_receipt": None,
            "gate_result": str(gate_result_path),
            "smoke_result": str(smoke_result_path),
            "smoke_check_result": str(smoke_check_result_path),
        },
        "gate_result_written": True,
        "smoke_result_written": False,
        "smoke_check_result_written": False,
        "package_artifacts_checked": False,
        "smoke_result_checked": False,
        "error_type": type(error).__name__,
        "error": str(error),
    }


def test_build_smoke_check_failure_result_preserves_cli_contract_fields(tmp_path: Path) -> None:
    smoke_result_path = tmp_path / MISSING_SMOKE_RESULT_NAME
    error = FileNotFoundError("missing smoke")

    smoke_check_failure_result = build_smoke_check_failure_result(
        smoke_result_path,
        error,
    )

    assert smoke_check_failure_result == {
        "check": SMOKE_CHECK_NAME,
        "status": "failed",
        "smoke_result_path": str(smoke_result_path),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(smoke_check_failure_result) == list(
        CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE["smoke_checker"]
    )


def test_build_artifact_check_failure_preserves_cli_fields(tmp_path: Path) -> None:
    output_dir = tmp_path / MISSING_OUTPUT_DIR_NAME
    error = FileNotFoundError("missing package")

    artifact_check_failure_result = build_package_artifact_check_failure_result(
        output_dir,
        error,
    )

    assert artifact_check_failure_result == {
        "status": "failed",
        "output_dir": str(output_dir),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(artifact_check_failure_result) == list(
        CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE["artifact_checker"]
    )


def test_build_cli_contract_manifest_validation_check_failure_result_preserves_cli_contract_fields(
    tmp_path: Path,
) -> None:
    validation_result_path = tmp_path / MISSING_VALIDATION_RESULT_NAME
    error = FileNotFoundError("missing manifest validation result")

    manifest_validation_check_failure_result = (
        build_cli_contract_manifest_validation_check_failure_result(
            validation_result_path,
            error,
        )
    )

    assert manifest_validation_check_failure_result == {
        "status": "failed",
        "check": CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
        "validation_result_path": str(validation_result_path),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(manifest_validation_check_failure_result) == list(
        CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FAILURE_FIELDS
    )


def test_build_cli_contract_manifest_validation_failure_result_preserves_cli_contract_fields(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / MISSING_MANIFEST_NAME
    error = FileNotFoundError("missing manifest")

    manifest_validation_failure_result = build_cli_contract_manifest_validation_failure_result(
        manifest_path=manifest_path,
        exc=error,
    )

    assert manifest_validation_failure_result == {
        "schema_purpose": CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
        "contract_version": CLI_CONTRACT_MANIFEST_CONTRACT_VERSION,
        "status": "failed",
        "manifest_path": str(manifest_path),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(manifest_validation_failure_result) == list(
        CLI_CONTRACT_MANIFEST_VALIDATION_FAILURE_FIELDS
    )


def test_build_gate_failure_result_preserves_cli_contract_fields(tmp_path: Path) -> None:
    output_dir = tmp_path / DEMO_OUTPUT_DIR_NAME
    error = ValueError("gate failed")

    gate_failure_result = build_gate_failure_result(
        output_dir,
        error,
    )

    assert gate_failure_result == {
        "status": "failed",
        "gate": GATE_NAME,
        "output_dir": str(output_dir),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(gate_failure_result) == list(
        CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE["evidence_gate"]
    )


def test_build_export_package_failure_result_preserves_cli_contract_fields(tmp_path: Path) -> None:
    data_dir, output_dir = _demo_paths(tmp_path)
    error = KeyError("missing project")

    export_failure_result = build_export_package_failure_result(
        data_dir=data_dir,
        tenant_id=FIXTURE_TENANT_ID,
        project_id=FIXTURE_PROJECT_ID,
        out_dir=output_dir,
        exc=error,
    )

    assert export_failure_result == {
        "status": "failed",
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "data_dir": str(data_dir),
        "tenant_id": FIXTURE_TENANT_ID,
        "project_id": FIXTURE_PROJECT_ID,
        "output_dir": str(output_dir),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(export_failure_result) == list(
        CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE["project_export"]
    )


def test_build_sample_builder_failure_result_preserves_cli_contract_fields(tmp_path: Path) -> None:
    sample_input_path = tmp_path / MISSING_SAMPLE_INPUT_NAME
    output_dir = tmp_path / DEMO_OUTPUT_DIR_NAME
    error = FileNotFoundError("missing sample")

    sample_builder_failure_result = build_sample_builder_failure_result(
        sample_input_path=sample_input_path,
        output_dir=output_dir,
        exc=error,
    )

    assert sample_builder_failure_result == {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "status": "failed",
        "sample_input": str(sample_input_path),
        "output_dir": str(output_dir),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(sample_builder_failure_result) == list(
        CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE["sample_builder"]
    )


def test_build_sample_validation_failure_preserves_cli_fields(tmp_path: Path) -> None:
    sample_input_path = tmp_path / MISSING_SAMPLE_INPUT_NAME
    expected_package_path = tmp_path / MISSING_EXPECTED_PACKAGE_NAME
    error = FileNotFoundError("missing sample")

    sample_validation_failure_result = build_sample_validation_failure_result(
        sample_input_path=sample_input_path,
        expected_package_path=expected_package_path,
        exc=error,
    )

    assert sample_validation_failure_result == {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
        "status": "failed",
        "sample_input": str(sample_input_path),
        "expected_package": str(expected_package_path),
        "error_type": type(error).__name__,
        "error": str(error),
    }
    assert list(sample_validation_failure_result) == list(
        CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE["sample_validator"]
    )


def test_write_demo_evidence_state_updates_demo_result_and_receipt(tmp_path: Path) -> None:
    _write_artifact_placeholders(tmp_path)
    write_json_atomic(
        _validation_summary_path(tmp_path),
        _review_only_validation_summary(),
    )
    demo_result = {
        "artifact_check": {
            "status": "pending",
            "operational_approval": False,
            "demo_result_checked": False,
            "artifact_inventory_checked": False,
            "demo_receipt_checked": False,
        },
        "artifact_inventory": build_artifact_inventory(tmp_path),
        "output_dir": str(tmp_path),
        "recommendation": DEMO_RECOMMENDATION,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
    }
    artifact_check = {
        "status": "passed",
        "operational_approval": False,
        "demo_result_checked": True,
        "artifact_inventory_checked": True,
        "demo_receipt_checked": True,
    }
    demo_result_path = _demo_result_path(tmp_path)
    receipt_path = _demo_receipt_path(tmp_path)

    written = write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=artifact_check,
        receipt_path=receipt_path,
    )

    assert written is demo_result
    assert demo_result["artifact_check"] == artifact_check
    assert load_json(demo_result_path)["artifact_check"] == artifact_check
    assert "demo_receipt_checked: true" in _read_artifact_text(tmp_path, DEMO_RECEIPT_NAME)


def test_write_validated_demo_evidence_completes_self_check_cycle(tmp_path: Path) -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    export_result = {
        **write_package_artifacts(package_doc, tmp_path),
        "tenant_id": FIXTURE_TENANT_ID,
        "project_id": FIXTURE_PROJECT_ID,
        "decision_id": "decision-a",
    }
    initial_check = build_package_artifact_check_result(tmp_path)
    demo_result = build_demo_run_result(
        export_result,
        output_dir=tmp_path,
        artifact_check=initial_check,
        seeded_decision_id="decision-a",
        demo_tenant_id=DEMO_FIXTURE_TENANT_ID,
        demo_project_id=DEMO_FIXTURE_PROJECT_ID,
        clean_output=False,
    )
    demo_result_path = _demo_result_path(tmp_path)
    receipt_path = _demo_receipt_path(tmp_path)

    written = write_validated_demo_evidence(
        demo_result,
        output_dir=tmp_path,
        demo_result_path=demo_result_path,
        receipt_path=receipt_path,
        initial_artifact_check=initial_check,
    )

    assert written is demo_result
    assert demo_result["artifact_check"]["demo_result_checked"] is True
    assert demo_result["artifact_check"]["artifact_inventory_checked"] is True
    assert demo_result["artifact_check"]["demo_receipt_checked"] is True
    assert (
        load_json(demo_result_path)["artifact_check"]
        == demo_result["artifact_check"]
    )
    assert "demo_receipt_checked: true" in _read_artifact_text(tmp_path, DEMO_RECEIPT_NAME)


def test_validate_demo_evidence_receipt_file_rejects_stale_path(tmp_path: Path) -> None:
    receipt_path = _demo_receipt_path(tmp_path)
    _write_text(receipt_path, f"{NON_AUTHORIZATION_MARKER}\n")
    demo_result = {"demo_receipt_path": str(tmp_path / STALE_DEMO_RECEIPT_NAME)}

    with pytest.raises(ValueError, match="demo_receipt_path"):
        validate_demo_evidence_receipt_file(
            receipt_path=receipt_path,
            demo_result=demo_result,
            artifact_inventory={},
            validation_summary={},
        )


def test_validate_evidence_summary_text_requires_source_and_missing_markers() -> None:
    with pytest.raises(ValueError, match="missing evidence type markers: source_fact"):
        validate_evidence_summary_text("## Evidence\n\n- missing_evidence: security owner")


def test_validate_markdown_artifact_files_rejects_stale_decision_summary(tmp_path: Path) -> None:
    _write_text(
        _signoff_summary_path(tmp_path),
        "\n".join(
            [
                "Status: `pending`",
                "Scope: `decision_package_review_only`",
                "Operational approval: `false`",
                NON_AUTHORIZATION_MARKER,
            ]
        ),
    )
    _write_text(_decision_summary_path(tmp_path), "stale decision summary\n")
    _write_text(
        _evidence_summary_path(tmp_path),
        "source_fact\nmissing_evidence\n",
    )

    with pytest.raises(ValueError, match=DECISION_SUMMARY_NAME):
        validate_markdown_artifact_files(tmp_path)


def test_validate_demo_run_result_rejects_stale_output_dir(tmp_path: Path) -> None:
    demo_result_path = _demo_result_path(tmp_path)
    demo_result = {
        "artifact_check": {
            "status": "passed",
            "operational_approval": False,
            "demo_result_checked": True,
        },
        "demo_result_path": str(demo_result_path),
        "output_dir": str(tmp_path / STALE_OUTPUT_DIR_NAME),
        "artifacts": list(INCLUDED_ARTIFACT_ORDER),
    }

    with pytest.raises(ValueError, match="demo_run_result.output_dir"):
        validate_demo_run_result(
            demo_result,
            output_dir=tmp_path,
            demo_result_path=demo_result_path,
        )


def test_validate_demo_evidence_files_reports_missing_demo_result(tmp_path: Path) -> None:
    assert validate_demo_evidence_files(tmp_path) == {
        "demo_result_checked": False,
        "artifact_inventory_checked": False,
        "demo_receipt_checked": False,
    }


def test_validate_demo_evidence_files_rejects_stale_output_dir(tmp_path: Path) -> None:
    demo_result_path = _demo_result_path(tmp_path)
    write_json_atomic(
        demo_result_path,
        {
            "artifact_check": {
                "status": "passed",
                "operational_approval": False,
                "demo_result_checked": True,
            },
            "demo_result_path": str(demo_result_path),
            "output_dir": str(tmp_path / STALE_OUTPUT_DIR_NAME),
            "artifacts": list(INCLUDED_ARTIFACT_ORDER),
        },
    )

    with pytest.raises(ValueError, match="demo_run_result.output_dir"):
        validate_demo_evidence_files(tmp_path)


def test_validate_package_artifact_files_rejects_missing_artifact(tmp_path: Path) -> None:
    _write_artifact_placeholders(
        tmp_path,
        missing_artifact=EXPORT_MANIFEST_NAME,
        content="{}\n",
    )

    with pytest.raises(ValueError, match="missing package artifacts: export_manifest.json"):
        validate_package_artifact_files(tmp_path)


def test_validate_json_artifact_rejects_stale_split_artifact(tmp_path: Path) -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    package = package_doc["package"]
    stale_handoff = copy.deepcopy(package["reviewer_handoff"])
    stale_handoff["requested_reviewer"] = "alternate-reviewer"
    write_json_atomic(_reviewer_handoff_path(tmp_path), stale_handoff)

    with pytest.raises(
        ValueError,
        match="reviewer_handoff.json must match decision_package.package.reviewer_handoff",
    ):
        validate_json_artifact_matches_package(
            tmp_path,
            package_doc,
            package,
            artifact_name=REVIEWER_HANDOFF_NAME,
            package_field="reviewer_handoff",
        )


def test_validate_local_package_artifacts_rejects_stale_split_artifact(tmp_path: Path) -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    write_package_artifacts(package_doc, tmp_path)
    reviewer_handoff = load_json(_reviewer_handoff_path(tmp_path))
    reviewer_handoff["requested_reviewer"] = "alternate-reviewer"
    write_json_atomic(_reviewer_handoff_path(tmp_path), reviewer_handoff)

    with pytest.raises(
        ValueError,
        match="reviewer_handoff.json must match decision_package.package.reviewer_handoff",
    ):
        validate_local_package_artifacts(tmp_path)


def test_build_artifact_check_result_reports_unchecked_demo_evidence(tmp_path: Path) -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    write_package_artifacts(package_doc, tmp_path)

    artifact_check_result = build_package_artifact_check_result(tmp_path)

    assert artifact_check_result == {
        "status": "passed",
        "output_dir": str(tmp_path),
        "artifact_count": len(INCLUDED_ARTIFACT_ORDER),
        "recommendation": DEMO_RECOMMENDATION,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        "operational_approval": False,
        "demo_result_checked": False,
        "artifact_inventory_checked": False,
        "demo_receipt_checked": False,
    }


def test_validate_expected_package_for_sample_rejects_opportunity_ref_drift() -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    expected_package = load_json(EXPECTED_PACKAGE_PATH)
    expected_package["package"]["opportunity_ref"]["title"] = "stale title"

    with pytest.raises(
        ValueError,
        match="expected_package.package.opportunity_ref.title must match sample input",
    ):
        validate_expected_package_for_sample(expected_package, sample_input=sample_input)


def test_validate_package_document_rejects_stale_proposal_package_id() -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    package_doc["package"]["proposal_handoff"]["source_package_id"] = STALE_PACKAGE_ID

    with pytest.raises(ValueError, match="source_package_id"):
        validate_package_document(package_doc)


def test_validate_package_document_for_path_rewrites_error_prefix() -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    package_doc["package"]["proposal_handoff"]["source_package_id"] = STALE_PACKAGE_ID

    with pytest.raises(
        ValueError,
        match="expected_package.package.proposal_handoff.source_package_id",
    ):
        validate_package_document_for_path(package_doc, path="expected_package")


def test_validate_package_section_for_path_rewrites_section_error_prefix() -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    proposal_handoff = copy.deepcopy(package_doc["package"]["proposal_handoff"])
    proposal_handoff["allowed_next_steps"].append("submit bid")

    with pytest.raises(
        ValueError,
        match="proposal_handoff.allowed_next_steps includes unknown values: submit bid",
    ):
        validate_package_section_for_path(
            package_doc,
            package_field="proposal_handoff",
            section=proposal_handoff,
            section_path="proposal_handoff",
            document_path="decision_package",
        )


def test_write_package_artifacts_rejects_malformed_package_before_writing(tmp_path: Path) -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    package_doc = build_decision_package(sample_input)
    package_doc["package"]["export_manifest"]["included_artifacts"].append("unreviewed.json")

    with pytest.raises(ValueError, match="included_artifacts includes unknown values"):
        write_package_artifacts(package_doc, tmp_path)

    assert not _decision_package_path(tmp_path).exists()


def test_write_json_atomic_creates_parent_directory_and_json_file(tmp_path: Path) -> None:
    output_path = _atomic_write_path(tmp_path, ATOMIC_JSON_RESULT_NAME)

    write_json_atomic(output_path, {"status": "passed", "items": ["contract", "receipt"]})

    assert load_json(output_path) == {
        "status": "passed",
        "items": ["contract", "receipt"],
    }
    assert _read_text(output_path).endswith("\n")


def test_write_text_atomic_creates_parent_directory_and_text_file(tmp_path: Path) -> None:
    output_path = _atomic_write_path(tmp_path, ATOMIC_TEXT_RECEIPT_NAME)

    write_text_atomic(output_path, "# Receipt\n\nlocal evidence\n")

    assert _read_text(output_path) == "# Receipt\n\nlocal evidence\n"


def test_validate_demo_input_rejects_missing_capability_profile() -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    broken_input = copy.deepcopy(sample_input)
    broken_input["capability_profile"]["service_lines"] = []

    with pytest.raises(ValueError, match="service_lines"):
        validate_demo_input(broken_input)


def test_validate_demo_input_rejects_non_string_required_capability() -> None:
    sample_input = load_json(SAMPLE_INPUT_PATH)
    broken_input = copy.deepcopy(sample_input)
    broken_input["opportunity"]["required_capabilities"].append(False)

    with pytest.raises(ValueError, match=r"required_capabilities\[4\] must be a non-empty string"):
        validate_demo_input(broken_input)


def test_build_decision_package_from_record_maps_project_state(tmp_path: Path) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))
    record = store.upsert(
        ProcurementDecisionUpsert(
            project_id=FIXTURE_PROJECT_ID,
            tenant_id=FIXTURE_TENANT_ID,
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="bid-001",
                source_url="https://example.test/bid-001",
                title="Public workflow modernization",
                issuer="Sample Agency",
                budget="KRW 100M",
                deadline="2026-07-15",
                bid_type="general",
                category="service",
                region="national",
                raw_text_preview="workflow modernization",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="security_plan",
                    label="Security handling plan",
                    status="unknown",
                    blocking=True,
                    reason="Security plan owner is not assigned.",
                )
            ],
            score_breakdown=[
                ProcurementScoreBreakdownItem(
                    key="security_readiness",
                    label="Security readiness",
                    score=52.0,
                    weight=0.2,
                    weighted_score=10.4,
                    summary="Security plan requires owner assignment.",
                )
            ],
            soft_fit_score=68.2,
            soft_fit_status="scored",
            missing_data=["security plan owner"],
            checklist_items=[
                ProcurementChecklistItem(
                    category="security_plan",
                    title="Finalize security handling plan",
                    status="action_needed",
                    severity="high",
                    remediation_note="Assign owner before proposal drafting.",
                )
            ],
            recommendation=ProcurementRecommendation(
                value=DEMO_RECOMMENDATION,
                summary="Conditional go because security readiness needs review.",
                evidence=["Weighted fit score: 68.20"],
                missing_data=["security plan owner"],
                remediation_notes=["Assign security plan owner."],
            ),
        )
    )

    package_doc = build_decision_package_from_record(record, reviewer_owner=FIXTURE_REVIEWER)
    record_package_artifacts = write_package_artifacts(
        package_doc,
        _package_output_dir(tmp_path),
    )

    package = package_doc["package"]
    assert package["recommendation"] == DEMO_RECOMMENDATION
    assert list(package["opportunity_ref"]) == OPPORTUNITY_REF_FIELD_ORDER
    assert package["opportunity_ref"]["opportunity_id"] == "bid-001"
    assert package["opportunity_ref"]["title"] == "Public workflow modernization"
    assert package["opportunity_ref"]["source_type"] == "g2b"
    assert all(
        list(hard_filter) == HARD_FILTER_FIELD_ORDER
        for hard_filter in package["hard_filters"]
    )
    assert list(package["soft_fit_score"]) == SOFT_FIT_SCORE_FIELD_ORDER
    assert all(
        list(soft_fit_factor) == SOFT_FIT_FACTOR_FIELD_ORDER
        for soft_fit_factor in package["soft_fit_score"]["factors"]
    )
    assert all(
        list(evidence_summary) == EVIDENCE_SUMMARY_FIELD_ORDER
        for evidence_summary in package["evidence_summary"]
    )
    assert all(
        list(checklist_item) == BID_READINESS_CHECKLIST_FIELD_ORDER
        for checklist_item in package["bid_readiness_checklist"]
    )
    assert package["pending_signoff"]["operational_approval"] is False
    assert package["pending_signoff"]["signoff_scope"] == SIGNOFF_SCOPE
    assert package["reviewer_handoff"]["requested_reviewer"] == FIXTURE_REVIEWER
    assert package["reviewer_handoff"]["non_authorization_note"] == NON_AUTHORIZATION_NOTE
    assert package["proposal_handoff"]["source_package_id"] == package["package_id"]
    assert package["proposal_handoff"]["recommendation"] == package["recommendation"]
    assert package["proposal_handoff"]["excluded_actions"] == EXCLUDED_ACTION_ORDER
    assert package["audit_manifest"]["package_id"] == package["package_id"]
    assert package["audit_manifest"]["recommendation"] == package["recommendation"]
    assert package["audit_manifest"]["included_artifacts"] == INCLUDED_ARTIFACT_ORDER
    assert list(package["validation_summary"]) == VALIDATION_SUMMARY_FIELD_ORDER
    assert NON_APPROVAL_MARKER in package["validation_summary"]["operator_summary"]
    assert SCOPED_REVIEW_MARKER in package["validation_summary"]["next_review_action"]
    assert "security plan owner" in package["validation_summary"]["unresolved_gaps"]
    assert record_package_artifacts["authorization_boundary"] == EXPLICIT_AUTHORIZATION_BOUNDARY


def test_export_manifest_helper_keeps_artifact_and_action_order() -> None:
    manifest = build_export_manifest()

    assert list(manifest) == EXPORT_MANIFEST_FIELD_ORDER
    assert manifest == {
        "included_artifacts": INCLUDED_ARTIFACT_ORDER,
        "excluded_actions": EXCLUDED_ACTION_ORDER,
    }
    assert manifest["included_artifacts"] is not INCLUDED_ARTIFACT_ORDER
    assert manifest["excluded_actions"] is not EXCLUDED_ACTION_ORDER


def test_audit_manifest_helper_keeps_artifact_and_action_order() -> None:
    manifest = build_audit_manifest(
        package_id=HELPER_PACKAGE_ID,
        recommendation=DEMO_RECOMMENDATION,
    )

    assert list(manifest) == AUDIT_MANIFEST_FIELD_ORDER
    assert manifest["schema_purpose"] == AUDIT_MANIFEST_SCHEMA_PURPOSE
    assert manifest["packet_status"] == AUDIT_MANIFEST_PACKET_STATUS
    assert manifest["package_id"] == HELPER_PACKAGE_ID
    assert manifest["recommendation"] == DEMO_RECOMMENDATION
    assert manifest["included_artifacts"] == INCLUDED_ARTIFACT_ORDER
    for group_name, expected_artifacts in AUDIT_MANIFEST_ARTIFACT_GROUPS.items():
        assert manifest[group_name] == expected_artifacts
        assert manifest[group_name] is not expected_artifacts
    assert manifest["excluded_actions"] == EXCLUDED_ACTION_ORDER
    assert manifest["included_artifacts"] is not INCLUDED_ARTIFACT_ORDER
    assert manifest["excluded_actions"] is not EXCLUDED_ACTION_ORDER
    assert NON_AUTHORIZATION_MARKER in manifest["non_authorization_note"]


def test_proposal_handoff_helper_keeps_boundary_lists_independent() -> None:
    handoff = build_proposal_handoff(
        package_id=HELPER_PACKAGE_ID,
        recommendation=DEMO_RECOMMENDATION,
        unresolved_gaps=["security-plan", "security-plan", "proposal-reviewer"],
    )

    assert list(handoff) == PROPOSAL_HANDOFF_FIELD_ORDER
    assert handoff["handoff_scope"] == PROPOSAL_HANDOFF_SCOPE
    assert handoff["source_package_id"] == HELPER_PACKAGE_ID
    assert handoff["drafting_status"] == "blocked_until_review"
    assert handoff["required_inputs"] == ["security-plan", "proposal-reviewer"]
    assert handoff["blocked_until"] == ["security-plan", "proposal-reviewer"]
    assert handoff["required_inputs"] is not handoff["blocked_until"]
    assert handoff["allowed_next_steps"] == PROPOSAL_ALLOWED_NEXT_STEPS
    assert handoff["allowed_next_steps"] is not PROPOSAL_ALLOWED_NEXT_STEPS
    assert handoff["excluded_actions"] == EXCLUDED_ACTION_ORDER
    assert handoff["excluded_actions"] is not EXCLUDED_ACTION_ORDER
    assert handoff["non_authorization_note"] == NON_AUTHORIZATION_NOTE


def test_proposal_handoff_helper_marks_gap_free_package_ready_for_scoped_draft() -> None:
    handoff = build_proposal_handoff(
        package_id=HELPER_PACKAGE_ID,
        recommendation="GO",
        unresolved_gaps=[],
    )

    assert handoff["drafting_status"] == "ready_for_scoped_draft"
    assert handoff["required_inputs"] == []
    assert handoff["blocked_until"] == []


def test_handoff_helpers_keep_review_boundary_explicit() -> None:
    handoff = build_reviewer_handoff(
        reviewer=FIXTURE_REVIEWER,
        requested_decision="review_conditional_go",
        review_prompt="Review before downstream handoff.",
    )
    signoff = build_pending_signoff(reviewer=FIXTURE_REVIEWER)

    assert list(handoff) == REVIEWER_HANDOFF_FIELD_ORDER
    assert list(signoff) == PENDING_SIGNOFF_FIELD_ORDER
    assert handoff == {
        "requested_reviewer": FIXTURE_REVIEWER,
        "requested_decision": "review_conditional_go",
        "review_prompt": "Review before downstream handoff.",
        "non_authorization_note": NON_AUTHORIZATION_NOTE,
    }
    assert signoff == {
        "status": "pending",
        "reviewer": FIXTURE_REVIEWER,
        "signoff_scope": SIGNOFF_SCOPE,
        "operational_approval": False,
    }


def test_build_decision_package_from_record_requires_recommendation(tmp_path: Path) -> None:
    store = ProcurementDecisionStore(base_dir=str(tmp_path))
    record = store.upsert(
        ProcurementDecisionUpsert(
            project_id=FIXTURE_PROJECT_ID,
            tenant_id=FIXTURE_TENANT_ID,
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="bid-001",
                title="Public workflow modernization",
            ),
        )
    )

    with pytest.raises(ValueError, match="recommendation"):
        build_decision_package_from_record(record)
