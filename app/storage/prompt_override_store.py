"""Tenant-scoped runtime prompt override storage."""

from __future__ import annotations

import hashlib
import json
import math
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.storage.conditional_state import mutate_with_retry, persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_backend_identity, state_lock
from app.tenant import require_tenant_id


class PromptOverrideStoreError(RuntimeError):
    """Raised when persisted prompt override state cannot be trusted."""


_override_stores: dict[tuple[Any, ...], "PromptOverrideStore"] = {}
_override_stores_guard = threading.Lock()
_MAX_MUTATION_ATTEMPTS = 32
_MAX_TRACKED_MUTATIONS = 64
_INCARNATION_ID_FIELD = "_incarnation_id"
_MUTATION_IDS_FIELD = "_mutation_ids"
_SAVE_RECEIPTS_FIELD = "_save_receipts"
_PRIVATE_RECORD_FIELDS = {
    _INCARNATION_ID_FIELD,
    _MUTATION_IDS_FIELD,
    _SAVE_RECEIPTS_FIELD,
}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PromptOverrideStoreError(
                f"Duplicate key in prompt override state: {key!r}"
            )
        result[key] = value
    return result


class PromptOverrideStore:
    """Read and update prompt improvement instructions for one tenant."""

    _RECORD_FIELDS = {
        "bundle_id",
        "tenant_id",
        "override_hint",
        "trigger_reason",
        "created_at",
        "applied_count",
        "avg_score_before",
    }

    def __init__(
        self,
        data_dir: Path,
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir)
        self._relative_path = str(
            Path("tenants") / self._tenant_id / "prompt_overrides.json"
        )
        self._path = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = state_lock(
            self._backend,
            data_dir=self._data_dir,
            relative_path=self._relative_path,
        )

    @staticmethod
    def _identifier(value: object, *, field_name: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise PromptOverrideStoreError(f"Invalid prompt override {field_name}")
        return value

    def _owns(self, record: object) -> bool:
        return isinstance(record, dict) and record.get("tenant_id") in {
            None,
            self._tenant_id,
        }

    def _validate_owned(
        self,
        storage_key: str,
        record: dict[str, Any],
        *,
        legacy: bool,
    ) -> None:
        expected_fields = self._RECORD_FIELDS - ({"tenant_id"} if legacy else set())
        record_fields = set(record)
        if (
            not expected_fields.issubset(record_fields)
            or record_fields - expected_fields - _PRIVATE_RECORD_FIELDS
        ):
            raise PromptOverrideStoreError("Invalid prompt override record fields")
        bundle_id = self._identifier(
            record.get("bundle_id"),
            field_name="bundle identity",
        )
        if storage_key != bundle_id:
            raise PromptOverrideStoreError("Prompt override storage identity mismatch")
        if not legacy and record.get("tenant_id") != self._tenant_id:
            raise PromptOverrideStoreError("Prompt override tenant ownership mismatch")
        self._identifier(record.get("override_hint"), field_name="hint")
        self._identifier(record.get("trigger_reason"), field_name="trigger reason")

        created_at = record.get("created_at")
        if not isinstance(created_at, str) or not created_at:
            raise PromptOverrideStoreError("Invalid prompt override timestamp")
        try:
            parsed = datetime.fromisoformat(created_at)
        except ValueError as exc:
            raise PromptOverrideStoreError("Invalid prompt override timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise PromptOverrideStoreError("Invalid prompt override timestamp")

        applied_count = record.get("applied_count")
        if (
            isinstance(applied_count, bool)
            or not isinstance(applied_count, int)
            or applied_count < 0
        ):
            raise PromptOverrideStoreError("Invalid prompt override applied count")
        avg_score = record.get("avg_score_before")
        if (
            isinstance(avg_score, bool)
            or not isinstance(avg_score, (int, float))
            or not math.isfinite(avg_score)
            or not 0.0 <= avg_score <= 1.0
        ):
            raise PromptOverrideStoreError("Invalid prompt override average score")
        self._incarnation_id(record)
        mutation_ids = self._mutation_ids(record)
        save_receipts = self._save_receipts(record)
        if not set(save_receipts).issubset(mutation_ids):
            raise PromptOverrideStoreError(
                "Prompt override save receipt has no mutation record"
            )

    def _read_state(self) -> tuple[str | None, dict[str, Any]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise PromptOverrideStoreError(
                "Prompt override state could not be read"
            ) from exc
        if raw is None:
            return None, {}
        return raw, self._decode_state(raw)

    def _load(self) -> dict[str, Any]:
        return self._read_state()[1]

    @staticmethod
    def _incarnation_id(record: dict[str, Any]) -> str | None:
        incarnation_id = record.get(_INCARNATION_ID_FIELD)
        if incarnation_id is not None and (
            not isinstance(incarnation_id, str) or not incarnation_id
        ):
            raise PromptOverrideStoreError("Invalid prompt override incarnation")
        return incarnation_id

    def _effective_incarnation_id(self, record: dict[str, Any]) -> str:
        incarnation_id = self._incarnation_id(record)
        if incarnation_id is not None:
            return incarnation_id
        legacy_identity = json.dumps(
            {
                "bundle_id": record["bundle_id"],
                "created_at": record["created_at"],
                "tenant_id": record.get("tenant_id") or self._tenant_id,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(legacy_identity.encode("utf-8")).hexdigest()
        return f"legacy-{digest}"

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
            raise PromptOverrideStoreError(
                "Invalid prompt override mutation history"
            )
        return list(mutation_ids)

    @staticmethod
    def _save_receipts(record: dict[str, Any]) -> dict[str, str]:
        receipts = record.get(_SAVE_RECEIPTS_FIELD, {})
        if (
            not isinstance(receipts, dict)
            or len(receipts) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str)
                or not mutation_id
                or not isinstance(payload_hash, str)
                or len(payload_hash) != 64
                or any(character not in "0123456789abcdef" for character in payload_hash)
                for mutation_id, payload_hash in receipts.items()
            )
        ):
            raise PromptOverrideStoreError(
                "Invalid prompt override save receipt history"
            )
        return dict(receipts)

    @staticmethod
    def _save_payload_hash(
        *,
        bundle_id: str,
        override_hint: str,
        trigger_reason: str,
        avg_score_before: float,
    ) -> str:
        payload = json.dumps(
            {
                "avg_score_before": float(avg_score_before),
                "bundle_id": bundle_id,
                "override_hint": override_hint,
                "trigger_reason": trigger_reason,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _record_mutation(
        self,
        record: dict[str, Any],
        *,
        previous: dict[str, Any] | None,
        mutation_id: str,
        save_payload_hash: str | None = None,
    ) -> dict[str, Any]:
        mutation_ids = self._mutation_ids(previous or {})
        save_receipts = self._save_receipts(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        if save_payload_hash is not None:
            save_receipts[mutation_id] = save_payload_hash
        mutation_ids = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        save_receipts = {
            tracked_id: save_receipts[tracked_id]
            for tracked_id in mutation_ids
            if tracked_id in save_receipts
        }
        persisted = dict(record)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids
        if save_receipts:
            persisted[_SAVE_RECEIPTS_FIELD] = save_receipts
        else:
            persisted.pop(_SAVE_RECEIPTS_FIELD, None)
        return persisted

    @staticmethod
    def _public_record(record: dict[str, Any]) -> dict[str, Any]:
        public = dict(record)
        for field in _PRIVATE_RECORD_FIELDS:
            public.pop(field, None)
        return public

    def _persist_if_current(
        self,
        expected: str | None,
        data: dict[str, Any],
        committed: Callable[[dict[str, Any]], bool],
    ) -> bool:
        for storage_key, record in data.items():
            if self._owns(record):
                self._validate_owned(
                    storage_key,
                    record,
                    legacy="tenant_id" not in record,
                )
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=payload,
                decode=self._decode_state,
                committed=committed,
                decode_errors=(PromptOverrideStoreError,),
            )
        except StateBackendError as exc:
            raise PromptOverrideStoreError(
                "Prompt override state could not be written"
            ) from exc

    def _decode_state(self, raw: str) -> dict[str, Any]:
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, PromptOverrideStoreError) as exc:
            raise PromptOverrideStoreError(
                "Invalid prompt override state document"
            ) from exc
        if not isinstance(data, dict):
            raise PromptOverrideStoreError("Invalid prompt override state")
        for storage_key, record in data.items():
            if not isinstance(record, dict):
                raise PromptOverrideStoreError("Invalid prompt override record")
            stored_tenant_id = record.get("tenant_id")
            if stored_tenant_id is not None:
                if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                    raise PromptOverrideStoreError(
                        "Invalid prompt override tenant identity"
                    )
                if stored_tenant_id != self._tenant_id:
                    continue
            self._validate_owned(
                storage_key,
                record,
                legacy=stored_tenant_id is None,
            )
        return data

    def _mutate(
        self,
        change: Callable[
            [dict[str, Any]],
            tuple[Any, bool],
        ],
        *,
        committed: Callable[[dict[str, Any]], bool],
    ) -> Any:
        return mutate_with_retry(
            read=self._read_state,
            change=change,
            persist=self._persist_if_current,
            committed=committed,
            max_attempts=_MAX_MUTATION_ATTEMPTS,
            conflict_error=lambda: PromptOverrideStoreError(
                "Prompt override state changed too many times to persist safely"
            ),
        )

    def save_override(
        self,
        bundle_id: str,
        override_hint: str,
        trigger_reason: str,
        avg_score_before: float = 0.0,
        *,
        operation_id: str | None = None,
    ) -> None:
        """Create or replace one validated prompt override."""
        try:
            self._identifier(bundle_id, field_name="bundle identity")
            self._identifier(override_hint, field_name="hint")
            self._identifier(trigger_reason, field_name="trigger reason")
        except PromptOverrideStoreError as exc:
            raise ValueError(str(exc)) from exc
        if (
            isinstance(avg_score_before, bool)
            or not isinstance(avg_score_before, (int, float))
            or not math.isfinite(avg_score_before)
            or not 0.0 <= avg_score_before <= 1.0
        ):
            raise ValueError("Invalid prompt override average score")
        if operation_id is not None:
            try:
                self._identifier(operation_id, field_name="operation identity")
            except PromptOverrideStoreError as exc:
                raise ValueError(str(exc)) from exc

        mutation_id = operation_id or uuid.uuid4().hex
        new_incarnation_id = uuid.uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        payload_hash = self._save_payload_hash(
            bundle_id=bundle_id,
            override_hint=override_hint,
            trigger_reason=trigger_reason,
            avg_score_before=float(avg_score_before),
        )

        def apply(data: dict[str, Any]) -> tuple[None, bool]:
            existing = data.get(bundle_id)
            if existing is not None and not self._owns(existing):
                raise PromptOverrideStoreError(
                    "Foreign prompt override must be preserved"
                )
            if self._owns(existing) and mutation_id in self._mutation_ids(existing):
                receipt_hash = self._save_receipts(existing).get(mutation_id)
                if receipt_hash is None:
                    existing_hash = self._save_payload_hash(
                        bundle_id=existing["bundle_id"],
                        override_hint=existing["override_hint"],
                        trigger_reason=existing["trigger_reason"],
                        avg_score_before=existing["avg_score_before"],
                    )
                    if existing_hash == payload_hash:
                        return None, False
                    raise PromptOverrideStoreError(
                        "Prompt override operation identity has no payload receipt"
                    )
                if receipt_hash != payload_hash:
                    raise PromptOverrideStoreError(
                        "Prompt override operation identity was reused with a different payload"
                    )
                return None, False
            incarnation_id = (
                self._effective_incarnation_id(existing)
                if self._owns(existing)
                else None
            ) or new_incarnation_id
            record = {
                "bundle_id": bundle_id,
                "tenant_id": self._tenant_id,
                "override_hint": override_hint,
                "trigger_reason": trigger_reason,
                "created_at": created_at,
                "applied_count": existing["applied_count"] if existing else 0,
                "avg_score_before": float(avg_score_before),
                _INCARNATION_ID_FIELD: incarnation_id,
            }
            data[bundle_id] = self._record_mutation(
                record,
                previous=existing,
                mutation_id=mutation_id,
                save_payload_hash=payload_hash,
            )
            return None, True

        def was_committed(data: dict[str, Any]) -> bool:
            record = data.get(bundle_id)
            return (
                self._owns(record)
                and self._save_receipts(record).get(mutation_id) == payload_hash
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def get_override(self, bundle_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._load().get(bundle_id)
            return self._public_record(record) if self._owns(record) else None

    def increment_applied(self, bundle_id: str) -> None:
        mutation_id = uuid.uuid4().hex
        target_incarnation: str | None = None
        target_bound = False

        def apply(data: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_bound, target_incarnation
            record = data.get(bundle_id)
            if not self._owns(record):
                return None, False
            incarnation_id = self._effective_incarnation_id(record)
            if not target_bound:
                target_incarnation = incarnation_id
                target_bound = True
            elif incarnation_id != target_incarnation:
                return None, False
            if mutation_id in self._mutation_ids(record):
                return None, False
            updated = dict(record)
            updated["applied_count"] += 1
            updated[_INCARNATION_ID_FIELD] = incarnation_id
            data[bundle_id] = self._record_mutation(
                updated,
                previous=record,
                mutation_id=mutation_id,
            )
            return None, True

        def was_committed(data: dict[str, Any]) -> bool:
            record = data.get(bundle_id)
            return (
                self._owns(record)
                and self._incarnation_id(record) == target_incarnation
                and mutation_id in self._mutation_ids(record)
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def list_overrides(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._public_record(record)
                for record in self._load().values()
                if self._owns(record)
            ]

    def delete_override(self, bundle_id: str) -> None:
        target_incarnation: str | None = None
        target_bound = False

        def apply(data: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_bound, target_incarnation
            record = data.get(bundle_id)
            if not self._owns(record):
                return None, False
            incarnation_id = self._effective_incarnation_id(record)
            if not target_bound:
                target_incarnation = incarnation_id
                target_bound = True
            elif incarnation_id != target_incarnation:
                return None, False
            data.pop(bundle_id)
            return None, True

        def was_committed(data: dict[str, Any]) -> bool:
            record = data.get(bundle_id)
            return not (
                self._owns(record)
                and self._effective_incarnation_id(record) == target_incarnation
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)


def get_override_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> PromptOverrideStore:
    """Return a cached store for one tenant and one state backend."""
    tenant_id = require_tenant_id(tenant_id)
    root = Path(data_dir or os.getenv("DATA_DIR", "./data"))
    explicit_backend = backend is not None
    selected_backend = backend or get_state_backend(data_dir=root)
    key = (
        tenant_id,
        root.resolve(),
        *state_backend_identity(
            selected_backend,
            data_dir=root,
            explicit_backend=explicit_backend,
        ),
    )
    with _override_stores_guard:
        store = _override_stores.get(key)
        if store is None:
            store = PromptOverrideStore(
                root,
                tenant_id=tenant_id,
                backend=selected_backend,
            )
            _override_stores[key] = store
        return store


def clear_override_store_cache() -> None:
    with _override_stores_guard:
        _override_stores.clear()
