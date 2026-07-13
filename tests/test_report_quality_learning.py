from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "docs/specs/report_quality_learning"
VALIDATOR_PATH = SPEC_DIR / "validate_correction_artifact.py"
PACKET_VALIDATOR_PATH = SPEC_DIR / "validate_review_packet.py"
TEMPLATE_PATH = SPEC_DIR / "correction_artifact_template.json"
REVIEW_PACKET_EVIDENCE_RUNBOOK = SPEC_DIR / "REVIEW_PACKET_EVIDENCE_RUNBOOK.md"
REVIEW_PACKET_EVIDENCE_CHECKLIST = SPEC_DIR / "review_packet_evidence_checklist.json"
REVIEW_PACKET_SIGNOFF_TEMPLATE = SPEC_DIR / "review_packet_signoff_template.json"
TRAINING_DISCUSSION_DECISION_TEMPLATE = SPEC_DIR / "training_discussion_decision_template.json"
TRAINING_EXPERIMENT_PLAN_REVIEW_TEMPLATE = SPEC_DIR / "training_experiment_plan_review_template.json"
TRAINING_FINAL_APPROVAL_PACKET_REVIEW_TEMPLATE = SPEC_DIR / "training_final_approval_packet_review_template.json"
TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE = SPEC_DIR / "training_final_approval_record_template.json"
TRAINING_NO_COST_FREEZE_TEMPLATE = SPEC_DIR / "training_no_cost_freeze_template.json"
TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_TEMPLATE = (
    SPEC_DIR / "training_no_cost_freeze_handoff_signoff_template.json"
)
TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_TEMPLATE = (
    SPEC_DIR / "training_no_cost_evidence_bundle_handoff_signoff_template.json"
)
TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_TEMPLATE = (
    SPEC_DIR / "training_no_cost_ops_lock_handoff_signoff_template.json"
)
TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_TEMPLATE = (
    SPEC_DIR / "training_no_cost_operator_handoff_signoff_template.json"
)
PACKET_SUMMARY_SCRIPT = REPO_ROOT / "scripts/summarize_report_quality_review_packets.py"
PACKET_ARTIFACT_EXPORT_SCRIPT = REPO_ROOT / "scripts/export_report_quality_artifacts_from_review_packets.py"
PACKET_EVIDENCE_PIPELINE_SCRIPT = REPO_ROOT / "scripts/build_report_quality_review_packet_evidence.py"
PACKET_EVIDENCE_VALIDATOR_SCRIPT = REPO_ROOT / "scripts/validate_report_quality_review_packet_evidence.py"
PACKET_HANDOFF_SCRIPT = REPO_ROOT / "scripts/create_report_quality_review_packet_handoff.py"
PACKET_HANDOFF_VALIDATOR_SCRIPT = REPO_ROOT / "scripts/validate_report_quality_review_packet_handoff.py"
PACKET_SIGNOFF_SCRIPT = REPO_ROOT / "scripts/create_report_quality_review_packet_signoff.py"
PACKET_SIGNOFF_VALIDATOR_SCRIPT = REPO_ROOT / "scripts/validate_report_quality_review_packet_signoff.py"
PACKET_SIGNOFF_SUMMARY_SCRIPT = REPO_ROOT / "scripts/summarize_report_quality_review_packet_signoffs.py"
PACKET_TRAINING_READINESS_SCRIPT = REPO_ROOT / "scripts/create_report_quality_review_packet_training_readiness.py"
PACKET_TRAINING_READINESS_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_readiness.py"
)
PACKET_TRAINING_DISCUSSION_HANDOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_discussion_handoff.py"
)
PACKET_TRAINING_DISCUSSION_HANDOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_discussion_handoff.py"
)
PACKET_TRAINING_DISCUSSION_DECISION_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_discussion_decision.py"
)
PACKET_TRAINING_DISCUSSION_DECISION_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_discussion_decision.py"
)
PACKET_TRAINING_EXPERIMENT_PLAN_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_experiment_plan_draft.py"
)
PACKET_TRAINING_EXPERIMENT_PLAN_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_experiment_plan_draft.py"
)
PACKET_TRAINING_EXPERIMENT_PLAN_REVIEW_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_experiment_plan_review.py"
)
PACKET_TRAINING_EXPERIMENT_PLAN_REVIEW_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_experiment_plan_review.py"
)
PACKET_TRAINING_FINAL_APPROVAL_PACKET_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_final_approval_packet.py"
)
PACKET_TRAINING_FINAL_APPROVAL_PACKET_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_packet.py"
)
PACKET_TRAINING_FINAL_APPROVAL_PACKET_REVIEW_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_final_approval_packet_review.py"
)
PACKET_TRAINING_FINAL_APPROVAL_PACKET_REVIEW_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_packet_review.py"
)
PACKET_TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_final_approval_record_template.py"
)
PACKET_TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_final_approval_record_template.py"
)
PACKET_TRAINING_NO_COST_FREEZE_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_freeze.py"
)
PACKET_TRAINING_NO_COST_FREEZE_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze.py"
)
PACKET_TRAINING_NO_COST_FREEZE_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_freezes.py"
)
PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_freeze_handoff.py"
)
PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff.py"
)
PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py"
)
PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py"
)
PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_archive_closure.py"
)
PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_archive_closure.py"
)
PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_archive_closures.py"
)
PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle.py"
)
PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle.py"
)
PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py"
)
PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py"
)
PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff.py"
)
PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff.py"
)
PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoffs.py"
)
PACKET_TRAINING_NO_COST_RESUME_GUARD_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_resume_guard.py"
)
PACKET_TRAINING_NO_COST_RESUME_GUARD_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_resume_guard.py"
)
PACKET_TRAINING_NO_COST_RESUME_GUARD_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_resume_guards.py"
)
PACKET_TRAINING_NO_COST_OPS_LOCK_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_ops_lock.py"
)
PACKET_TRAINING_NO_COST_OPS_LOCK_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_ops_lock.py"
)
PACKET_TRAINING_NO_COST_OPS_LOCK_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_ops_locks.py"
)
PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_ops_lock_handoff.py"
)
PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_ops_lock_handoff.py"
)
PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff.py"
)
PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff.py"
)
PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoffs.py"
)
PACKET_TRAINING_NO_COST_FINAL_HOLD_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_final_hold.py"
)
PACKET_TRAINING_NO_COST_FINAL_HOLD_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_final_hold.py"
)
PACKET_TRAINING_NO_COST_FINAL_HOLD_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_final_holds.py"
)
PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_closeout_receipt.py"
)
PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_closeout_receipt.py"
)
PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_closeout_receipts.py"
)
PACKET_TRAINING_NO_COST_SERVICE_LOCK_CHECK_SCRIPT = (
    REPO_ROOT / "scripts/check_report_quality_review_packet_training_no_cost_service_lock.py"
)
PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_service_lock_report.py"
)
PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report.py"
)
PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_service_lock_reports.py"
)
PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_service_lock_report_summary.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_operator_handoff.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SUMMARY_SCRIPT = (
    REPO_ROOT / "scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_signoffs.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SUMMARY_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff_summary.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SCRIPT = (
    REPO_ROOT / "scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_VALIDATOR_SCRIPT = (
    REPO_ROOT / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SUMMARY_SCRIPT = (
    REPO_ROOT
    / "scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipts.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SUMMARY_VALIDATOR_SCRIPT = (
    REPO_ROOT
    / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SCRIPT = (
    REPO_ROOT
    / "scripts/create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_VALIDATOR_SCRIPT = (
    REPO_ROOT
    / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SUMMARY_SCRIPT = (
    REPO_ROOT
    / "scripts/summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_packages.py"
)
PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SUMMARY_VALIDATOR_SCRIPT = (
    REPO_ROOT
    / "scripts/validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package_summary.py"
)


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_correction_artifact", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_validator():
    spec = importlib.util.spec_from_file_location("validate_review_packet", PACKET_VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packets",
        PACKET_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_artifact_export_script():
    spec = importlib.util.spec_from_file_location(
        "export_report_quality_artifacts_from_review_packets",
        PACKET_ARTIFACT_EXPORT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_evidence_pipeline_script():
    spec = importlib.util.spec_from_file_location(
        "build_report_quality_review_packet_evidence",
        PACKET_EVIDENCE_PIPELINE_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_evidence_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_evidence",
        PACKET_EVIDENCE_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_handoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_handoff",
        PACKET_HANDOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_handoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_handoff",
        PACKET_HANDOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_signoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_signoff",
        PACKET_SIGNOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_signoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_signoff",
        PACKET_SIGNOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_signoff_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_signoffs",
        PACKET_SIGNOFF_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_readiness_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_readiness",
        PACKET_TRAINING_READINESS_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_readiness_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_readiness",
        PACKET_TRAINING_READINESS_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_discussion_handoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_discussion_handoff",
        PACKET_TRAINING_DISCUSSION_HANDOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_discussion_handoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_discussion_handoff",
        PACKET_TRAINING_DISCUSSION_HANDOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_discussion_decision_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_discussion_decision",
        PACKET_TRAINING_DISCUSSION_DECISION_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_discussion_decision_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_discussion_decision",
        PACKET_TRAINING_DISCUSSION_DECISION_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_experiment_plan_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_experiment_plan_draft",
        PACKET_TRAINING_EXPERIMENT_PLAN_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_experiment_plan_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_experiment_plan_draft",
        PACKET_TRAINING_EXPERIMENT_PLAN_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_experiment_plan_review_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_experiment_plan_review",
        PACKET_TRAINING_EXPERIMENT_PLAN_REVIEW_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_experiment_plan_review_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_experiment_plan_review",
        PACKET_TRAINING_EXPERIMENT_PLAN_REVIEW_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_final_approval_packet_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_final_approval_packet",
        PACKET_TRAINING_FINAL_APPROVAL_PACKET_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_final_approval_packet_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_final_approval_packet",
        PACKET_TRAINING_FINAL_APPROVAL_PACKET_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_final_approval_packet_review_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_final_approval_packet_review",
        PACKET_TRAINING_FINAL_APPROVAL_PACKET_REVIEW_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_final_approval_packet_review_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_final_approval_packet_review",
        PACKET_TRAINING_FINAL_APPROVAL_PACKET_REVIEW_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_final_approval_record_template_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_final_approval_record_template",
        PACKET_TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_final_approval_record_template_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_final_approval_record_template",
        PACKET_TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_freeze_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_freeze",
        PACKET_TRAINING_NO_COST_FREEZE_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_freeze_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_freeze",
        PACKET_TRAINING_NO_COST_FREEZE_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_freeze_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_freezes",
        PACKET_TRAINING_NO_COST_FREEZE_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_freeze_handoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_freeze_handoff",
        PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_freeze_handoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_freeze_handoff",
        PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_freeze_handoff_signoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_freeze_handoff_signoff",
        PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_freeze_handoff_signoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff",
        PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_archive_closure_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_archive_closure",
        PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_archive_closure_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_archive_closure",
        PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_archive_closure_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_archive_closures",
        PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_evidence_bundle_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_evidence_bundle",
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_evidence_bundle_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_evidence_bundle",
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_evidence_bundle_handoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff",
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_evidence_bundle_handoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff",
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_evidence_bundle_handoff_signoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff",
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_evidence_bundle_handoff_signoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff",
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_evidence_bundle_handoff_signoff_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoffs",
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_resume_guard_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_resume_guard",
        PACKET_TRAINING_NO_COST_RESUME_GUARD_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_resume_guard_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_resume_guard",
        PACKET_TRAINING_NO_COST_RESUME_GUARD_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_resume_guard_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_resume_guards",
        PACKET_TRAINING_NO_COST_RESUME_GUARD_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_ops_lock_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_ops_lock",
        PACKET_TRAINING_NO_COST_OPS_LOCK_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_ops_lock_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_ops_lock",
        PACKET_TRAINING_NO_COST_OPS_LOCK_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_ops_lock_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_ops_locks",
        PACKET_TRAINING_NO_COST_OPS_LOCK_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_ops_lock_handoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_ops_lock_handoff",
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_ops_lock_handoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_ops_lock_handoff",
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_ops_lock_handoff_signoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff",
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_ops_lock_handoff_signoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff",
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_ops_lock_handoff_signoff_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoffs",
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_final_hold_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_final_hold",
        PACKET_TRAINING_NO_COST_FINAL_HOLD_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_final_hold_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_final_hold",
        PACKET_TRAINING_NO_COST_FINAL_HOLD_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_final_hold_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_final_holds",
        PACKET_TRAINING_NO_COST_FINAL_HOLD_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_closeout_receipt_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_closeout_receipt",
        PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_closeout_receipt_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_closeout_receipt",
        PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_closeout_receipt_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_closeout_receipts",
        PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_service_lock_check_script():
    spec = importlib.util.spec_from_file_location(
        "check_report_quality_review_packet_training_no_cost_service_lock",
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_CHECK_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_service_lock_report_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_service_lock_report",
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_service_lock_report_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_service_lock_report",
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_service_lock_report_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_service_lock_reports",
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_service_lock_report_summary_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_service_lock_report_summary",
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_operator_handoff",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_signoff_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_operator_handoff_signoff",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_signoff_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_signoff_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_operator_handoff_signoffs",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_signoff_summary_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff_summary",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SUMMARY_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_closeout_receipt_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_closeout_receipt_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_closeout_receipt_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipts",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_closeout_receipt_summary_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SUMMARY_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_closeout_package_script():
    spec = importlib.util.spec_from_file_location(
        "create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_closeout_package_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_closeout_package_summary_script():
    spec = importlib.util.spec_from_file_location(
        "summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_packages",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SUMMARY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_packet_training_no_cost_operator_handoff_closeout_package_summary_validator_script():
    spec = importlib.util.spec_from_file_location(
        "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package_summary",
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SUMMARY_VALIDATOR_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _accepted_payload() -> dict:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    payload["quality_baseline"]["overall_score"] = 0.88
    for key in payload["quality_baseline"]["dimension_scores"]:
        payload["quality_baseline"]["dimension_scores"][key] = 0.86
    payload["correction"]["reviewer"] = "pm-reviewer"
    payload["correction"]["reviewed_at"] = "2026-05-14T12:30:00+09:00"
    for key in payload["correction"]["rationale_by_dimension"]:
        payload["correction"]["rationale_by_dimension"][key] = f"{key} improved through manual correction"
    payload["learning_labels"]["accepted_for_learning"] = True
    payload["learning_labels"]["forbidden_terms_scan"] = "pass"
    payload["learning_labels"]["privacy_security_scan"] = "pass"
    payload["learning_labels"]["human_review_status"] = "accepted"
    payload["learning_labels"]["confirmed_claims"] = ["교정 후 최종 메시지는 사람이 확인함"]
    payload["after"]["final_output_reference"] = "workflow_snapshot:rw_example"
    return payload


def _review_packet(*, ready: bool = True) -> dict:
    dimensions = _accepted_payload()["quality_baseline"]["dimension_scores"]
    preview_artifact = _accepted_payload()
    preview_artifact["artifact_id"] = "rqc_ready"
    preview_artifact["workflow_reference"]["report_workflow_id"] = "rw_quality_ready"
    preview_artifact["document_profile"]["domain"] = "public_procurement"
    quality_payload = {
        "username": "operator",
        "reviewer": "pm-reviewer" if ready else "",
        "reviewed_at": "2026-05-14T12:30:00+09:00" if ready else "",
        "domain": "public_procurement",
        "language": "ko",
        "overall_score": 0.88,
        "dimension_scores": dict(dimensions),
        "hard_failures": [],
        "change_requests": [
            {
                "target": "slide:1",
                "issue": "문제 정의와 기대효과 연결이 약함",
                "correction": "문제-원인-해결-운영-효과 chain으로 재구성",
                "rationale": "승인자가 핵심 근거를 빠르게 확인해야 하기 때문",
            }
        ],
        "rationale_by_dimension": {
            dimension: f"{dimension} manual review rationale"
            for dimension in dimensions
        },
        "after_planning_summary": "교정 후 기획은 정책 문제, 실행 구조, 기대효과를 한 흐름으로 연결합니다.",
        "accepted_for_learning": ready,
        "task_types": ["develop_quality_improvement"],
        "skills": ["develop-document-improver"],
        "confirmed_claims": ["PM 검토 완료 구조"],
        "assumed_claims": [],
        "todo_claims": [],
        "forbidden_terms_scan": "pass" if ready else "not_run",
        "privacy_security_scan": "pass" if ready else "not_run",
        "human_review_status": "accepted" if ready else "pending",
    }
    return {
        "packet_version": "decisiondoc_report_quality_review_packet.v1",
        "exported_at": "2026-05-14T12:35:00+09:00",
        "source": "client_side_review_packet",
        "server_file_written": False,
        "report_workflow": {
            "report_workflow_id": "rw_quality_ready",
            "title": "품질 개선 검토",
            "status": "final_approved" if ready else "draft",
            "learning_opt_in": ready,
            "client": "internal",
            "audience": "PM",
        },
        "quality_payload": quality_payload,
        "checklist": [
            {"label": "Workflow gate", "pass": ready, "pending": not ready, "detail": "", "focus_target_id": ""},
            {"label": "Correction content", "pass": ready, "pending": False, "detail": "", "focus_target_id": ""},
            {"label": "Server preview", "pass": ready, "pending": not ready, "detail": "", "focus_target_id": ""},
        ],
        "preview_validation": {
            "ok": ready,
            "ready_for_learning": ready,
            "errors": [] if ready else ["accepted artifacts require workflow_reference.learning_opt_in=true"],
            "warnings": [],
            "artifact_id": "rqc_ready",
            "schema_version": "decisiondoc_report_quality_correction_artifact.v1",
        } if ready else None,
        "preview_artifact": preview_artifact if ready else None,
        "preview_persisted": False,
        "preview_artifact_id": "rqc_ready" if ready else "",
        "develop_preview": {
            "task_type": "develop_quality_improvement",
            "skill_name": "develop-document-improver",
            "qa": {"passed": True},
            "critique": ["논리 연결 보강 필요"],
            "revision_tasks": ["효과 지표를 근거와 연결"],
            "evidence_status": {"confirmed_claims": ["PM 검토 완료 구조"]},
        },
        "training_boundary": {
            "server_file_written": False,
            "persisted_learning_artifact": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "provider_job_polling_authorized": False,
            "training_execution_authorized": False,
            "model_candidate_emission_authorized": False,
            "model_promotion_authorized": False,
        },
    }


def test_report_quality_learning_docs_and_template_exist():
    for path in (
        SPEC_DIR / "README.md",
        SPEC_DIR / "QUALITY_RUBRIC.md",
        SPEC_DIR / "PILOT_REVIEW_RUNBOOK.md",
        REVIEW_PACKET_EVIDENCE_RUNBOOK,
        REVIEW_PACKET_EVIDENCE_CHECKLIST,
        REVIEW_PACKET_SIGNOFF_TEMPLATE,
        TRAINING_DISCUSSION_DECISION_TEMPLATE,
        TRAINING_EXPERIMENT_PLAN_REVIEW_TEMPLATE,
        TRAINING_FINAL_APPROVAL_PACKET_REVIEW_TEMPLATE,
        TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE,
        TRAINING_NO_COST_FREEZE_TEMPLATE,
        TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_TEMPLATE,
        TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_TEMPLATE,
        TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_TEMPLATE,
        TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_TEMPLATE,
        TEMPLATE_PATH,
        VALIDATOR_PATH,
        PACKET_VALIDATOR_PATH,
        PACKET_SUMMARY_SCRIPT,
        PACKET_ARTIFACT_EXPORT_SCRIPT,
        PACKET_EVIDENCE_PIPELINE_SCRIPT,
        PACKET_EVIDENCE_VALIDATOR_SCRIPT,
        PACKET_HANDOFF_SCRIPT,
        PACKET_HANDOFF_VALIDATOR_SCRIPT,
        PACKET_SIGNOFF_SCRIPT,
        PACKET_SIGNOFF_VALIDATOR_SCRIPT,
        PACKET_SIGNOFF_SUMMARY_SCRIPT,
        PACKET_TRAINING_READINESS_SCRIPT,
        PACKET_TRAINING_READINESS_VALIDATOR_SCRIPT,
        PACKET_TRAINING_DISCUSSION_HANDOFF_SCRIPT,
        PACKET_TRAINING_DISCUSSION_HANDOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_DISCUSSION_DECISION_SCRIPT,
        PACKET_TRAINING_DISCUSSION_DECISION_VALIDATOR_SCRIPT,
        PACKET_TRAINING_EXPERIMENT_PLAN_SCRIPT,
        PACKET_TRAINING_EXPERIMENT_PLAN_VALIDATOR_SCRIPT,
        PACKET_TRAINING_EXPERIMENT_PLAN_REVIEW_SCRIPT,
        PACKET_TRAINING_EXPERIMENT_PLAN_REVIEW_VALIDATOR_SCRIPT,
        PACKET_TRAINING_FINAL_APPROVAL_PACKET_SCRIPT,
        PACKET_TRAINING_FINAL_APPROVAL_PACKET_VALIDATOR_SCRIPT,
        PACKET_TRAINING_FINAL_APPROVAL_PACKET_REVIEW_SCRIPT,
        PACKET_TRAINING_FINAL_APPROVAL_PACKET_REVIEW_VALIDATOR_SCRIPT,
        PACKET_TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE_SCRIPT,
        PACKET_TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_FREEZE_SCRIPT,
        PACKET_TRAINING_NO_COST_FREEZE_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_FREEZE_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SCRIPT,
        PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_SCRIPT,
        PACKET_TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_SCRIPT,
        PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_ARCHIVE_CLOSURE_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_SCRIPT,
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SCRIPT,
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_SCRIPT,
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_RESUME_GUARD_SCRIPT,
        PACKET_TRAINING_NO_COST_RESUME_GUARD_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_RESUME_GUARD_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_OPS_LOCK_SCRIPT,
        PACKET_TRAINING_NO_COST_OPS_LOCK_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPS_LOCK_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SCRIPT,
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_SCRIPT,
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_FINAL_HOLD_SCRIPT,
        PACKET_TRAINING_NO_COST_FINAL_HOLD_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_FINAL_HOLD_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_SCRIPT,
        PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_CLOSEOUT_RECEIPT_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_CHECK_SCRIPT,
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SCRIPT,
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_SERVICE_LOCK_REPORT_SUMMARY_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_SUMMARY_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_RECEIPT_SUMMARY_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_VALIDATOR_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SUMMARY_SCRIPT,
        PACKET_TRAINING_NO_COST_OPERATOR_HANDOFF_CLOSEOUT_PACKAGE_SUMMARY_VALIDATOR_SCRIPT,
    ):
        assert path.exists(), path

    rubric = (SPEC_DIR / "QUALITY_RUBRIC.md").read_text(encoding="utf-8")
    assert "Hard Fail" in rubric
    assert "slide_structure" in rubric
    assert "visual_design" in rubric
    assert "export_readiness" in rubric
    decision_template = json.loads(TRAINING_DISCUSSION_DECISION_TEMPLATE.read_text(encoding="utf-8"))
    assert decision_template["schema_version"] == "decisiondoc_report_quality_training_discussion_decision.v1"
    assert decision_template["decision"] == "pending"
    assert decision_template["decision_boundary"]["training_execution_authorized"] is False
    review_template = json.loads(TRAINING_EXPERIMENT_PLAN_REVIEW_TEMPLATE.read_text(encoding="utf-8"))
    assert review_template["schema_version"] == "decisiondoc_report_quality_training_experiment_plan_review.v1"
    assert review_template["decision"] == "pending"
    assert review_template["review_boundary"]["provider_job_creation_authorized"] is False
    packet_review_template = json.loads(TRAINING_FINAL_APPROVAL_PACKET_REVIEW_TEMPLATE.read_text(encoding="utf-8"))
    assert packet_review_template["schema_version"] == "decisiondoc_report_quality_training_final_approval_packet_review.v1"
    assert packet_review_template["decision"] == "pending"
    assert packet_review_template["review_boundary"]["final_training_approval_granted"] is False
    approval_record_template = json.loads(TRAINING_FINAL_APPROVAL_RECORD_TEMPLATE.read_text(encoding="utf-8"))
    assert (
        approval_record_template["schema_version"]
        == "decisiondoc_report_quality_training_final_approval_record_template.v1"
    )
    assert approval_record_template["approval_state"]["template_only"] is True
    assert approval_record_template["approval_state"]["final_training_approval_granted"] is False
    assert {item["decision"] for item in approval_record_template["required_approvals"]} == {"pending"}
    freeze_template = json.loads(TRAINING_NO_COST_FREEZE_TEMPLATE.read_text(encoding="utf-8"))
    assert freeze_template["schema_version"] == "decisiondoc_report_quality_training_no_cost_freeze.v1"
    assert freeze_template["freeze_state"]["freeze_only"] is True
    assert freeze_template["freeze_state"]["aws_cost_increase_allowed"] is False
    assert freeze_template["freeze_state"]["training_execution_allowed"] is False
    freeze_handoff_signoff_template = json.loads(
        TRAINING_NO_COST_FREEZE_HANDOFF_SIGNOFF_TEMPLATE.read_text(encoding="utf-8")
    )
    assert (
        freeze_handoff_signoff_template["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_freeze_handoff_signoff.v1"
    )
    assert freeze_handoff_signoff_template["decision"] == "pending"
    assert freeze_handoff_signoff_template["signoff_boundary"]["aws_cost_increase_authorized"] is False
    assert freeze_handoff_signoff_template["signoff_boundary"]["training_execution_authorized"] is False
    evidence_bundle_handoff_signoff_template = json.loads(
        TRAINING_NO_COST_EVIDENCE_BUNDLE_HANDOFF_SIGNOFF_TEMPLATE.read_text(encoding="utf-8")
    )
    assert (
        evidence_bundle_handoff_signoff_template["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_evidence_bundle_handoff_signoff.v1"
    )
    assert evidence_bundle_handoff_signoff_template["decision"] == "pending"
    assert (
        evidence_bundle_handoff_signoff_template["acknowledgements"]["evidence_bundle_handoff_reviewed"]
        is False
    )
    assert evidence_bundle_handoff_signoff_template["signoff_boundary"]["aws_cost_increase_authorized"] is False
    assert evidence_bundle_handoff_signoff_template["signoff_boundary"]["training_execution_authorized"] is False
    ops_lock_handoff_signoff_template = json.loads(
        TRAINING_NO_COST_OPS_LOCK_HANDOFF_SIGNOFF_TEMPLATE.read_text(encoding="utf-8")
    )
    assert (
        ops_lock_handoff_signoff_template["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_ops_lock_handoff_signoff.v1"
    )
    assert ops_lock_handoff_signoff_template["decision"] == "pending"
    assert ops_lock_handoff_signoff_template["acknowledgements"]["ops_lock_handoff_reviewed"] is False
    assert ops_lock_handoff_signoff_template["signoff_boundary"]["service_operation_authorized"] is False
    assert ops_lock_handoff_signoff_template["signoff_boundary"]["training_execution_authorized"] is False
    operator_handoff_signoff_template = json.loads(
        TRAINING_NO_COST_OPERATOR_HANDOFF_SIGNOFF_TEMPLATE.read_text(encoding="utf-8")
    )
    assert (
        operator_handoff_signoff_template["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_operator_handoff_signoff.v1"
    )
    assert operator_handoff_signoff_template["decision"] == "pending"
    assert operator_handoff_signoff_template["acknowledgements"]["operator_handoff_reviewed"] is False
    assert operator_handoff_signoff_template["signoff_boundary"]["service_operation_authorized"] is False
    assert operator_handoff_signoff_template["signoff_boundary"]["training_execution_authorized"] is False


def test_review_packet_evidence_runbook_documents_operator_handoff():
    runbook = REVIEW_PACKET_EVIDENCE_RUNBOOK.read_text(encoding="utf-8")
    checklist = json.loads(REVIEW_PACKET_EVIDENCE_CHECKLIST.read_text(encoding="utf-8"))

    assert "Review Packet Evidence Runbook" in runbook
    assert "validate_review_packet.py" in runbook
    assert "build_report_quality_review_packet_evidence.py" in runbook
    assert "validate_report_quality_review_packet_evidence.py" in runbook
    assert "create_report_quality_review_packet_handoff.py" in runbook
    assert "validate_report_quality_review_packet_handoff.py" in runbook
    assert "create_report_quality_review_packet_signoff.py" in runbook
    assert "validate_report_quality_review_packet_signoff.py" in runbook
    assert "summarize_report_quality_review_packet_signoffs.py" in runbook
    assert "create_report_quality_review_packet_training_readiness.py" in runbook
    assert "validate_report_quality_review_packet_training_readiness.py" in runbook
    assert "create_report_quality_review_packet_training_discussion_handoff.py" in runbook
    assert "validate_report_quality_review_packet_training_discussion_handoff.py" in runbook
    assert "create_report_quality_review_packet_training_discussion_decision.py" in runbook
    assert "validate_report_quality_review_packet_training_discussion_decision.py" in runbook
    assert "create_report_quality_review_packet_training_experiment_plan_draft.py" in runbook
    assert "validate_report_quality_review_packet_training_experiment_plan_draft.py" in runbook
    assert "create_report_quality_review_packet_training_experiment_plan_review.py" in runbook
    assert "validate_report_quality_review_packet_training_experiment_plan_review.py" in runbook
    assert "create_report_quality_review_packet_training_final_approval_packet.py" in runbook
    assert "validate_report_quality_review_packet_training_final_approval_packet.py" in runbook
    assert "create_report_quality_review_packet_training_final_approval_packet_review.py" in runbook
    assert "validate_report_quality_review_packet_training_final_approval_packet_review.py" in runbook
    assert "create_report_quality_review_packet_training_final_approval_record_template.py" in runbook
    assert "validate_report_quality_review_packet_training_final_approval_record_template.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_freeze.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_freeze.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_freezes.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_freeze_handoff.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_freeze_handoff.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_freeze_handoff_signoff.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_archive_closure.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_archive_closure.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_archive_closures.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_evidence_bundle.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_evidence_bundle.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoff.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_evidence_bundle_handoff_signoffs.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_resume_guard.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_resume_guard.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_resume_guards.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_ops_lock.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_ops_lock.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_ops_locks.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_ops_lock_handoff.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_ops_lock_handoff.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoff.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_ops_lock_handoff_signoffs.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_final_hold.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_final_hold.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_final_holds.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_closeout_receipt.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_closeout_receipt.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_closeout_receipts.py" in runbook
    assert "check_report_quality_review_packet_training_no_cost_service_lock.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_service_lock_report.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_service_lock_report.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_service_lock_reports.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_service_lock_report_summary.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_operator_handoff.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_operator_handoff.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_operator_handoff_signoffs.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_operator_handoff_signoff_summary.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipts.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_receipt_summary.py" in runbook
    assert "create_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package.py" in runbook
    assert "summarize_report_quality_review_packet_training_no_cost_operator_handoff_closeout_packages.py" in runbook
    assert "validate_report_quality_review_packet_training_no_cost_operator_handoff_closeout_package_summary.py" in runbook
    assert "validate_correction_artifact.py" in runbook
    assert "provider_fine_tune_api_called: `false`" in runbook
    assert "training_execution_started: `false`" in runbook

    assert checklist["checklist_version"] == "decisiondoc_report_quality_review_packet_evidence_checklist.v1"
    command_names = {item["name"] for item in checklist["required_commands"]}
    assert command_names == {
        "validate_single_packet",
        "build_evidence_pipeline",
        "validate_evidence_pipeline",
        "validate_extracted_artifact_jsonl",
        "create_handoff_index",
        "validate_handoff_manifest",
        "create_pending_signoff",
        "validate_reviewer_signoff",
        "summarize_signoffs",
        "create_training_readiness",
        "validate_training_readiness",
        "create_training_discussion_handoff",
        "validate_training_discussion_handoff",
        "create_pending_training_discussion_decision",
        "validate_training_discussion_decision",
        "create_training_experiment_plan_draft",
        "validate_training_experiment_plan_draft",
        "create_pending_training_experiment_plan_review",
        "validate_training_experiment_plan_review",
        "create_training_final_approval_packet",
        "validate_training_final_approval_packet",
        "create_pending_training_final_approval_packet_review",
        "validate_training_final_approval_packet_review",
        "create_training_final_approval_record_template",
        "validate_training_final_approval_record_template",
        "create_training_no_cost_freeze",
        "validate_training_no_cost_freeze",
        "summarize_training_no_cost_freezes",
        "create_training_no_cost_freeze_handoff",
        "validate_training_no_cost_freeze_handoff",
        "create_pending_training_no_cost_freeze_handoff_signoff",
        "validate_training_no_cost_freeze_handoff_signoff",
        "create_training_no_cost_archive_closure",
        "validate_training_no_cost_archive_closure",
        "summarize_training_no_cost_archive_closures",
        "create_training_no_cost_evidence_bundle",
        "validate_training_no_cost_evidence_bundle",
        "create_training_no_cost_evidence_bundle_handoff",
        "validate_training_no_cost_evidence_bundle_handoff",
        "create_pending_training_no_cost_evidence_bundle_handoff_signoff",
        "validate_training_no_cost_evidence_bundle_handoff_signoff",
        "summarize_training_no_cost_evidence_bundle_handoff_signoffs",
        "create_training_no_cost_resume_guard",
        "validate_training_no_cost_resume_guard",
        "summarize_training_no_cost_resume_guards",
        "create_training_no_cost_ops_lock",
        "validate_training_no_cost_ops_lock",
        "summarize_training_no_cost_ops_locks",
        "create_training_no_cost_ops_lock_handoff",
        "validate_training_no_cost_ops_lock_handoff",
        "create_pending_training_no_cost_ops_lock_handoff_signoff",
        "validate_training_no_cost_ops_lock_handoff_signoff",
        "summarize_training_no_cost_ops_lock_handoff_signoffs",
        "create_training_no_cost_final_hold",
        "validate_training_no_cost_final_hold",
        "summarize_training_no_cost_final_holds",
        "create_training_no_cost_closeout_receipt",
        "validate_training_no_cost_closeout_receipt",
        "summarize_training_no_cost_closeout_receipts",
        "check_training_no_cost_service_lock",
        "create_training_no_cost_service_lock_report",
        "validate_training_no_cost_service_lock_report",
        "summarize_training_no_cost_service_lock_reports",
        "validate_training_no_cost_service_lock_report_summary",
        "create_training_no_cost_operator_handoff",
        "validate_training_no_cost_operator_handoff",
        "create_pending_training_no_cost_operator_handoff_signoff",
        "validate_training_no_cost_operator_handoff_signoff",
        "summarize_training_no_cost_operator_handoff_signoffs",
        "validate_training_no_cost_operator_handoff_signoff_summary",
        "create_training_no_cost_operator_handoff_closeout_receipt",
        "validate_training_no_cost_operator_handoff_closeout_receipt",
        "summarize_training_no_cost_operator_handoff_closeout_receipts",
        "validate_training_no_cost_operator_handoff_closeout_receipt_summary",
        "create_training_no_cost_operator_handoff_closeout_package",
        "validate_training_no_cost_operator_handoff_closeout_package",
        "summarize_training_no_cost_operator_handoff_closeout_packages",
        "validate_training_no_cost_operator_handoff_closeout_package_summary",
    }
    boundary = checklist["side_effect_boundary"]
    assert boundary["server_file_written"] is False
    assert boundary["provider_fine_tune_api_called"] is False
    assert boundary["training_execution_started"] is False
    assert "any no-side-effect boundary flag is true" in checklist["stop_gate"]


def test_correction_artifact_template_is_valid_shape_but_not_learning_ready():
    validator = _load_validator()
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is True
    assert result["ready_for_learning"] is False


def test_completed_correction_artifact_is_learning_ready():
    validator = _load_validator()

    result = validator.validate_correction_artifact(_accepted_payload())

    assert result["ok"] is True
    assert result["ready_for_learning"] is True
    assert result["errors"] == []


def test_validator_accepts_exported_jsonl_with_require_ready(tmp_path, capsys):
    validator = _load_validator()
    first = _accepted_payload()
    second = _accepted_payload()
    second["artifact_id"] = "rqc_second"
    export_path = tmp_path / "report_quality_correction_artifacts.jsonl"
    export_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in (first, second)) + "\n",
        encoding="utf-8",
    )

    exit_code = validator.main([str(export_path), "--require-ready"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS report quality correction artifact JSONL validated" in out
    assert "ready_for_learning=true" in out
    assert "artifact_count=2" in out
    assert "min_records=1" in out
    assert "ready_artifacts=2" in out
    assert "not_ready_artifacts=0" in out


def test_validator_enforces_jsonl_min_records(tmp_path, capsys):
    validator = _load_validator()
    export_path = tmp_path / "small_batch.jsonl"
    export_path.write_text(json.dumps(_accepted_payload(), ensure_ascii=False) + "\n", encoding="utf-8")

    exit_code = validator.main([str(export_path), "--require-ready", "--min-records", "2", "--json"])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert result["artifact_count"] == 1
    assert result["min_records"] == 2
    assert "artifact_count 1 is below min_records 2" in "\n".join(result["errors"])


def test_validator_rejects_jsonl_parse_errors(tmp_path, capsys):
    validator = _load_validator()
    export_path = tmp_path / "broken_export.jsonl"
    export_path.write_text(json.dumps(_accepted_payload(), ensure_ascii=False) + "\nnot-json\n", encoding="utf-8")

    exit_code = validator.main([str(export_path), "--require-ready", "--json"])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert result["artifact_count"] == 1
    assert result["ready_artifacts"] == 1
    assert "line 2: invalid JSON" in "\n".join(result["errors"])


def test_validator_require_ready_fails_for_valid_but_pending_json(tmp_path):
    validator = _load_validator()
    artifact_path = tmp_path / "pending_correction_artifact.json"
    artifact_path.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    exit_code = validator.main([str(artifact_path), "--require-ready"])

    assert exit_code == 1


def test_learning_ready_artifact_requires_opt_in():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["workflow_reference"]["learning_opt_in"] = False

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert "learning_opt_in=true" in "\n".join(result["errors"])


def test_correction_artifact_rejects_training_authorization_and_raw_content_keys():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["training_boundary"]["provider_fine_tune_api_call_authorized"] = True
    payload["before"]["raw_attachment"] = "must not be present"

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    joined = "\n".join(result["errors"])
    assert "provider_fine_tune_api_call_authorized must be false" in joined
    assert "forbidden raw or secret-like content key" in joined


def test_completed_artifact_requires_quality_thresholds():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["quality_baseline"]["dimension_scores"]["logic"] = 0.5

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    assert "logic >= 0.75" in "\n".join(result["errors"])


def test_completed_artifact_requires_non_empty_dimension_rationale():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["correction"]["rationale_by_dimension"]["evidence"] = "  "

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert "rationale_by_dimension.evidence must be non-empty" in "\n".join(result["errors"])


def test_completed_artifact_rejects_todo_placeholders():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["after"]["planning_summary"] = "TODO_사람이 승인 가능한 최종 기획 구조 요약"

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert "placeholder value" in "\n".join(result["errors"])


def test_review_packet_validator_accepts_ready_client_packet_with_require_ready(tmp_path, capsys):
    validator = _load_packet_validator()
    packet_path = tmp_path / "report-quality-review-packet-rw_quality_ready.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")

    exit_code = validator.main([str(packet_path), "--require-ready"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS report quality review packet validated" in out
    assert "ready_for_learning=true" in out
    assert "checklist_passed=3/3" in out
    assert "preview_ready_for_learning=true" in out
    assert "preview_artifact_ready_for_learning=true" in out


def test_review_packet_validator_rejects_side_effect_boundary_break():
    validator = _load_packet_validator()
    packet = _review_packet()
    packet["training_boundary"]["provider_fine_tune_api_call_authorized"] = True
    packet["preview_persisted"] = True

    result = validator.validate_review_packet(packet, require_ready=True)

    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    joined = "\n".join(result["errors"])
    assert "provider_fine_tune_api_call_authorized must be false" in joined
    assert "preview_persisted must remain false" in joined


def test_review_packet_validator_cross_checks_preview_artifact():
    validator = _load_packet_validator()
    packet = _review_packet()
    packet["preview_artifact"]["training_boundary"]["provider_job_creation_authorized"] = True

    result = validator.validate_review_packet(packet, require_ready=True)

    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert result["preview_artifact_ok"] is False
    joined = "\n".join(result["errors"])
    assert "preview_artifact: training_boundary.provider_job_creation_authorized must be false" in joined


def test_review_packet_validator_rejects_pending_packet_when_ready_required(tmp_path, capsys):
    validator = _load_packet_validator()
    packet_path = tmp_path / "pending-review-packet.json"
    packet_path.write_text(json.dumps(_review_packet(ready=False), ensure_ascii=False), encoding="utf-8")

    exit_code = validator.main([str(packet_path), "--require-ready", "--json"])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    joined = "\n".join(result["errors"])
    assert "learning_opt_in=true" in joined
    assert "preview_validation" in joined
    assert "every checklist item to pass" in joined


def test_review_packet_batch_summary_accepts_ready_packets(tmp_path, capsys):
    summarizer = _load_packet_summary_script()
    first = _review_packet()
    second = _review_packet()
    second["report_workflow"]["report_workflow_id"] = "rw_quality_ready_002"
    second["preview_artifact_id"] = "rqc_ready_002"
    second["preview_validation"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["workflow_reference"]["report_workflow_id"] = "rw_quality_ready_002"
    first_path = tmp_path / "report-quality-review-packet-rw_quality_ready.json"
    second_path = tmp_path / "report-quality-review-packet-rw_quality_ready_002.json"
    first_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    second_path.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    manifest_path = tmp_path / "pilot-rqp-001-manifest.json"
    markdown_path = tmp_path / "pilot-rqp-001-summary.md"

    exit_code = summarizer.main([
        str(first_path),
        str(second_path),
        "--batch-id",
        "pilot-rqp-001",
        "--min-packets",
        "2",
        "--require-ready",
        "--output",
        str(manifest_path),
        "--markdown",
        str(markdown_path),
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Report quality review packet readiness: PASS" in out
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "decisiondoc_report_quality_review_packet_batch_manifest.v1"
    assert manifest["readiness"]["ok"] is True
    assert manifest["counts"]["packet_count"] == 2
    assert manifest["counts"]["ready_packets"] == 2
    assert manifest["side_effect_boundary"]["server_file_written"] is False
    assert manifest["side_effect_boundary"]["provider_fine_tune_api_called"] is False
    assert manifest["side_effect_boundary"]["training_execution_started"] is False
    assert manifest["packets"][0]["sha256"]
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Review Packet Batch Summary" in markdown
    assert "provider_fine_tune_api_called: `false`" in markdown


def test_review_packet_batch_summary_blocks_pending_packets_when_ready_required(tmp_path):
    summarizer = _load_packet_summary_script()
    ready_path = tmp_path / "ready.json"
    pending_path = tmp_path / "pending.json"
    ready_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    pending_path.write_text(json.dumps(_review_packet(ready=False), ensure_ascii=False), encoding="utf-8")

    manifest = summarizer.create_review_packet_batch_manifest(
        packet_paths=[ready_path, pending_path],
        batch_id="pilot-rqp-pending",
        min_packets=2,
        require_ready=True,
    )

    assert manifest["readiness"]["ok"] is False
    assert manifest["counts"]["packet_count"] == 2
    assert manifest["counts"]["ready_packets"] == 1
    assert "invalid_packets_present" in manifest["readiness"]["blocker_reasons"]
    assert "not_ready_packets_present" in manifest["readiness"]["blocker_reasons"]
    assert manifest["side_effect_boundary"]["persisted_learning_artifact"] is False


def test_review_packet_artifact_export_writes_ready_correction_jsonl(tmp_path, capsys):
    exporter = _load_packet_artifact_export_script()
    validator = _load_validator()
    first = _review_packet()
    second = _review_packet()
    second["report_workflow"]["report_workflow_id"] = "rw_quality_ready_002"
    second["preview_artifact_id"] = "rqc_ready_002"
    second["preview_validation"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["workflow_reference"]["report_workflow_id"] = "rw_quality_ready_002"
    first_path = tmp_path / "packet-one.json"
    second_path = tmp_path / "packet-two.json"
    first_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    second_path.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "from-review-packets.jsonl"
    manifest_path = tmp_path / "from-review-packets-manifest.json"

    exit_code = exporter.main([
        str(first_path),
        str(second_path),
        "--batch-id",
        "pilot-rqp-export",
        "--min-packets",
        "2",
        "--output",
        str(output_path),
        "--manifest",
        str(manifest_path),
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Report quality artifact export: PASS" in out
    lines = [json.loads(line) for line in output_path.read_text(encoding="utf-8").splitlines()]
    assert [line["artifact_id"] for line in lines] == ["rqc_ready", "rqc_ready_002"]
    validation = validator._validate_jsonl_artifacts(output_path, require_ready=True, min_records=2)
    assert validation["ok"] is True
    assert validation["ready_for_learning"] is True
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "decisiondoc_report_quality_review_packet_artifact_export.v1"
    assert manifest["counts"]["exported_artifacts"] == 2
    assert manifest["output"]["jsonl_sha256"]
    assert manifest["side_effect_boundary"]["server_file_written"] is False
    assert manifest["side_effect_boundary"]["provider_fine_tune_api_called"] is False
    assert manifest["side_effect_boundary"]["training_execution_started"] is False


def test_review_packet_artifact_export_blocks_pending_packet_by_default(tmp_path):
    exporter = _load_packet_artifact_export_script()
    ready_path = tmp_path / "ready.json"
    pending_path = tmp_path / "pending.json"
    output_path = tmp_path / "blocked.jsonl"
    ready_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    pending_path.write_text(json.dumps(_review_packet(ready=False), ensure_ascii=False), encoding="utf-8")

    manifest = exporter.export_artifacts_from_review_packets(
        packet_paths=[ready_path, pending_path],
        output_path=output_path,
        batch_id="pilot-rqp-blocked",
        min_packets=2,
        require_ready=True,
    )

    assert manifest["readiness"]["ok"] is False
    assert manifest["counts"]["packet_count"] == 2
    assert manifest["counts"]["exported_artifacts"] == 1
    assert "invalid_packets_present" in manifest["readiness"]["blocker_reasons"]
    assert "not_ready_packets_present" in manifest["readiness"]["blocker_reasons"]
    assert "minimum_exported_artifact_count_not_met" in manifest["readiness"]["blocker_reasons"]
    assert output_path.read_text(encoding="utf-8").count("\n") == 1


def test_review_packet_evidence_pipeline_builds_all_local_outputs(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    first = _review_packet()
    second = _review_packet()
    second["report_workflow"]["report_workflow_id"] = "rw_quality_ready_002"
    second["preview_artifact_id"] = "rqc_ready_002"
    second["preview_validation"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["workflow_reference"]["report_workflow_id"] = "rw_quality_ready_002"
    first_path = tmp_path / "packet-one.json"
    second_path = tmp_path / "packet-two.json"
    first_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    second_path.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "evidence"

    exit_code = pipeline.main([
        str(first_path),
        str(second_path),
        "--batch-id",
        "pilot-rqp-pipeline",
        "--min-packets",
        "2",
        "--output-root",
        str(output_root),
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Report quality review packet evidence pipeline: PASS" in out
    pipeline_manifest_path = output_root / "pilot-rqp-pipeline-evidence-pipeline-manifest.json"
    manifest = json.loads(pipeline_manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "decisiondoc_report_quality_review_packet_evidence_pipeline.v1"
    assert manifest["readiness"]["ok"] is True
    assert manifest["counts"]["packet_count"] == 2
    assert manifest["counts"]["exported_artifacts"] == 2
    assert manifest["counts"]["ready_artifacts"] == 2
    assert manifest["side_effect_boundary"]["provider_fine_tune_api_called"] is False
    assert manifest["side_effect_boundary"]["training_execution_started"] is False
    for output_path in manifest["outputs"].values():
        assert Path(output_path).exists(), output_path
    artifact_jsonl = Path(manifest["outputs"]["artifact_jsonl"])
    assert artifact_jsonl.read_text(encoding="utf-8").count("\n") == 2
    artifact_summary = Path(manifest["outputs"]["artifact_batch_summary"]).read_text(encoding="utf-8")
    assert "Report Quality Correction Batch Summary" in artifact_summary


def test_review_packet_evidence_pipeline_reports_stage_blockers(tmp_path):
    pipeline = _load_packet_evidence_pipeline_script()
    ready_path = tmp_path / "ready.json"
    pending_path = tmp_path / "pending.json"
    ready_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    pending_path.write_text(json.dumps(_review_packet(ready=False), ensure_ascii=False), encoding="utf-8")

    manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[ready_path, pending_path],
        batch_id="pilot-rqp-pipeline-blocked",
        output_root=tmp_path / "blocked",
        min_packets=2,
        require_ready=True,
    )

    assert manifest["readiness"]["ok"] is False
    blockers = "\n".join(manifest["readiness"]["blocker_reasons"])
    assert "review_packet_summary:invalid_packets_present" in blockers
    assert "artifact_export:not_ready_packets_present" in blockers
    assert "artifact_batch_summary:minimum_record_count_not_met" in blockers
    assert manifest["side_effect_boundary"]["server_file_written"] is False


def test_review_packet_evidence_validator_accepts_generated_pipeline(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    validator = _load_packet_evidence_validator_script()
    first = _review_packet()
    second = _review_packet()
    second["report_workflow"]["report_workflow_id"] = "rw_quality_ready_002"
    second["preview_artifact_id"] = "rqc_ready_002"
    second["preview_validation"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["workflow_reference"]["report_workflow_id"] = "rw_quality_ready_002"
    first_path = tmp_path / "packet-one.json"
    second_path = tmp_path / "packet-two.json"
    first_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    second_path.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "evidence"
    pipeline.main([
        str(first_path),
        str(second_path),
        "--batch-id",
        "pilot-rqp-validate",
        "--min-packets",
        "2",
        "--output-root",
        str(output_root),
    ])
    capsys.readouterr()
    manifest_path = output_root / "pilot-rqp-validate-evidence-pipeline-manifest.json"

    exit_code = validator.main([str(manifest_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS report quality review packet evidence validated" in out
    result = validator.validate_review_packet_evidence_manifest(manifest_path)
    assert result["ok"] is True
    assert result["output_count"] == 7
    assert result["validated_outputs"] == [
        "artifact_batch_manifest",
        "artifact_export_manifest",
        "review_packet_manifest",
    ]


def test_review_packet_evidence_validator_rejects_hash_and_boundary_breaks(tmp_path):
    pipeline = _load_packet_evidence_pipeline_script()
    validator = _load_packet_evidence_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-broken",
        output_root=tmp_path / "broken",
        min_packets=1,
        require_ready=True,
    )
    manifest_path = Path(manifest["outputs"]["pipeline_manifest"])
    artifact_jsonl = Path(manifest["outputs"]["artifact_jsonl"])
    artifact_jsonl.write_text(artifact_jsonl.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["side_effect_boundary"]["provider_fine_tune_api_called"] = True
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = validator.validate_review_packet_evidence_manifest(manifest_path)

    assert result["ok"] is False
    joined = "\n".join(result["errors"])
    assert "provider_fine_tune_api_called must be false" in joined
    assert "jsonl_sha256 does not match artifact_jsonl" in joined


def test_review_packet_handoff_generator_creates_reviewer_index(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    first = _review_packet()
    second = _review_packet()
    second["report_workflow"]["report_workflow_id"] = "rw_quality_ready_002"
    second["preview_artifact_id"] = "rqc_ready_002"
    second["preview_validation"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["artifact_id"] = "rqc_ready_002"
    second["preview_artifact"]["workflow_reference"]["report_workflow_id"] = "rw_quality_ready_002"
    first_path = tmp_path / "packet-one.json"
    second_path = tmp_path / "packet-two.json"
    first_path.write_text(json.dumps(first, ensure_ascii=False), encoding="utf-8")
    second_path.write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "evidence"
    pipeline.main([
        str(first_path),
        str(second_path),
        "--batch-id",
        "pilot-rqp-handoff",
        "--min-packets",
        "2",
        "--output-root",
        str(output_root),
    ])
    capsys.readouterr()
    pipeline_manifest = output_root / "pilot-rqp-handoff-evidence-pipeline-manifest.json"

    exit_code = handoff.main([str(pipeline_manifest)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Report quality review packet handoff: PASS" in out
    handoff_manifest_path = output_root / "pilot-rqp-handoff-handoff-manifest.json"
    handoff_index_path = output_root / "pilot-rqp-handoff-handoff-index.md"
    handoff_manifest = json.loads(handoff_manifest_path.read_text(encoding="utf-8"))
    assert handoff_manifest["schema_version"] == "decisiondoc_report_quality_review_packet_handoff.v1"
    assert handoff_manifest["handoff_index_path"] == str(handoff_index_path)
    assert handoff_manifest["handoff_manifest_path"] == str(handoff_manifest_path)
    assert handoff_manifest["readiness"]["ok"] is True
    assert handoff_manifest["counts"]["packet_count"] == 2
    assert handoff_manifest["counts"]["ready_artifacts"] == 2
    assert handoff_manifest["side_effect_boundary"]["provider_fine_tune_api_called"] is False
    assert handoff_manifest["side_effect_boundary"]["training_execution_started"] is False
    assert handoff_manifest["handoff_files"]["artifact_jsonl"]["exists"] is True
    assert handoff_manifest["handoff_files"]["artifact_jsonl"]["sha256"]
    handoff_index = handoff_index_path.read_text(encoding="utf-8")
    assert "Report Quality Review Packet Handoff" in handoff_index
    assert "training_authorized: `false`" in handoff_index
    assert "provider_fine_tune_api_called: `false`" in handoff_index


def test_review_packet_handoff_validator_accepts_generated_handoff(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    validator = _load_packet_handoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "evidence"
    pipeline.main([
        str(packet_path),
        "--batch-id",
        "pilot-rqp-handoff-validate",
        "--min-packets",
        "1",
        "--output-root",
        str(output_root),
    ])
    capsys.readouterr()
    pipeline_manifest = output_root / "pilot-rqp-handoff-validate-evidence-pipeline-manifest.json"
    handoff.main([str(pipeline_manifest)])
    capsys.readouterr()
    handoff_manifest = output_root / "pilot-rqp-handoff-validate-handoff-manifest.json"

    exit_code = validator.main([str(handoff_manifest)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS report quality review packet handoff validated" in out
    result = validator.validate_review_packet_handoff_manifest(handoff_manifest)
    assert result["ok"] is True
    assert result["handoff_file_count"] == 7
    assert result["handoff_index_path"].endswith("pilot-rqp-handoff-validate-handoff-index.md")


def test_review_packet_handoff_validator_rejects_hash_and_boundary_breaks(tmp_path):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    validator = _load_packet_handoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "broken"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-handoff-broken",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    handoff_manifest = handoff.create_review_packet_handoff(
        pipeline_manifest_path=Path(pipeline_manifest["outputs"]["pipeline_manifest"]),
    )
    handoff_manifest_path = Path(handoff_manifest["handoff_manifest_path"])
    artifact_summary = Path(handoff_manifest["handoff_files"]["artifact_batch_summary"]["path"])
    artifact_summary.write_text(artifact_summary.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    payload = json.loads(handoff_manifest_path.read_text(encoding="utf-8"))
    payload["side_effect_boundary"]["training_execution_started"] = True
    handoff_manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = validator.validate_review_packet_handoff_manifest(handoff_manifest_path)

    assert result["ok"] is False
    joined = "\n".join(result["errors"])
    assert "training_execution_started must be false" in joined
    assert "handoff_files.artifact_batch_summary.sha256 does not match file" in joined


def test_review_packet_signoff_generator_creates_pending_record_from_handoff(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    generator = _load_packet_signoff_script()
    validator = _load_packet_signoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "generated-signoff"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-generated-signoff",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    handoff_manifest = handoff.create_review_packet_handoff(
        pipeline_manifest_path=Path(pipeline_manifest["outputs"]["pipeline_manifest"]),
    )
    handoff_manifest_path = Path(handoff_manifest["handoff_manifest_path"])
    signoff_path = output_root / "pilot-rqp-generated-signoff-signoff.json"

    exit_code = generator.main([
        str(handoff_manifest_path),
        "--output",
        str(signoff_path),
        "--signoff-id",
        "rqp_signoff_generated001",
        "--created-at",
        "2026-05-14T13:05:00+09:00",
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Report quality review packet pending signoff: PASS" in out
    assert "training_boundary=not_authorized" in out
    signoff = json.loads(signoff_path.read_text(encoding="utf-8"))
    assert signoff["signoff_id"] == "rqp_signoff_generated001"
    assert signoff["decision"] == "pending"
    assert signoff["created_at"] == "2026-05-14T13:05:00+09:00"
    assert signoff["handoff_manifest_path"] == str(handoff_manifest_path.resolve())
    assert signoff["handoff_manifest_sha256"] == validator._sha256(handoff_manifest_path)
    assert signoff["reviewer"] == {"name": "", "title_or_team": "", "reviewed_at": ""}
    assert signoff["evidence_reviewed"] == []
    assert signoff["generation_context"]["handoff_validation"]["ok"] is True
    assert signoff["generation_context"]["evidence_to_review"]
    assert all(value is False for value in signoff["acknowledgements"].values())
    assert all(value is False for value in signoff["signoff_boundary"].values())
    assert signoff["generation_boundary"]["training_execution_started"] is False
    pending_result = validator.validate_review_packet_signoff(signoff, require_complete=False)
    completed_result = validator.validate_review_packet_signoff(signoff, require_complete=True)
    assert pending_result["ok"] is True
    assert pending_result["completed"] is False
    assert completed_result["ok"] is False
    assert "signoff decision must be completed" in "\n".join(completed_result["errors"])


def test_review_packet_signoff_validator_accepts_completed_record(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    validator = _load_packet_signoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "signoff"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-signoff",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    handoff_manifest = handoff.create_review_packet_handoff(
        pipeline_manifest_path=Path(pipeline_manifest["outputs"]["pipeline_manifest"]),
    )
    handoff_manifest_path = Path(handoff_manifest["handoff_manifest_path"])
    signoff = json.loads(REVIEW_PACKET_SIGNOFF_TEMPLATE.read_text(encoding="utf-8"))
    signoff.update({
        "signoff_id": "rqp_signoff_001",
        "created_at": "2026-05-14T13:10:00+09:00",
        "handoff_manifest_path": str(handoff_manifest_path),
        "handoff_manifest_sha256": validator._sha256(handoff_manifest_path),
        "decision": "accepted",
        "evidence_reviewed": [
            "pilot-rqp-signoff-handoff-index.md",
            "pilot-rqp-signoff-from-review-packets.jsonl",
        ],
    })
    signoff["reviewer"] = {
        "name": "pm-reviewer",
        "title_or_team": "Product/PM",
        "reviewed_at": "2026-05-14T13:20:00+09:00",
    }
    signoff["findings"]["summary"] = "Review packet evidence is ready for human training review discussion."
    for key in signoff["acknowledgements"]:
        signoff["acknowledgements"][key] = True
    signoff_path = tmp_path / "pilot-rqp-signoff.json"
    signoff_path.write_text(json.dumps(signoff, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = validator.main([str(signoff_path), "--require-complete"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS report quality review packet signoff validated" in out
    assert "completed=true" in out
    result = validator.validate_review_packet_signoff(signoff, require_complete=True)
    assert result["ok"] is True
    assert result["completed"] is True
    assert result["handoff_validation_ok"] is True


def test_review_packet_signoff_validator_rejects_pending_and_boundary_break(tmp_path):
    validator = _load_packet_signoff_validator_script()
    pending = json.loads(REVIEW_PACKET_SIGNOFF_TEMPLATE.read_text(encoding="utf-8"))

    pending_result = validator.validate_review_packet_signoff(pending, require_complete=True)

    assert pending_result["ok"] is False
    assert "signoff decision must be completed" in "\n".join(pending_result["errors"])

    broken = json.loads(REVIEW_PACKET_SIGNOFF_TEMPLATE.read_text(encoding="utf-8"))
    broken.update({
        "signoff_id": "rqp_signoff_broken",
        "created_at": "2026-05-14T13:10:00+09:00",
        "decision": "accepted",
        "evidence_reviewed": ["handoff-index.md"],
    })
    broken["reviewer"] = {
        "name": "pm-reviewer",
        "title_or_team": "Product/PM",
        "reviewed_at": "2026-05-14T13:20:00+09:00",
    }
    broken["findings"]["summary"] = "Reviewed."
    for key in broken["acknowledgements"]:
        broken["acknowledgements"][key] = True
    broken["signoff_boundary"]["provider_fine_tune_api_call_authorized"] = True

    broken_result = validator.validate_review_packet_signoff(broken, require_complete=True)

    assert broken_result["ok"] is False
    joined = "\n".join(broken_result["errors"])
    assert "completed signoff requires handoff_manifest_path" in joined
    assert "provider_fine_tune_api_call_authorized must be false" in joined


def test_review_packet_signoff_summary_reports_pending_and_completed_records(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    generator = _load_packet_signoff_script()
    summarizer = _load_packet_signoff_summary_script()
    validator = _load_packet_signoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "signoff-summary"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-signoff-summary",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    handoff_manifest = handoff.create_review_packet_handoff(
        pipeline_manifest_path=Path(pipeline_manifest["outputs"]["pipeline_manifest"]),
    )
    handoff_manifest_path = Path(handoff_manifest["handoff_manifest_path"])
    pending = generator.build_pending_review_packet_signoff(
        handoff_manifest_path=handoff_manifest_path,
        signoff_id="rqp_signoff_summarypending",
        created_at="2026-05-14T13:05:00+09:00",
    )
    pending_path = output_root / "pending-signoff.json"
    pending_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    completed = json.loads(json.dumps(pending))
    completed.update({
        "signoff_id": "rqp_signoff_summarydone",
        "created_at": "2026-05-14T13:10:00+09:00",
        "decision": "accepted",
        "evidence_reviewed": ["pilot-rqp-signoff-summary-handoff-index.md"],
    })
    completed["reviewer"] = {
        "name": "pm-reviewer",
        "title_or_team": "Product/PM",
        "reviewed_at": "2026-05-14T13:20:00+09:00",
    }
    completed["findings"]["summary"] = "Review packet sign-off evidence is complete."
    for key in completed["acknowledgements"]:
        completed["acknowledgements"][key] = True
    completed["handoff_manifest_sha256"] = validator._sha256(handoff_manifest_path)
    completed_path = output_root / "completed-signoff.json"
    completed_path.write_text(json.dumps(completed, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path = output_root / "signoff-summary.json"
    markdown_path = output_root / "signoff-summary.md"

    exit_code = summarizer.main([
        str(pending_path),
        str(completed_path),
        "--generated-at",
        "2026-05-14T14:00:00+09:00",
        "--output",
        str(summary_path),
        "--markdown",
        str(markdown_path),
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Report quality review packet signoff summary: PASS" in out
    assert "training_boundary=not_authorized" in out
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["schema_version"] == "decisiondoc_report_quality_review_packet_signoff_summary.v1"
    assert summary["ok"] is True
    assert summary["readiness"]["status"] == "pending_or_follow_up_required"
    assert summary["counts"]["record_count"] == 2
    assert summary["counts"]["completed_record_count"] == 1
    assert summary["counts"]["pending_record_count"] == 1
    assert summary["counts"]["invalid_record_count"] == 0
    assert summary["counts"]["decision_counts"]["accepted"] == 1
    assert summary["counts"]["decision_counts"]["pending"] == 1
    assert summary["side_effect_boundary"]["training_execution_started"] is False
    assert "training_authorized: `false`" in markdown_path.read_text(encoding="utf-8")

    strict_summary = summarizer.build_signoff_summary(
        [pending_path, completed_path],
        generated_at="2026-05-14T14:00:00+09:00",
        require_complete=True,
    )
    assert strict_summary["ok"] is False
    assert strict_summary["readiness"]["require_complete_ok"] is False


def test_review_packet_signoff_summary_flags_boundary_break(tmp_path):
    summarizer = _load_packet_signoff_summary_script()
    broken = json.loads(REVIEW_PACKET_SIGNOFF_TEMPLATE.read_text(encoding="utf-8"))
    broken["signoff_id"] = "rqp_signoff_summarybroken"
    broken["created_at"] = "2026-05-14T13:10:00+09:00"
    broken["signoff_boundary"]["training_execution_authorized"] = True
    broken_path = tmp_path / "broken-signoff.json"
    broken_path.write_text(json.dumps(broken, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = summarizer.build_signoff_summary([broken_path])

    assert summary["ok"] is False
    assert summary["counts"]["record_count"] == 1
    assert summary["counts"]["invalid_record_count"] == 1
    assert summary["records"][0]["record_status"] == "attention_required_boundary_violation"
    assert "signoff_boundary.training_execution_authorized must be false" in "\n".join(
        summary["records"][0]["boundary_findings"]
    )


def test_review_packet_training_readiness_accepts_completed_signoff_summary(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    generator = _load_packet_signoff_script()
    summarizer = _load_packet_signoff_summary_script()
    readiness = _load_packet_training_readiness_script()
    validator = _load_packet_signoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "training-readiness"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-training-ready",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    evidence_manifest_path = Path(pipeline_manifest["outputs"]["pipeline_manifest"])
    handoff_manifest = handoff.create_review_packet_handoff(pipeline_manifest_path=evidence_manifest_path)
    handoff_manifest_path = Path(handoff_manifest["handoff_manifest_path"])
    completed = generator.build_pending_review_packet_signoff(
        handoff_manifest_path=handoff_manifest_path,
        signoff_id="rqp_signoff_readinessdone",
        created_at="2026-05-14T13:05:00+09:00",
    )
    completed.update({
        "decision": "accepted",
        "evidence_reviewed": ["pilot-rqp-training-ready-handoff-index.md"],
    })
    completed["reviewer"] = {
        "name": "pm-reviewer",
        "title_or_team": "Product/PM",
        "reviewed_at": "2026-05-14T13:20:00+09:00",
    }
    completed["findings"]["summary"] = "Review packet evidence is complete for training discussion."
    for key in completed["acknowledgements"]:
        completed["acknowledgements"][key] = True
    completed["handoff_manifest_sha256"] = validator._sha256(handoff_manifest_path)
    signoff_path = output_root / "completed-signoff.json"
    signoff_path.write_text(json.dumps(completed, ensure_ascii=False, indent=2), encoding="utf-8")
    signoff_summary_path = output_root / "pilot-rqp-training-ready-signoff-summary.json"
    summarizer.main([
        str(signoff_path),
        "--require-complete",
        "--output",
        str(signoff_summary_path),
    ])
    capsys.readouterr()
    readiness_path = output_root / "pilot-rqp-training-ready-training-readiness-manifest.json"
    readiness_md_path = output_root / "pilot-rqp-training-ready-training-readiness.md"

    exit_code = readiness.main([
        str(evidence_manifest_path),
        str(signoff_summary_path),
        "--generated-at",
        "2026-05-14T14:30:00+09:00",
        "--min-ready-artifacts",
        "1",
        "--output",
        str(readiness_path),
        "--markdown",
        str(readiness_md_path),
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Report quality review packet training readiness: PASS" in out
    assert "ready_for_training_discussion=true" in out
    assert "training_boundary=not_authorized" in out
    manifest = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "decisiondoc_report_quality_review_packet_training_readiness.v1"
    assert manifest["readiness"]["ok"] is True
    assert manifest["readiness"]["ready_for_training_discussion"] is True
    assert manifest["counts"]["ready_artifacts"] == 1
    assert manifest["counts"]["completed_signoff_count"] == 1
    assert manifest["counts"]["invalid_signoff_count"] == 0
    assert manifest["validations"]["evidence_pipeline"]["ok"] is True
    assert manifest["validations"]["signoff_summary_require_complete_ok"] is True
    assert manifest["side_effect_boundary"]["training_execution_started"] is False
    assert "training_authorized: `false`" in readiness_md_path.read_text(encoding="utf-8")


def test_review_packet_training_readiness_blocks_pending_signoff_and_boundary_break(tmp_path):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    generator = _load_packet_signoff_script()
    summarizer = _load_packet_signoff_summary_script()
    readiness = _load_packet_training_readiness_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "training-readiness-blocked"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-training-blocked",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    evidence_manifest_path = Path(pipeline_manifest["outputs"]["pipeline_manifest"])
    handoff_manifest = handoff.create_review_packet_handoff(pipeline_manifest_path=evidence_manifest_path)
    pending = generator.build_pending_review_packet_signoff(
        handoff_manifest_path=Path(handoff_manifest["handoff_manifest_path"]),
        signoff_id="rqp_signoff_readinesspending",
        created_at="2026-05-14T13:05:00+09:00",
    )
    pending_path = output_root / "pending-signoff.json"
    pending_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    pending_summary = summarizer.build_signoff_summary([pending_path], require_complete=False)
    pending_summary_path = output_root / "pending-summary.json"
    pending_summary_path.write_text(json.dumps(pending_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    blocked = readiness.build_training_readiness_manifest(
        evidence_manifest_path=evidence_manifest_path,
        signoff_summary_path=pending_summary_path,
        min_ready_artifacts=1,
        require_completed_signoffs=True,
    )

    assert blocked["readiness"]["ok"] is False
    joined = "\n".join(blocked["errors"])
    assert "signoff_summary.readiness.require_complete_ok must be true" in joined
    assert "signoff record rqp_signoff_readinesspending must be completed" in joined

    broken_summary = json.loads(json.dumps(pending_summary))
    broken_summary["side_effect_boundary"]["training_execution_started"] = True
    broken_summary_path = output_root / "broken-summary.json"
    broken_summary_path.write_text(json.dumps(broken_summary, ensure_ascii=False, indent=2), encoding="utf-8")

    broken = readiness.build_training_readiness_manifest(
        evidence_manifest_path=evidence_manifest_path,
        signoff_summary_path=broken_summary_path,
    )

    assert broken["readiness"]["ok"] is False
    assert "signoff_summary: $.side_effect_boundary.training_execution_started must be false" in "\n".join(
        broken["errors"]
    )


def test_review_packet_training_readiness_validator_accepts_generated_manifest(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    generator = _load_packet_signoff_script()
    summarizer = _load_packet_signoff_summary_script()
    readiness = _load_packet_training_readiness_script()
    validator = _load_packet_training_readiness_validator_script()
    signoff_validator = _load_packet_signoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "readiness-validator"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-readiness-validator",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    evidence_manifest_path = Path(pipeline_manifest["outputs"]["pipeline_manifest"])
    handoff_manifest = handoff.create_review_packet_handoff(pipeline_manifest_path=evidence_manifest_path)
    handoff_manifest_path = Path(handoff_manifest["handoff_manifest_path"])
    signoff = generator.build_pending_review_packet_signoff(
        handoff_manifest_path=handoff_manifest_path,
        signoff_id="rqp_signoff_readinessvalid",
        created_at="2026-05-14T13:05:00+09:00",
    )
    signoff.update({
        "decision": "accepted",
        "evidence_reviewed": ["pilot-rqp-readiness-validator-handoff-index.md"],
    })
    signoff["reviewer"] = {
        "name": "pm-reviewer",
        "title_or_team": "Product/PM",
        "reviewed_at": "2026-05-14T13:20:00+09:00",
    }
    signoff["findings"]["summary"] = "Review packet readiness evidence is complete."
    for key in signoff["acknowledgements"]:
        signoff["acknowledgements"][key] = True
    signoff["handoff_manifest_sha256"] = signoff_validator._sha256(handoff_manifest_path)
    signoff_path = output_root / "completed-signoff.json"
    signoff_path.write_text(json.dumps(signoff, ensure_ascii=False, indent=2), encoding="utf-8")
    signoff_summary_path = output_root / "signoff-summary.json"
    summarizer.main([str(signoff_path), "--require-complete", "--output", str(signoff_summary_path)])
    capsys.readouterr()
    readiness_path = output_root / "training-readiness-manifest.json"
    readiness.main([
        str(evidence_manifest_path),
        str(signoff_summary_path),
        "--output",
        str(readiness_path),
    ])
    capsys.readouterr()

    exit_code = validator.main([str(readiness_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS report quality review packet training readiness validated" in out
    assert "ready_for_training_discussion=true" in out
    result = validator.validate_training_readiness_manifest(readiness_path)
    assert result["ok"] is True
    assert result["evidence_validation_ok"] is True
    assert result["signoff_summary_ok"] is True


def test_review_packet_training_readiness_validator_rejects_hash_and_boundary_break(tmp_path):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    generator = _load_packet_signoff_script()
    summarizer = _load_packet_signoff_summary_script()
    readiness = _load_packet_training_readiness_script()
    validator = _load_packet_training_readiness_validator_script()
    signoff_validator = _load_packet_signoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "readiness-validator-broken"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-readiness-broken",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    evidence_manifest_path = Path(pipeline_manifest["outputs"]["pipeline_manifest"])
    handoff_manifest = handoff.create_review_packet_handoff(pipeline_manifest_path=evidence_manifest_path)
    handoff_manifest_path = Path(handoff_manifest["handoff_manifest_path"])
    signoff = generator.build_pending_review_packet_signoff(
        handoff_manifest_path=handoff_manifest_path,
        signoff_id="rqp_signoff_readinessbroken",
        created_at="2026-05-14T13:05:00+09:00",
    )
    signoff.update({
        "decision": "accepted",
        "evidence_reviewed": ["pilot-rqp-readiness-broken-handoff-index.md"],
    })
    signoff["reviewer"] = {
        "name": "pm-reviewer",
        "title_or_team": "Product/PM",
        "reviewed_at": "2026-05-14T13:20:00+09:00",
    }
    signoff["findings"]["summary"] = "Review packet readiness evidence is complete."
    for key in signoff["acknowledgements"]:
        signoff["acknowledgements"][key] = True
    signoff["handoff_manifest_sha256"] = signoff_validator._sha256(handoff_manifest_path)
    signoff_path = output_root / "completed-signoff.json"
    signoff_path.write_text(json.dumps(signoff, ensure_ascii=False, indent=2), encoding="utf-8")
    signoff_summary_path = output_root / "signoff-summary.json"
    signoff_summary = summarizer.build_signoff_summary([signoff_path], require_complete=True)
    signoff_summary_path.write_text(json.dumps(signoff_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    readiness_manifest = readiness.build_training_readiness_manifest(
        evidence_manifest_path=evidence_manifest_path,
        signoff_summary_path=signoff_summary_path,
    )
    readiness_manifest["inputs"]["signoff_summary_sha256"] = "bad-sha256"
    readiness_manifest["side_effect_boundary"]["training_execution_started"] = True
    readiness_path = output_root / "training-readiness-manifest.json"
    readiness_path.write_text(json.dumps(readiness_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    result = validator.validate_training_readiness_manifest(readiness_path)

    assert result["ok"] is False
    joined = "\n".join(result["errors"])
    assert "inputs.signoff_summary_sha256 does not match referenced file" in joined
    assert "training_readiness_manifest: $.side_effect_boundary.training_execution_started must be false" in joined


def test_review_packet_training_discussion_handoff_packages_ready_bundle(tmp_path, capsys):
    pipeline = _load_packet_evidence_pipeline_script()
    handoff = _load_packet_handoff_script()
    generator = _load_packet_signoff_script()
    summarizer = _load_packet_signoff_summary_script()
    readiness = _load_packet_training_readiness_script()
    discussion_handoff = _load_packet_training_discussion_handoff_script()
    discussion_handoff_validator = _load_packet_training_discussion_handoff_validator_script()
    discussion_decision = _load_packet_training_discussion_decision_script()
    discussion_decision_validator = _load_packet_training_discussion_decision_validator_script()
    experiment_plan = _load_packet_training_experiment_plan_script()
    experiment_plan_validator = _load_packet_training_experiment_plan_validator_script()
    experiment_plan_review = _load_packet_training_experiment_plan_review_script()
    experiment_plan_review_validator = _load_packet_training_experiment_plan_review_validator_script()
    final_packet = _load_packet_training_final_approval_packet_script()
    final_packet_validator = _load_packet_training_final_approval_packet_validator_script()
    final_packet_review = _load_packet_training_final_approval_packet_review_script()
    final_packet_review_validator = _load_packet_training_final_approval_packet_review_validator_script()
    final_approval_record_template = _load_packet_training_final_approval_record_template_script()
    final_approval_record_template_validator = (
        _load_packet_training_final_approval_record_template_validator_script()
    )
    no_cost_freeze = _load_packet_training_no_cost_freeze_script()
    no_cost_freeze_validator = _load_packet_training_no_cost_freeze_validator_script()
    no_cost_freeze_summary = _load_packet_training_no_cost_freeze_summary_script()
    no_cost_freeze_handoff = _load_packet_training_no_cost_freeze_handoff_script()
    no_cost_freeze_handoff_validator = _load_packet_training_no_cost_freeze_handoff_validator_script()
    no_cost_freeze_handoff_signoff = _load_packet_training_no_cost_freeze_handoff_signoff_script()
    no_cost_freeze_handoff_signoff_validator = (
        _load_packet_training_no_cost_freeze_handoff_signoff_validator_script()
    )
    no_cost_archive_closure = _load_packet_training_no_cost_archive_closure_script()
    no_cost_archive_closure_validator = _load_packet_training_no_cost_archive_closure_validator_script()
    no_cost_archive_closure_summary = _load_packet_training_no_cost_archive_closure_summary_script()
    no_cost_evidence_bundle = _load_packet_training_no_cost_evidence_bundle_script()
    no_cost_evidence_bundle_validator = _load_packet_training_no_cost_evidence_bundle_validator_script()
    no_cost_evidence_bundle_handoff = _load_packet_training_no_cost_evidence_bundle_handoff_script()
    no_cost_evidence_bundle_handoff_validator = (
        _load_packet_training_no_cost_evidence_bundle_handoff_validator_script()
    )
    no_cost_evidence_bundle_handoff_signoff = (
        _load_packet_training_no_cost_evidence_bundle_handoff_signoff_script()
    )
    no_cost_evidence_bundle_handoff_signoff_validator = (
        _load_packet_training_no_cost_evidence_bundle_handoff_signoff_validator_script()
    )
    no_cost_evidence_bundle_handoff_signoff_summary = (
        _load_packet_training_no_cost_evidence_bundle_handoff_signoff_summary_script()
    )
    no_cost_resume_guard = _load_packet_training_no_cost_resume_guard_script()
    no_cost_resume_guard_validator = _load_packet_training_no_cost_resume_guard_validator_script()
    no_cost_resume_guard_summary = _load_packet_training_no_cost_resume_guard_summary_script()
    no_cost_ops_lock = _load_packet_training_no_cost_ops_lock_script()
    no_cost_ops_lock_validator = _load_packet_training_no_cost_ops_lock_validator_script()
    no_cost_ops_lock_summary = _load_packet_training_no_cost_ops_lock_summary_script()
    no_cost_ops_lock_handoff = _load_packet_training_no_cost_ops_lock_handoff_script()
    no_cost_ops_lock_handoff_validator = _load_packet_training_no_cost_ops_lock_handoff_validator_script()
    no_cost_ops_lock_handoff_signoff = _load_packet_training_no_cost_ops_lock_handoff_signoff_script()
    no_cost_ops_lock_handoff_signoff_validator = (
        _load_packet_training_no_cost_ops_lock_handoff_signoff_validator_script()
    )
    no_cost_ops_lock_handoff_signoff_summary = (
        _load_packet_training_no_cost_ops_lock_handoff_signoff_summary_script()
    )
    no_cost_final_hold = _load_packet_training_no_cost_final_hold_script()
    no_cost_final_hold_validator = _load_packet_training_no_cost_final_hold_validator_script()
    no_cost_final_hold_summary = _load_packet_training_no_cost_final_hold_summary_script()
    no_cost_closeout_receipt = _load_packet_training_no_cost_closeout_receipt_script()
    no_cost_closeout_receipt_validator = _load_packet_training_no_cost_closeout_receipt_validator_script()
    no_cost_closeout_receipt_summary = _load_packet_training_no_cost_closeout_receipt_summary_script()
    no_cost_service_lock_check = _load_packet_training_no_cost_service_lock_check_script()
    no_cost_service_lock_report = _load_packet_training_no_cost_service_lock_report_script()
    no_cost_service_lock_report_validator = _load_packet_training_no_cost_service_lock_report_validator_script()
    no_cost_service_lock_report_summary = _load_packet_training_no_cost_service_lock_report_summary_script()
    no_cost_service_lock_report_summary_validator = (
        _load_packet_training_no_cost_service_lock_report_summary_validator_script()
    )
    no_cost_operator_handoff = _load_packet_training_no_cost_operator_handoff_script()
    no_cost_operator_handoff_validator = _load_packet_training_no_cost_operator_handoff_validator_script()
    no_cost_operator_handoff_signoff = _load_packet_training_no_cost_operator_handoff_signoff_script()
    no_cost_operator_handoff_signoff_validator = (
        _load_packet_training_no_cost_operator_handoff_signoff_validator_script()
    )
    no_cost_operator_handoff_signoff_summary = _load_packet_training_no_cost_operator_handoff_signoff_summary_script()
    no_cost_operator_handoff_signoff_summary_validator = (
        _load_packet_training_no_cost_operator_handoff_signoff_summary_validator_script()
    )
    no_cost_operator_handoff_closeout_receipt = (
        _load_packet_training_no_cost_operator_handoff_closeout_receipt_script()
    )
    no_cost_operator_handoff_closeout_receipt_validator = (
        _load_packet_training_no_cost_operator_handoff_closeout_receipt_validator_script()
    )
    no_cost_operator_handoff_closeout_receipt_summary = (
        _load_packet_training_no_cost_operator_handoff_closeout_receipt_summary_script()
    )
    no_cost_operator_handoff_closeout_receipt_summary_validator = (
        _load_packet_training_no_cost_operator_handoff_closeout_receipt_summary_validator_script()
    )
    no_cost_operator_handoff_closeout_package = (
        _load_packet_training_no_cost_operator_handoff_closeout_package_script()
    )
    no_cost_operator_handoff_closeout_package_validator = (
        _load_packet_training_no_cost_operator_handoff_closeout_package_validator_script()
    )
    no_cost_operator_handoff_closeout_package_summary = (
        _load_packet_training_no_cost_operator_handoff_closeout_package_summary_script()
    )
    no_cost_operator_handoff_closeout_package_summary_validator = (
        _load_packet_training_no_cost_operator_handoff_closeout_package_summary_validator_script()
    )
    signoff_validator = _load_packet_signoff_validator_script()
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(_review_packet(), ensure_ascii=False), encoding="utf-8")
    output_root = tmp_path / "discussion-handoff"
    pipeline_manifest = pipeline.build_review_packet_evidence_pipeline(
        packet_paths=[packet_path],
        batch_id="pilot-rqp-discussion",
        output_root=output_root,
        min_packets=1,
        require_ready=True,
    )
    evidence_manifest_path = Path(pipeline_manifest["outputs"]["pipeline_manifest"])
    handoff_manifest = handoff.create_review_packet_handoff(pipeline_manifest_path=evidence_manifest_path)
    handoff_manifest_path = Path(handoff_manifest["handoff_manifest_path"])
    signoff = generator.build_pending_review_packet_signoff(
        handoff_manifest_path=handoff_manifest_path,
        signoff_id="rqp_signoff_discussiondone",
        created_at="2026-05-14T13:05:00+09:00",
    )
    signoff.update({
        "decision": "accepted",
        "evidence_reviewed": ["pilot-rqp-discussion-handoff-index.md"],
    })
    signoff["reviewer"] = {
        "name": "pm-reviewer",
        "title_or_team": "Product/PM",
        "reviewed_at": "2026-05-14T13:20:00+09:00",
    }
    signoff["findings"]["summary"] = "Discussion handoff evidence is complete."
    for key in signoff["acknowledgements"]:
        signoff["acknowledgements"][key] = True
    signoff["handoff_manifest_sha256"] = signoff_validator._sha256(handoff_manifest_path)
    signoff_path = output_root / "completed-signoff.json"
    signoff_path.write_text(json.dumps(signoff, ensure_ascii=False, indent=2), encoding="utf-8")
    signoff_summary_path = output_root / "signoff-summary.json"
    summarizer.main([str(signoff_path), "--require-complete", "--output", str(signoff_summary_path)])
    capsys.readouterr()
    readiness_path = output_root / "training-readiness-manifest.json"
    readiness.main([str(evidence_manifest_path), str(signoff_summary_path), "--output", str(readiness_path)])
    capsys.readouterr()
    discussion_manifest_path = output_root / "training-discussion-handoff-manifest.json"
    discussion_markdown_path = output_root / "training-discussion-handoff.md"

    exit_code = discussion_handoff.main([
        str(readiness_path),
        "--output-manifest",
        str(discussion_manifest_path),
        "--output-markdown",
        str(discussion_markdown_path),
        "--generated-at",
        "2026-05-14T15:00:00+09:00",
    ])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Report quality training discussion handoff: PASS" in out
    assert "ready_for_training_discussion=true" in out
    assert "training_boundary=not_authorized" in out
    manifest = json.loads(discussion_manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "decisiondoc_report_quality_review_packet_training_discussion_handoff.v1"
    assert manifest["readiness"]["ok"] is True
    assert manifest["readiness_validation"]["ok"] is True
    assert manifest["counts"]["ready_artifacts"] == 1
    assert manifest["counts"]["completed_signoff_count"] == 1
    assert manifest["counts"]["missing_file_count"] == 0
    assert manifest["handoff_files"]["training_readiness_manifest"]["exists"] is True
    assert manifest["handoff_files"]["evidence_artifact_jsonl"]["exists"] is True
    assert manifest["handoff_files"]["signoff_record_rqp_signoff_discussiondone"]["exists"] is True
    assert manifest["side_effect_boundary"]["training_execution_started"] is False
    markdown = discussion_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training Discussion Handoff" in markdown
    assert "training_authorized: `false`" in markdown

    validation_exit_code = discussion_handoff_validator.main([str(discussion_manifest_path)])
    assert validation_exit_code == 0
    validation_out = capsys.readouterr().out
    assert "PASS report quality training discussion handoff validated" in validation_out
    assert "ready_for_training_discussion=true" in validation_out
    assert "training_boundary=not_authorized" in validation_out
    validation = discussion_handoff_validator.validate_training_discussion_handoff_manifest(
        discussion_manifest_path,
    )
    assert validation["ok"] is True
    assert validation["readiness_validation_ok"] is True

    decision_path = output_root / "training-discussion-decision.json"
    decision_exit_code = discussion_decision.main([
        str(discussion_manifest_path),
        "--output",
        str(decision_path),
        "--decision-id",
        "rqp_training_discussion_decision_discussiondone",
        "--created-at",
        "2026-05-14T15:30:00+09:00",
    ])
    assert decision_exit_code == 0
    decision_out = capsys.readouterr().out
    assert "Report quality training discussion pending decision: PASS" in decision_out
    assert "pending_validation_ok=true" in decision_out
    assert "training_boundary=not_authorized" in decision_out
    decision_record = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision_record["schema_version"] == "decisiondoc_report_quality_training_discussion_decision.v1"
    assert decision_record["decision"] == "pending"
    assert decision_record["discussion_handoff_manifest_sha256"] == discussion_decision._sha256(discussion_manifest_path)
    assert len(decision_record["generation_context"]["evidence_to_review"]) >= 3
    assert decision_record["decision_boundary"]["training_execution_authorized"] is False
    assert decision_record["generation_boundary"]["provider_fine_tune_api_called"] is False

    pending_validation = discussion_decision_validator.validate_training_discussion_decision(decision_record)
    assert pending_validation["ok"] is True
    assert pending_validation["completed"] is False

    decision_record.update({
        "decision": "plan_draft_requested",
        "requested_next_step": "draft_training_experiment_plan",
        "discussion_summary": "Evidence package is ready for a future local experiment plan draft.",
        "decision_rationale": "The packet, sign-off summary, readiness, and handoff hashes were reviewed.",
        "evidence_reviewed": [str(discussion_manifest_path), str(readiness_path), str(signoff_summary_path)],
    })
    decision_record["participants"] = [
        {
            "name": "ml-owner",
            "role_or_team": "ML/AI Owner",
            "reviewed_at": "2026-05-14T15:40:00+09:00",
        }
    ]
    for key in decision_record["acknowledgements"]:
        decision_record["acknowledgements"][key] = True
    completed_validation = discussion_decision_validator.validate_training_discussion_decision(
        decision_record,
        require_complete=True,
    )
    assert completed_validation["ok"] is True
    assert completed_validation["completed"] is True
    assert completed_validation["requested_next_step"] == "draft_training_experiment_plan"
    decision_path.write_text(json.dumps(decision_record, ensure_ascii=False, indent=2), encoding="utf-8")

    plan_manifest_path = output_root / "training-experiment-plan-draft-manifest.json"
    plan_markdown_path = output_root / "training-experiment-plan-draft.md"
    plan_exit_code = experiment_plan.main([
        str(decision_path),
        "--output-manifest",
        str(plan_manifest_path),
        "--output-markdown",
        str(plan_markdown_path),
        "--provider",
        "provider_agnostic",
        "--base-model",
        "manual-selection-required",
        "--generated-at",
        "2026-05-14T16:00:00+09:00",
    ])
    assert plan_exit_code == 0
    plan_out = capsys.readouterr().out
    assert "Report quality training experiment plan draft: PASS" in plan_out
    assert "planning_only=true" in plan_out
    assert "training_boundary=not_authorized" in plan_out
    plan = json.loads(plan_manifest_path.read_text(encoding="utf-8"))
    assert plan["schema_version"] == "decisiondoc_report_quality_training_experiment_plan_draft.v1"
    assert plan["readiness"]["planning_only"] is True
    assert plan["readiness"]["training_execution_allowed"] is False
    assert plan["job_spec"]["provider"] == "provider_agnostic"
    assert plan["job_spec"]["base_model"] == "manual-selection-required"
    assert plan["job_spec"]["dataset"]["artifact_jsonl_sha256"]
    assert plan["job_spec"]["evaluation"]["suite"] == "report_quality_offline_eval"
    assert plan["job_spec"]["execution_steps"][2]["step"] == "call_provider_fine_tune_api"
    assert plan["job_spec"]["execution_steps"][2]["status"] == "not_started"
    assert plan["side_effect_boundary"]["training_execution_started"] is False
    assert "training_execution_allowed: `false`" in plan_markdown_path.read_text(encoding="utf-8")

    plan_validation_exit_code = experiment_plan_validator.main([str(plan_manifest_path)])
    assert plan_validation_exit_code == 0
    plan_validation_out = capsys.readouterr().out
    assert "PASS report quality training experiment plan draft validated" in plan_validation_out
    assert "planning_only=true" in plan_validation_out
    assert "training_boundary=not_authorized" in plan_validation_out
    plan_validation = experiment_plan_validator.validate_training_experiment_plan_draft(plan_manifest_path)
    assert plan_validation["ok"] is True
    assert plan_validation["decision_validation_ok"] is True

    plan_review_path = output_root / "training-experiment-plan-review.json"
    review_exit_code = experiment_plan_review.main([
        str(plan_manifest_path),
        "--output",
        str(plan_review_path),
        "--review-id",
        "rqp_training_experiment_plan_review_discussiondone",
        "--created-at",
        "2026-05-14T16:20:00+09:00",
    ])
    assert review_exit_code == 0
    review_out = capsys.readouterr().out
    assert "Report quality training experiment plan pending review: PASS" in review_out
    assert "pending_validation_ok=true" in review_out
    assert "training_boundary=not_authorized" in review_out
    review_record = json.loads(plan_review_path.read_text(encoding="utf-8"))
    assert review_record["schema_version"] == "decisiondoc_report_quality_training_experiment_plan_review.v1"
    assert review_record["decision"] == "pending"
    assert review_record["plan_manifest_sha256"] == experiment_plan_review._sha256(plan_manifest_path)
    assert len(review_record["generation_context"]["evidence_to_review"]) >= 5
    assert review_record["review_boundary"]["training_execution_authorized"] is False
    assert review_record["generation_boundary"]["provider_job_created"] is False

    pending_review_validation = experiment_plan_review_validator.validate_training_experiment_plan_review(
        review_record,
    )
    assert pending_review_validation["ok"] is True
    assert pending_review_validation["completed"] is False

    review_record.update({
        "decision": "planning_complete",
        "requested_next_step": "prepare_final_approval_packet",
        "review_summary": "Plan draft references the expected dataset, eval suite, and not-started execution steps.",
        "decision_rationale": "The plan is complete enough for a separate final approval packet.",
        "evidence_reviewed": [str(plan_manifest_path), str(plan_markdown_path), str(decision_path)],
    })
    review_record["reviewers"] = [
        {
            "name": "release-owner",
            "role_or_team": "Release Owner",
            "reviewed_at": "2026-05-14T16:35:00+09:00",
        }
    ]
    for key in review_record["acknowledgements"]:
        review_record["acknowledgements"][key] = True
    completed_review_validation = experiment_plan_review_validator.validate_training_experiment_plan_review(
        review_record,
        require_complete=True,
    )
    assert completed_review_validation["ok"] is True
    assert completed_review_validation["completed"] is True
    assert completed_review_validation["requested_next_step"] == "prepare_final_approval_packet"
    plan_review_path.write_text(json.dumps(review_record, ensure_ascii=False, indent=2), encoding="utf-8")

    final_packet_manifest_path = output_root / "training-final-approval-packet-manifest.json"
    final_packet_markdown_path = output_root / "training-final-approval-packet.md"
    final_packet_exit_code = final_packet.main([
        str(plan_review_path),
        "--output-manifest",
        str(final_packet_manifest_path),
        "--output-markdown",
        str(final_packet_markdown_path),
        "--generated-at",
        "2026-05-14T17:00:00+09:00",
    ])
    assert final_packet_exit_code == 0
    final_packet_out = capsys.readouterr().out
    assert "Report quality training final approval packet: PASS" in final_packet_out
    assert "approval_packet_only=true" in final_packet_out
    assert "packet_validation_ok=true" in final_packet_out
    assert "training_boundary=not_authorized" in final_packet_out
    packet = json.loads(final_packet_manifest_path.read_text(encoding="utf-8"))
    assert packet["schema_version"] == "decisiondoc_report_quality_training_final_approval_packet.v1"
    assert packet["readiness"]["approval_packet_only"] is True
    assert packet["readiness"]["final_training_approval_granted"] is False
    assert packet["readiness"]["training_execution_allowed"] is False
    assert packet["source_files"]["plan_review_record"]["exists"] is True
    assert packet["source_files"]["plan_manifest"]["sha256"] == final_packet._sha256(plan_manifest_path)
    assert "Compliance/Security" in packet["required_final_approver_roles"]
    assert packet["side_effect_boundary"]["training_execution_started"] is False
    assert "final_training_approval_granted: `false`" in final_packet_markdown_path.read_text(encoding="utf-8")

    final_packet_validation_exit_code = final_packet_validator.main([str(final_packet_manifest_path)])
    assert final_packet_validation_exit_code == 0
    final_packet_validation_out = capsys.readouterr().out
    assert "PASS report quality training final approval packet validated" in final_packet_validation_out
    assert "approval_packet_only=true" in final_packet_validation_out
    assert "training_boundary=not_authorized" in final_packet_validation_out
    packet_validation = final_packet_validator.validate_training_final_approval_packet(final_packet_manifest_path)
    assert packet_validation["ok"] is True
    assert packet_validation["plan_review_validation_ok"] is True

    final_packet_review_path = output_root / "training-final-approval-packet-review.json"
    final_packet_review_exit_code = final_packet_review.main([
        str(final_packet_manifest_path),
        "--output",
        str(final_packet_review_path),
        "--review-id",
        "rqp_training_final_approval_packet_review_discussiondone",
        "--created-at",
        "2026-05-14T17:20:00+09:00",
    ])
    assert final_packet_review_exit_code == 0
    final_packet_review_out = capsys.readouterr().out
    assert "Report quality training final approval packet pending review: PASS" in final_packet_review_out
    assert "pending_validation_ok=true" in final_packet_review_out
    assert "training_boundary=not_authorized" in final_packet_review_out
    packet_review_record = json.loads(final_packet_review_path.read_text(encoding="utf-8"))
    assert packet_review_record["schema_version"] == "decisiondoc_report_quality_training_final_approval_packet_review.v1"
    assert packet_review_record["decision"] == "pending"
    assert packet_review_record["packet_manifest_sha256"] == final_packet_review._sha256(final_packet_manifest_path)
    assert len(packet_review_record["generation_context"]["evidence_to_review"]) >= 5
    assert packet_review_record["review_boundary"]["final_training_approval_granted"] is False
    assert packet_review_record["generation_boundary"]["provider_job_polled"] is False

    pending_packet_review_validation = final_packet_review_validator.validate_training_final_approval_packet_review(
        packet_review_record,
    )
    assert pending_packet_review_validation["ok"] is True
    assert pending_packet_review_validation["completed"] is False

    packet_review_record.update({
        "decision": "packet_review_complete",
        "requested_next_step": "prepare_final_approval_record_template",
        "review_summary": "Final approval packet lists the required approver roles and evidence hashes.",
        "decision_rationale": "The packet is ready for a separate approval record template, not execution.",
        "evidence_reviewed": [
            str(final_packet_manifest_path),
            str(final_packet_markdown_path),
            str(plan_review_path),
        ],
    })
    packet_review_record["reviewers"] = [
        {
            "name": "security-owner",
            "role_or_team": "Compliance/Security",
            "reviewed_at": "2026-05-14T17:35:00+09:00",
        }
    ]
    for key in packet_review_record["acknowledgements"]:
        packet_review_record["acknowledgements"][key] = True
    completed_packet_review_validation = final_packet_review_validator.validate_training_final_approval_packet_review(
        packet_review_record,
        require_complete=True,
    )
    assert completed_packet_review_validation["ok"] is True
    assert completed_packet_review_validation["completed"] is True
    assert completed_packet_review_validation["requested_next_step"] == "prepare_final_approval_record_template"
    final_packet_review_path.write_text(json.dumps(packet_review_record, ensure_ascii=False, indent=2), encoding="utf-8")

    final_approval_record_path = output_root / "training-final-approval-record-template.json"
    final_approval_record_markdown_path = output_root / "training-final-approval-record-template.md"
    final_approval_record_exit_code = final_approval_record_template.main([
        str(final_packet_review_path),
        "--output",
        str(final_approval_record_path),
        "--markdown",
        str(final_approval_record_markdown_path),
        "--template-id",
        "rqp_training_final_approval_record_template_discussiondone",
        "--generated-at",
        "2026-05-14T17:50:00+09:00",
    ])
    assert final_approval_record_exit_code == 0
    final_approval_record_out = capsys.readouterr().out
    assert "Report quality training final approval record template: PASS" in final_approval_record_out
    assert "template_only=true" in final_approval_record_out
    assert "approval_granted=false" in final_approval_record_out
    assert "training_boundary=not_authorized" in final_approval_record_out
    final_approval_record = json.loads(final_approval_record_path.read_text(encoding="utf-8"))
    assert (
        final_approval_record["schema_version"]
        == "decisiondoc_report_quality_training_final_approval_record_template.v1"
    )
    assert final_approval_record["approval_state"]["template_only"] is True
    assert final_approval_record["approval_state"]["approval_record_completed"] is False
    assert final_approval_record["approval_state"]["final_training_approval_granted"] is False
    assert final_approval_record["packet_review_sha256"] == final_approval_record_template._sha256(
        final_packet_review_path
    )
    assert final_approval_record["packet_manifest_sha256"] == final_approval_record_template._sha256(
        final_packet_manifest_path
    )
    assert {item["role"] for item in final_approval_record["required_approvals"]} == {
        "ML/AI Owner",
        "Product/PM",
        "Compliance/Security",
        "Release Owner",
    }
    assert {item["decision"] for item in final_approval_record["required_approvals"]} == {"pending"}
    assert final_approval_record["source_files"]["packet_review_record"]["exists"] is True
    assert final_approval_record["source_files"]["packet_manifest"]["exists"] is True
    assert final_approval_record["side_effect_boundary"]["training_execution_started"] is False
    assert final_approval_record["generation_boundary"]["provider_job_created"] is False
    for step in final_approval_record["job_spec_snapshot"]["execution_steps"]:
        assert step["status"] == "not_started"
    assert "final_training_approval_granted: `false`" in final_approval_record_markdown_path.read_text(
        encoding="utf-8"
    )

    final_approval_record_validation_exit_code = final_approval_record_template_validator.main([
        str(final_approval_record_path),
    ])
    assert final_approval_record_validation_exit_code == 0
    final_approval_record_validation_out = capsys.readouterr().out
    assert "PASS report quality training final approval record template validated" in final_approval_record_validation_out
    assert "template_only=true" in final_approval_record_validation_out
    assert "approval_granted=false" in final_approval_record_validation_out
    assert "training_boundary=not_authorized" in final_approval_record_validation_out
    record_validation = final_approval_record_template_validator.validate_training_final_approval_record_template(
        final_approval_record_path,
    )
    assert record_validation["ok"] is True
    assert record_validation["packet_review_validation_ok"] is True

    freeze_manifest_path = output_root / "training-no-cost-freeze-manifest.json"
    freeze_markdown_path = output_root / "training-no-cost-freeze.md"
    freeze_exit_code = no_cost_freeze.main([
        str(final_approval_record_path),
        "--output-manifest",
        str(freeze_manifest_path),
        "--output-markdown",
        str(freeze_markdown_path),
        "--freeze-id",
        "rqp_training_no_cost_freeze_discussiondone",
        "--generated-at",
        "2026-05-14T18:00:00+09:00",
    ])
    assert freeze_exit_code == 0
    freeze_out = capsys.readouterr().out
    assert "Report quality training no-cost freeze: PASS" in freeze_out
    assert "freeze_only=true" in freeze_out
    assert "aws_cost_boundary=no_cost_increase" in freeze_out
    assert "training_boundary=not_authorized" in freeze_out
    freeze = json.loads(freeze_manifest_path.read_text(encoding="utf-8"))
    assert freeze["schema_version"] == "decisiondoc_report_quality_training_no_cost_freeze.v1"
    assert freeze["freeze_state"]["freeze_only"] is True
    assert freeze["freeze_state"]["service_operation_allowed"] is False
    assert freeze["freeze_state"]["aws_cost_increase_allowed"] is False
    assert freeze["freeze_state"]["provider_api_calls_allowed"] is False
    assert freeze["freeze_state"]["training_execution_allowed"] is False
    assert freeze["approval_record_template_sha256"] == no_cost_freeze._sha256(final_approval_record_path)
    assert freeze["source_files"]["approval_record_template"]["exists"] is True
    assert freeze["source_files"]["approval_record_markdown"]["exists"] is True
    assert freeze["cost_boundary"]["aws_resource_created"] is False
    assert freeze["cost_boundary"]["provider_fine_tune_api_called"] is False
    assert freeze["generation_boundary"]["training_execution_started"] is False
    assert len(freeze["resume_requirements"]) >= 4
    for step in freeze["job_spec_snapshot"]["execution_steps"]:
        assert step["status"] == "not_started"
    freeze_markdown = freeze_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Freeze" in freeze_markdown
    assert "aws_cost_increase_allowed: `false`" in freeze_markdown

    freeze_validation_exit_code = no_cost_freeze_validator.main([str(freeze_manifest_path)])
    assert freeze_validation_exit_code == 0
    freeze_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost freeze validated" in freeze_validation_out
    assert "freeze_only=true" in freeze_validation_out
    assert "aws_cost_boundary=no_cost_increase" in freeze_validation_out
    assert "training_boundary=not_authorized" in freeze_validation_out
    freeze_validation = no_cost_freeze_validator.validate_training_no_cost_freeze(freeze_manifest_path)
    assert freeze_validation["ok"] is True
    assert freeze_validation["approval_record_template_validation_ok"] is True

    freeze_summary_path = output_root / "training-no-cost-freeze-summary.json"
    freeze_summary_markdown_path = output_root / "training-no-cost-freeze-summary.md"
    freeze_summary_exit_code = no_cost_freeze_summary.main([
        str(freeze_manifest_path),
        "--output",
        str(freeze_summary_path),
        "--markdown",
        str(freeze_summary_markdown_path),
        "--generated-at",
        "2026-05-14T18:05:00+09:00",
    ])
    assert freeze_summary_exit_code == 0
    freeze_summary_out = capsys.readouterr().out
    assert "Report quality training no-cost freeze summary: PASS" in freeze_summary_out
    assert "freeze_count=1" in freeze_summary_out
    assert "valid_freeze_count=1" in freeze_summary_out
    assert "aws_cost_boundary=no_cost_increase" in freeze_summary_out
    assert "training_boundary=not_authorized" in freeze_summary_out
    freeze_summary = json.loads(freeze_summary_path.read_text(encoding="utf-8"))
    assert freeze_summary["schema_version"] == "decisiondoc_report_quality_training_no_cost_freeze_summary.v1"
    assert freeze_summary["ok"] is True
    assert freeze_summary["readiness"]["status"] == "all_freezes_confirm_no_cost_hold"
    assert freeze_summary["counts"]["freeze_count"] == 1
    assert freeze_summary["counts"]["valid_freeze_count"] == 1
    assert freeze_summary["counts"]["no_cost_hold_count"] == 1
    assert freeze_summary["freezes"][0]["freeze_id"] == "rqp_training_no_cost_freeze_discussiondone"
    assert freeze_summary["side_effect_boundary"]["aws_cost_increase_allowed"] is False
    freeze_summary_markdown = freeze_summary_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Freeze Summary" in freeze_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in freeze_summary_markdown

    freeze_handoff_manifest_path = output_root / "training-no-cost-freeze-handoff-manifest.json"
    freeze_handoff_markdown_path = output_root / "training-no-cost-freeze-handoff.md"
    freeze_handoff_exit_code = no_cost_freeze_handoff.main([
        str(freeze_summary_path),
        "--output-manifest",
        str(freeze_handoff_manifest_path),
        "--output-markdown",
        str(freeze_handoff_markdown_path),
        "--generated-at",
        "2026-05-14T18:10:00+09:00",
    ])
    assert freeze_handoff_exit_code == 0
    freeze_handoff_out = capsys.readouterr().out
    assert "Report quality training no-cost freeze handoff: PASS" in freeze_handoff_out
    assert "handoff_ready=true" in freeze_handoff_out
    assert "aws_cost_boundary=no_cost_increase" in freeze_handoff_out
    assert "training_boundary=not_authorized" in freeze_handoff_out
    freeze_handoff = json.loads(freeze_handoff_manifest_path.read_text(encoding="utf-8"))
    assert freeze_handoff["schema_version"] == "decisiondoc_report_quality_training_no_cost_freeze_handoff.v1"
    assert freeze_handoff["readiness"]["ok"] is True
    assert freeze_handoff["readiness"]["status"] == "no_cost_freeze_handoff_ready"
    assert freeze_handoff["readiness"]["aws_cost_increase_allowed"] is False
    assert freeze_handoff["readiness"]["provider_fine_tune_api_call_authorized"] is False
    assert freeze_handoff["counts"]["freeze_count"] == 1
    assert freeze_handoff["counts"]["valid_freeze_count"] == 1
    assert freeze_handoff["counts"]["no_cost_hold_count"] == 1
    assert freeze_handoff["source_files"]["freeze_summary_json"]["exists"] is True
    assert freeze_handoff["handoff_boundary"]["aws_resource_created"] is False
    assert freeze_handoff["handoff_boundary"]["training_execution_started"] is False
    freeze_handoff_markdown = freeze_handoff_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Freeze Handoff" in freeze_handoff_markdown
    assert "aws_cost_increase_allowed: `false`" in freeze_handoff_markdown

    freeze_handoff_validation_exit_code = no_cost_freeze_handoff_validator.main([
        str(freeze_handoff_manifest_path),
    ])
    assert freeze_handoff_validation_exit_code == 0
    freeze_handoff_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost freeze handoff validated" in freeze_handoff_validation_out
    assert "handoff_ready=true" in freeze_handoff_validation_out
    assert "aws_cost_boundary=no_cost_increase" in freeze_handoff_validation_out
    assert "training_boundary=not_authorized" in freeze_handoff_validation_out
    freeze_handoff_validation = no_cost_freeze_handoff_validator.validate_training_no_cost_freeze_handoff(
        freeze_handoff_manifest_path,
    )
    assert freeze_handoff_validation["ok"] is True
    assert freeze_handoff_validation["freeze_summary_validation_ok"] is True

    freeze_handoff_signoff_path = output_root / "training-no-cost-freeze-handoff-signoff.json"
    freeze_handoff_signoff_exit_code = no_cost_freeze_handoff_signoff.main([
        str(freeze_handoff_manifest_path),
        "--output",
        str(freeze_handoff_signoff_path),
        "--signoff-id",
        "rqp_training_no_cost_freeze_handoff_signoff_discussiondone",
        "--created-at",
        "2026-05-14T18:20:00+09:00",
    ])
    assert freeze_handoff_signoff_exit_code == 0
    freeze_handoff_signoff_out = capsys.readouterr().out
    assert "Report quality training no-cost freeze handoff pending signoff: PASS" in freeze_handoff_signoff_out
    assert "pending_validation_ok=true" in freeze_handoff_signoff_out
    assert "aws_cost_boundary=no_cost_increase" in freeze_handoff_signoff_out
    assert "training_boundary=not_authorized" in freeze_handoff_signoff_out
    freeze_handoff_signoff = json.loads(freeze_handoff_signoff_path.read_text(encoding="utf-8"))
    assert (
        freeze_handoff_signoff["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_freeze_handoff_signoff.v1"
    )
    assert freeze_handoff_signoff["decision"] == "pending"
    assert freeze_handoff_signoff["handoff_manifest_sha256"] == no_cost_freeze_handoff_signoff._sha256(
        freeze_handoff_manifest_path
    )
    assert freeze_handoff_signoff["signoff_boundary"]["aws_cost_increase_authorized"] is False
    assert freeze_handoff_signoff["signoff_boundary"]["training_execution_authorized"] is False
    assert freeze_handoff_signoff["generation_boundary"]["provider_job_created"] is False
    assert str(freeze_handoff_manifest_path) in freeze_handoff_signoff["generation_context"]["evidence_to_review"]
    assert str(freeze_summary_path) in freeze_handoff_signoff["generation_context"]["evidence_to_review"]
    pending_freeze_handoff_signoff_validation = (
        no_cost_freeze_handoff_signoff_validator.validate_training_no_cost_freeze_handoff_signoff(
            freeze_handoff_signoff,
        )
    )
    assert pending_freeze_handoff_signoff_validation["ok"] is True
    assert pending_freeze_handoff_signoff_validation["completed"] is False

    freeze_handoff_signoff["decision"] = "accepted"
    freeze_handoff_signoff["reviewer"] = {
        "name": "ops-reviewer",
        "title_or_team": "Ops",
        "reviewed_at": "2026-05-14T18:25:00+09:00",
    }
    freeze_handoff_signoff["evidence_reviewed"] = [
        str(freeze_handoff_manifest_path),
        str(freeze_handoff_markdown_path),
        str(freeze_summary_path),
        str(freeze_manifest_path),
    ]
    freeze_handoff_signoff["findings"] = {
        "summary": "No-cost freeze handoff reviewed and confirmed as evidence-only.",
        "changes_requested": [],
        "residual_risks": ["Project resume still requires separate approval and budget review."],
    }
    for key in freeze_handoff_signoff["acknowledgements"]:
        freeze_handoff_signoff["acknowledgements"][key] = True
    completed_freeze_handoff_signoff_validation = (
        no_cost_freeze_handoff_signoff_validator.validate_training_no_cost_freeze_handoff_signoff(
            freeze_handoff_signoff,
            require_complete=True,
        )
    )
    assert completed_freeze_handoff_signoff_validation["ok"] is True
    assert completed_freeze_handoff_signoff_validation["completed"] is True
    assert completed_freeze_handoff_signoff_validation["handoff_validation_ok"] is True
    freeze_handoff_signoff_path.write_text(
        json.dumps(freeze_handoff_signoff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    freeze_handoff_signoff_validation_exit_code = no_cost_freeze_handoff_signoff_validator.main([
        str(freeze_handoff_signoff_path),
        "--require-complete",
    ])
    assert freeze_handoff_signoff_validation_exit_code == 0
    freeze_handoff_signoff_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost freeze handoff signoff validated"
        in freeze_handoff_signoff_validation_out
    )
    assert "completed=true" in freeze_handoff_signoff_validation_out
    assert "decision=accepted" in freeze_handoff_signoff_validation_out
    assert "aws_cost_boundary=no_cost_increase" in freeze_handoff_signoff_validation_out
    assert "training_boundary=not_authorized" in freeze_handoff_signoff_validation_out

    archive_closure_manifest_path = output_root / "training-no-cost-archive-closure-manifest.json"
    archive_closure_markdown_path = output_root / "training-no-cost-archive-closure.md"
    archive_closure_exit_code = no_cost_archive_closure.main([
        str(freeze_handoff_signoff_path),
        "--output-manifest",
        str(archive_closure_manifest_path),
        "--output-markdown",
        str(archive_closure_markdown_path),
        "--generated-at",
        "2026-05-14T18:30:00+09:00",
    ])
    assert archive_closure_exit_code == 0
    archive_closure_out = capsys.readouterr().out
    assert "Report quality training no-cost archive closure: PASS" in archive_closure_out
    assert "archive_ready=true" in archive_closure_out
    assert "aws_cost_boundary=no_cost_increase" in archive_closure_out
    assert "training_boundary=not_authorized" in archive_closure_out
    archive_closure = json.loads(archive_closure_manifest_path.read_text(encoding="utf-8"))
    assert archive_closure["schema_version"] == "decisiondoc_report_quality_training_no_cost_archive_closure.v1"
    assert archive_closure["closure_state"]["ok"] is True
    assert archive_closure["closure_state"]["status"] == "archived_no_cost_hold"
    assert archive_closure["closure_state"]["archive_only"] is True
    assert archive_closure["closure_state"]["operation_resume_approved"] is False
    assert archive_closure["closure_state"]["aws_cost_increase_allowed"] is False
    assert archive_closure["closure_state"]["training_execution_started"] is False
    assert archive_closure["signoff_sha256"] == no_cost_archive_closure._sha256(freeze_handoff_signoff_path)
    assert archive_closure["handoff_manifest_sha256"] == no_cost_archive_closure._sha256(
        freeze_handoff_manifest_path
    )
    assert archive_closure["source_files"]["freeze_handoff_signoff"]["exists"] is True
    assert archive_closure["source_files"]["freeze_handoff_manifest"]["exists"] is True
    assert archive_closure["source_files"]["freeze_summary_json"]["exists"] is True
    assert archive_closure["closure_boundary"]["aws_cost_increase_allowed"] is False
    assert archive_closure["closure_boundary"]["training_execution_started"] is False
    archive_closure_markdown = archive_closure_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Archive Closure" in archive_closure_markdown
    assert "operation_resume_approved: `false`" in archive_closure_markdown
    assert "aws_cost_increase_allowed: `false`" in archive_closure_markdown

    archive_closure_validation_exit_code = no_cost_archive_closure_validator.main([
        str(archive_closure_manifest_path),
    ])
    assert archive_closure_validation_exit_code == 0
    archive_closure_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost archive closure validated" in archive_closure_validation_out
    assert "archive_ready=true" in archive_closure_validation_out
    assert "aws_cost_boundary=no_cost_increase" in archive_closure_validation_out
    assert "training_boundary=not_authorized" in archive_closure_validation_out
    archive_closure_validation = no_cost_archive_closure_validator.validate_training_no_cost_archive_closure(
        archive_closure_manifest_path,
    )
    assert archive_closure_validation["ok"] is True
    assert archive_closure_validation["signoff_validation_ok"] is True

    archive_closure_summary_path = output_root / "training-no-cost-archive-closure-summary.json"
    archive_closure_summary_markdown_path = output_root / "training-no-cost-archive-closure-summary.md"
    archive_closure_summary_exit_code = no_cost_archive_closure_summary.main([
        str(archive_closure_manifest_path),
        "--output",
        str(archive_closure_summary_path),
        "--markdown",
        str(archive_closure_summary_markdown_path),
        "--generated-at",
        "2026-05-14T18:35:00+09:00",
    ])
    assert archive_closure_summary_exit_code == 0
    archive_closure_summary_out = capsys.readouterr().out
    assert "Report quality training no-cost archive closure summary: PASS" in archive_closure_summary_out
    assert "archive_closure_count=1" in archive_closure_summary_out
    assert "valid_archive_closure_count=1" in archive_closure_summary_out
    assert "aws_cost_boundary=no_cost_increase" in archive_closure_summary_out
    assert "training_boundary=not_authorized" in archive_closure_summary_out
    archive_closure_summary = json.loads(archive_closure_summary_path.read_text(encoding="utf-8"))
    assert (
        archive_closure_summary["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_archive_closure_summary.v1"
    )
    assert archive_closure_summary["ok"] is True
    assert archive_closure_summary["readiness"]["status"] == "all_archive_closures_confirm_no_cost_hold"
    assert archive_closure_summary["counts"]["archive_closure_count"] == 1
    assert archive_closure_summary["counts"]["valid_archive_closure_count"] == 1
    assert archive_closure_summary["counts"]["archived_no_cost_hold_count"] == 1
    assert archive_closure_summary["closures"][0]["status"] == "archived_no_cost_hold"
    assert archive_closure_summary["closures"][0]["operation_resume_approved"] is False
    assert archive_closure_summary["side_effect_boundary"]["aws_cost_increase_allowed"] is False
    archive_closure_summary_markdown = archive_closure_summary_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Archive Closure Summary" in archive_closure_summary_markdown
    assert "operation_resume_approved: `false`" in archive_closure_summary_markdown

    evidence_bundle_manifest_path = output_root / "training-no-cost-evidence-bundle-manifest.json"
    evidence_bundle_markdown_path = output_root / "training-no-cost-evidence-bundle.md"
    evidence_bundle_exit_code = no_cost_evidence_bundle.main([
        str(archive_closure_summary_path),
        "--output-manifest",
        str(evidence_bundle_manifest_path),
        "--output-markdown",
        str(evidence_bundle_markdown_path),
        "--generated-at",
        "2026-05-14T18:40:00+09:00",
    ])
    assert evidence_bundle_exit_code == 0
    evidence_bundle_out = capsys.readouterr().out
    assert "Report quality training no-cost evidence bundle: PASS" in evidence_bundle_out
    assert "bundle_ready=true" in evidence_bundle_out
    assert "aws_cost_boundary=no_cost_increase" in evidence_bundle_out
    assert "training_boundary=not_authorized" in evidence_bundle_out
    evidence_bundle = json.loads(evidence_bundle_manifest_path.read_text(encoding="utf-8"))
    assert evidence_bundle["schema_version"] == "decisiondoc_report_quality_training_no_cost_evidence_bundle.v1"
    assert evidence_bundle["bundle_state"]["ok"] is True
    assert evidence_bundle["bundle_state"]["status"] == "no_cost_evidence_bundle_ready"
    assert evidence_bundle["bundle_state"]["bundle_only"] is True
    assert evidence_bundle["bundle_state"]["operation_resume_approved"] is False
    assert evidence_bundle["bundle_state"]["aws_cost_increase_allowed"] is False
    assert evidence_bundle["bundle_state"]["training_execution_started"] is False
    assert evidence_bundle["archive_closure_summary_sha256"] == no_cost_evidence_bundle._sha256(
        archive_closure_summary_path
    )
    assert evidence_bundle["source_files"]["archive_closure_summary_json"]["exists"] is True
    assert evidence_bundle["source_files"]["archive_closure_manifest_1"]["exists"] is True
    assert evidence_bundle["source_files"]["archive_closure_signoff_1"]["exists"] is True
    assert evidence_bundle["bundle_boundary"]["aws_cost_increase_allowed"] is False
    evidence_bundle_markdown = evidence_bundle_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Evidence Bundle" in evidence_bundle_markdown
    assert "operation_resume_approved: `false`" in evidence_bundle_markdown

    evidence_bundle_validation_exit_code = no_cost_evidence_bundle_validator.main([
        str(evidence_bundle_manifest_path),
    ])
    assert evidence_bundle_validation_exit_code == 0
    evidence_bundle_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost evidence bundle validated" in evidence_bundle_validation_out
    assert "bundle_ready=true" in evidence_bundle_validation_out
    assert "aws_cost_boundary=no_cost_increase" in evidence_bundle_validation_out
    assert "training_boundary=not_authorized" in evidence_bundle_validation_out
    evidence_bundle_validation = no_cost_evidence_bundle_validator.validate_training_no_cost_evidence_bundle(
        evidence_bundle_manifest_path,
    )
    assert evidence_bundle_validation["ok"] is True
    assert evidence_bundle_validation["archive_closure_summary_validation_ok"] is True

    evidence_bundle_handoff_manifest_path = (
        output_root / "training-no-cost-evidence-bundle-handoff-manifest.json"
    )
    evidence_bundle_handoff_markdown_path = output_root / "training-no-cost-evidence-bundle-handoff.md"
    evidence_bundle_handoff_exit_code = no_cost_evidence_bundle_handoff.main([
        str(evidence_bundle_manifest_path),
        "--output-manifest",
        str(evidence_bundle_handoff_manifest_path),
        "--output-markdown",
        str(evidence_bundle_handoff_markdown_path),
        "--generated-at",
        "2026-05-14T18:45:00+09:00",
    ])
    assert evidence_bundle_handoff_exit_code == 0
    evidence_bundle_handoff_out = capsys.readouterr().out
    assert "Report quality training no-cost evidence bundle handoff: PASS" in evidence_bundle_handoff_out
    assert "handoff_ready=true" in evidence_bundle_handoff_out
    assert "aws_cost_boundary=no_cost_increase" in evidence_bundle_handoff_out
    assert "training_boundary=not_authorized" in evidence_bundle_handoff_out
    evidence_bundle_handoff = json.loads(evidence_bundle_handoff_manifest_path.read_text(encoding="utf-8"))
    assert (
        evidence_bundle_handoff["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_evidence_bundle_handoff.v1"
    )
    assert evidence_bundle_handoff["readiness"]["ok"] is True
    assert evidence_bundle_handoff["readiness"]["status"] == "no_cost_evidence_bundle_handoff_ready"
    assert evidence_bundle_handoff["readiness"]["handoff_only"] is True
    assert evidence_bundle_handoff["readiness"]["operation_resume_approved"] is False
    assert evidence_bundle_handoff["readiness"]["aws_cost_increase_allowed"] is False
    assert evidence_bundle_handoff["evidence_bundle_sha256"] == no_cost_evidence_bundle_handoff._sha256(
        evidence_bundle_manifest_path
    )
    assert evidence_bundle_handoff["source_files"]["evidence_bundle_manifest"]["exists"] is True
    assert evidence_bundle_handoff["source_files"]["archive_closure_summary_json"]["exists"] is True
    assert evidence_bundle_handoff["handoff_boundary"]["training_execution_started"] is False
    evidence_bundle_handoff_markdown = evidence_bundle_handoff_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Evidence Bundle Handoff" in evidence_bundle_handoff_markdown
    assert "operation_resume_approved: `false`" in evidence_bundle_handoff_markdown
    assert "aws_cost_increase_allowed: `false`" in evidence_bundle_handoff_markdown

    evidence_bundle_handoff_validation_exit_code = no_cost_evidence_bundle_handoff_validator.main([
        str(evidence_bundle_handoff_manifest_path),
    ])
    assert evidence_bundle_handoff_validation_exit_code == 0
    evidence_bundle_handoff_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost evidence bundle handoff validated"
        in evidence_bundle_handoff_validation_out
    )
    assert "handoff_ready=true" in evidence_bundle_handoff_validation_out
    assert "aws_cost_boundary=no_cost_increase" in evidence_bundle_handoff_validation_out
    assert "training_boundary=not_authorized" in evidence_bundle_handoff_validation_out
    evidence_bundle_handoff_validation = (
        no_cost_evidence_bundle_handoff_validator.validate_training_no_cost_evidence_bundle_handoff(
            evidence_bundle_handoff_manifest_path,
        )
    )
    assert evidence_bundle_handoff_validation["ok"] is True
    assert evidence_bundle_handoff_validation["evidence_bundle_validation_ok"] is True

    evidence_bundle_handoff_signoff_path = (
        output_root / "training-no-cost-evidence-bundle-handoff-signoff.json"
    )
    evidence_bundle_handoff_signoff_exit_code = no_cost_evidence_bundle_handoff_signoff.main([
        str(evidence_bundle_handoff_manifest_path),
        "--output",
        str(evidence_bundle_handoff_signoff_path),
        "--signoff-id",
        "rqp_training_no_cost_evidence_bundle_handoff_signoff_discussiondone",
        "--created-at",
        "2026-05-14T18:50:00+09:00",
    ])
    assert evidence_bundle_handoff_signoff_exit_code == 0
    evidence_bundle_handoff_signoff_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost evidence bundle handoff pending signoff: PASS"
        in evidence_bundle_handoff_signoff_out
    )
    assert "pending_validation_ok=true" in evidence_bundle_handoff_signoff_out
    assert "aws_cost_boundary=no_cost_increase" in evidence_bundle_handoff_signoff_out
    assert "training_boundary=not_authorized" in evidence_bundle_handoff_signoff_out
    evidence_bundle_handoff_signoff = json.loads(
        evidence_bundle_handoff_signoff_path.read_text(encoding="utf-8")
    )
    assert (
        evidence_bundle_handoff_signoff["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_evidence_bundle_handoff_signoff.v1"
    )
    assert evidence_bundle_handoff_signoff["decision"] == "pending"
    assert (
        evidence_bundle_handoff_signoff["handoff_manifest_sha256"]
        == no_cost_evidence_bundle_handoff_signoff._sha256(evidence_bundle_handoff_manifest_path)
    )
    assert evidence_bundle_handoff_signoff["signoff_boundary"]["aws_cost_increase_authorized"] is False
    assert evidence_bundle_handoff_signoff["signoff_boundary"]["training_execution_authorized"] is False
    assert evidence_bundle_handoff_signoff["generation_boundary"]["provider_job_created"] is False
    assert (
        str(evidence_bundle_handoff_manifest_path)
        in evidence_bundle_handoff_signoff["generation_context"]["evidence_to_review"]
    )
    assert (
        str(evidence_bundle_manifest_path)
        in evidence_bundle_handoff_signoff["generation_context"]["evidence_to_review"]
    )
    pending_evidence_bundle_handoff_signoff_validation = (
        no_cost_evidence_bundle_handoff_signoff_validator.validate_training_no_cost_evidence_bundle_handoff_signoff(
            evidence_bundle_handoff_signoff,
        )
    )
    assert pending_evidence_bundle_handoff_signoff_validation["ok"] is True
    assert pending_evidence_bundle_handoff_signoff_validation["completed"] is False

    evidence_bundle_handoff_signoff["decision"] = "accepted"
    evidence_bundle_handoff_signoff["reviewer"] = {
        "name": "archive-reviewer",
        "title_or_team": "Ops/Archive",
        "reviewed_at": "2026-05-14T18:55:00+09:00",
    }
    evidence_bundle_handoff_signoff["evidence_reviewed"] = [
        str(evidence_bundle_handoff_manifest_path),
        str(evidence_bundle_handoff_markdown_path),
        str(evidence_bundle_manifest_path),
        str(archive_closure_summary_path),
    ]
    evidence_bundle_handoff_signoff["findings"] = {
        "summary": "No-cost evidence bundle handoff reviewed and confirmed as archive-only evidence.",
        "changes_requested": [],
        "residual_risks": ["Project resume still requires separate approval and budget review."],
    }
    for key in evidence_bundle_handoff_signoff["acknowledgements"]:
        evidence_bundle_handoff_signoff["acknowledgements"][key] = True
    completed_evidence_bundle_handoff_signoff_validation = (
        no_cost_evidence_bundle_handoff_signoff_validator.validate_training_no_cost_evidence_bundle_handoff_signoff(
            evidence_bundle_handoff_signoff,
            require_complete=True,
        )
    )
    assert completed_evidence_bundle_handoff_signoff_validation["ok"] is True
    assert completed_evidence_bundle_handoff_signoff_validation["completed"] is True
    assert completed_evidence_bundle_handoff_signoff_validation["handoff_validation_ok"] is True
    evidence_bundle_handoff_signoff_path.write_text(
        json.dumps(evidence_bundle_handoff_signoff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    evidence_bundle_handoff_signoff_validation_exit_code = (
        no_cost_evidence_bundle_handoff_signoff_validator.main([
            str(evidence_bundle_handoff_signoff_path),
            "--require-complete",
        ])
    )
    assert evidence_bundle_handoff_signoff_validation_exit_code == 0
    evidence_bundle_handoff_signoff_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost evidence bundle handoff signoff validated"
        in evidence_bundle_handoff_signoff_validation_out
    )
    assert "completed=true" in evidence_bundle_handoff_signoff_validation_out
    assert "decision=accepted" in evidence_bundle_handoff_signoff_validation_out
    assert "aws_cost_boundary=no_cost_increase" in evidence_bundle_handoff_signoff_validation_out
    assert "training_boundary=not_authorized" in evidence_bundle_handoff_signoff_validation_out

    evidence_bundle_handoff_signoff_summary_path = (
        output_root / "training-no-cost-evidence-bundle-handoff-signoff-summary.json"
    )
    evidence_bundle_handoff_signoff_summary_markdown_path = (
        output_root / "training-no-cost-evidence-bundle-handoff-signoff-summary.md"
    )
    evidence_bundle_handoff_signoff_summary_exit_code = no_cost_evidence_bundle_handoff_signoff_summary.main([
        str(evidence_bundle_handoff_signoff_path),
        "--output",
        str(evidence_bundle_handoff_signoff_summary_path),
        "--markdown",
        str(evidence_bundle_handoff_signoff_summary_markdown_path),
        "--generated-at",
        "2026-05-14T19:00:00+09:00",
    ])
    assert evidence_bundle_handoff_signoff_summary_exit_code == 0
    evidence_bundle_handoff_signoff_summary_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost evidence bundle handoff signoff summary: PASS"
        in evidence_bundle_handoff_signoff_summary_out
    )
    assert "signoff_count=1" in evidence_bundle_handoff_signoff_summary_out
    assert "valid_signoff_count=1" in evidence_bundle_handoff_signoff_summary_out
    assert "completed_signoff_count=1" in evidence_bundle_handoff_signoff_summary_out
    assert "aws_cost_boundary=no_cost_increase" in evidence_bundle_handoff_signoff_summary_out
    assert "training_boundary=not_authorized" in evidence_bundle_handoff_signoff_summary_out
    evidence_bundle_handoff_signoff_summary_payload = json.loads(
        evidence_bundle_handoff_signoff_summary_path.read_text(encoding="utf-8")
    )
    assert (
        evidence_bundle_handoff_signoff_summary_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_evidence_bundle_handoff_signoff_summary.v1"
    )
    assert evidence_bundle_handoff_signoff_summary_payload["ok"] is True
    assert (
        evidence_bundle_handoff_signoff_summary_payload["readiness"]["status"]
        == "all_evidence_bundle_handoff_signoffs_confirm_archive_only"
    )
    assert evidence_bundle_handoff_signoff_summary_payload["counts"]["signoff_count"] == 1
    assert evidence_bundle_handoff_signoff_summary_payload["counts"]["valid_signoff_count"] == 1
    assert evidence_bundle_handoff_signoff_summary_payload["counts"]["completed_signoff_count"] == 1
    assert evidence_bundle_handoff_signoff_summary_payload["counts"]["accepted_signoff_count"] == 1
    assert evidence_bundle_handoff_signoff_summary_payload["counts"]["archive_only_review_count"] == 1
    assert evidence_bundle_handoff_signoff_summary_payload["side_effect_boundary"][
        "aws_cost_increase_allowed"
    ] is False
    evidence_bundle_handoff_signoff_summary_markdown = (
        evidence_bundle_handoff_signoff_summary_markdown_path.read_text(encoding="utf-8")
    )
    assert (
        "Report Quality Training No-Cost Evidence Bundle Handoff Sign-Off Summary"
        in evidence_bundle_handoff_signoff_summary_markdown
    )
    assert "operation_resume_approved: `false`" in evidence_bundle_handoff_signoff_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in evidence_bundle_handoff_signoff_summary_markdown

    resume_guard_manifest_path = output_root / "training-no-cost-resume-guard-manifest.json"
    resume_guard_markdown_path = output_root / "training-no-cost-resume-guard.md"
    resume_guard_exit_code = no_cost_resume_guard.main([
        str(evidence_bundle_handoff_signoff_summary_path),
        "--summary-markdown",
        str(evidence_bundle_handoff_signoff_summary_markdown_path),
        "--output-manifest",
        str(resume_guard_manifest_path),
        "--output-markdown",
        str(resume_guard_markdown_path),
        "--generated-at",
        "2026-05-14T19:05:00+09:00",
    ])
    assert resume_guard_exit_code == 0
    resume_guard_out = capsys.readouterr().out
    assert "Report quality training no-cost resume guard: PASS" in resume_guard_out
    assert "resume_guard_active=true" in resume_guard_out
    assert "resume_blocked=true" in resume_guard_out
    assert "aws_cost_boundary=no_cost_increase" in resume_guard_out
    assert "training_boundary=not_authorized" in resume_guard_out
    resume_guard = json.loads(resume_guard_manifest_path.read_text(encoding="utf-8"))
    assert resume_guard["schema_version"] == "decisiondoc_report_quality_training_no_cost_resume_guard.v1"
    assert resume_guard["guard_state"]["ok"] is True
    assert resume_guard["guard_state"]["status"] == "no_cost_resume_guard_active"
    assert resume_guard["guard_state"]["resume_blocked"] is True
    assert resume_guard["guard_state"]["operation_resume_approved"] is False
    assert resume_guard["guard_state"]["aws_cost_increase_allowed"] is False
    assert resume_guard["signoff_summary_sha256"] == no_cost_resume_guard._sha256(
        evidence_bundle_handoff_signoff_summary_path
    )
    assert resume_guard["counts"]["signoff_count"] == 1
    assert resume_guard["counts"]["archive_only_review_count"] == 1
    assert resume_guard["source_files"]["signoff_summary_json"]["exists"] is True
    assert resume_guard["guard_boundary"]["training_execution_started"] is False
    resume_guard_markdown = resume_guard_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Resume Guard" in resume_guard_markdown
    assert "resume_blocked: `true`" in resume_guard_markdown
    assert "operation_resume_approved: `false`" in resume_guard_markdown
    assert "aws_cost_increase_allowed: `false`" in resume_guard_markdown

    resume_guard_validation_exit_code = no_cost_resume_guard_validator.main([
        str(resume_guard_manifest_path),
    ])
    assert resume_guard_validation_exit_code == 0
    resume_guard_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost resume guard validated" in resume_guard_validation_out
    assert "resume_guard_active=true" in resume_guard_validation_out
    assert "resume_blocked=true" in resume_guard_validation_out
    assert "aws_cost_boundary=no_cost_increase" in resume_guard_validation_out
    assert "training_boundary=not_authorized" in resume_guard_validation_out
    resume_guard_validation = no_cost_resume_guard_validator.validate_training_no_cost_resume_guard(
        resume_guard_manifest_path,
    )
    assert resume_guard_validation["ok"] is True
    assert resume_guard_validation["summary_validation_ok"] is True

    resume_guard_summary_path = output_root / "training-no-cost-resume-guard-summary.json"
    resume_guard_summary_markdown_path = output_root / "training-no-cost-resume-guard-summary.md"
    resume_guard_summary_exit_code = no_cost_resume_guard_summary.main([
        str(resume_guard_manifest_path),
        "--output",
        str(resume_guard_summary_path),
        "--markdown",
        str(resume_guard_summary_markdown_path),
        "--generated-at",
        "2026-05-14T19:10:00+09:00",
    ])
    assert resume_guard_summary_exit_code == 0
    resume_guard_summary_out = capsys.readouterr().out
    assert "Report quality training no-cost resume guard summary: PASS" in resume_guard_summary_out
    assert "resume_guard_count=1" in resume_guard_summary_out
    assert "valid_resume_guard_count=1" in resume_guard_summary_out
    assert "active_resume_guard_count=1" in resume_guard_summary_out
    assert "aws_cost_boundary=no_cost_increase" in resume_guard_summary_out
    assert "training_boundary=not_authorized" in resume_guard_summary_out
    resume_guard_summary = json.loads(resume_guard_summary_path.read_text(encoding="utf-8"))
    assert resume_guard_summary["schema_version"] == "decisiondoc_report_quality_training_no_cost_resume_guard_summary.v1"
    assert resume_guard_summary["ok"] is True
    assert resume_guard_summary["readiness"]["status"] == "all_resume_guards_confirm_no_cost_block"
    assert resume_guard_summary["readiness"]["resume_blocked"] is True
    assert resume_guard_summary["counts"]["resume_guard_count"] == 1
    assert resume_guard_summary["counts"]["valid_resume_guard_count"] == 1
    assert resume_guard_summary["counts"]["active_resume_guard_count"] == 1
    assert resume_guard_summary["side_effect_boundary"]["aws_cost_increase_allowed"] is False
    resume_guard_summary_markdown = resume_guard_summary_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Resume Guard Summary" in resume_guard_summary_markdown
    assert "resume_blocked: `true`" in resume_guard_summary_markdown
    assert "operation_resume_approved: `false`" in resume_guard_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in resume_guard_summary_markdown

    ops_lock_manifest_path = output_root / "training-no-cost-ops-lock-manifest.json"
    ops_lock_markdown_path = output_root / "training-no-cost-ops-lock.md"
    ops_lock_exit_code = no_cost_ops_lock.main([
        str(resume_guard_summary_path),
        "--summary-markdown",
        str(resume_guard_summary_markdown_path),
        "--output-manifest",
        str(ops_lock_manifest_path),
        "--output-markdown",
        str(ops_lock_markdown_path),
        "--generated-at",
        "2026-05-14T19:15:00+09:00",
    ])
    assert ops_lock_exit_code == 0
    ops_lock_out = capsys.readouterr().out
    assert "Report quality training no-cost ops lock: PASS" in ops_lock_out
    assert "ops_lock_active=true" in ops_lock_out
    assert "service_operation_locked=true" in ops_lock_out
    assert "resume_blocked=true" in ops_lock_out
    assert "aws_cost_boundary=no_cost_increase" in ops_lock_out
    assert "training_boundary=not_authorized" in ops_lock_out
    ops_lock = json.loads(ops_lock_manifest_path.read_text(encoding="utf-8"))
    assert ops_lock["schema_version"] == "decisiondoc_report_quality_training_no_cost_ops_lock.v1"
    assert ops_lock["lock_state"]["ok"] is True
    assert ops_lock["lock_state"]["status"] == "no_cost_ops_lock_active"
    assert ops_lock["lock_state"]["lock_only"] is True
    assert ops_lock["lock_state"]["service_operation_locked"] is True
    assert ops_lock["lock_state"]["resume_blocked"] is True
    assert ops_lock["lock_state"]["operation_resume_approved"] is False
    assert ops_lock["lock_state"]["service_operation_allowed"] is False
    assert ops_lock["lock_state"]["aws_cost_increase_allowed"] is False
    assert ops_lock["resume_guard_summary_sha256"] == no_cost_ops_lock._sha256(resume_guard_summary_path)
    assert ops_lock["counts"]["resume_guard_count"] == 1
    assert ops_lock["counts"]["valid_resume_guard_count"] == 1
    assert ops_lock["counts"]["active_resume_guard_count"] == 1
    assert ops_lock["source_files"]["resume_guard_summary_json"]["exists"] is True
    assert ops_lock["source_files"]["resume_guard_manifest_1"]["exists"] is True
    assert ops_lock["lock_boundary"]["aws_cost_increase_allowed"] is False
    assert ops_lock["lock_boundary"]["training_execution_started"] is False
    ops_lock_markdown = ops_lock_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Ops Lock" in ops_lock_markdown
    assert "ops_lock_active: `true`" in ops_lock_markdown
    assert "service_operation_locked: `true`" in ops_lock_markdown
    assert "resume_blocked: `true`" in ops_lock_markdown
    assert "operation_resume_approved: `false`" in ops_lock_markdown
    assert "aws_cost_increase_allowed: `false`" in ops_lock_markdown

    ops_lock_validation_exit_code = no_cost_ops_lock_validator.main([
        str(ops_lock_manifest_path),
    ])
    assert ops_lock_validation_exit_code == 0
    ops_lock_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost ops lock validated" in ops_lock_validation_out
    assert "ops_lock_active=true" in ops_lock_validation_out
    assert "service_operation_locked=true" in ops_lock_validation_out
    assert "resume_blocked=true" in ops_lock_validation_out
    assert "aws_cost_boundary=no_cost_increase" in ops_lock_validation_out
    assert "training_boundary=not_authorized" in ops_lock_validation_out
    ops_lock_validation = no_cost_ops_lock_validator.validate_training_no_cost_ops_lock(
        ops_lock_manifest_path,
    )
    assert ops_lock_validation["ok"] is True
    assert ops_lock_validation["summary_validation_ok"] is True

    ops_lock_summary_path = output_root / "training-no-cost-ops-lock-summary.json"
    ops_lock_summary_markdown_path = output_root / "training-no-cost-ops-lock-summary.md"
    ops_lock_summary_exit_code = no_cost_ops_lock_summary.main([
        str(ops_lock_manifest_path),
        "--output",
        str(ops_lock_summary_path),
        "--markdown",
        str(ops_lock_summary_markdown_path),
        "--generated-at",
        "2026-05-14T19:20:00+09:00",
    ])
    assert ops_lock_summary_exit_code == 0
    ops_lock_summary_out = capsys.readouterr().out
    assert "Report quality training no-cost ops lock summary: PASS" in ops_lock_summary_out
    assert "ops_lock_count=1" in ops_lock_summary_out
    assert "valid_ops_lock_count=1" in ops_lock_summary_out
    assert "active_ops_lock_count=1" in ops_lock_summary_out
    assert "service_operation_locked=true" in ops_lock_summary_out
    assert "aws_cost_boundary=no_cost_increase" in ops_lock_summary_out
    assert "training_boundary=not_authorized" in ops_lock_summary_out
    ops_lock_summary = json.loads(ops_lock_summary_path.read_text(encoding="utf-8"))
    assert ops_lock_summary["schema_version"] == "decisiondoc_report_quality_training_no_cost_ops_lock_summary.v1"
    assert ops_lock_summary["ok"] is True
    assert ops_lock_summary["readiness"]["status"] == "all_ops_locks_confirm_no_cost_service_lock"
    assert ops_lock_summary["readiness"]["service_operation_locked"] is True
    assert ops_lock_summary["readiness"]["resume_blocked"] is True
    assert ops_lock_summary["counts"]["ops_lock_count"] == 1
    assert ops_lock_summary["counts"]["valid_ops_lock_count"] == 1
    assert ops_lock_summary["counts"]["active_ops_lock_count"] == 1
    assert ops_lock_summary["side_effect_boundary"]["aws_cost_increase_allowed"] is False
    ops_lock_summary_markdown = ops_lock_summary_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Ops Lock Summary" in ops_lock_summary_markdown
    assert "service_operation_locked: `true`" in ops_lock_summary_markdown
    assert "resume_blocked: `true`" in ops_lock_summary_markdown
    assert "operation_resume_approved: `false`" in ops_lock_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in ops_lock_summary_markdown

    ops_lock_handoff_manifest_path = output_root / "training-no-cost-ops-lock-handoff-manifest.json"
    ops_lock_handoff_markdown_path = output_root / "training-no-cost-ops-lock-handoff.md"
    ops_lock_handoff_exit_code = no_cost_ops_lock_handoff.main([
        str(ops_lock_summary_path),
        "--summary-markdown",
        str(ops_lock_summary_markdown_path),
        "--output-manifest",
        str(ops_lock_handoff_manifest_path),
        "--output-markdown",
        str(ops_lock_handoff_markdown_path),
        "--generated-at",
        "2026-05-14T19:25:00+09:00",
    ])
    assert ops_lock_handoff_exit_code == 0
    ops_lock_handoff_out = capsys.readouterr().out
    assert "Report quality training no-cost ops lock handoff: PASS" in ops_lock_handoff_out
    assert "handoff_ready=true" in ops_lock_handoff_out
    assert "service_operation_locked=true" in ops_lock_handoff_out
    assert "resume_blocked=true" in ops_lock_handoff_out
    assert "aws_cost_boundary=no_cost_increase" in ops_lock_handoff_out
    assert "training_boundary=not_authorized" in ops_lock_handoff_out
    ops_lock_handoff_payload = json.loads(ops_lock_handoff_manifest_path.read_text(encoding="utf-8"))
    assert (
        ops_lock_handoff_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_ops_lock_handoff.v1"
    )
    assert ops_lock_handoff_payload["readiness"]["ok"] is True
    assert ops_lock_handoff_payload["readiness"]["status"] == "no_cost_ops_lock_handoff_ready"
    assert ops_lock_handoff_payload["readiness"]["handoff_only"] is True
    assert ops_lock_handoff_payload["readiness"]["service_operation_locked"] is True
    assert ops_lock_handoff_payload["readiness"]["resume_blocked"] is True
    assert ops_lock_handoff_payload["readiness"]["operation_resume_approved"] is False
    assert ops_lock_handoff_payload["readiness"]["aws_cost_increase_allowed"] is False
    assert ops_lock_handoff_payload["ops_lock_summary_sha256"] == no_cost_ops_lock_handoff._sha256(
        ops_lock_summary_path
    )
    assert ops_lock_handoff_payload["counts"]["ops_lock_count"] == 1
    assert ops_lock_handoff_payload["counts"]["valid_ops_lock_count"] == 1
    assert ops_lock_handoff_payload["counts"]["active_ops_lock_count"] == 1
    assert ops_lock_handoff_payload["source_files"]["ops_lock_summary_json"]["exists"] is True
    assert ops_lock_handoff_payload["source_files"]["ops_lock_manifest_1"]["exists"] is True
    assert ops_lock_handoff_payload["handoff_boundary"]["training_execution_started"] is False
    ops_lock_handoff_markdown = ops_lock_handoff_markdown_path.read_text(encoding="utf-8")
    assert "Report Quality Training No-Cost Ops Lock Handoff" in ops_lock_handoff_markdown
    assert "handoff_ready: `true`" in ops_lock_handoff_markdown
    assert "service_operation_locked: `true`" in ops_lock_handoff_markdown
    assert "resume_blocked: `true`" in ops_lock_handoff_markdown
    assert "operation_resume_approved: `false`" in ops_lock_handoff_markdown
    assert "aws_cost_increase_allowed: `false`" in ops_lock_handoff_markdown

    ops_lock_handoff_validation_exit_code = no_cost_ops_lock_handoff_validator.main([
        str(ops_lock_handoff_manifest_path),
    ])
    assert ops_lock_handoff_validation_exit_code == 0
    ops_lock_handoff_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost ops lock handoff validated"
        in ops_lock_handoff_validation_out
    )
    assert "handoff_ready=true" in ops_lock_handoff_validation_out
    assert "service_operation_locked=true" in ops_lock_handoff_validation_out
    assert "resume_blocked=true" in ops_lock_handoff_validation_out
    assert "aws_cost_boundary=no_cost_increase" in ops_lock_handoff_validation_out
    assert "training_boundary=not_authorized" in ops_lock_handoff_validation_out
    ops_lock_handoff_validation = no_cost_ops_lock_handoff_validator.validate_training_no_cost_ops_lock_handoff(
        ops_lock_handoff_manifest_path,
    )
    assert ops_lock_handoff_validation["ok"] is True
    assert ops_lock_handoff_validation["summary_validation_ok"] is True

    ops_lock_handoff_signoff_path = output_root / "training-no-cost-ops-lock-handoff-signoff.json"
    ops_lock_handoff_signoff_exit_code = no_cost_ops_lock_handoff_signoff.main([
        str(ops_lock_handoff_manifest_path),
        "--output",
        str(ops_lock_handoff_signoff_path),
        "--signoff-id",
        "rqp_training_no_cost_ops_lock_handoff_signoff_discussiondone",
        "--created-at",
        "2026-05-14T19:30:00+09:00",
    ])
    assert ops_lock_handoff_signoff_exit_code == 0
    ops_lock_handoff_signoff_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost ops lock handoff pending signoff: PASS"
        in ops_lock_handoff_signoff_out
    )
    assert "pending_validation_ok=true" in ops_lock_handoff_signoff_out
    assert "aws_cost_boundary=no_cost_increase" in ops_lock_handoff_signoff_out
    assert "training_boundary=not_authorized" in ops_lock_handoff_signoff_out
    ops_lock_handoff_signoff_payload = json.loads(ops_lock_handoff_signoff_path.read_text(encoding="utf-8"))
    assert (
        ops_lock_handoff_signoff_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_ops_lock_handoff_signoff.v1"
    )
    assert ops_lock_handoff_signoff_payload["decision"] == "pending"
    assert (
        ops_lock_handoff_signoff_payload["handoff_manifest_sha256"]
        == no_cost_ops_lock_handoff_signoff._sha256(ops_lock_handoff_manifest_path)
    )
    assert ops_lock_handoff_signoff_payload["signoff_boundary"]["service_operation_authorized"] is False
    assert ops_lock_handoff_signoff_payload["signoff_boundary"]["aws_cost_increase_authorized"] is False
    assert ops_lock_handoff_signoff_payload["generation_boundary"]["provider_job_created"] is False
    assert (
        str(ops_lock_handoff_manifest_path)
        in ops_lock_handoff_signoff_payload["generation_context"]["evidence_to_review"]
    )
    assert (
        str(ops_lock_summary_path)
        in ops_lock_handoff_signoff_payload["generation_context"]["evidence_to_review"]
    )
    pending_ops_lock_handoff_signoff_validation = (
        no_cost_ops_lock_handoff_signoff_validator.validate_training_no_cost_ops_lock_handoff_signoff(
            ops_lock_handoff_signoff_payload,
        )
    )
    assert pending_ops_lock_handoff_signoff_validation["ok"] is True
    assert pending_ops_lock_handoff_signoff_validation["completed"] is False

    ops_lock_handoff_signoff_payload["decision"] = "accepted"
    ops_lock_handoff_signoff_payload["reviewer"] = {
        "name": "ops-lock-reviewer",
        "title_or_team": "Ops/Archive",
        "reviewed_at": "2026-05-14T19:35:00+09:00",
    }
    ops_lock_handoff_signoff_payload["evidence_reviewed"] = [
        str(ops_lock_handoff_manifest_path),
        str(ops_lock_handoff_markdown_path),
        str(ops_lock_summary_path),
        str(ops_lock_manifest_path),
    ]
    ops_lock_handoff_signoff_payload["findings"] = {
        "summary": "No-cost ops lock handoff reviewed and confirmed as service-operation lock evidence.",
        "changes_requested": [],
        "residual_risks": ["Project resume still requires separate approval and budget review."],
    }
    for key in ops_lock_handoff_signoff_payload["acknowledgements"]:
        ops_lock_handoff_signoff_payload["acknowledgements"][key] = True
    completed_ops_lock_handoff_signoff_validation = (
        no_cost_ops_lock_handoff_signoff_validator.validate_training_no_cost_ops_lock_handoff_signoff(
            ops_lock_handoff_signoff_payload,
            require_complete=True,
        )
    )
    assert completed_ops_lock_handoff_signoff_validation["ok"] is True
    assert completed_ops_lock_handoff_signoff_validation["completed"] is True
    assert completed_ops_lock_handoff_signoff_validation["handoff_validation_ok"] is True
    ops_lock_handoff_signoff_path.write_text(
        json.dumps(ops_lock_handoff_signoff_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    ops_lock_handoff_signoff_validation_exit_code = no_cost_ops_lock_handoff_signoff_validator.main([
        str(ops_lock_handoff_signoff_path),
        "--require-complete",
    ])
    assert ops_lock_handoff_signoff_validation_exit_code == 0
    ops_lock_handoff_signoff_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost ops lock handoff signoff validated"
        in ops_lock_handoff_signoff_validation_out
    )
    assert "completed=true" in ops_lock_handoff_signoff_validation_out
    assert "decision=accepted" in ops_lock_handoff_signoff_validation_out
    assert "aws_cost_boundary=no_cost_increase" in ops_lock_handoff_signoff_validation_out
    assert "training_boundary=not_authorized" in ops_lock_handoff_signoff_validation_out

    ops_lock_handoff_signoff_summary_path = (
        output_root / "training-no-cost-ops-lock-handoff-signoff-summary.json"
    )
    ops_lock_handoff_signoff_summary_markdown_path = (
        output_root / "training-no-cost-ops-lock-handoff-signoff-summary.md"
    )
    ops_lock_handoff_signoff_summary_exit_code = no_cost_ops_lock_handoff_signoff_summary.main([
        str(ops_lock_handoff_signoff_path),
        "--output",
        str(ops_lock_handoff_signoff_summary_path),
        "--markdown",
        str(ops_lock_handoff_signoff_summary_markdown_path),
        "--generated-at",
        "2026-05-14T19:40:00+09:00",
    ])
    assert ops_lock_handoff_signoff_summary_exit_code == 0
    ops_lock_handoff_signoff_summary_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost ops lock handoff signoff summary: PASS"
        in ops_lock_handoff_signoff_summary_out
    )
    assert "signoff_count=1" in ops_lock_handoff_signoff_summary_out
    assert "valid_signoff_count=1" in ops_lock_handoff_signoff_summary_out
    assert "completed_signoff_count=1" in ops_lock_handoff_signoff_summary_out
    assert "accepted_signoff_count=1" in ops_lock_handoff_signoff_summary_out
    assert "service_lock_review_count=1" in ops_lock_handoff_signoff_summary_out
    assert "aws_cost_boundary=no_cost_increase" in ops_lock_handoff_signoff_summary_out
    assert "training_boundary=not_authorized" in ops_lock_handoff_signoff_summary_out
    ops_lock_handoff_signoff_summary_payload = json.loads(
        ops_lock_handoff_signoff_summary_path.read_text(encoding="utf-8")
    )
    assert (
        ops_lock_handoff_signoff_summary_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_ops_lock_handoff_signoff_summary.v1"
    )
    assert ops_lock_handoff_signoff_summary_payload["ok"] is True
    assert (
        ops_lock_handoff_signoff_summary_payload["readiness"]["status"]
        == "all_ops_lock_handoff_signoffs_confirm_service_lock"
    )
    assert ops_lock_handoff_signoff_summary_payload["readiness"]["service_operation_locked"] is True
    assert ops_lock_handoff_signoff_summary_payload["readiness"]["resume_blocked"] is True
    assert ops_lock_handoff_signoff_summary_payload["readiness"]["operation_resume_approved"] is False
    assert ops_lock_handoff_signoff_summary_payload["readiness"]["service_operation_allowed"] is False
    assert ops_lock_handoff_signoff_summary_payload["counts"]["signoff_count"] == 1
    assert ops_lock_handoff_signoff_summary_payload["counts"]["valid_signoff_count"] == 1
    assert ops_lock_handoff_signoff_summary_payload["counts"]["completed_signoff_count"] == 1
    assert ops_lock_handoff_signoff_summary_payload["counts"]["accepted_signoff_count"] == 1
    assert ops_lock_handoff_signoff_summary_payload["counts"]["service_lock_review_count"] == 1
    assert (
        ops_lock_handoff_signoff_summary_payload["side_effect_boundary"]["aws_cost_increase_allowed"]
        is False
    )
    assert (
        ops_lock_handoff_signoff_summary_payload["side_effect_boundary"]["training_execution_started"]
        is False
    )
    ops_lock_handoff_signoff_summary_markdown = (
        ops_lock_handoff_signoff_summary_markdown_path.read_text(encoding="utf-8")
    )
    assert (
        "# Report Quality Training No-Cost Ops Lock Handoff Sign-Off Summary"
        in ops_lock_handoff_signoff_summary_markdown
    )
    assert "service_operation_locked: `true`" in ops_lock_handoff_signoff_summary_markdown
    assert "resume_blocked: `true`" in ops_lock_handoff_signoff_summary_markdown
    assert "operation_resume_approved: `false`" in ops_lock_handoff_signoff_summary_markdown
    assert "service_operation_allowed: `false`" in ops_lock_handoff_signoff_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in ops_lock_handoff_signoff_summary_markdown

    final_hold_manifest_path = output_root / "training-no-cost-final-hold-manifest.json"
    final_hold_markdown_path = output_root / "training-no-cost-final-hold.md"
    final_hold_exit_code = no_cost_final_hold.main([
        str(ops_lock_handoff_signoff_summary_path),
        "--summary-markdown",
        str(ops_lock_handoff_signoff_summary_markdown_path),
        "--output-manifest",
        str(final_hold_manifest_path),
        "--output-markdown",
        str(final_hold_markdown_path),
        "--generated-at",
        "2026-05-14T19:45:00+09:00",
    ])
    assert final_hold_exit_code == 0
    final_hold_out = capsys.readouterr().out
    assert "Report quality training no-cost final hold: PASS" in final_hold_out
    assert "final_hold_active=true" in final_hold_out
    assert "service_operation_locked=true" in final_hold_out
    assert "resume_blocked=true" in final_hold_out
    assert "aws_cost_boundary=no_cost_increase" in final_hold_out
    assert "training_boundary=not_authorized" in final_hold_out
    final_hold_payload = json.loads(final_hold_manifest_path.read_text(encoding="utf-8"))
    assert final_hold_payload["schema_version"] == "decisiondoc_report_quality_training_no_cost_final_hold.v1"
    assert final_hold_payload["final_hold_state"]["status"] == "no_cost_final_hold_active"
    assert final_hold_payload["final_hold_state"]["active"] is True
    assert final_hold_payload["final_hold_state"]["service_operation_locked"] is True
    assert final_hold_payload["final_hold_state"]["resume_blocked"] is True
    assert final_hold_payload["final_hold_state"]["operation_resume_approved"] is False
    assert final_hold_payload["final_hold_state"]["service_operation_allowed"] is False
    assert (
        final_hold_payload["ops_lock_handoff_signoff_summary_sha256"]
        == no_cost_final_hold._sha256(ops_lock_handoff_signoff_summary_path)
    )
    assert final_hold_payload["summary_validation"]["ok"] is True
    assert final_hold_payload["counts"]["signoff_count"] == 1
    assert final_hold_payload["counts"]["service_lock_review_count"] == 1
    assert final_hold_payload["counts"]["missing_file_count"] == 0
    assert final_hold_payload["final_hold_boundary"]["aws_cost_increase_allowed"] is False
    assert final_hold_payload["final_hold_boundary"]["training_execution_started"] is False

    final_hold_validation_exit_code = no_cost_final_hold_validator.main([
        str(final_hold_manifest_path),
    ])
    assert final_hold_validation_exit_code == 0
    final_hold_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost final hold validated" in final_hold_validation_out
    assert "final_hold_active=true" in final_hold_validation_out
    assert "service_operation_locked=true" in final_hold_validation_out
    assert "resume_blocked=true" in final_hold_validation_out
    assert "aws_cost_boundary=no_cost_increase" in final_hold_validation_out
    assert "training_boundary=not_authorized" in final_hold_validation_out
    final_hold_markdown = final_hold_markdown_path.read_text(encoding="utf-8")
    assert "# Report Quality Training No-Cost Final Hold" in final_hold_markdown
    assert "final_hold_active: `true`" in final_hold_markdown
    assert "service_operation_locked: `true`" in final_hold_markdown
    assert "resume_blocked: `true`" in final_hold_markdown
    assert "operation_resume_approved: `false`" in final_hold_markdown
    assert "aws_cost_increase_allowed: `false`" in final_hold_markdown

    final_hold_summary_path = output_root / "training-no-cost-final-hold-summary.json"
    final_hold_summary_markdown_path = output_root / "training-no-cost-final-hold-summary.md"
    final_hold_summary_exit_code = no_cost_final_hold_summary.main([
        str(final_hold_manifest_path),
        "--output",
        str(final_hold_summary_path),
        "--markdown",
        str(final_hold_summary_markdown_path),
        "--generated-at",
        "2026-05-14T19:50:00+09:00",
    ])
    assert final_hold_summary_exit_code == 0
    final_hold_summary_out = capsys.readouterr().out
    assert "Report quality training no-cost final hold summary: PASS" in final_hold_summary_out
    assert "final_hold_count=1" in final_hold_summary_out
    assert "valid_final_hold_count=1" in final_hold_summary_out
    assert "active_final_hold_count=1" in final_hold_summary_out
    assert "service_operation_locked=true" in final_hold_summary_out
    assert "aws_cost_boundary=no_cost_increase" in final_hold_summary_out
    assert "training_boundary=not_authorized" in final_hold_summary_out
    final_hold_summary_payload = json.loads(final_hold_summary_path.read_text(encoding="utf-8"))
    assert (
        final_hold_summary_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_final_hold_summary.v1"
    )
    assert final_hold_summary_payload["ok"] is True
    assert (
        final_hold_summary_payload["readiness"]["status"]
        == "all_final_holds_confirm_no_cost_service_lock"
    )
    assert final_hold_summary_payload["readiness"]["service_operation_locked"] is True
    assert final_hold_summary_payload["readiness"]["resume_blocked"] is True
    assert final_hold_summary_payload["readiness"]["operation_resume_approved"] is False
    assert final_hold_summary_payload["readiness"]["service_operation_allowed"] is False
    assert final_hold_summary_payload["counts"]["final_hold_count"] == 1
    assert final_hold_summary_payload["counts"]["valid_final_hold_count"] == 1
    assert final_hold_summary_payload["counts"]["active_final_hold_count"] == 1
    assert final_hold_summary_payload["counts"]["signoff_count"] == 1
    assert final_hold_summary_payload["counts"]["service_lock_review_count"] == 1
    assert final_hold_summary_payload["side_effect_boundary"]["aws_cost_increase_allowed"] is False
    assert final_hold_summary_payload["side_effect_boundary"]["training_execution_started"] is False
    final_hold_summary_markdown = final_hold_summary_markdown_path.read_text(encoding="utf-8")
    assert "# Report Quality Training No-Cost Final Hold Summary" in final_hold_summary_markdown
    assert "service_operation_locked: `true`" in final_hold_summary_markdown
    assert "resume_blocked: `true`" in final_hold_summary_markdown
    assert "operation_resume_approved: `false`" in final_hold_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in final_hold_summary_markdown

    closeout_receipt_manifest_path = output_root / "training-no-cost-closeout-receipt-manifest.json"
    closeout_receipt_markdown_path = output_root / "training-no-cost-closeout-receipt.md"
    closeout_receipt_exit_code = no_cost_closeout_receipt.main([
        str(final_hold_summary_path),
        "--summary-markdown",
        str(final_hold_summary_markdown_path),
        "--output-manifest",
        str(closeout_receipt_manifest_path),
        "--output-markdown",
        str(closeout_receipt_markdown_path),
        "--generated-at",
        "2026-05-14T19:55:00+09:00",
    ])
    assert closeout_receipt_exit_code == 0
    closeout_receipt_out = capsys.readouterr().out
    assert "Report quality training no-cost closeout receipt: PASS" in closeout_receipt_out
    assert "receipt_ready=true" in closeout_receipt_out
    assert "service_operation_locked=true" in closeout_receipt_out
    assert "resume_blocked=true" in closeout_receipt_out
    assert "aws_cost_boundary=no_cost_increase" in closeout_receipt_out
    assert "training_boundary=not_authorized" in closeout_receipt_out
    closeout_receipt_payload = json.loads(closeout_receipt_manifest_path.read_text(encoding="utf-8"))
    assert (
        closeout_receipt_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_closeout_receipt.v1"
    )
    assert closeout_receipt_payload["receipt_state"]["status"] == "no_cost_closeout_receipt_ready"
    assert closeout_receipt_payload["receipt_state"]["ready"] is True
    assert closeout_receipt_payload["receipt_state"]["service_operation_locked"] is True
    assert closeout_receipt_payload["receipt_state"]["resume_blocked"] is True
    assert closeout_receipt_payload["receipt_state"]["operation_resume_approved"] is False
    assert closeout_receipt_payload["receipt_state"]["service_operation_allowed"] is False
    assert (
        closeout_receipt_payload["final_hold_summary_sha256"]
        == no_cost_closeout_receipt._sha256(final_hold_summary_path)
    )
    assert closeout_receipt_payload["summary_validation"]["ok"] is True
    assert closeout_receipt_payload["counts"]["final_hold_count"] == 1
    assert closeout_receipt_payload["counts"]["active_final_hold_count"] == 1
    assert closeout_receipt_payload["counts"]["missing_file_count"] == 0
    assert closeout_receipt_payload["closeout_boundary"]["aws_cost_increase_allowed"] is False
    assert closeout_receipt_payload["closeout_boundary"]["training_execution_started"] is False

    closeout_receipt_validation_exit_code = no_cost_closeout_receipt_validator.main([
        str(closeout_receipt_manifest_path),
    ])
    assert closeout_receipt_validation_exit_code == 0
    closeout_receipt_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost closeout receipt validated" in closeout_receipt_validation_out
    assert "receipt_ready=true" in closeout_receipt_validation_out
    assert "service_operation_locked=true" in closeout_receipt_validation_out
    assert "resume_blocked=true" in closeout_receipt_validation_out
    assert "aws_cost_boundary=no_cost_increase" in closeout_receipt_validation_out
    assert "training_boundary=not_authorized" in closeout_receipt_validation_out
    closeout_receipt_markdown = closeout_receipt_markdown_path.read_text(encoding="utf-8")
    assert "# Report Quality Training No-Cost Closeout Receipt" in closeout_receipt_markdown
    assert "receipt_ready: `true`" in closeout_receipt_markdown
    assert "service_operation_locked: `true`" in closeout_receipt_markdown
    assert "resume_blocked: `true`" in closeout_receipt_markdown
    assert "operation_resume_approved: `false`" in closeout_receipt_markdown
    assert "aws_cost_increase_allowed: `false`" in closeout_receipt_markdown

    closeout_receipt_summary_path = output_root / "training-no-cost-closeout-receipt-summary.json"
    closeout_receipt_summary_markdown_path = output_root / "training-no-cost-closeout-receipt-summary.md"
    closeout_receipt_summary_exit_code = no_cost_closeout_receipt_summary.main([
        str(closeout_receipt_manifest_path),
        "--output",
        str(closeout_receipt_summary_path),
        "--markdown",
        str(closeout_receipt_summary_markdown_path),
        "--generated-at",
        "2026-05-14T20:00:00+09:00",
    ])
    assert closeout_receipt_summary_exit_code == 0
    closeout_receipt_summary_out = capsys.readouterr().out
    assert "Report quality training no-cost closeout receipt summary: PASS" in closeout_receipt_summary_out
    assert "closeout_receipt_count=1" in closeout_receipt_summary_out
    assert "valid_closeout_receipt_count=1" in closeout_receipt_summary_out
    assert "ready_closeout_receipt_count=1" in closeout_receipt_summary_out
    assert "service_operation_locked=true" in closeout_receipt_summary_out
    assert "aws_cost_boundary=no_cost_increase" in closeout_receipt_summary_out
    assert "training_boundary=not_authorized" in closeout_receipt_summary_out
    closeout_receipt_summary_payload = json.loads(closeout_receipt_summary_path.read_text(encoding="utf-8"))
    assert (
        closeout_receipt_summary_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_closeout_receipt_summary.v1"
    )
    assert closeout_receipt_summary_payload["ok"] is True
    assert (
        closeout_receipt_summary_payload["readiness"]["status"]
        == "all_closeout_receipts_confirm_no_cost_service_lock"
    )
    assert closeout_receipt_summary_payload["readiness"]["service_operation_locked"] is True
    assert closeout_receipt_summary_payload["readiness"]["resume_blocked"] is True
    assert closeout_receipt_summary_payload["readiness"]["operation_resume_approved"] is False
    assert closeout_receipt_summary_payload["readiness"]["service_operation_allowed"] is False
    assert closeout_receipt_summary_payload["counts"]["closeout_receipt_count"] == 1
    assert closeout_receipt_summary_payload["counts"]["valid_closeout_receipt_count"] == 1
    assert closeout_receipt_summary_payload["counts"]["ready_closeout_receipt_count"] == 1
    assert closeout_receipt_summary_payload["counts"]["final_hold_count"] == 1
    assert closeout_receipt_summary_payload["counts"]["active_final_hold_count"] == 1
    assert closeout_receipt_summary_payload["side_effect_boundary"]["aws_cost_increase_allowed"] is False
    assert closeout_receipt_summary_payload["side_effect_boundary"]["training_execution_started"] is False
    closeout_receipt_summary_markdown = closeout_receipt_summary_markdown_path.read_text(encoding="utf-8")
    assert "# Report Quality Training No-Cost Closeout Receipt Summary" in closeout_receipt_summary_markdown
    assert "service_operation_locked: `true`" in closeout_receipt_summary_markdown
    assert "resume_blocked: `true`" in closeout_receipt_summary_markdown
    assert "operation_resume_approved: `false`" in closeout_receipt_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in closeout_receipt_summary_markdown

    service_lock_check_exit_code = no_cost_service_lock_check.main([
        str(closeout_receipt_summary_path),
    ])
    assert service_lock_check_exit_code == 0
    service_lock_check_out = capsys.readouterr().out
    assert "PASS report quality training no-cost service lock checked" in service_lock_check_out
    assert "status=service_locked" in service_lock_check_out
    assert "service_operation_locked=true" in service_lock_check_out
    assert "resume_blocked=true" in service_lock_check_out
    assert "operation_resume_approved=false" in service_lock_check_out
    assert "aws_cost_boundary=no_cost_increase" in service_lock_check_out
    assert "training_boundary=not_authorized" in service_lock_check_out

    service_lock_report_path = output_root / "training-no-cost-service-lock-report.json"
    service_lock_report_markdown_path = output_root / "training-no-cost-service-lock-report.md"
    service_lock_report_exit_code = no_cost_service_lock_report.main([
        str(closeout_receipt_summary_path),
        "--output-manifest",
        str(service_lock_report_path),
        "--output-markdown",
        str(service_lock_report_markdown_path),
        "--generated-at",
        "2026-05-14T20:05:00+09:00",
    ])
    assert service_lock_report_exit_code == 0
    service_lock_report_out = capsys.readouterr().out
    assert "Report quality training no-cost service lock report: PASS" in service_lock_report_out
    assert "service_lock_report_ready=true" in service_lock_report_out
    assert "service_operation_locked=true" in service_lock_report_out
    assert "resume_blocked=true" in service_lock_report_out
    assert "aws_cost_boundary=no_cost_increase" in service_lock_report_out
    assert "training_boundary=not_authorized" in service_lock_report_out
    service_lock_report_payload = json.loads(service_lock_report_path.read_text(encoding="utf-8"))
    assert (
        service_lock_report_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_service_lock_report.v1"
    )
    assert service_lock_report_payload["report_state"]["status"] == "no_cost_service_lock_report_ready"
    assert service_lock_report_payload["report_state"]["ready"] is True
    assert service_lock_report_payload["report_state"]["service_operation_locked"] is True
    assert service_lock_report_payload["report_state"]["resume_blocked"] is True
    assert service_lock_report_payload["report_state"]["operation_resume_approved"] is False
    assert service_lock_report_payload["report_state"]["service_operation_allowed"] is False
    assert service_lock_report_payload["service_lock_check"]["ok"] is True
    assert (
        service_lock_report_payload["closeout_receipt_summary_sha256"]
        == no_cost_service_lock_report._sha256(closeout_receipt_summary_path)
    )
    assert service_lock_report_payload["counts"]["closeout_receipt_count"] == 1
    assert service_lock_report_payload["counts"]["ready_closeout_receipt_count"] == 1
    assert service_lock_report_payload["report_boundary"]["aws_cost_increase_allowed"] is False
    assert service_lock_report_payload["report_boundary"]["training_execution_started"] is False
    service_lock_report_markdown = service_lock_report_markdown_path.read_text(encoding="utf-8")
    assert "# Report Quality Training No-Cost Service Lock Report" in service_lock_report_markdown
    assert "service_lock_check_ok: `true`" in service_lock_report_markdown
    assert "service_operation_locked: `true`" in service_lock_report_markdown
    assert "resume_blocked: `true`" in service_lock_report_markdown
    assert "operation_resume_approved: `false`" in service_lock_report_markdown
    assert "aws_cost_increase_allowed: `false`" in service_lock_report_markdown

    service_lock_report_validation_exit_code = no_cost_service_lock_report_validator.main([
        str(service_lock_report_path),
    ])
    assert service_lock_report_validation_exit_code == 0
    service_lock_report_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost service lock report validated" in service_lock_report_validation_out
    assert "service_lock_report_ready=true" in service_lock_report_validation_out
    assert "service_operation_locked=true" in service_lock_report_validation_out
    assert "resume_blocked=true" in service_lock_report_validation_out
    assert "aws_cost_boundary=no_cost_increase" in service_lock_report_validation_out
    assert "training_boundary=not_authorized" in service_lock_report_validation_out

    service_lock_report_summary_path = output_root / "training-no-cost-service-lock-report-summary.json"
    service_lock_report_summary_markdown_path = output_root / "training-no-cost-service-lock-report-summary.md"
    service_lock_report_summary_exit_code = no_cost_service_lock_report_summary.main([
        str(service_lock_report_path),
        "--output",
        str(service_lock_report_summary_path),
        "--markdown",
        str(service_lock_report_summary_markdown_path),
        "--generated-at",
        "2026-05-14T20:10:00+09:00",
    ])
    assert service_lock_report_summary_exit_code == 0
    service_lock_report_summary_out = capsys.readouterr().out
    assert "Report quality training no-cost service lock report summary: PASS" in service_lock_report_summary_out
    assert "service_lock_report_count=1" in service_lock_report_summary_out
    assert "valid_service_lock_report_count=1" in service_lock_report_summary_out
    assert "ready_service_lock_report_count=1" in service_lock_report_summary_out
    assert "service_operation_locked=true" in service_lock_report_summary_out
    assert "aws_cost_boundary=no_cost_increase" in service_lock_report_summary_out
    assert "training_boundary=not_authorized" in service_lock_report_summary_out
    service_lock_report_summary_payload = json.loads(service_lock_report_summary_path.read_text(encoding="utf-8"))
    assert (
        service_lock_report_summary_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_service_lock_report_summary.v1"
    )
    assert service_lock_report_summary_payload["ok"] is True
    assert (
        service_lock_report_summary_payload["readiness"]["status"]
        == "all_service_lock_reports_confirm_no_cost_service_lock"
    )
    assert service_lock_report_summary_payload["readiness"]["service_operation_locked"] is True
    assert service_lock_report_summary_payload["readiness"]["resume_blocked"] is True
    assert service_lock_report_summary_payload["readiness"]["operation_resume_approved"] is False
    assert service_lock_report_summary_payload["readiness"]["service_operation_allowed"] is False
    assert service_lock_report_summary_payload["counts"]["service_lock_report_count"] == 1
    assert service_lock_report_summary_payload["counts"]["valid_service_lock_report_count"] == 1
    assert service_lock_report_summary_payload["counts"]["ready_service_lock_report_count"] == 1
    assert service_lock_report_summary_payload["counts"]["closeout_receipt_count"] == 1
    assert service_lock_report_summary_payload["counts"]["ready_closeout_receipt_count"] == 1
    assert service_lock_report_summary_payload["side_effect_boundary"]["aws_cost_increase_allowed"] is False
    assert service_lock_report_summary_payload["side_effect_boundary"]["training_execution_started"] is False
    service_lock_report_summary_markdown = service_lock_report_summary_markdown_path.read_text(encoding="utf-8")
    assert "# Report Quality Training No-Cost Service Lock Report Summary" in service_lock_report_summary_markdown
    assert "service_operation_locked: `true`" in service_lock_report_summary_markdown
    assert "resume_blocked: `true`" in service_lock_report_summary_markdown
    assert "operation_resume_approved: `false`" in service_lock_report_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in service_lock_report_summary_markdown

    service_lock_report_summary_validation_exit_code = no_cost_service_lock_report_summary_validator.main([
        str(service_lock_report_summary_path),
    ])
    assert service_lock_report_summary_validation_exit_code == 0
    service_lock_report_summary_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost service lock report summary validated"
        in service_lock_report_summary_validation_out
    )
    assert "service_lock_report_summary_ready=true" in service_lock_report_summary_validation_out
    assert "service_operation_locked=true" in service_lock_report_summary_validation_out
    assert "resume_blocked=true" in service_lock_report_summary_validation_out
    assert "aws_cost_boundary=no_cost_increase" in service_lock_report_summary_validation_out
    assert "training_boundary=not_authorized" in service_lock_report_summary_validation_out

    operator_handoff_manifest_path = output_root / "training-no-cost-operator-handoff-manifest.json"
    operator_handoff_markdown_path = output_root / "training-no-cost-operator-handoff.md"
    operator_handoff_exit_code = no_cost_operator_handoff.main([
        str(service_lock_report_summary_path),
        "--output-manifest",
        str(operator_handoff_manifest_path),
        "--output-markdown",
        str(operator_handoff_markdown_path),
        "--generated-at",
        "2026-05-14T20:15:00+09:00",
    ])
    assert operator_handoff_exit_code == 0
    operator_handoff_out = capsys.readouterr().out
    assert "Report quality training no-cost operator handoff: PASS" in operator_handoff_out
    assert "operator_handoff_ready=true" in operator_handoff_out
    assert "service_operation_locked=true" in operator_handoff_out
    assert "resume_blocked=true" in operator_handoff_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_out
    assert "training_boundary=not_authorized" in operator_handoff_out
    operator_handoff_payload = json.loads(operator_handoff_manifest_path.read_text(encoding="utf-8"))
    assert (
        operator_handoff_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_operator_handoff.v1"
    )
    assert operator_handoff_payload["handoff_state"]["status"] == "no_cost_operator_handoff_ready"
    assert operator_handoff_payload["handoff_state"]["ready"] is True
    assert operator_handoff_payload["handoff_state"]["service_operation_locked"] is True
    assert operator_handoff_payload["handoff_state"]["resume_blocked"] is True
    assert operator_handoff_payload["handoff_state"]["operation_resume_approved"] is False
    assert operator_handoff_payload["handoff_state"]["service_operation_allowed"] is False
    assert operator_handoff_payload["summary_validation"]["ok"] is True
    assert (
        operator_handoff_payload["service_lock_report_summary_sha256"]
        == no_cost_operator_handoff._sha256(service_lock_report_summary_path)
    )
    assert operator_handoff_payload["counts"]["service_lock_report_count"] == 1
    assert operator_handoff_payload["counts"]["ready_service_lock_report_count"] == 1
    assert operator_handoff_payload["handoff_boundary"]["aws_cost_increase_allowed"] is False
    assert operator_handoff_payload["handoff_boundary"]["training_execution_started"] is False
    operator_handoff_markdown = operator_handoff_markdown_path.read_text(encoding="utf-8")
    assert "# Report Quality Training No-Cost Operator Handoff" in operator_handoff_markdown
    assert "handoff_ready: `true`" in operator_handoff_markdown
    assert "service_operation_locked: `true`" in operator_handoff_markdown
    assert "resume_blocked: `true`" in operator_handoff_markdown
    assert "operation_resume_approved: `false`" in operator_handoff_markdown
    assert "aws_cost_increase_allowed: `false`" in operator_handoff_markdown

    operator_handoff_validation_exit_code = no_cost_operator_handoff_validator.main([
        str(operator_handoff_manifest_path),
    ])
    assert operator_handoff_validation_exit_code == 0
    operator_handoff_validation_out = capsys.readouterr().out
    assert "PASS report quality training no-cost operator handoff validated" in operator_handoff_validation_out
    assert "operator_handoff_ready=true" in operator_handoff_validation_out
    assert "service_operation_locked=true" in operator_handoff_validation_out
    assert "resume_blocked=true" in operator_handoff_validation_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_validation_out
    assert "training_boundary=not_authorized" in operator_handoff_validation_out

    operator_handoff_signoff_path = output_root / "training-no-cost-operator-handoff-signoff.json"
    operator_handoff_signoff_exit_code = no_cost_operator_handoff_signoff.main([
        str(operator_handoff_manifest_path),
        "--output",
        str(operator_handoff_signoff_path),
        "--signoff-id",
        "rqp_training_no_cost_operator_handoff_signoff_discussiondone",
        "--created-at",
        "2026-05-14T20:20:00+09:00",
    ])
    assert operator_handoff_signoff_exit_code == 0
    operator_handoff_signoff_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost operator handoff pending signoff: PASS"
        in operator_handoff_signoff_out
    )
    assert "pending_validation_ok=true" in operator_handoff_signoff_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_signoff_out
    assert "training_boundary=not_authorized" in operator_handoff_signoff_out
    operator_handoff_signoff_payload = json.loads(operator_handoff_signoff_path.read_text(encoding="utf-8"))
    assert (
        operator_handoff_signoff_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_operator_handoff_signoff.v1"
    )
    assert operator_handoff_signoff_payload["decision"] == "pending"
    assert (
        operator_handoff_signoff_payload["handoff_manifest_sha256"]
        == no_cost_operator_handoff_signoff._sha256(operator_handoff_manifest_path)
    )
    assert operator_handoff_signoff_payload["signoff_boundary"]["service_operation_authorized"] is False
    assert operator_handoff_signoff_payload["signoff_boundary"]["aws_cost_increase_authorized"] is False
    assert operator_handoff_signoff_payload["generation_boundary"]["provider_job_created"] is False
    assert (
        str(operator_handoff_markdown_path.resolve())
        in operator_handoff_signoff_payload["generation_context"]["evidence_to_review"]
    )
    assert (
        str(service_lock_report_summary_path.resolve())
        in operator_handoff_signoff_payload["generation_context"]["evidence_to_review"]
    )

    pending_operator_handoff_signoff_validation = (
        no_cost_operator_handoff_signoff_validator.validate_training_no_cost_operator_handoff_signoff(
            operator_handoff_signoff_payload,
        )
    )
    assert pending_operator_handoff_signoff_validation["ok"] is True
    assert pending_operator_handoff_signoff_validation["completed"] is False

    operator_handoff_signoff_payload["decision"] = "accepted"
    operator_handoff_signoff_payload["reviewer"] = {
        "name": "No-Cost Operator Reviewer",
        "title_or_team": "Ops",
        "reviewed_at": "2026-05-14T20:30:00+09:00",
    }
    operator_handoff_signoff_payload["evidence_reviewed"] = [
        str(operator_handoff_manifest_path.resolve()),
        str(operator_handoff_markdown_path.resolve()),
        str(service_lock_report_summary_path.resolve()),
    ]
    operator_handoff_signoff_payload["findings"] = {
        "summary": "Operator handoff reviewed as no-cost service lock evidence.",
        "changes_requested": [],
        "residual_risks": ["Service resume still requires separate approval."],
    }
    for key in operator_handoff_signoff_payload["acknowledgements"]:
        operator_handoff_signoff_payload["acknowledgements"][key] = True
    completed_operator_handoff_signoff_validation = (
        no_cost_operator_handoff_signoff_validator.validate_training_no_cost_operator_handoff_signoff(
            operator_handoff_signoff_payload,
            require_complete=True,
        )
    )
    assert completed_operator_handoff_signoff_validation["ok"] is True
    assert completed_operator_handoff_signoff_validation["completed"] is True
    assert completed_operator_handoff_signoff_validation["handoff_validation_ok"] is True
    operator_handoff_signoff_path.write_text(
        json.dumps(operator_handoff_signoff_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    operator_handoff_signoff_validation_exit_code = no_cost_operator_handoff_signoff_validator.main([
        str(operator_handoff_signoff_path),
        "--require-complete",
    ])
    assert operator_handoff_signoff_validation_exit_code == 0
    operator_handoff_signoff_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost operator handoff signoff validated"
        in operator_handoff_signoff_validation_out
    )
    assert "completed=true" in operator_handoff_signoff_validation_out
    assert "decision=accepted" in operator_handoff_signoff_validation_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_signoff_validation_out
    assert "training_boundary=not_authorized" in operator_handoff_signoff_validation_out

    operator_handoff_signoff_summary_path = (
        output_root / "training-no-cost-operator-handoff-signoff-summary.json"
    )
    operator_handoff_signoff_summary_markdown_path = (
        output_root / "training-no-cost-operator-handoff-signoff-summary.md"
    )
    operator_handoff_signoff_summary_exit_code = no_cost_operator_handoff_signoff_summary.main([
        str(operator_handoff_signoff_path),
        "--output",
        str(operator_handoff_signoff_summary_path),
        "--markdown",
        str(operator_handoff_signoff_summary_markdown_path),
        "--generated-at",
        "2026-05-14T20:35:00+09:00",
    ])
    assert operator_handoff_signoff_summary_exit_code == 0
    operator_handoff_signoff_summary_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost operator handoff signoff summary: PASS"
        in operator_handoff_signoff_summary_out
    )
    assert "signoff_count=1" in operator_handoff_signoff_summary_out
    assert "valid_signoff_count=1" in operator_handoff_signoff_summary_out
    assert "completed_signoff_count=1" in operator_handoff_signoff_summary_out
    assert "accepted_signoff_count=1" in operator_handoff_signoff_summary_out
    assert "operator_handoff_review_count=1" in operator_handoff_signoff_summary_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_signoff_summary_out
    assert "training_boundary=not_authorized" in operator_handoff_signoff_summary_out
    operator_handoff_signoff_summary_payload = json.loads(
        operator_handoff_signoff_summary_path.read_text(encoding="utf-8")
    )
    assert (
        operator_handoff_signoff_summary_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_operator_handoff_signoff_summary.v1"
    )
    assert operator_handoff_signoff_summary_payload["ok"] is True
    assert (
        operator_handoff_signoff_summary_payload["readiness"]["status"]
        == "all_operator_handoff_signoffs_confirm_service_lock"
    )
    assert operator_handoff_signoff_summary_payload["readiness"]["service_operation_locked"] is True
    assert operator_handoff_signoff_summary_payload["readiness"]["resume_blocked"] is True
    assert operator_handoff_signoff_summary_payload["readiness"]["operation_resume_approved"] is False
    assert operator_handoff_signoff_summary_payload["readiness"]["service_operation_allowed"] is False
    assert operator_handoff_signoff_summary_payload["counts"]["signoff_count"] == 1
    assert operator_handoff_signoff_summary_payload["counts"]["valid_signoff_count"] == 1
    assert operator_handoff_signoff_summary_payload["counts"]["completed_signoff_count"] == 1
    assert operator_handoff_signoff_summary_payload["counts"]["accepted_signoff_count"] == 1
    assert operator_handoff_signoff_summary_payload["counts"]["operator_handoff_review_count"] == 1
    assert (
        operator_handoff_signoff_summary_payload["side_effect_boundary"]["aws_cost_increase_allowed"]
        is False
    )
    assert (
        operator_handoff_signoff_summary_payload["side_effect_boundary"]["training_execution_started"]
        is False
    )
    operator_handoff_signoff_summary_markdown = (
        operator_handoff_signoff_summary_markdown_path.read_text(encoding="utf-8")
    )
    assert (
        "# Report Quality Training No-Cost Operator Handoff Sign-Off Summary"
        in operator_handoff_signoff_summary_markdown
    )
    assert "service_operation_locked: `true`" in operator_handoff_signoff_summary_markdown
    assert "resume_blocked: `true`" in operator_handoff_signoff_summary_markdown
    assert "operation_resume_approved: `false`" in operator_handoff_signoff_summary_markdown
    assert "service_operation_allowed: `false`" in operator_handoff_signoff_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in operator_handoff_signoff_summary_markdown

    operator_handoff_signoff_summary_validation_exit_code = (
        no_cost_operator_handoff_signoff_summary_validator.main([
            str(operator_handoff_signoff_summary_path),
        ])
    )
    assert operator_handoff_signoff_summary_validation_exit_code == 0
    operator_handoff_signoff_summary_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost operator handoff signoff summary validated"
        in operator_handoff_signoff_summary_validation_out
    )
    assert "operator_handoff_signoff_summary_ready=true" in operator_handoff_signoff_summary_validation_out
    assert "service_operation_locked=true" in operator_handoff_signoff_summary_validation_out
    assert "resume_blocked=true" in operator_handoff_signoff_summary_validation_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_signoff_summary_validation_out
    assert "training_boundary=not_authorized" in operator_handoff_signoff_summary_validation_out

    operator_handoff_closeout_receipt_path = (
        output_root / "training-no-cost-operator-handoff-closeout-receipt-manifest.json"
    )
    operator_handoff_closeout_receipt_markdown_path = (
        output_root / "training-no-cost-operator-handoff-closeout-receipt.md"
    )
    operator_handoff_closeout_receipt_exit_code = no_cost_operator_handoff_closeout_receipt.main([
        str(operator_handoff_signoff_summary_path),
        "--summary-markdown",
        str(operator_handoff_signoff_summary_markdown_path),
        "--output-manifest",
        str(operator_handoff_closeout_receipt_path),
        "--output-markdown",
        str(operator_handoff_closeout_receipt_markdown_path),
        "--generated-at",
        "2026-05-14T20:40:00+09:00",
    ])
    assert operator_handoff_closeout_receipt_exit_code == 0
    operator_handoff_closeout_receipt_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost operator handoff closeout receipt: PASS"
        in operator_handoff_closeout_receipt_out
    )
    assert "receipt_ready=true" in operator_handoff_closeout_receipt_out
    assert "service_operation_locked=true" in operator_handoff_closeout_receipt_out
    assert "resume_blocked=true" in operator_handoff_closeout_receipt_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_closeout_receipt_out
    assert "training_boundary=not_authorized" in operator_handoff_closeout_receipt_out
    operator_handoff_closeout_receipt_payload = json.loads(
        operator_handoff_closeout_receipt_path.read_text(encoding="utf-8")
    )
    assert (
        operator_handoff_closeout_receipt_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_operator_handoff_closeout_receipt.v1"
    )
    assert (
        operator_handoff_closeout_receipt_payload["receipt_state"]["status"]
        == "no_cost_operator_handoff_closeout_receipt_ready"
    )
    assert operator_handoff_closeout_receipt_payload["receipt_state"]["ready"] is True
    assert operator_handoff_closeout_receipt_payload["receipt_state"]["service_operation_locked"] is True
    assert operator_handoff_closeout_receipt_payload["receipt_state"]["resume_blocked"] is True
    assert operator_handoff_closeout_receipt_payload["receipt_state"]["operation_resume_approved"] is False
    assert operator_handoff_closeout_receipt_payload["receipt_state"]["service_operation_allowed"] is False
    assert operator_handoff_closeout_receipt_payload["summary_validation"]["ok"] is True
    assert (
        operator_handoff_closeout_receipt_payload["operator_handoff_signoff_summary_sha256"]
        == no_cost_operator_handoff_closeout_receipt._sha256(operator_handoff_signoff_summary_path)
    )
    assert operator_handoff_closeout_receipt_payload["counts"]["signoff_count"] == 1
    assert operator_handoff_closeout_receipt_payload["counts"]["operator_handoff_review_count"] == 1
    assert (
        operator_handoff_closeout_receipt_payload["receipt_boundary"]["aws_cost_increase_allowed"]
        is False
    )
    assert (
        operator_handoff_closeout_receipt_payload["receipt_boundary"]["training_execution_started"]
        is False
    )
    operator_handoff_closeout_receipt_markdown = (
        operator_handoff_closeout_receipt_markdown_path.read_text(encoding="utf-8")
    )
    assert (
        "# Report Quality Training No-Cost Operator Handoff Closeout Receipt"
        in operator_handoff_closeout_receipt_markdown
    )
    assert "receipt_ready: `true`" in operator_handoff_closeout_receipt_markdown
    assert "service_operation_locked: `true`" in operator_handoff_closeout_receipt_markdown
    assert "resume_blocked: `true`" in operator_handoff_closeout_receipt_markdown
    assert "operation_resume_approved: `false`" in operator_handoff_closeout_receipt_markdown
    assert "aws_cost_increase_allowed: `false`" in operator_handoff_closeout_receipt_markdown

    operator_handoff_closeout_receipt_validation_exit_code = (
        no_cost_operator_handoff_closeout_receipt_validator.main([
            str(operator_handoff_closeout_receipt_path),
        ])
    )
    assert operator_handoff_closeout_receipt_validation_exit_code == 0
    operator_handoff_closeout_receipt_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost operator handoff closeout receipt validated"
        in operator_handoff_closeout_receipt_validation_out
    )
    assert "receipt_ready=true" in operator_handoff_closeout_receipt_validation_out
    assert "service_operation_locked=true" in operator_handoff_closeout_receipt_validation_out
    assert "resume_blocked=true" in operator_handoff_closeout_receipt_validation_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_closeout_receipt_validation_out
    assert "training_boundary=not_authorized" in operator_handoff_closeout_receipt_validation_out

    operator_handoff_closeout_receipt_summary_path = (
        output_root / "training-no-cost-operator-handoff-closeout-receipt-summary.json"
    )
    operator_handoff_closeout_receipt_summary_markdown_path = (
        output_root / "training-no-cost-operator-handoff-closeout-receipt-summary.md"
    )
    operator_handoff_closeout_receipt_summary_exit_code = (
        no_cost_operator_handoff_closeout_receipt_summary.main([
            str(operator_handoff_closeout_receipt_path),
            "--output",
            str(operator_handoff_closeout_receipt_summary_path),
            "--markdown",
            str(operator_handoff_closeout_receipt_summary_markdown_path),
            "--generated-at",
            "2026-05-14T20:45:00+09:00",
        ])
    )
    assert operator_handoff_closeout_receipt_summary_exit_code == 0
    operator_handoff_closeout_receipt_summary_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost operator handoff closeout receipt summary: PASS"
        in operator_handoff_closeout_receipt_summary_out
    )
    assert "receipt_count=1" in operator_handoff_closeout_receipt_summary_out
    assert "valid_receipt_count=1" in operator_handoff_closeout_receipt_summary_out
    assert "ready_receipt_count=1" in operator_handoff_closeout_receipt_summary_out
    assert "service_operation_locked=true" in operator_handoff_closeout_receipt_summary_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_closeout_receipt_summary_out
    assert "training_boundary=not_authorized" in operator_handoff_closeout_receipt_summary_out
    operator_handoff_closeout_receipt_summary_payload = json.loads(
        operator_handoff_closeout_receipt_summary_path.read_text(encoding="utf-8")
    )
    assert (
        operator_handoff_closeout_receipt_summary_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_operator_handoff_closeout_receipt_summary.v1"
    )
    assert operator_handoff_closeout_receipt_summary_payload["ok"] is True
    assert operator_handoff_closeout_receipt_summary_payload["read_only"] is True
    assert (
        operator_handoff_closeout_receipt_summary_payload["readiness"]["status"]
        == "all_operator_handoff_closeout_receipts_confirm_service_lock"
    )
    assert (
        operator_handoff_closeout_receipt_summary_payload["readiness"]["service_operation_locked"]
        is True
    )
    assert operator_handoff_closeout_receipt_summary_payload["readiness"]["resume_blocked"] is True
    assert (
        operator_handoff_closeout_receipt_summary_payload["readiness"]["operation_resume_approved"]
        is False
    )
    assert (
        operator_handoff_closeout_receipt_summary_payload["readiness"]["service_operation_allowed"]
        is False
    )
    assert operator_handoff_closeout_receipt_summary_payload["counts"]["receipt_count"] == 1
    assert operator_handoff_closeout_receipt_summary_payload["counts"]["valid_receipt_count"] == 1
    assert operator_handoff_closeout_receipt_summary_payload["counts"]["ready_receipt_count"] == 1
    assert operator_handoff_closeout_receipt_summary_payload["counts"]["signoff_count"] == 1
    assert operator_handoff_closeout_receipt_summary_payload["counts"]["operator_handoff_review_count"] == 1
    assert operator_handoff_closeout_receipt_summary_payload["receipts"][0]["validation"]["ok"] is True
    assert (
        operator_handoff_closeout_receipt_summary_payload["side_effect_boundary"][
            "reads_local_operator_handoff_closeout_receipts"
        ]
        is True
    )
    assert (
        operator_handoff_closeout_receipt_summary_payload["side_effect_boundary"]["aws_cost_increase_allowed"]
        is False
    )
    assert (
        operator_handoff_closeout_receipt_summary_payload["side_effect_boundary"]["training_execution_started"]
        is False
    )
    operator_handoff_closeout_receipt_summary_markdown = (
        operator_handoff_closeout_receipt_summary_markdown_path.read_text(encoding="utf-8")
    )
    assert (
        "# Report Quality Training No-Cost Operator Handoff Closeout Receipt Summary"
        in operator_handoff_closeout_receipt_summary_markdown
    )
    assert "service_operation_locked: `true`" in operator_handoff_closeout_receipt_summary_markdown
    assert "resume_blocked: `true`" in operator_handoff_closeout_receipt_summary_markdown
    assert "operation_resume_approved: `false`" in operator_handoff_closeout_receipt_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in operator_handoff_closeout_receipt_summary_markdown

    operator_handoff_closeout_receipt_summary_validation_exit_code = (
        no_cost_operator_handoff_closeout_receipt_summary_validator.main([
            str(operator_handoff_closeout_receipt_summary_path),
        ])
    )
    assert operator_handoff_closeout_receipt_summary_validation_exit_code == 0
    operator_handoff_closeout_receipt_summary_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost operator handoff closeout receipt summary validated"
        in operator_handoff_closeout_receipt_summary_validation_out
    )
    assert (
        "operator_handoff_closeout_receipt_summary_ready=true"
        in operator_handoff_closeout_receipt_summary_validation_out
    )
    assert "service_operation_locked=true" in operator_handoff_closeout_receipt_summary_validation_out
    assert "resume_blocked=true" in operator_handoff_closeout_receipt_summary_validation_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_closeout_receipt_summary_validation_out
    assert "training_boundary=not_authorized" in operator_handoff_closeout_receipt_summary_validation_out

    operator_handoff_closeout_package_path = (
        output_root / "training-no-cost-operator-handoff-closeout-package-manifest.json"
    )
    operator_handoff_closeout_package_markdown_path = (
        output_root / "training-no-cost-operator-handoff-closeout-package.md"
    )
    operator_handoff_closeout_package_exit_code = no_cost_operator_handoff_closeout_package.main([
        str(operator_handoff_closeout_receipt_summary_path),
        "--summary-markdown",
        str(operator_handoff_closeout_receipt_summary_markdown_path),
        "--output-manifest",
        str(operator_handoff_closeout_package_path),
        "--output-markdown",
        str(operator_handoff_closeout_package_markdown_path),
        "--generated-at",
        "2026-05-14T20:50:00+09:00",
    ])
    assert operator_handoff_closeout_package_exit_code == 0
    operator_handoff_closeout_package_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost operator handoff closeout package: PASS"
        in operator_handoff_closeout_package_out
    )
    assert "package_ready=true" in operator_handoff_closeout_package_out
    assert "service_operation_locked=true" in operator_handoff_closeout_package_out
    assert "resume_blocked=true" in operator_handoff_closeout_package_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_closeout_package_out
    assert "training_boundary=not_authorized" in operator_handoff_closeout_package_out
    operator_handoff_closeout_package_payload = json.loads(
        operator_handoff_closeout_package_path.read_text(encoding="utf-8")
    )
    assert (
        operator_handoff_closeout_package_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_operator_handoff_closeout_package.v1"
    )
    assert (
        operator_handoff_closeout_package_payload["package_state"]["status"]
        == "no_cost_operator_handoff_closeout_package_ready"
    )
    assert operator_handoff_closeout_package_payload["package_state"]["ready"] is True
    assert operator_handoff_closeout_package_payload["package_state"]["service_operation_locked"] is True
    assert operator_handoff_closeout_package_payload["package_state"]["resume_blocked"] is True
    assert operator_handoff_closeout_package_payload["package_state"]["operation_resume_approved"] is False
    assert operator_handoff_closeout_package_payload["package_state"]["service_operation_allowed"] is False
    assert operator_handoff_closeout_package_payload["summary_validation"]["ok"] is True
    assert (
        operator_handoff_closeout_package_payload["operator_handoff_closeout_receipt_summary_sha256"]
        == no_cost_operator_handoff_closeout_package._sha256(operator_handoff_closeout_receipt_summary_path)
    )
    assert operator_handoff_closeout_package_payload["counts"]["receipt_count"] == 1
    assert operator_handoff_closeout_package_payload["counts"]["operator_handoff_review_count"] == 1
    assert (
        operator_handoff_closeout_package_payload["package_boundary"]["aws_cost_increase_allowed"]
        is False
    )
    assert (
        operator_handoff_closeout_package_payload["package_boundary"]["training_execution_started"]
        is False
    )
    operator_handoff_closeout_package_markdown = (
        operator_handoff_closeout_package_markdown_path.read_text(encoding="utf-8")
    )
    assert (
        "# Report Quality Training No-Cost Operator Handoff Closeout Package"
        in operator_handoff_closeout_package_markdown
    )
    assert "package_ready: `true`" in operator_handoff_closeout_package_markdown
    assert "service_operation_locked: `true`" in operator_handoff_closeout_package_markdown
    assert "resume_blocked: `true`" in operator_handoff_closeout_package_markdown
    assert "operation_resume_approved: `false`" in operator_handoff_closeout_package_markdown
    assert "aws_cost_increase_allowed: `false`" in operator_handoff_closeout_package_markdown

    operator_handoff_closeout_package_validation_exit_code = (
        no_cost_operator_handoff_closeout_package_validator.main([
            str(operator_handoff_closeout_package_path),
        ])
    )
    assert operator_handoff_closeout_package_validation_exit_code == 0
    operator_handoff_closeout_package_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost operator handoff closeout package validated"
        in operator_handoff_closeout_package_validation_out
    )
    assert "package_ready=true" in operator_handoff_closeout_package_validation_out
    assert "service_operation_locked=true" in operator_handoff_closeout_package_validation_out
    assert "resume_blocked=true" in operator_handoff_closeout_package_validation_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_closeout_package_validation_out
    assert "training_boundary=not_authorized" in operator_handoff_closeout_package_validation_out

    operator_handoff_closeout_package_summary_path = (
        output_root / "training-no-cost-operator-handoff-closeout-package-summary.json"
    )
    operator_handoff_closeout_package_summary_markdown_path = (
        output_root / "training-no-cost-operator-handoff-closeout-package-summary.md"
    )
    operator_handoff_closeout_package_summary_exit_code = (
        no_cost_operator_handoff_closeout_package_summary.main([
            str(operator_handoff_closeout_package_path),
            "--output",
            str(operator_handoff_closeout_package_summary_path),
            "--markdown",
            str(operator_handoff_closeout_package_summary_markdown_path),
            "--generated-at",
            "2026-05-14T20:55:00+09:00",
        ])
    )
    assert operator_handoff_closeout_package_summary_exit_code == 0
    operator_handoff_closeout_package_summary_out = capsys.readouterr().out
    assert (
        "Report quality training no-cost operator handoff closeout package summary: PASS"
        in operator_handoff_closeout_package_summary_out
    )
    assert "package_count=1" in operator_handoff_closeout_package_summary_out
    assert "valid_package_count=1" in operator_handoff_closeout_package_summary_out
    assert "ready_package_count=1" in operator_handoff_closeout_package_summary_out
    assert "service_operation_locked=true" in operator_handoff_closeout_package_summary_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_closeout_package_summary_out
    assert "training_boundary=not_authorized" in operator_handoff_closeout_package_summary_out
    operator_handoff_closeout_package_summary_payload = json.loads(
        operator_handoff_closeout_package_summary_path.read_text(encoding="utf-8")
    )
    assert (
        operator_handoff_closeout_package_summary_payload["schema_version"]
        == "decisiondoc_report_quality_training_no_cost_operator_handoff_closeout_package_summary.v1"
    )
    assert operator_handoff_closeout_package_summary_payload["ok"] is True
    assert operator_handoff_closeout_package_summary_payload["read_only"] is True
    assert (
        operator_handoff_closeout_package_summary_payload["readiness"]["status"]
        == "all_operator_handoff_closeout_packages_confirm_service_lock"
    )
    assert (
        operator_handoff_closeout_package_summary_payload["readiness"]["service_operation_locked"]
        is True
    )
    assert operator_handoff_closeout_package_summary_payload["readiness"]["resume_blocked"] is True
    assert (
        operator_handoff_closeout_package_summary_payload["readiness"]["operation_resume_approved"]
        is False
    )
    assert (
        operator_handoff_closeout_package_summary_payload["readiness"]["service_operation_allowed"]
        is False
    )
    assert operator_handoff_closeout_package_summary_payload["counts"]["package_count"] == 1
    assert operator_handoff_closeout_package_summary_payload["counts"]["valid_package_count"] == 1
    assert operator_handoff_closeout_package_summary_payload["counts"]["ready_package_count"] == 1
    assert operator_handoff_closeout_package_summary_payload["counts"]["receipt_count"] == 1
    assert operator_handoff_closeout_package_summary_payload["counts"]["operator_handoff_review_count"] == 1
    assert operator_handoff_closeout_package_summary_payload["packages"][0]["validation"]["ok"] is True
    assert (
        operator_handoff_closeout_package_summary_payload["side_effect_boundary"][
            "reads_local_operator_handoff_closeout_packages"
        ]
        is True
    )
    assert (
        operator_handoff_closeout_package_summary_payload["side_effect_boundary"]["aws_cost_increase_allowed"]
        is False
    )
    assert (
        operator_handoff_closeout_package_summary_payload["side_effect_boundary"]["training_execution_started"]
        is False
    )
    operator_handoff_closeout_package_summary_markdown = (
        operator_handoff_closeout_package_summary_markdown_path.read_text(encoding="utf-8")
    )
    assert (
        "# Report Quality Training No-Cost Operator Handoff Closeout Package Summary"
        in operator_handoff_closeout_package_summary_markdown
    )
    assert "service_operation_locked: `true`" in operator_handoff_closeout_package_summary_markdown
    assert "resume_blocked: `true`" in operator_handoff_closeout_package_summary_markdown
    assert "operation_resume_approved: `false`" in operator_handoff_closeout_package_summary_markdown
    assert "aws_cost_increase_allowed: `false`" in operator_handoff_closeout_package_summary_markdown

    operator_handoff_closeout_package_summary_validation_exit_code = (
        no_cost_operator_handoff_closeout_package_summary_validator.main([
            str(operator_handoff_closeout_package_summary_path),
        ])
    )
    assert operator_handoff_closeout_package_summary_validation_exit_code == 0
    operator_handoff_closeout_package_summary_validation_out = capsys.readouterr().out
    assert (
        "PASS report quality training no-cost operator handoff closeout package summary validated"
        in operator_handoff_closeout_package_summary_validation_out
    )
    assert (
        "operator_handoff_closeout_package_summary_ready=true"
        in operator_handoff_closeout_package_summary_validation_out
    )
    assert "service_operation_locked=true" in operator_handoff_closeout_package_summary_validation_out
    assert "resume_blocked=true" in operator_handoff_closeout_package_summary_validation_out
    assert "aws_cost_boundary=no_cost_increase" in operator_handoff_closeout_package_summary_validation_out
    assert "training_boundary=not_authorized" in operator_handoff_closeout_package_summary_validation_out

    broken_operator_handoff_closeout_package_summary_payload = json.loads(
        json.dumps(operator_handoff_closeout_package_summary_payload)
    )
    broken_operator_handoff_closeout_package_summary_payload["side_effect_boundary"][
        "aws_cost_increase_allowed"
    ] = True
    operator_handoff_closeout_package_summary_path.write_text(
        json.dumps(broken_operator_handoff_closeout_package_summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validate_operator_handoff_closeout_package_summary = getattr(
        no_cost_operator_handoff_closeout_package_summary_validator,
        "validate_training_no_cost_operator_handoff_closeout_package_summary",
    )
    broken_operator_handoff_closeout_package_summary_validation = (
        validate_operator_handoff_closeout_package_summary(operator_handoff_closeout_package_summary_path)
    )
    assert broken_operator_handoff_closeout_package_summary_validation["ok"] is False
    assert "side_effect_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_operator_handoff_closeout_package_summary_validation["errors"]
    )
    assert (
        "training_no_cost_operator_handoff_closeout_package_summary: "
        "$.side_effect_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_operator_handoff_closeout_package_summary_validation["errors"])
    )

    broken_operator_handoff_closeout_package_payload = json.loads(
        json.dumps(operator_handoff_closeout_package_payload)
    )
    broken_operator_handoff_closeout_package_payload["package_boundary"]["aws_cost_increase_allowed"] = True
    operator_handoff_closeout_package_path.write_text(
        json.dumps(broken_operator_handoff_closeout_package_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validate_operator_handoff_closeout_package = getattr(
        no_cost_operator_handoff_closeout_package_validator,
        "validate_training_no_cost_operator_handoff_closeout_package",
    )
    broken_operator_handoff_closeout_package_validation = validate_operator_handoff_closeout_package(
        operator_handoff_closeout_package_path,
    )
    assert broken_operator_handoff_closeout_package_validation["ok"] is False
    assert "package_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_operator_handoff_closeout_package_validation["errors"]
    )
    assert (
        "training_no_cost_operator_handoff_closeout_package: "
        "$.package_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_operator_handoff_closeout_package_validation["errors"])
    )
    summarize_operator_handoff_closeout_packages = getattr(
        no_cost_operator_handoff_closeout_package_summary,
        "build_training_no_cost_operator_handoff_closeout_package_summary",
    )
    broken_operator_handoff_closeout_package_summary = summarize_operator_handoff_closeout_packages([
        operator_handoff_closeout_package_path,
    ])
    assert broken_operator_handoff_closeout_package_summary["ok"] is False
    assert broken_operator_handoff_closeout_package_summary["counts"]["invalid_package_count"] == 1
    assert "invalid_operator_handoff_closeout_packages" in broken_operator_handoff_closeout_package_summary[
        "readiness"
    ]["blocker_reasons"]

    broken_operator_handoff_closeout_receipt_summary_payload = json.loads(
        json.dumps(operator_handoff_closeout_receipt_summary_payload)
    )
    broken_operator_handoff_closeout_receipt_summary_payload["side_effect_boundary"][
        "aws_cost_increase_allowed"
    ] = True
    operator_handoff_closeout_receipt_summary_path.write_text(
        json.dumps(broken_operator_handoff_closeout_receipt_summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validate_operator_handoff_closeout_receipt_summary = getattr(
        no_cost_operator_handoff_closeout_receipt_summary_validator,
        "validate_training_no_cost_operator_handoff_closeout_receipt_summary",
    )
    broken_operator_handoff_closeout_receipt_summary_validation = (
        validate_operator_handoff_closeout_receipt_summary(operator_handoff_closeout_receipt_summary_path)
    )
    assert broken_operator_handoff_closeout_receipt_summary_validation["ok"] is False
    assert "side_effect_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_operator_handoff_closeout_receipt_summary_validation["errors"]
    )
    assert (
        "training_no_cost_operator_handoff_closeout_receipt_summary: "
        "$.side_effect_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_operator_handoff_closeout_receipt_summary_validation["errors"])
    )

    broken_operator_handoff_closeout_receipt_payload = json.loads(
        json.dumps(operator_handoff_closeout_receipt_payload)
    )
    broken_operator_handoff_closeout_receipt_payload["receipt_boundary"]["aws_cost_increase_allowed"] = True
    operator_handoff_closeout_receipt_path.write_text(
        json.dumps(broken_operator_handoff_closeout_receipt_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_operator_handoff_closeout_receipt_validation = (
        no_cost_operator_handoff_closeout_receipt_validator.validate_training_no_cost_operator_handoff_closeout_receipt(
            operator_handoff_closeout_receipt_path,
        )
    )
    assert broken_operator_handoff_closeout_receipt_validation["ok"] is False
    assert "receipt_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_operator_handoff_closeout_receipt_validation["errors"]
    )
    assert (
        "training_no_cost_operator_handoff_closeout_receipt: "
        "$.receipt_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_operator_handoff_closeout_receipt_validation["errors"])
    )
    summarize_operator_handoff_closeout_receipts = getattr(
        no_cost_operator_handoff_closeout_receipt_summary,
        "build_training_no_cost_operator_handoff_closeout_receipt_summary",
    )
    broken_operator_handoff_closeout_receipt_summary = summarize_operator_handoff_closeout_receipts([
        operator_handoff_closeout_receipt_path,
    ])
    assert broken_operator_handoff_closeout_receipt_summary["ok"] is False
    assert broken_operator_handoff_closeout_receipt_summary["counts"]["invalid_receipt_count"] == 1
    assert "invalid_operator_handoff_closeout_receipts" in broken_operator_handoff_closeout_receipt_summary[
        "readiness"
    ]["blocker_reasons"]

    broken_operator_handoff_signoff_summary_payload = json.loads(
        operator_handoff_signoff_summary_path.read_text(encoding="utf-8")
    )
    broken_operator_handoff_signoff_summary_payload["side_effect_boundary"][
        "aws_cost_increase_allowed"
    ] = True
    operator_handoff_signoff_summary_path.write_text(
        json.dumps(broken_operator_handoff_signoff_summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_operator_handoff_signoff_summary_validation = (
        no_cost_operator_handoff_signoff_summary_validator.validate_training_no_cost_operator_handoff_signoff_summary(
            operator_handoff_signoff_summary_path,
        )
    )
    assert broken_operator_handoff_signoff_summary_validation["ok"] is False
    assert "side_effect_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_operator_handoff_signoff_summary_validation["errors"]
    )
    assert (
        "training_no_cost_operator_handoff_signoff_summary: "
        "$.side_effect_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_operator_handoff_signoff_summary_validation["errors"])
    )

    broken_operator_handoff_signoff = json.loads(json.dumps(operator_handoff_signoff_payload))
    broken_operator_handoff_signoff["signoff_boundary"]["aws_cost_increase_authorized"] = True
    broken_operator_handoff_signoff_validation = (
        no_cost_operator_handoff_signoff_validator.validate_training_no_cost_operator_handoff_signoff(
            broken_operator_handoff_signoff,
            require_complete=True,
        )
    )
    assert broken_operator_handoff_signoff_validation["ok"] is False
    assert "signoff_boundary.aws_cost_increase_authorized must be false" in "\n".join(
        broken_operator_handoff_signoff_validation["errors"]
    )
    operator_handoff_signoff_path.write_text(
        json.dumps(broken_operator_handoff_signoff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_operator_handoff_signoff_summary = (
        no_cost_operator_handoff_signoff_summary.build_training_no_cost_operator_handoff_signoff_summary([
            operator_handoff_signoff_path,
        ])
    )
    assert broken_operator_handoff_signoff_summary["ok"] is False
    assert broken_operator_handoff_signoff_summary["counts"]["invalid_signoff_count"] == 1
    assert "invalid_operator_handoff_signoffs" in broken_operator_handoff_signoff_summary["readiness"][
        "blocker_reasons"
    ]

    broken_operator_handoff_payload = json.loads(operator_handoff_manifest_path.read_text(encoding="utf-8"))
    broken_operator_handoff_payload["handoff_boundary"]["aws_cost_increase_allowed"] = True
    operator_handoff_manifest_path.write_text(
        json.dumps(broken_operator_handoff_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_operator_handoff_validation_exit_code = no_cost_operator_handoff_validator.main([
        str(operator_handoff_manifest_path),
    ])
    assert broken_operator_handoff_validation_exit_code == 1
    broken_operator_handoff_validation_out = capsys.readouterr().out
    assert (
        "FAIL report quality training no-cost operator handoff validation failed"
        in broken_operator_handoff_validation_out
    )
    assert "handoff_boundary.aws_cost_increase_allowed must be false" in broken_operator_handoff_validation_out

    service_lock_report_summary_payload["side_effect_boundary"]["aws_cost_increase_allowed"] = True
    service_lock_report_summary_path.write_text(
        json.dumps(service_lock_report_summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_service_lock_report_summary_validation = (
        no_cost_service_lock_report_summary_validator.validate_training_no_cost_service_lock_report_summary(
            service_lock_report_summary_path,
        )
    )
    assert broken_service_lock_report_summary_validation["ok"] is False
    assert "side_effect_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_service_lock_report_summary_validation["errors"]
    )
    assert (
        "training_no_cost_service_lock_report_summary: $.side_effect_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_service_lock_report_summary_validation["errors"])
    )
    broken_operator_handoff_exit_code = no_cost_operator_handoff.main([
        str(service_lock_report_summary_path),
        "--output-manifest",
        str(operator_handoff_manifest_path),
        "--output-markdown",
        str(operator_handoff_markdown_path),
    ])
    assert broken_operator_handoff_exit_code == 1
    broken_operator_handoff_out = capsys.readouterr().out
    assert "FAIL report quality training no-cost operator handoff generation failed" in broken_operator_handoff_out
    assert "side_effect_boundary.aws_cost_increase_allowed must be false" in broken_operator_handoff_out

    service_lock_report_payload["report_boundary"]["aws_cost_increase_allowed"] = True
    service_lock_report_path.write_text(
        json.dumps(service_lock_report_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_service_lock_report_validation = (
        no_cost_service_lock_report_validator.validate_training_no_cost_service_lock_report(
            service_lock_report_path,
        )
    )
    assert broken_service_lock_report_validation["ok"] is False
    assert "report_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_service_lock_report_validation["errors"]
    )
    assert (
        "training_no_cost_service_lock_report: $.report_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_service_lock_report_validation["errors"])
    )
    broken_service_lock_report_summary = (
        no_cost_service_lock_report_summary.build_training_no_cost_service_lock_report_summary([
            service_lock_report_path,
        ])
    )
    assert broken_service_lock_report_summary["ok"] is False
    assert broken_service_lock_report_summary["counts"]["invalid_service_lock_report_count"] == 1
    assert "invalid_service_lock_reports" in broken_service_lock_report_summary["readiness"][
        "blocker_reasons"
    ]

    closeout_receipt_summary_payload["readiness"]["service_operation_allowed"] = True
    closeout_receipt_summary_path.write_text(
        json.dumps(closeout_receipt_summary_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_service_lock_check = no_cost_service_lock_check.validate_no_cost_service_lock(
        closeout_receipt_summary_path,
    )
    assert broken_service_lock_check["ok"] is False
    assert "readiness.service_operation_allowed must be false" in "\n".join(
        broken_service_lock_check["errors"]
    )
    assert (
        "training_no_cost_service_lock: $.readiness.service_operation_allowed must be false"
        in "\n".join(broken_service_lock_check["errors"])
    )
    broken_service_lock_report_exit_code = no_cost_service_lock_report.main([
        str(closeout_receipt_summary_path),
        "--output-manifest",
        str(service_lock_report_path),
        "--output-markdown",
        str(service_lock_report_markdown_path),
    ])
    assert broken_service_lock_report_exit_code == 1
    broken_service_lock_report_out = capsys.readouterr().out
    assert "FAIL report quality training no-cost service lock report generation failed" in broken_service_lock_report_out
    assert "readiness.service_operation_allowed must be false" in broken_service_lock_report_out

    closeout_receipt_payload["closeout_boundary"]["aws_cost_increase_allowed"] = True
    closeout_receipt_manifest_path.write_text(
        json.dumps(closeout_receipt_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_closeout_receipt_validation = no_cost_closeout_receipt_validator.validate_training_no_cost_closeout_receipt(
        closeout_receipt_manifest_path,
    )
    assert broken_closeout_receipt_validation["ok"] is False
    assert (
        "training_no_cost_closeout_receipt: $.closeout_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_closeout_receipt_validation["errors"])
    )
    broken_closeout_receipt_summary = (
        no_cost_closeout_receipt_summary.build_training_no_cost_closeout_receipt_summary([
            closeout_receipt_manifest_path,
        ])
    )
    assert broken_closeout_receipt_summary["ok"] is False
    assert broken_closeout_receipt_summary["counts"]["invalid_closeout_receipt_count"] == 1
    assert "invalid_closeout_receipt_manifests" in broken_closeout_receipt_summary["readiness"][
        "blocker_reasons"
    ]

    final_hold_payload["final_hold_boundary"]["aws_cost_increase_allowed"] = True
    final_hold_manifest_path.write_text(
        json.dumps(final_hold_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_final_hold_validation = no_cost_final_hold_validator.validate_training_no_cost_final_hold(
        final_hold_manifest_path,
    )
    assert broken_final_hold_validation["ok"] is False
    assert "training_no_cost_final_hold: $.final_hold_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_final_hold_validation["errors"]
    )
    broken_final_hold_summary = no_cost_final_hold_summary.build_training_no_cost_final_hold_summary([
        final_hold_manifest_path,
    ])
    assert broken_final_hold_summary["ok"] is False
    assert broken_final_hold_summary["counts"]["invalid_final_hold_count"] == 1
    assert "invalid_final_hold_manifests" in broken_final_hold_summary["readiness"]["blocker_reasons"]

    ops_lock_handoff_signoff_payload["signoff_boundary"]["aws_cost_increase_authorized"] = True
    broken_ops_lock_handoff_signoff_validation = (
        no_cost_ops_lock_handoff_signoff_validator.validate_training_no_cost_ops_lock_handoff_signoff(
            ops_lock_handoff_signoff_payload,
            require_complete=True,
        )
    )
    assert broken_ops_lock_handoff_signoff_validation["ok"] is False
    assert "signoff_boundary.aws_cost_increase_authorized must be false" in "\n".join(
        broken_ops_lock_handoff_signoff_validation["errors"]
    )
    ops_lock_handoff_signoff_path.write_text(
        json.dumps(ops_lock_handoff_signoff_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_ops_lock_handoff_signoff_summary = (
        no_cost_ops_lock_handoff_signoff_summary.build_training_no_cost_ops_lock_handoff_signoff_summary([
            ops_lock_handoff_signoff_path,
        ])
    )
    assert broken_ops_lock_handoff_signoff_summary["ok"] is False
    assert broken_ops_lock_handoff_signoff_summary["counts"]["invalid_signoff_count"] == 1
    assert "invalid_ops_lock_handoff_signoffs" in broken_ops_lock_handoff_signoff_summary["readiness"][
        "blocker_reasons"
    ]

    ops_lock_handoff_payload["handoff_boundary"]["aws_cost_increase_allowed"] = True
    ops_lock_handoff_manifest_path.write_text(
        json.dumps(ops_lock_handoff_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_ops_lock_handoff_validation = (
        no_cost_ops_lock_handoff_validator.validate_training_no_cost_ops_lock_handoff(
            ops_lock_handoff_manifest_path,
        )
    )
    assert broken_ops_lock_handoff_validation["ok"] is False
    assert "training_no_cost_ops_lock_handoff: $.handoff_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_ops_lock_handoff_validation["errors"]
    )

    ops_lock["lock_boundary"]["aws_cost_increase_allowed"] = True
    ops_lock_manifest_path.write_text(
        json.dumps(ops_lock, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_ops_lock_validation = no_cost_ops_lock_validator.validate_training_no_cost_ops_lock(
        ops_lock_manifest_path,
    )
    assert broken_ops_lock_validation["ok"] is False
    assert "training_no_cost_ops_lock: $.lock_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_ops_lock_validation["errors"]
    )
    broken_ops_lock_summary = no_cost_ops_lock_summary.build_training_no_cost_ops_lock_summary([
        ops_lock_manifest_path,
    ])
    assert broken_ops_lock_summary["ok"] is False
    assert broken_ops_lock_summary["counts"]["invalid_ops_lock_count"] == 1
    assert "invalid_ops_lock_manifests" in broken_ops_lock_summary["readiness"]["blocker_reasons"]

    resume_guard["guard_boundary"]["aws_cost_increase_allowed"] = True
    resume_guard_manifest_path.write_text(
        json.dumps(resume_guard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_resume_guard_validation = no_cost_resume_guard_validator.validate_training_no_cost_resume_guard(
        resume_guard_manifest_path,
    )
    assert broken_resume_guard_validation["ok"] is False
    assert "training_no_cost_resume_guard: $.guard_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_resume_guard_validation["errors"]
    )
    broken_resume_guard_summary = no_cost_resume_guard_summary.build_training_no_cost_resume_guard_summary([
        resume_guard_manifest_path,
    ])
    assert broken_resume_guard_summary["ok"] is False
    assert broken_resume_guard_summary["counts"]["invalid_resume_guard_count"] == 1
    assert "invalid_resume_guard_manifests" in broken_resume_guard_summary["readiness"]["blocker_reasons"]

    evidence_bundle_handoff_signoff["signoff_boundary"]["aws_cost_increase_authorized"] = True
    broken_evidence_bundle_handoff_signoff_validation = (
        no_cost_evidence_bundle_handoff_signoff_validator.validate_training_no_cost_evidence_bundle_handoff_signoff(
            evidence_bundle_handoff_signoff,
            require_complete=True,
        )
    )
    assert broken_evidence_bundle_handoff_signoff_validation["ok"] is False
    assert "signoff_boundary.aws_cost_increase_authorized must be false" in "\n".join(
        broken_evidence_bundle_handoff_signoff_validation["errors"]
    )
    evidence_bundle_handoff_signoff_path.write_text(
        json.dumps(evidence_bundle_handoff_signoff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_evidence_bundle_handoff_signoff_summary = (
        no_cost_evidence_bundle_handoff_signoff_summary.build_training_no_cost_evidence_bundle_handoff_signoff_summary([
            evidence_bundle_handoff_signoff_path,
        ])
    )
    assert broken_evidence_bundle_handoff_signoff_summary["ok"] is False
    assert broken_evidence_bundle_handoff_signoff_summary["counts"]["invalid_signoff_count"] == 1
    assert "invalid_evidence_bundle_handoff_signoffs" in broken_evidence_bundle_handoff_signoff_summary[
        "readiness"
    ]["blocker_reasons"]

    evidence_bundle_handoff["handoff_boundary"]["aws_cost_increase_allowed"] = True
    evidence_bundle_handoff_manifest_path.write_text(
        json.dumps(evidence_bundle_handoff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_evidence_bundle_handoff_validation = (
        no_cost_evidence_bundle_handoff_validator.validate_training_no_cost_evidence_bundle_handoff(
            evidence_bundle_handoff_manifest_path,
        )
    )
    assert broken_evidence_bundle_handoff_validation["ok"] is False
    assert (
        "training_no_cost_evidence_bundle_handoff: $.handoff_boundary.aws_cost_increase_allowed must be false"
        in "\n".join(broken_evidence_bundle_handoff_validation["errors"])
    )

    evidence_bundle["bundle_boundary"]["aws_cost_increase_allowed"] = True
    evidence_bundle_manifest_path.write_text(
        json.dumps(evidence_bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_evidence_bundle_validation = no_cost_evidence_bundle_validator.validate_training_no_cost_evidence_bundle(
        evidence_bundle_manifest_path,
    )
    assert broken_evidence_bundle_validation["ok"] is False
    assert "training_no_cost_evidence_bundle: $.bundle_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_evidence_bundle_validation["errors"]
    )

    archive_closure["closure_boundary"]["aws_cost_increase_allowed"] = True
    archive_closure_manifest_path.write_text(
        json.dumps(archive_closure, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_archive_closure_validation = no_cost_archive_closure_validator.validate_training_no_cost_archive_closure(
        archive_closure_manifest_path,
    )
    assert broken_archive_closure_validation["ok"] is False
    assert "training_no_cost_archive_closure: $.closure_boundary.aws_cost_increase_allowed must be false" in "\n".join(
        broken_archive_closure_validation["errors"]
    )
    broken_archive_closure_summary = no_cost_archive_closure_summary.build_training_no_cost_archive_closure_summary([
        archive_closure_manifest_path,
    ])
    assert broken_archive_closure_summary["ok"] is False
    assert broken_archive_closure_summary["counts"]["invalid_archive_closure_count"] == 1
    assert "invalid_archive_closure_manifests" in broken_archive_closure_summary["readiness"]["blocker_reasons"]

    freeze_handoff_signoff["signoff_boundary"]["aws_cost_increase_authorized"] = True
    broken_freeze_handoff_signoff_validation = (
        no_cost_freeze_handoff_signoff_validator.validate_training_no_cost_freeze_handoff_signoff(
            freeze_handoff_signoff,
            require_complete=True,
        )
    )
    assert broken_freeze_handoff_signoff_validation["ok"] is False
    assert "signoff_boundary.aws_cost_increase_authorized must be false" in "\n".join(
        broken_freeze_handoff_signoff_validation["errors"]
    )

    freeze["freeze_state"]["aws_cost_increase_allowed"] = True
    freeze_manifest_path.write_text(json.dumps(freeze, ensure_ascii=False, indent=2), encoding="utf-8")
    broken_freeze_validation = no_cost_freeze_validator.validate_training_no_cost_freeze(freeze_manifest_path)
    assert broken_freeze_validation["ok"] is False
    assert "training_no_cost_freeze: $.freeze_state.aws_cost_increase_allowed must be false" in "\n".join(
        broken_freeze_validation["errors"]
    )
    broken_freeze_summary = no_cost_freeze_summary.build_training_no_cost_freeze_summary([freeze_manifest_path])
    assert broken_freeze_summary["ok"] is False
    assert broken_freeze_summary["counts"]["invalid_freeze_count"] == 1
    assert "invalid_freeze_manifests" in broken_freeze_summary["readiness"]["blocker_reasons"]
    broken_handoff_validation = no_cost_freeze_handoff_validator.validate_training_no_cost_freeze_handoff(
        freeze_handoff_manifest_path,
    )
    assert broken_handoff_validation["ok"] is False
    assert "rebuilt no-cost freeze summary validation must pass" in "\n".join(
        broken_handoff_validation["errors"]
    )

    final_approval_record["approval_state"]["final_training_approval_granted"] = True
    final_approval_record_path.write_text(
        json.dumps(final_approval_record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    broken_record_validation = final_approval_record_template_validator.validate_training_final_approval_record_template(
        final_approval_record_path,
    )
    assert broken_record_validation["ok"] is False
    assert (
        "training_final_approval_record_template: $.approval_state.final_training_approval_granted must be false"
        in "\n".join(broken_record_validation["errors"])
    )

    packet_review_record["review_boundary"]["actual_training_approval_recorded"] = True
    broken_packet_review_validation = final_packet_review_validator.validate_training_final_approval_packet_review(
        packet_review_record,
        require_complete=True,
    )
    assert broken_packet_review_validation["ok"] is False
    assert "review_boundary.actual_training_approval_recorded must be false" in "\n".join(
        broken_packet_review_validation["errors"]
    )

    packet["readiness"]["final_training_approval_granted"] = True
    final_packet_manifest_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    broken_packet_validation = final_packet_validator.validate_training_final_approval_packet(
        final_packet_manifest_path,
    )
    assert broken_packet_validation["ok"] is False
    assert "training_final_approval_packet: $.readiness.final_training_approval_granted must be false" in "\n".join(
        broken_packet_validation["errors"]
    )

    review_record["review_boundary"]["provider_job_creation_authorized"] = True
    broken_review_validation = experiment_plan_review_validator.validate_training_experiment_plan_review(
        review_record,
        require_complete=True,
    )
    assert broken_review_validation["ok"] is False
    assert "review_boundary.provider_job_creation_authorized must be false" in "\n".join(
        broken_review_validation["errors"]
    )

    plan["side_effect_boundary"]["training_execution_started"] = True
    plan_manifest_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    broken_plan_validation = experiment_plan_validator.validate_training_experiment_plan_draft(plan_manifest_path)
    assert broken_plan_validation["ok"] is False
    assert "training_experiment_plan_draft: $.side_effect_boundary.training_execution_started must be false" in "\n".join(
        broken_plan_validation["errors"]
    )

    decision_record["decision_boundary"]["training_execution_authorized"] = True
    broken_decision_validation = discussion_decision_validator.validate_training_discussion_decision(
        decision_record,
        require_complete=True,
    )
    assert broken_decision_validation["ok"] is False
    assert "decision_boundary.training_execution_authorized must be false" in "\n".join(
        broken_decision_validation["errors"]
    )

    manifest["readiness_manifest_sha256"] = "bad-sha256"
    discussion_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    broken_hash_validation = discussion_handoff_validator.validate_training_discussion_handoff_manifest(
        discussion_manifest_path,
    )
    assert broken_hash_validation["ok"] is False
    assert "readiness_manifest_sha256 does not match readiness_manifest_path" in "\n".join(
        broken_hash_validation["errors"]
    )

    manifest["readiness_manifest_sha256"] = discussion_handoff._sha256(readiness_path)
    manifest["side_effect_boundary"]["provider_fine_tune_api_called"] = True
    discussion_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    broken_validation = discussion_handoff_validator.validate_training_discussion_handoff_manifest(
        discussion_manifest_path,
    )
    assert broken_validation["ok"] is False
    assert (
        "training_discussion_handoff: $.side_effect_boundary.provider_fine_tune_api_called must be false"
        in "\n".join(broken_validation["errors"])
    )


def test_review_packet_training_discussion_handoff_flags_not_ready_manifest(tmp_path):
    discussion_handoff = _load_packet_training_discussion_handoff_script()
    not_ready = {
        "schema_version": "decisiondoc_report_quality_review_packet_training_readiness.v1",
        "readiness": {
            "ok": False,
            "ready_for_training_discussion": False,
            "training_execution_authorized": False,
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "inputs": {
            "evidence_manifest_path": "",
            "evidence_manifest_sha256": "",
            "signoff_summary_path": "",
            "signoff_summary_sha256": "",
        },
        "counts": {
            "ready_artifacts": 0,
            "completed_signoff_count": 0,
            "invalid_signoff_count": 0,
        },
        "requirements": {"min_ready_artifacts": 1, "require_completed_signoffs": True},
        "validations": {},
        "side_effect_boundary": {"training_execution_started": False},
    }
    not_ready_path = tmp_path / "not-ready-training-readiness-manifest.json"
    not_ready_path.write_text(json.dumps(not_ready, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = discussion_handoff.create_training_discussion_handoff(
        readiness_manifest_path=not_ready_path,
        output_manifest=tmp_path / "handoff-manifest.json",
        output_markdown=tmp_path / "handoff.md",
        require_ready=True,
    )

    assert manifest["readiness"]["ok"] is False
    assert manifest["readiness"]["ready_for_training_discussion"] is False
    assert manifest["readiness_validation"]["ok"] is False
    assert manifest["side_effect_boundary"]["training_execution_started"] is False
