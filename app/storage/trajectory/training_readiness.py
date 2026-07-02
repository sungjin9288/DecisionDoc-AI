"""Helper functions for training readiness recommendations and provider labels."""
from __future__ import annotations

import re

from app.storage.trajectory.redaction import _dedupe


def _training_readiness_recommendations(blockers: list[str]) -> list[str]:
    if not blockers:
        return ["review_latest_freeze_and_approval_before_explicit_training_execution"]
    recommendations: list[str] = []
    if "no_dataset_freeze_manifest" in blockers or "latest_dataset_freeze_manifest_missing" in blockers:
        recommendations.append("create_dataset_freeze_manifest_from_reviewed_sft_export")
    if "no_dry_run_training_approval" in blockers:
        recommendations.append("record_dry_run_training_approval_with_separate_approver")
    if "latest_training_approval_missing_eval_plan" in blockers or "latest_training_approval_missing_required_metrics" in blockers:
        recommendations.append("complete_eval_plan_suite_and_required_metrics")
    if "provider_job_started_detected" in blockers or "dataset_training_started_flag_detected" in blockers:
        recommendations.append("investigate_existing_training_state_before_new_execution")
    if "latest_reviewed_sft_export_missing" in blockers or "latest_training_approval_file_missing" in blockers:
        recommendations.append("restore_or_recreate_missing_manifest_artifact")
    return _dedupe(recommendations)


def _safe_provider_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())[:80].strip("._-")
    return label or "provider_agnostic"
