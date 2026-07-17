"""app/storage/procurement_store.py — Project-scoped public procurement state.

Stores one additive procurement decision record per project and keeps raw
source snapshots in separate JSON files.

Storage:
  - data/tenants/{tenant_id}/procurement_decisions.json
  - data/tenants/{tenant_id}/procurement_snapshots/{project_id}/{snapshot_id}.json
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.schemas import (
    ProcurementDecisionRecord,
    ProcurementDecisionUpsert,
    ProcurementSourceSnapshotMetadata,
)
from app.storage.state_backend import (
    StateBackend,
    StateBackendError,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


class ProcurementDecisionStoreError(ValueError):
    """Raised when persisted procurement state cannot be trusted."""


def _require_path_segment(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"Invalid {field}")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProcurementDecisionStoreError(
                f"Duplicate key in procurement state: {key!r}"
            )
        result[key] = value
    return result


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProcurementDecisionStore:
    """Thread-safe, tenant-scoped JSON-backed procurement state store."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _relative_path(self, tenant_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        return str(Path("tenants") / tenant_id / "procurement_decisions.json")

    def _snapshot_relpath(self, tenant_id: str, project_id: str, snapshot_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_path_segment(project_id, field="project_id")
        snapshot_id = _require_path_segment(snapshot_id, field="snapshot_id")
        return str(
            Path("tenants")
            / tenant_id
            / "procurement_snapshots"
            / project_id
            / f"{snapshot_id}.json"
        )

    def _decision_lock(self, tenant_id: str):
        relative_path = self._relative_path(tenant_id)
        return state_lock(
            self._backend,
            data_dir=self._base,
            relative_path=relative_path,
        )

    def _load(self, tenant_id: str) -> list[Any]:
        tenant_id = require_tenant_id(tenant_id)
        try:
            raw = self._backend.read_text(self._relative_path(tenant_id))
        except (StateBackendError, UnicodeError) as exc:
            raise ProcurementDecisionStoreError(
                "Invalid procurement decision state document"
            ) from exc
        if raw is None:
            return []
        if not raw.strip():
            raise ProcurementDecisionStoreError(
                "Invalid procurement decision state document"
            )
        try:
            records = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProcurementDecisionStoreError(
                "Invalid procurement decision state document"
            ) from exc
        if not isinstance(records, list):
            raise ProcurementDecisionStoreError(
                "Invalid procurement decision state document"
            )
        return records

    def _save(self, tenant_id: str, records: list[Any]) -> None:
        self._owned_records(records, tenant_id=tenant_id)
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        try:
            self._backend.write_text(self._relative_path(tenant_id), payload)
        except StateBackendError as exc:
            raise ProcurementDecisionStoreError(
                "Failed to persist procurement decision state"
            ) from exc

    def _from_dict(self, data: dict[str, Any]) -> ProcurementDecisionRecord:
        record = ProcurementDecisionRecord.model_validate(data)
        require_tenant_id(record.tenant_id)
        _require_path_segment(record.project_id, field="project_id")
        snapshot_ids: set[str] = set()
        for snapshot in record.source_snapshots:
            if snapshot.snapshot_id in snapshot_ids:
                raise ProcurementDecisionStoreError(
                    "Duplicate procurement source snapshot metadata"
                )
            snapshot_ids.add(snapshot.snapshot_id)
            expected_path = self._snapshot_relpath(
                record.tenant_id,
                record.project_id,
                snapshot.snapshot_id,
            )
            if snapshot.storage_path != expected_path:
                raise ProcurementDecisionStoreError(
                    "Procurement source snapshot ownership mismatch"
                )
        return record

    @staticmethod
    def _to_dict(record: ProcurementDecisionRecord) -> dict[str, Any]:
        return record.model_dump(mode="json")

    def _owned_records(
        self,
        records: list[Any],
        *,
        tenant_id: str,
    ) -> list[tuple[int, ProcurementDecisionRecord]]:
        tenant_id = require_tenant_id(tenant_id)
        owned: list[tuple[int, ProcurementDecisionRecord]] = []
        project_ids: set[str] = set()
        decision_ids: set[str] = set()
        for index, raw_record in enumerate(records):
            if not isinstance(raw_record, dict):
                continue
            if raw_record.get("tenant_id") != tenant_id:
                continue
            try:
                record = self._from_dict(raw_record)
            except (TypeError, ValueError) as exc:
                raise ProcurementDecisionStoreError(
                    "Invalid owned procurement decision record"
                ) from exc
            if record.project_id in project_ids:
                raise ProcurementDecisionStoreError(
                    "Duplicate procurement project records"
                )
            if record.decision_id in decision_ids:
                raise ProcurementDecisionStoreError(
                    "Duplicate procurement decision records"
                )
            project_ids.add(record.project_id)
            decision_ids.add(record.decision_id)
            owned.append((index, record))
        return owned

    def _find_owned(
        self,
        records: list[Any],
        *,
        tenant_id: str,
        project_id: str,
    ) -> tuple[int, ProcurementDecisionRecord] | None:
        project_id = _require_path_segment(project_id, field="project_id")
        for index, record in self._owned_records(records, tenant_id=tenant_id):
            if record.project_id == project_id:
                return index, record
        return None

    def _flush(
        self,
        tenant_id: str,
        records: list[Any],
        idx: int,
        record: ProcurementDecisionRecord,
    ) -> ProcurementDecisionRecord:
        records[idx] = self._to_dict(record)
        self._save(tenant_id, records)
        return record

    def upsert(self, payload: ProcurementDecisionUpsert) -> ProcurementDecisionRecord:
        tenant_id = require_tenant_id(payload.tenant_id)
        project_id = _require_path_segment(payload.project_id, field="project_id")
        with self._decision_lock(tenant_id):
            now = _now_iso()
            records = self._load(tenant_id)
            result = self._find_owned(
                records,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            record_data = payload.model_dump(mode="json")
            if result is None:
                record = self._from_dict(
                    {
                        **record_data,
                        "decision_id": str(uuid.uuid4()),
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                records.append(self._to_dict(record))
                self._save(tenant_id, records)
                return record

            idx, existing = result
            record = self._from_dict(
                {
                    **record_data,
                    "decision_id": existing.decision_id,
                    "created_at": existing.created_at,
                    "updated_at": now,
                }
            )
            return self._flush(tenant_id, records, idx, record)

    def get(self, project_id: str, *, tenant_id: str) -> ProcurementDecisionRecord | None:
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_path_segment(project_id, field="project_id")
        with self._decision_lock(tenant_id):
            result = self._find_owned(
                self._load(tenant_id),
                tenant_id=tenant_id,
                project_id=project_id,
            )
            return result[1] if result else None

    def update_notes(
        self,
        *,
        project_id: str,
        tenant_id: str,
        notes: str,
    ) -> ProcurementDecisionRecord:
        """Update operator notes without invalidating procurement decision freshness."""
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_path_segment(project_id, field="project_id")
        with self._decision_lock(tenant_id):
            records = self._load(tenant_id)
            result = self._find_owned(
                records,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if result is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

            idx, existing = result
            record_data = existing.model_dump(mode="json")
            record_data["notes"] = notes
            record = self._from_dict(record_data)
            return self._flush(tenant_id, records, idx, record)

    def list_by_tenant(self, tenant_id: str) -> list[ProcurementDecisionRecord]:
        tenant_id = require_tenant_id(tenant_id)
        with self._decision_lock(tenant_id):
            records = [
                record
                for _, record in self._owned_records(
                    self._load(tenant_id),
                    tenant_id=tenant_id,
                )
            ]
        return sorted(records, key=lambda record: record.updated_at, reverse=True)

    def save_source_snapshot(
        self,
        *,
        tenant_id: str,
        project_id: str,
        source_kind: str,
        payload: Any,
        source_label: str = "",
        external_id: str = "",
        content_type: str = "application/json",
    ) -> ProcurementSourceSnapshotMetadata:
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_path_segment(project_id, field="project_id")
        snapshot_id = str(uuid.uuid4())
        try:
            snapshot_payload = json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise ProcurementDecisionStoreError(
                "Invalid procurement source snapshot payload"
            ) from exc
        snapshot_relpath = self._snapshot_relpath(tenant_id, project_id, snapshot_id)
        metadata = ProcurementSourceSnapshotMetadata.model_validate(
            {
                "snapshot_id": snapshot_id,
                "source_kind": source_kind,
                "source_label": source_label,
                "external_id": external_id,
                "captured_at": _now_iso(),
                "storage_path": snapshot_relpath,
                "content_type": content_type,
            }
        )
        try:
            self._backend.write_text(snapshot_relpath, snapshot_payload)
        except StateBackendError as exc:
            raise ProcurementDecisionStoreError(
                "Failed to persist procurement source snapshot"
            ) from exc
        return metadata

    def load_source_snapshot(
        self,
        *,
        tenant_id: str,
        project_id: str,
        snapshot_id: str,
    ) -> Any | None:
        snapshot_relpath = self._snapshot_relpath(tenant_id, project_id, snapshot_id)
        try:
            raw = self._backend.read_text(snapshot_relpath)
        except (StateBackendError, UnicodeError) as exc:
            raise ProcurementDecisionStoreError(
                "Invalid procurement source snapshot"
            ) from exc
        if raw is None:
            return None
        if not raw.strip():
            raise ProcurementDecisionStoreError(
                "Invalid procurement source snapshot"
            )
        try:
            return json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProcurementDecisionStoreError(
                "Invalid procurement source snapshot"
            ) from exc
