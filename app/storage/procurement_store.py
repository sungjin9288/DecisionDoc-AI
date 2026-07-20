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
from typing import Any, Callable, TypeVar

from app.schemas import (
    ProcurementDecisionRecord,
    ProcurementDecisionUpsert,
    ProcurementSourceSnapshotMetadata,
)
from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import (
    StateBackend,
    StateBackendError,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


class ProcurementDecisionStoreError(ValueError):
    """Raised when persisted procurement state cannot be trusted."""


class _ProcurementMutationHistoryError(ProcurementDecisionStoreError):
    """Raised when a private mutation receipt is malformed."""


_MUTATION_IDS_FIELD = "_mutation_ids"
_MAX_TRACKED_MUTATIONS = 64
_MAX_MUTATION_ATTEMPTS = 32
_MutationResult = TypeVar("_MutationResult")


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

    def __init__(
        self, base_dir: str = "data", *, backend: StateBackend | None = None
    ) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _relative_path(self, tenant_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        return str(Path("tenants") / tenant_id / "procurement_decisions.json")

    def _snapshot_relpath(
        self, tenant_id: str, project_id: str, snapshot_id: str
    ) -> str:
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

    @staticmethod
    def _decode_records(raw: str) -> list[Any]:
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

    def _read_state(self, tenant_id: str) -> tuple[str | None, list[Any]]:
        tenant_id = require_tenant_id(tenant_id)
        try:
            raw = self._backend.read_text(self._relative_path(tenant_id))
        except (StateBackendError, UnicodeError) as exc:
            raise ProcurementDecisionStoreError(
                "Invalid procurement decision state document"
            ) from exc
        if raw is None:
            return None, []
        return raw, self._decode_records(raw)

    def _load(self, tenant_id: str) -> list[Any]:
        return self._read_state(tenant_id)[1]

    @staticmethod
    def _mutation_ids(record: dict[str, Any]) -> list[str]:
        mutation_ids = record.get(_MUTATION_IDS_FIELD, [])
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise _ProcurementMutationHistoryError(
                "Invalid procurement decision mutation history"
            )
        return list(mutation_ids)

    def _record_payload(
        self,
        record: ProcurementDecisionRecord,
        *,
        previous: dict[str, Any] | None,
        mutation_id: str,
    ) -> dict[str, Any]:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = self._to_dict(record)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    def _persist_if_current(
        self,
        tenant_id: str,
        *,
        expected: str | None,
        records: list[Any],
        committed: Callable[[list[Any]], bool],
    ) -> bool:
        tenant_id = require_tenant_id(tenant_id)
        self._owned_records(records, tenant_id=tenant_id)
        payload = json.dumps(records, ensure_ascii=False, indent=2)

        def decode(raw: str) -> list[Any]:
            observed = self._decode_records(raw)
            self._owned_records(observed, tenant_id=tenant_id)
            return observed

        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path(tenant_id),
                expected=expected,
                replacement=payload,
                decode=decode,
                committed=committed,
                decode_errors=(ProcurementDecisionStoreError,),
            )
        except StateBackendError as exc:
            raise ProcurementDecisionStoreError(
                "Failed to persist procurement decision state"
            ) from exc

    def _mutate_state(
        self,
        tenant_id: str,
        change: Callable[[list[Any]], tuple[_MutationResult, bool]],
        *,
        committed: Callable[[list[Any]], bool],
    ) -> _MutationResult:
        tenant_id = require_tenant_id(tenant_id)
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, records = self._read_state(tenant_id)
            self._owned_records(records, tenant_id=tenant_id)
            result, changed = change(records)
            if not changed:
                return result
            if self._persist_if_current(
                tenant_id,
                expected=expected,
                records=records,
                committed=committed,
            ):
                return result
        raise ProcurementDecisionStoreError(
            "Procurement decision state changed too many times to persist safely"
        )

    def _from_dict(self, data: dict[str, Any]) -> ProcurementDecisionRecord:
        public = dict(data)
        self._mutation_ids(public)
        public.pop(_MUTATION_IDS_FIELD, None)
        record = ProcurementDecisionRecord.model_validate(public)
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
            except _ProcurementMutationHistoryError:
                raise
            except (ProcurementDecisionStoreError, TypeError, ValueError) as exc:
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

    def upsert(self, payload: ProcurementDecisionUpsert) -> ProcurementDecisionRecord:
        tenant_id = require_tenant_id(payload.tenant_id)
        project_id = _require_path_segment(payload.project_id, field="project_id")
        mutation_id = uuid.uuid4().hex
        new_decision_id = str(uuid.uuid4())
        target_decision_id: str | None = None
        target_bound = False
        record_data = payload.model_dump(mode="json")

        def apply(records: list[Any]) -> tuple[ProcurementDecisionRecord, bool]:
            nonlocal target_bound, target_decision_id
            now = _now_iso()
            result = self._find_owned(
                records,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if result is None:
                if target_bound and target_decision_id != new_decision_id:
                    raise ProcurementDecisionStoreError(
                        "Procurement decision identity changed during mutation"
                    )
                target_bound = True
                target_decision_id = new_decision_id
                record = self._from_dict(
                    {
                        **record_data,
                        "decision_id": new_decision_id,
                        "created_at": now,
                        "updated_at": now,
                    }
                )
                records.append(
                    self._record_payload(
                        record,
                        previous=None,
                        mutation_id=mutation_id,
                    )
                )
                return record, True

            idx, existing = result
            if not target_bound:
                target_bound = True
                target_decision_id = existing.decision_id
            elif target_decision_id == new_decision_id:
                target_decision_id = existing.decision_id
            elif existing.decision_id != target_decision_id:
                raise ProcurementDecisionStoreError(
                    "Procurement decision identity changed during mutation"
                )

            previous = records[idx]
            if mutation_id in self._mutation_ids(previous):
                return existing, False
            record = self._from_dict(
                {
                    **record_data,
                    "decision_id": existing.decision_id,
                    "created_at": existing.created_at,
                    "updated_at": now,
                }
            )
            records[idx] = self._record_payload(
                record,
                previous=previous,
                mutation_id=mutation_id,
            )
            return record, True

        def was_committed(records: list[Any]) -> bool:
            result = self._find_owned(
                records,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if result is None:
                return False
            idx, record = result
            return (
                record.decision_id == target_decision_id
                and mutation_id in self._mutation_ids(records[idx])
            )

        with self._decision_lock(tenant_id):
            return self._mutate_state(
                tenant_id,
                apply,
                committed=was_committed,
            )

    def get(
        self, project_id: str, *, tenant_id: str
    ) -> ProcurementDecisionRecord | None:
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
        mutation_id = uuid.uuid4().hex
        target_decision_id: str | None = None

        def apply(records: list[Any]) -> tuple[ProcurementDecisionRecord, bool]:
            nonlocal target_decision_id
            result = self._find_owned(
                records,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if result is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

            idx, existing = result
            if target_decision_id is None:
                target_decision_id = existing.decision_id
            elif existing.decision_id != target_decision_id:
                raise ProcurementDecisionStoreError(
                    "Procurement decision identity changed during mutation"
                )

            previous = records[idx]
            if mutation_id in self._mutation_ids(previous):
                return existing, False
            record_data = existing.model_dump(mode="json")
            record_data["notes"] = notes
            record = self._from_dict(record_data)
            records[idx] = self._record_payload(
                record,
                previous=previous,
                mutation_id=mutation_id,
            )
            return record, True

        def was_committed(records: list[Any]) -> bool:
            result = self._find_owned(
                records,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if result is None:
                return False
            idx, record = result
            return (
                record.decision_id == target_decision_id
                and mutation_id in self._mutation_ids(records[idx])
            )

        with self._decision_lock(tenant_id):
            return self._mutate_state(
                tenant_id,
                apply,
                committed=was_committed,
            )

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
            created = self._backend.write_text_if_absent(
                snapshot_relpath,
                snapshot_payload,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_text(snapshot_relpath)
            except (StateBackendError, UnicodeError):
                observed = None
            if observed == snapshot_payload:
                return metadata
            raise ProcurementDecisionStoreError(
                "Failed to persist procurement source snapshot"
            ) from exc
        if not created:
            raise ProcurementDecisionStoreError(
                "Procurement source snapshot identity is already in use"
            )
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
            raise ProcurementDecisionStoreError("Invalid procurement source snapshot")
        try:
            return json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ProcurementDecisionStoreError(
                "Invalid procurement source snapshot"
            ) from exc
