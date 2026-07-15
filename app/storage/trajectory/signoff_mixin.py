"""Tenant-local reviewer sign-off summary (read-only, no training authorization)."""
from __future__ import annotations

import json
from typing import Any

from app.storage.trajectory.redaction import _now_iso
from app.storage.trajectory.signoff import (
    _list_reviewer_signoff_record_paths,
    _reviewer_signoff_summary_blockers,
    _summarize_reviewer_signoff_record,
)


class TrajectorySignoffMixin:
    """Reviewer sign-off summary read path."""

    def reviewer_signoff_summary(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Summarize tenant-local reviewer sign-off JSON records without side effects."""
        signoff_dir = self._reviewer_signoff_dir(tenant_id)
        paths = _list_reviewer_signoff_record_paths(signoff_dir, limit=limit)
        records: list[dict[str, Any]] = []
        load_errors: list[dict[str, str]] = []
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("sign-off record must be a JSON object")
                if data.get("tenant_id") not in (None, tenant_id):
                    continue
                records.append(_summarize_reviewer_signoff_record(path.name, data))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                load_errors.append({"filename": path.name, "error": str(exc)})

        completed_count = sum(1 for item in records if item["completed_validation"]["valid"])
        pending_count = sum(
            1
            for item in records
            if item["record_status"] == "pending_manual_signoff_no_training_authorization"
        )
        follow_up_count = sum(
            1
            for item in records
            if item["record_status"] == "manual_follow_up_required_no_training_authorization"
        )
        boundary_violation_count = sum(
            1
            for item in records
            if item["record_status"] == "attention_required_boundary_violation"
        )
        all_protected_false = all(
            item["boundary"]["protected_training_flags_false"]
            and item["boundary"]["generation_side_effect_flags_false"]
            for item in records
        )
        if load_errors:
            overall_status = "attention_required_load_errors"
        elif not records:
            overall_status = "no_signoff_records_found"
        elif boundary_violation_count:
            overall_status = "attention_required_boundary_violation"
        elif completed_count == len(records):
            overall_status = "manual_signoff_complete_no_training_authorization"
        elif follow_up_count:
            overall_status = "manual_follow_up_required_no_training_authorization"
        else:
            overall_status = "pending_manual_signoff_no_training_authorization"

        return {
            "report_type": "document_ops_phase25_signoff_summary_endpoint",
            "tenant_id": tenant_id,
            "generated_at": _now_iso(),
            "read_only": True,
            "summary_source": "tenant_local_reviewer_signoff_records",
            "record_directory_exists": signoff_dir.is_dir(),
            "record_count": len(records),
            "load_error_count": len(load_errors),
            "overall_status": overall_status,
            "status": overall_status,
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
            "records": records,
            "load_errors": load_errors,
            "aggregate": {
                "completed_record_count": completed_count,
                "pending_record_count": pending_count,
                "manual_follow_up_record_count": follow_up_count,
                "boundary_violation_count": boundary_violation_count,
                "load_error_count": len(load_errors),
                "all_protected_training_flags_false": all_protected_false,
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
            "blockers": _reviewer_signoff_summary_blockers(
                records=records,
                load_errors=load_errors,
                overall_status=overall_status,
            ),
        }
