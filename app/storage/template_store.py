"""Tenant-scoped storage for reusable document form templates."""

from __future__ import annotations

import datetime
import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id


_template_locks: dict[Path, threading.RLock] = {}
_template_locks_guard = threading.Lock()


class TemplateStoreError(ValueError):
    """Raised when persisted template state cannot be trusted."""


def _lock_for_path(path: Path) -> threading.RLock:
    with _template_locks_guard:
        return _template_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TemplateStoreError(f"Duplicate key in template state: {key!r}")
        result[key] = value
    return result


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class TemplateEntry:
    template_id: str
    tenant_id: str
    user_id: str
    name: str
    bundle_id: str
    bundle_name: str
    form_data: dict = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)
    use_count: int = 0


class TemplateStore:
    """Thread-safe JSONL template state scoped to a single tenant."""

    def __init__(
        self,
        tenant_id: str,
        *,
        data_dir: str | Path | None = None,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "data"))
        self._relative_path = str(Path("tenants") / self._tenant_id / "templates.jsonl")
        self._path = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = _lock_for_path(self._path)

    def _owns(self, entry: dict) -> bool:
        stored_tenant_id = entry.get("tenant_id")
        return stored_tenant_id is None or stored_tenant_id == self._tenant_id

    def _validate_record(self, entry: object) -> dict[str, Any]:
        if not isinstance(entry, dict):
            raise TemplateStoreError("Invalid template record")

        stored_tenant_id = entry.get("tenant_id")
        if stored_tenant_id is not None:
            if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                raise TemplateStoreError("Invalid template identity")
            if stored_tenant_id != self._tenant_id:
                return entry

        required_strings = (
            "template_id",
            "user_id",
            "name",
            "bundle_id",
            "bundle_name",
            "created_at",
            "updated_at",
        )
        if any(not isinstance(entry.get(key), str) for key in required_strings):
            raise TemplateStoreError("Invalid template record")
        if any(
            not entry[key] for key in ("template_id", "user_id", "name", "bundle_id")
        ):
            raise TemplateStoreError("Invalid template identity")
        if not isinstance(entry.get("form_data"), dict):
            raise TemplateStoreError("Invalid template form data")
        use_count = entry.get("use_count")
        if (
            isinstance(use_count, bool)
            or not isinstance(use_count, int)
            or use_count < 0
        ):
            raise TemplateStoreError("Invalid template use count")
        try:
            datetime.datetime.fromisoformat(entry["created_at"])
            datetime.datetime.fromisoformat(entry["updated_at"])
        except ValueError as exc:
            raise TemplateStoreError("Invalid template timestamp") from exc
        return entry

    def _validate_entries(self, entries: object) -> list[dict[str, Any]]:
        if not isinstance(entries, list):
            raise TemplateStoreError("Invalid template state")

        template_ids: set[str] = set()
        for entry in entries:
            self._validate_record(entry)
            if not self._owns(entry):
                continue
            template_id = entry["template_id"]
            if template_id in template_ids:
                raise TemplateStoreError("Duplicate template identity")
            template_ids.add(template_id)
        return entries

    def _load(self) -> list[dict[str, Any]]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None:
            return []
        if not raw.strip():
            return []

        entries: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line, object_pairs_hook=_unique_object)
                self._validate_record(entry)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise TemplateStoreError(
                    f"Invalid template state at line {line_number}"
                ) from exc
            entries.append(entry)
        return self._validate_entries(entries)

    def _save(self, entries: list[dict[str, Any]]) -> None:
        self._validate_entries(entries)
        payload = "".join(
            f"{json.dumps(entry, ensure_ascii=False)}\n" for entry in entries
        )
        self._backend.write_text(
            self._relative_path,
            payload,
            content_type="application/x-ndjson; charset=utf-8",
        )

    def add(self, entry: TemplateEntry) -> None:
        if entry.tenant_id != self._tenant_id:
            raise ValueError("Template tenant does not match store tenant")
        record = self._validate_record(asdict(entry))
        with self._lock:
            entries = self._load()
            if any(
                self._owns(item) and item["template_id"] == entry.template_id
                for item in entries
            ):
                raise TemplateStoreError("Duplicate template identity")
            entries.append(record)
            self._save(entries)

    def list_for_user(self, user_id: str) -> list[dict]:
        with self._lock:
            entries = self._load()
        return [
            entry
            for entry in entries
            if self._owns(entry) and entry["user_id"] == user_id
        ]

    def get(self, template_id: str, user_id: str) -> dict | None:
        with self._lock:
            entries = self._load()
        for entry in entries:
            if (
                self._owns(entry)
                and entry["template_id"] == template_id
                and entry["user_id"] == user_id
            ):
                return entry
        return None

    def delete(self, template_id: str, user_id: str) -> bool:
        with self._lock:
            entries = self._load()
            remaining = [
                entry
                for entry in entries
                if not (
                    self._owns(entry)
                    and entry["template_id"] == template_id
                    and entry["user_id"] == user_id
                )
            ]
            if len(remaining) == len(entries):
                return False
            self._save(remaining)
        return True

    def increment_use_count(self, template_id: str, user_id: str) -> None:
        with self._lock:
            entries = self._load()
            for entry in entries:
                if (
                    self._owns(entry)
                    and entry["template_id"] == template_id
                    and entry["user_id"] == user_id
                ):
                    entry["use_count"] += 1
                    entry["updated_at"] = _now_iso()
                    self._save(entries)
                    return
