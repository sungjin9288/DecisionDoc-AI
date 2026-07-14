"""TrajectoryStore — reviewed DocumentOps trajectory persistence.

This store complements FineTuneStore. It keeps rich internal trajectories in a
tenant-scoped JSONL file, then exports reviewed/accepted examples into
SFT-compatible message records only when explicitly requested.

The implementation is split into focused mixins and helper modules (core_mixin,
sft_export_mixin, freeze_mixin, training_approval_mixin, training_execution_mixin,
training_audit_mixin, signoff_mixin, plus the standalone helper modules
constants, redaction, sft_quality, training_readiness, signoff). This package
composes them into the single public ``TrajectoryStore`` class and re-exports
every public and internal symbol so existing
``from app.storage.trajectory_store import X`` imports keep working unchanged.
"""
from __future__ import annotations

from app.storage.trajectory.constants import (
    _EXPORT_FILENAME_RE,
    _FREEZE_FILENAME_RE,
    _MANIFEST_ID_RE,
    _SENSITIVE_KEY_PARTS,
    _SIGNOFF_DEFAULT_ALLOWED_DECISIONS,
    _SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS,
    _SIGNOFF_PROTECTED_FALSE_GENERATION_KEYS,
    _SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS,
    _SIGNOFF_REQUIRED_REVIEWER_ROLES,
    _TRAINING_APPROVAL_FILENAME_RE,
    _TRAINING_AUDIT_FILENAME_RE,
    _TRAINING_EXECUTION_REQUEST_FILENAME_RE,
)
from app.storage.trajectory.redaction import (
    _dedupe,
    _file_sha256,
    _is_safe_export_filename,
    _is_safe_freeze_filename,
    _is_safe_manifest_id,
    _is_safe_training_approval_filename,
    _is_safe_training_audit_filename,
    _is_safe_training_execution_request_filename,
    _json_sha256,
    _now_iso,
    _redact_input,
    _safe_label,
    _string_list,
)
from app.storage.trajectory.sft_quality import (
    _blocker_summary,
    _build_sft_quality_report,
    _count_by,
    _coverage_ratio,
    _is_accepted,
    _metadata_quality_score,
    _quality_recommendations,
    _quality_score,
    _record_preview,
    _score_summary,
    _sft_export_blockers,
    _skill_counts,
    _source_references,
    _validate_sft_record,
)
from app.storage.trajectory.training_readiness import (
    _safe_provider_label,
    _training_readiness_recommendations,
)
from app.storage.trajectory.signoff import (
    _as_text,
    _is_iso_datetime,
    _list_reviewer_signoff_record_paths,
    _load_json_file,
    _reviewer_signoff_summary_blockers,
    _signoff_acknowledgement_summary,
    _signoff_boundary_summary,
    _signoff_record_status,
    _summarize_reviewer_signoff_record,
    _summarize_signoff_reviewer,
    _validate_reviewer_signoff_record,
)
from app.storage.trajectory.core_mixin import TrajectoryCoreMixin, TrajectoryReviewConflictError, _log
from app.storage.trajectory.freeze_mixin import TrajectoryFreezeMixin
from app.storage.trajectory.sft_export_mixin import TrajectorySftExportMixin
from app.storage.trajectory.signoff_mixin import TrajectorySignoffMixin
from app.storage.trajectory.training_approval_mixin import TrajectoryTrainingApprovalMixin
from app.storage.trajectory.training_audit_mixin import TrajectoryTrainingAuditMixin
from app.storage.trajectory.training_execution_mixin import TrajectoryTrainingExecutionMixin

__all__ = ["TrajectoryReviewConflictError", "TrajectoryStore"]


class TrajectoryStore(
    TrajectoryCoreMixin,
    TrajectorySftExportMixin,
    TrajectoryFreezeMixin,
    TrajectoryTrainingApprovalMixin,
    TrajectoryTrainingExecutionMixin,
    TrajectoryTrainingAuditMixin,
    TrajectorySignoffMixin,
):
    """Thread-safe JSONL store for DocumentOps trajectories."""
