from __future__ import annotations

from app.services.document_ops_training_adapter import (
    training_adapter_contract_summary,
    training_execution_rehearsal_summary,
)


def test_training_adapter_contract_is_stub_only_and_disabled_by_default() -> None:
    summary = training_adapter_contract_summary(provider="openai", base_model="gpt-test-base", env={})

    assert summary["report_type"] == "document_ops_training_provider_adapter_contract"
    assert summary["provider"] == "openai"
    assert summary["base_model"] == "gpt-test-base"
    assert summary["read_only"] is True
    assert summary["adapter_status"] == "stub_only"
    assert summary["execution_enabled"] is False
    assert summary["configured_execution_flag"] is False
    assert summary["training_execution_allowed"] is False
    assert summary["provider_api_calls_allowed"] is False
    assert summary["external_upload_allowed"] is False
    assert summary["provider_job_started"] is False
    assert summary["model_promotion_allowed"] is False
    assert summary["config_valid"] is True
    assert summary["config_errors"] == []
    assert "execution_feature_flag_disabled_by_default" in summary["config_warnings"]
    assert "create_training_job" in summary["adapter_contract"]["required_methods"]
    assert "upload_dataset" in summary["adapter_contract"]["forbidden_in_stub"]


def test_training_adapter_contract_blocks_enabled_stub_configuration() -> None:
    summary = training_adapter_contract_summary(
        provider="openai",
        env={"DECISIONDOC_TRAINING_EXECUTION_ENABLED": "true"},
    )

    assert summary["execution_enabled"] is False
    assert summary["configured_execution_flag"] is True
    assert summary["training_execution_allowed"] is False
    assert summary["provider_api_calls_allowed"] is False
    assert summary["config_valid"] is False
    assert "execution_feature_flag_enabled_but_adapter_is_stub_only" in summary["config_errors"]
    assert "provider_not_in_execution_allowlist" in summary["config_errors"]
    assert "missing_execution_acknowledgement" in summary["config_errors"]


def test_training_execution_rehearsal_validates_governance_and_contract_without_side_effects() -> None:
    governance = {
        "status": "governance_ready_for_human_review",
        "no_side_effects": True,
        "latest": {
            "reviewed_sft_export": {"filename": "sft_policy_20260507T000000.jsonl"},
            "dataset_freeze": {"manifest_id": "dsf_" + "a" * 32},
            "pre_execution_audit": {"audit_id": "tea_" + "b" * 32},
        },
    }
    contract = training_adapter_contract_summary(
        provider="openai",
        base_model="gpt-test-base",
        env={},
    )

    rehearsal = training_execution_rehearsal_summary(
        governance_summary=governance,
        adapter_contract=contract,
    )

    assert rehearsal["report_type"] == "document_ops_training_provider_execution_rehearsal"
    assert rehearsal["status"] == "rehearsal_ready"
    assert rehearsal["dry_run"] is True
    assert rehearsal["rehearsal_only"] is True
    assert rehearsal["training_execution_allowed"] is False
    assert rehearsal["provider_api_calls_allowed"] is False
    assert rehearsal["external_upload_allowed"] is False
    assert rehearsal["provider_job_started"] is False
    assert rehearsal["model_promotion_allowed"] is False
    assert rehearsal["blockers"] == []
    assert rehearsal["validation_summary"]["governance_summary_ready"] is True
    assert rehearsal["validation_summary"]["adapter_contract_stub_only"] is True
    assert all(item["side_effect"] is False for item in rehearsal["rehearsal_steps"])
    assert "create_provider_fine_tune_job" in {item["step"] for item in rehearsal["rehearsal_steps"]}


def test_training_execution_rehearsal_blocks_missing_artifacts() -> None:
    rehearsal = training_execution_rehearsal_summary(
        governance_summary={"status": "needs_attention", "no_side_effects": True, "latest": {}},
        adapter_contract=training_adapter_contract_summary(provider="openai", env={}),
    )

    assert rehearsal["status"] == "blocked"
    assert "governance_summary_ready" in rehearsal["blockers"]
    assert "dataset_reference_ready" in rehearsal["blockers"]
