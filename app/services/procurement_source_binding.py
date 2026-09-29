"""Capture exact source bytes and compare pinned procurement context."""

import hashlib
import json

from app.schemas import ProcurementDecisionRecord
from app.schemas.procurement_binding import ProcurementSourceBinding
from app.storage.procurement_project_state import ProcurementDecisionEntry
from app.storage.procurement_store import (
    ProcurementDecisionStoreError,
    validate_procurement_record,
)
from app.storage.state_backend import StateBackend, StateBackendError


def procurement_record_sha256(record: ProcurementDecisionRecord) -> str:
    content = json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def require_binding_matches_record(
    binding: ProcurementSourceBinding,
    record: ProcurementDecisionRecord,
) -> ProcurementSourceBinding:
    binding = ProcurementSourceBinding.model_validate(binding.model_dump(mode="json"))
    record = validate_procurement_record(record.model_dump(mode="json"))
    if (binding.tenant_id, binding.project_id, binding.decision_id) != (
        record.tenant_id,
        record.project_id,
        record.decision_id,
    ):
        raise ValueError("Procurement source binding scope mismatch")
    if record.opportunity is None or (binding.source_kind, binding.source_id) != (
        record.opportunity.source_kind,
        record.opportunity.source_id,
    ):
        raise ValueError("Procurement source binding opportunity mismatch")
    if (
        binding.source_updated_at != record.updated_at
        or binding.record_sha256 != procurement_record_sha256(record)
    ):
        raise ValueError("Procurement source binding record mismatch")
    if [item.snapshot_id for item in binding.snapshots] != [
        item.snapshot_id for item in record.source_snapshots
    ]:
        raise ValueError("Procurement source binding snapshot mismatch")
    return binding


def capture_procurement_source_binding(
    entry: ProcurementDecisionEntry,
    *,
    backend: StateBackend,
) -> ProcurementSourceBinding:
    entry = ProcurementDecisionEntry.model_validate(entry.model_dump(mode="json"))
    record = entry.record
    if record.opportunity is None:
        raise ValueError("Procurement opportunity is required for source binding")
    snapshots = []
    for snapshot in record.source_snapshots:
        try:
            content = backend.read_bytes(snapshot.storage_path)
        except StateBackendError as exc:
            raise ProcurementDecisionStoreError(
                "Cannot read procurement source snapshot"
            ) from exc
        if content is None:
            raise ProcurementDecisionStoreError(
                "Procurement source snapshot is missing"
            )
        snapshots.append(
            {
                "snapshot_id": snapshot.snapshot_id,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return ProcurementSourceBinding(
        tenant_id=record.tenant_id,
        project_id=record.project_id,
        decision_id=record.decision_id,
        decision_revision=entry.decision_revision,
        source_kind=record.opportunity.source_kind,
        source_id=record.opportunity.source_id,
        source_updated_at=record.updated_at,
        record_sha256=procurement_record_sha256(record),
        snapshots=snapshots,
    )
