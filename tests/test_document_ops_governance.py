from __future__ import annotations

from copy import deepcopy

from app.services.document_ops_governance import (
    build_document_ops_governance_overview,
)


def _governance_summary() -> dict:
    return {
        "read_only": True,
        "status": "governance_ready_for_human_review",
        "no_side_effects": True,
        "training_execution_allowed": False,
        "provider_api_calls_allowed": False,
        "external_upload_allowed": False,
        "provider_job_started": False,
        "model_promotion_allowed": False,
        "blockers": [],
    }


def _artifact_inventory() -> dict:
    return {
        "read_only": True,
        "status": "clean",
        "counts": {
            "authoritative_references": 5,
            "referenced_verified": 5,
            "invalid_reference": 0,
            "referenced_missing": 0,
            "referenced_tampered": 0,
            "unreferenced": 0,
        },
        "observation_boundary": {
            "metadata_snapshot_atomic": True,
            "multi_object_snapshot_atomic": False,
        },
        "cleanup_boundary": {
            "automatic_cleanup_allowed": False,
            "objects_deleted": False,
            "manual_recheck_required": True,
        },
    }


def _signoff_summary() -> dict:
    return {
        "read_only": True,
        "overall_status": "manual_signoff_complete_no_training_authorization",
        "training_execution_allowed": False,
        "provider_api_calls_allowed": False,
        "external_upload_allowed": False,
        "provider_job_started": False,
        "model_promotion_allowed": False,
        "aggregate": {
            "completed_record_count": 1,
            "pending_record_count": 0,
            "manual_follow_up_record_count": 0,
            "all_protected_training_flags_false": True,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "side_effect_boundary": {
            "actual_reviewer_approval_recorded_by_summary": False,
            "training_execution_started": False,
            "external_dataset_uploaded": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "model_promoted": False,
        },
        "blockers": [],
    }


def _build(
    *,
    governance: dict | None = None,
    inventory: dict | None = None,
    signoff: dict | None = None,
) -> dict:
    return build_document_ops_governance_overview(
        tenant_id="alpha",
        generated_at="2026-07-20T14:00:00+00:00",
        training_governance_summary=(
            governance if governance is not None else _governance_summary()
        ),
        artifact_inventory=(
            inventory if inventory is not None else _artifact_inventory()
        ),
        reviewer_signoff_summary=(
            signoff if signoff is not None else _signoff_summary()
        ),
    )


def test_governance_overview_reports_three_independent_ready_checks() -> None:
    overview = _build()

    assert overview["status"] == "review_evidence_ready"
    assert [item["status"] for item in overview["checks"]] == [
        "passed",
        "passed",
        "passed",
    ]
    assert overview["observation_boundary"] == {
        "source_reports_read_independently": True,
        "combined_snapshot_atomic": False,
        "manual_recheck_required": True,
    }
    assert all(value is False for value in overview["authorization_boundary"].values())
    assert "외부 실행 권한은 별도 승인 대상" in overview["next_review_action"]


def test_governance_overview_prioritizes_integrity_and_review_blockers() -> None:
    inventory = deepcopy(_artifact_inventory())
    inventory["status"] = "attention_required"
    inventory["counts"]["referenced_tampered"] = 1
    assert _build(inventory=inventory)["status"] == "artifact_integrity_attention"

    governance = deepcopy(_governance_summary())
    governance["status"] = "needs_attention"
    governance["blockers"] = ["latest_training_audit_integrity_failed"]
    assert _build(governance=governance)["status"] == "governance_review_needed"

    signoff = deepcopy(_signoff_summary())
    signoff["overall_status"] = "pending_manual_signoff_no_training_authorization"
    signoff["aggregate"]["completed_record_count"] = 0
    signoff["aggregate"]["pending_record_count"] = 1
    assert _build(signoff=signoff)["status"] == "reviewer_signoff_pending"


def test_governance_overview_fails_closed_when_a_boundary_drifts() -> None:
    signoff = deepcopy(_signoff_summary())
    signoff["aggregate"]["provider_job_creation_authorized"] = True

    overview = _build(signoff=signoff)

    assert overview["status"] == "boundary_attention"
    assert overview["checks"][2]["status"] == "boundary_attention"
    assert "외부 실행을 중단" in overview["next_review_action"]

    missing_source_overview = _build(governance={})
    assert missing_source_overview["status"] == "boundary_attention"
    assert missing_source_overview["checks"][1]["status"] == "boundary_attention"
