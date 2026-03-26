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

from app.schemas import ProcurementDecisionRecord, ProcurementDecisionUpsert, ProcurementSourceSnapshotMetadata
from app.storage.base import BaseJsonStore, atomic_write_text
from app.storage.state_backend import StateBackend, get_state_backend


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProcurementDecisionStore(BaseJsonStore):
    """Thread-safe, tenant-scoped JSON-backed procurement state store."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        super().__init__()
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _get_path(self) -> Path:  # multi-tenant: use tenant-specific helpers below
        return self._base / "tenants"

    def _path(self, tenant_id: str) -> Path:
        tenant_dir = self._base / "tenants" / tenant_id
        if self._backend.kind == "local":
            tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir / "procurement_decisions.json"

    def _snapshot_dir(self, tenant_id: str, project_id: str) -> Path:
        path = self._base / "tenants" / tenant_id / "procurement_snapshots" / project_id
        if self._backend.kind == "local":
            path.mkdir(parents=True, exist_ok=True)
        return path

    def _relative_path(self, tenant_id: str) -> str:
        return str(Path("tenants") / tenant_id / "procurement_decisions.json")

    def _snapshot_relpath(self, tenant_id: str, project_id: str, snapshot_id: str) -> str:
        return str(Path("tenants") / tenant_id / "procurement_snapshots" / project_id / f"{snapshot_id}.json")

    def _snapshot_abspath(self, tenant_id: str, project_id: str, snapshot_id: str) -> Path:
        return self._snapshot_dir(tenant_id, project_id) / f"{snapshot_id}.json"

    def _load(self, tenant_id: str) -> list[dict[str, Any]]:
        raw = self._backend.read_text(self._relative_path(tenant_id))
        if raw is None:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []

    def _save(self, tenant_id: str, records: list[dict[str, Any]]) -> None:
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        if self._backend.kind == "local":
            atomic_write_text(self._path(tenant_id), payload)
            return
        self._backend.write_text(self._relative_path(tenant_id), payload)

    @staticmethod
    def _from_dict(data: dict[str, Any]) -> ProcurementDecisionRecord:
        return ProcurementDecisionRecord.model_validate(data)

    @staticmethod
    def _to_dict(record: ProcurementDecisionRecord) -> dict[str, Any]:
        return record.model_dump(mode="json")

    def _find(
        self,
        project_id: str,
        tenant_id: str | None = None,
    ) -> tuple[str, list[dict[str, Any]], int, ProcurementDecisionRecord] | None:
        if tenant_id is not None:
            records = self._load(tenant_id)
            for idx, record in enumerate(records):
                if record.get("project_id") == project_id:
                    parsed = self._from_dict(record)
                    if parsed.tenant_id != tenant_id:
                        return None
                    return tenant_id, records, idx, parsed
            return None

        tenant_paths = self._backend.list_prefix("tenants/")
        tenant_ids = sorted(
            {
                Path(path).parts[1]
                for path in tenant_paths
                if len(Path(path).parts) >= 3 and Path(path).parts[0] == "tenants"
            }
        )
        for tid in tenant_ids:
            records = self._load(tid)
            for idx, record in enumerate(records):
                if record.get("project_id") == project_id:
                    return tid, records, idx, self._from_dict(record)
        return None

    def _flush(
        self,
        tenant_id: str,
        records: list[dict[str, Any]],
        idx: int,
        record: ProcurementDecisionRecord,
    ) -> ProcurementDecisionRecord:
        records[idx] = self._to_dict(record)
        self._save(tenant_id, records)
        return record

    def upsert(self, payload: ProcurementDecisionUpsert) -> ProcurementDecisionRecord:
        with self._lock:
            now = _now_iso()
            result = self._find(payload.project_id, tenant_id=payload.tenant_id)
            record_data = payload.model_dump(mode="json")
            if result is None:
                record = ProcurementDecisionRecord.model_validate(
                    {
                        **record_data,
                        "decision_id": str(uuid.uuid4()),
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                records = self._load(payload.tenant_id)
                records.append(self._to_dict(record))
                self._save(payload.tenant_id, records)
                return record

            tenant_id, records, idx, existing = result
            record = ProcurementDecisionRecord.model_validate(
                {
                    **record_data,
                    "decision_id": existing.decision_id,
                    "created_at": existing.created_at,
                    "updated_at": now,
                }
            )
            return self._flush(tenant_id, records, idx, record)

    def get(self, project_id: str, tenant_id: str | None = None) -> ProcurementDecisionRecord | None:
        with self._lock:
            result = self._find(project_id, tenant_id=tenant_id)
            return result[3] if result else None

    def list_by_tenant(self, tenant_id: str) -> list[ProcurementDecisionRecord]:
        with self._lock:
            records = [self._from_dict(item) for item in self._load(tenant_id)]
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
        snapshot_id = str(uuid.uuid4())
        snapshot_payload = json.dumps(payload, ensure_ascii=False, indent=2)
        snapshot_relpath = self._snapshot_relpath(tenant_id, project_id, snapshot_id)
        if self._backend.kind == "local":
            atomic_write_text(self._snapshot_abspath(tenant_id, project_id, snapshot_id), snapshot_payload)
        else:
            self._backend.write_text(snapshot_relpath, snapshot_payload)
        return ProcurementSourceSnapshotMetadata.model_validate(
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

    def load_source_snapshot(
        self,
        *,
        tenant_id: str,
        project_id: str,
        snapshot_id: str,
    ) -> Any | None:
        raw = self._backend.read_text(self._snapshot_relpath(tenant_id, project_id, snapshot_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
