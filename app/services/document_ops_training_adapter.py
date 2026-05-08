"""Provider execution adapter contract stubs for DocumentOps training.

This module intentionally does not upload datasets, create fine-tune jobs, or
call provider APIs. It only validates disabled-by-default configuration and
returns the contract a future execution adapter must satisfy.
"""
from __future__ import annotations

import os
import re
from typing import Any


_SUPPORTED_PROVIDERS = {"provider_agnostic", "openai"}
_ENABLE_ACK = "DOCUMENTOPS_TRAINING_EXECUTION_REQUIRES_SEPARATE_APPROVAL"


def training_adapter_contract_summary(
    *,
    provider: str = "provider_agnostic",
    base_model: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a provider adapter contract and disabled config validation."""
    source = env if env is not None else os.environ
    provider_label = _safe_provider_label(provider)
    execution_enabled = _truthy(source.get("DECISIONDOC_TRAINING_EXECUTION_ENABLED", "0"))
    allowlist = _csv_set(source.get("DECISIONDOC_TRAINING_EXECUTION_PROVIDER_ALLOWLIST", ""))
    ack = str(source.get("DECISIONDOC_TRAINING_EXECUTION_ACK", "")).strip()

    config_errors: list[str] = []
    config_warnings: list[str] = []
    if provider_label not in _SUPPORTED_PROVIDERS:
        config_errors.append("unsupported_provider")
    if execution_enabled:
        config_errors.append("execution_feature_flag_enabled_but_adapter_is_stub_only")
        if provider_label not in allowlist:
            config_errors.append("provider_not_in_execution_allowlist")
        if ack != _ENABLE_ACK:
            config_errors.append("missing_execution_acknowledgement")
    else:
        config_warnings.append("execution_feature_flag_disabled_by_default")

    return {
        "report_type": "document_ops_training_provider_adapter_contract",
        "provider": provider_label,
        "base_model": (base_model or "").strip() or "to_be_selected",
        "read_only": True,
        "adapter_status": "stub_only",
        "execution_enabled": False,
        "configured_execution_flag": execution_enabled,
        "training_execution_allowed": False,
        "provider_api_calls_allowed": False,
        "external_upload_allowed": False,
        "provider_job_started": False,
        "model_promotion_allowed": False,
        "config_valid": not config_errors,
        "config_errors": config_errors,
        "config_warnings": config_warnings,
        "required_env": {
            "DECISIONDOC_TRAINING_EXECUTION_ENABLED": "must remain false until a separate execution workflow is approved",
            "DECISIONDOC_TRAINING_EXECUTION_PROVIDER_ALLOWLIST": "future execution-only allowlist; ignored while disabled",
            "DECISIONDOC_TRAINING_EXECUTION_ACK": _ENABLE_ACK,
        },
        "adapter_contract": {
            "input": {
                "freeze_manifest_id": "required",
                "export_sha256": "required",
                "audit_id": "required",
                "provider": provider_label,
                "base_model": (base_model or "").strip() or "to_be_selected",
            },
            "required_methods": [
                "validate_dataset_reference",
                "prepare_provider_dataset",
                "create_training_job",
                "poll_training_job",
                "collect_eval_results",
                "emit_model_candidate",
            ],
            "forbidden_in_stub": [
                "upload_dataset",
                "create_provider_fine_tune_job",
                "start_training",
                "promote_model",
            ],
            "output": {
                "provider_job_id": "future execution only",
                "model_candidate_id": "future execution only",
                "eval_result_id": "future execution only",
            },
        },
    }


def training_execution_rehearsal_summary(
    *,
    governance_summary: dict[str, Any],
    adapter_contract: dict[str, Any],
) -> dict[str, Any]:
    """Validate artifacts against the adapter contract without side effects."""
    governance_ready = governance_summary.get("status") == "governance_ready_for_human_review"
    governance_no_side_effects = governance_summary.get("no_side_effects") is True
    contract_valid = adapter_contract.get("config_valid") is True
    contract_stub_only = adapter_contract.get("adapter_status") == "stub_only"
    contract_no_side_effects = (
        adapter_contract.get("training_execution_allowed") is False
        and adapter_contract.get("provider_api_calls_allowed") is False
        and adapter_contract.get("external_upload_allowed") is False
        and adapter_contract.get("provider_job_started") is False
        and adapter_contract.get("model_promotion_allowed") is False
    )
    latest = governance_summary.get("latest") if isinstance(governance_summary.get("latest"), dict) else {}
    audit = latest.get("pre_execution_audit") if isinstance(latest.get("pre_execution_audit"), dict) else {}
    freeze = latest.get("dataset_freeze") if isinstance(latest.get("dataset_freeze"), dict) else {}
    export = latest.get("reviewed_sft_export") if isinstance(latest.get("reviewed_sft_export"), dict) else {}
    adapter_input = (
        adapter_contract.get("adapter_contract", {}).get("input", {})
        if isinstance(adapter_contract.get("adapter_contract"), dict)
        else {}
    )
    dataset_reference_ready = bool(
        freeze.get("manifest_id")
        and (export.get("filename") or freeze.get("export_filename"))
        and audit.get("audit_id")
    )
    provider_matches = str(adapter_contract.get("provider") or "") == str(adapter_input.get("provider") or "")
    base_model_matches = str(adapter_contract.get("base_model") or "") == str(adapter_input.get("base_model") or "")
    validations = [
        ("governance_summary_ready", governance_ready),
        ("governance_no_side_effects", governance_no_side_effects),
        ("adapter_contract_valid", contract_valid),
        ("adapter_contract_stub_only", contract_stub_only),
        ("adapter_contract_no_side_effects", contract_no_side_effects),
        ("dataset_reference_ready", dataset_reference_ready),
        ("adapter_provider_matches_contract_input", provider_matches),
        ("adapter_base_model_matches_contract_input", base_model_matches),
    ]
    blockers = [name for name, passed in validations if not passed]
    rehearsal_steps = [
        _rehearsal_step("validate_governance_summary", governance_ready, "read_only_validation"),
        _rehearsal_step("validate_adapter_contract", contract_valid and contract_stub_only, "read_only_validation"),
        _rehearsal_step("validate_dataset_reference", dataset_reference_ready, "metadata_only"),
        _rehearsal_step("prepare_provider_dataset", True, "skipped_no_upload"),
        _rehearsal_step("create_provider_fine_tune_job", True, "skipped_no_provider_api_call"),
        _rehearsal_step("poll_training_job", True, "skipped_no_provider_job"),
        _rehearsal_step("collect_eval_results", True, "planned_for_future_execution"),
        _rehearsal_step("emit_model_candidate", True, "skipped_no_model_promotion"),
    ]
    return {
        "report_type": "document_ops_training_provider_execution_rehearsal",
        "read_only": True,
        "dry_run": True,
        "rehearsal_only": True,
        "training_execution_allowed": False,
        "provider_api_calls_allowed": False,
        "external_upload_allowed": False,
        "provider_job_started": False,
        "model_promotion_allowed": False,
        "status": "rehearsal_ready" if not blockers else "blocked",
        "provider": adapter_contract.get("provider"),
        "base_model": adapter_contract.get("base_model"),
        "blockers": blockers,
        "validation_summary": {name: passed for name, passed in validations},
        "rehearsal_steps": rehearsal_steps,
        "artifact_references": {
            "reviewed_sft_export": export,
            "dataset_freeze": freeze,
            "pre_execution_audit": audit,
        },
        "adapter_contract": adapter_contract,
        "governance_status": governance_summary.get("status"),
    }


def _rehearsal_step(step: str, passed: bool, mode: str) -> dict[str, Any]:
    return {
        "step": step,
        "status": "dry_run_pass" if passed else "blocked",
        "mode": mode,
        "side_effect": False,
    }


def _safe_provider_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())[:80].strip("._-")
    return label or "provider_agnostic"


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _csv_set(value: str) -> set[str]:
    return {_safe_provider_label(item) for item in str(value or "").split(",") if item.strip()}
