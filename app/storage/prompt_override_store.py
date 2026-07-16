"""Tenant-scoped runtime prompt override storage."""

from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, get_state_backend
from app.storage.state_lock import state_backend_identity, state_lock
from app.tenant import require_tenant_id


class PromptOverrideStoreError(RuntimeError):
    """Raised when persisted prompt override state cannot be trusted."""


_override_stores: dict[tuple[Any, ...], "PromptOverrideStore"] = {}
_override_stores_guard = threading.Lock()


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
        if set(record) != expected_fields:
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

    def _load(self) -> dict[str, Any]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return {}
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

    def _save(self, data: dict[str, Any]) -> None:
        self._backend.write_text(
            self._relative_path,
            json.dumps(data, ensure_ascii=False, indent=2),
        )

    def save_override(
        self,
        bundle_id: str,
        override_hint: str,
        trigger_reason: str,
        avg_score_before: float = 0.0,
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

        with self._lock:
            data = self._load()
            existing = data.get(bundle_id)
            if existing is not None and not self._owns(existing):
                raise PromptOverrideStoreError(
                    "Foreign prompt override must be preserved"
                )
            record = {
                "bundle_id": bundle_id,
                "tenant_id": self._tenant_id,
                "override_hint": override_hint,
                "trigger_reason": trigger_reason,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "applied_count": existing["applied_count"] if existing else 0,
                "avg_score_before": float(avg_score_before),
            }
            self._validate_owned(bundle_id, record, legacy=False)
            data[bundle_id] = record
            self._save(data)

    def get_override(self, bundle_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._load().get(bundle_id)
            return record if self._owns(record) else None

    def increment_applied(self, bundle_id: str) -> None:
        with self._lock:
            data = self._load()
            record = data.get(bundle_id)
            if not self._owns(record):
                return
            record["applied_count"] += 1
            self._validate_owned(bundle_id, record, legacy="tenant_id" not in record)
            self._save(data)

    def list_overrides(self) -> list[dict[str, Any]]:
        with self._lock:
            return [record for record in self._load().values() if self._owns(record)]

    def delete_override(self, bundle_id: str) -> None:
        with self._lock:
            data = self._load()
            if not self._owns(data.get(bundle_id)):
                return
            data.pop(bundle_id)
            self._save(data)


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
