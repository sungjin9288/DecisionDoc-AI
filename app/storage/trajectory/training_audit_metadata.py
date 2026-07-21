"""Metadata projection for immutable training audit artifacts."""

from __future__ import annotations

from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def training_audit_metadata_item(
    *,
    tenant_id: str,
    audit_file: str,
    audit_record: dict[str, Any],
    audit_size_bytes: int,
    audit_sha256: str,
) -> dict[str, Any]:
    gate = _mapping(audit_record.get("audit_gate"))
    guard = _mapping(audit_record.get("execution_guard"))
    checklist = _mapping(audit_record.get("checklist_snapshot"))
    packet = _mapping(checklist.get("human_review_packet"))
    dataset = _mapping(packet.get("dataset"))
    plan = _mapping(checklist.get("training_plan_preview"))
    job_spec = _mapping(plan.get("job_spec"))
    return {
        "tenant_id": tenant_id,
        "audit_id": audit_record.get("audit_id"),
        "audit_file": audit_file,
        "audit_size_bytes": audit_size_bytes,
        "audit_sha256": audit_sha256,
        "status": gate.get("status"),
        "auditor": gate.get("auditor"),
        "request_id": packet.get("latest_request_id"),
        "manifest_id": dataset.get("freeze_manifest_id"),
        "provider": job_spec.get("provider"),
        "base_model": job_spec.get("base_model"),
        "training_execution_allowed": guard.get(
            "training_execution_allowed",
            False,
        ),
        "provider_job_started": guard.get("provider_job_started", False),
        "external_upload_started": guard.get("external_upload_started", False),
        "provider_api_calls_allowed": guard.get(
            "provider_api_calls_allowed",
            False,
        ),
        "model_promotion_allowed": guard.get("model_promotion_allowed", False),
        "created_at": audit_record.get("created_at"),
    }
