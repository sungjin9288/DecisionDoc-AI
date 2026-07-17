"""Tenant-scoped storage for reusable document form templates."""

from __future__ import annotations

import datetime
import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id


_template_locks: dict[Path, threading.RLock] = {}
_template_locks_guard = threading.Lock()
_MAX_MUTATION_ATTEMPTS = 32
_MUTATION_IDS_FIELD = "_mutation_ids"
_INCARNATION_ID_FIELD = "_incarnation_id"
_MAX_TRACKED_MUTATIONS = 64
_MutationResult = TypeVar("_MutationResult")


class TemplateStoreError(RuntimeError):
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
        self._incarnation_id(entry)
        self._mutation_ids(entry)
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

    def _read_state(self) -> tuple[str | None, list[dict[str, Any]]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise TemplateStoreError("Invalid template state document") from exc
        if raw is None:
            return None, []
        return raw, self._decode_entries(raw)

    def _decode_entries(self, raw: str) -> list[dict[str, Any]]:
        if not raw.strip():
            return []

        entries: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line, object_pairs_hook=_unique_object)
                self._validate_record(entry)
            except (
                json.JSONDecodeError,
                TemplateStoreError,
                TypeError,
                ValueError,
            ) as exc:
                raise TemplateStoreError(
                    f"Invalid template state at line {line_number}"
                ) from exc
            entries.append(entry)
        return self._validate_entries(entries)

    def _load(self) -> list[dict[str, Any]]:
        return self._read_state()[1]

    @staticmethod
    def _incarnation_id(record: dict[str, Any]) -> str | None:
        incarnation_id = record.get(_INCARNATION_ID_FIELD)
        if incarnation_id is not None and (
            not isinstance(incarnation_id, str) or not incarnation_id
        ):
            raise TemplateStoreError("Invalid template incarnation")
        return incarnation_id

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
            raise TemplateStoreError("Invalid template mutation history")
        return list(mutation_ids)

    def _record_mutation(
        self,
        record: dict[str, Any],
        *,
        previous: dict[str, Any] | None,
        mutation_id: str,
    ) -> dict[str, Any]:
        mutation_ids = self._mutation_ids(previous or {})
        if mutation_id not in mutation_ids:
            mutation_ids.append(mutation_id)
        persisted = dict(record)
        persisted[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return persisted

    @staticmethod
    def _public_entry(entry: dict[str, Any]) -> dict[str, Any]:
        public_entry = dict(entry)
        public_entry.pop(_MUTATION_IDS_FIELD, None)
        public_entry.pop(_INCARNATION_ID_FIELD, None)
        return public_entry

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        entries: list[dict[str, Any]],
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> bool:
        self._validate_entries(entries)
        payload = "".join(
            f"{json.dumps(entry, ensure_ascii=False)}\n" for entry in entries
        )
        content_type = "application/x-ndjson; charset=utf-8"
        try:
            if expected is None:
                return self._backend.write_text_if_absent(
                    self._relative_path,
                    payload,
                    content_type=content_type,
                )
            return self._backend.replace_text_if_equal(
                self._relative_path,
                expected=expected,
                replacement=payload,
                content_type=content_type,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_text(self._relative_path)
            except (StateBackendError, UnicodeError):
                observed = None
            if observed == payload:
                return True
            if observed is not None:
                try:
                    observed_entries = self._decode_entries(observed)
                except TemplateStoreError:
                    pass
                else:
                    if committed(observed_entries):
                        return True
            raise TemplateStoreError("Failed to persist template state") from exc

    def _mutate(
        self,
        change: Callable[
            [list[dict[str, Any]]],
            tuple[_MutationResult, bool],
        ],
        *,
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> _MutationResult:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, entries = self._read_state()
            result, changed = change(entries)
            if not changed:
                return result
            if self._persist_if_current(
                expected=expected,
                entries=entries,
                committed=committed,
            ):
                return result
        raise TemplateStoreError(
            "Template state changed too many times to persist safely"
        )

    def add(self, entry: TemplateEntry) -> None:
        if entry.tenant_id != self._tenant_id:
            raise ValueError("Template tenant does not match store tenant")
        try:
            record = self._validate_record(asdict(entry))
        except TemplateStoreError as exc:
            raise ValueError(str(exc)) from exc
        mutation_id = uuid.uuid4().hex
        persisted = self._record_mutation(
            record,
            previous=None,
            mutation_id=mutation_id,
        )
        persisted[_INCARNATION_ID_FIELD] = uuid.uuid4().hex

        def apply(entries: list[dict[str, Any]]) -> tuple[None, bool]:
            if any(
                self._owns(item) and item["template_id"] == entry.template_id
                for item in entries
            ):
                raise TemplateStoreError("Duplicate template identity")
            entries.append(persisted)
            return None, True

        def was_committed(entries: list[dict[str, Any]]) -> bool:
            return any(
                self._owns(item)
                and item.get("template_id") == entry.template_id
                and mutation_id in self._mutation_ids(item)
                for item in entries
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)

    def list_for_user(self, user_id: str) -> list[dict]:
        with self._lock:
            entries = self._load()
        return [
            self._public_entry(entry)
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
                return self._public_entry(entry)
        return None

    def delete(self, template_id: str, user_id: str) -> bool:
        target_incarnation: str | None = None
        target_bound = False

        def apply(entries: list[dict[str, Any]]) -> tuple[bool, bool]:
            nonlocal target_bound, target_incarnation
            for index, entry in enumerate(entries):
                if (
                    self._owns(entry)
                    and entry["template_id"] == template_id
                    and entry["user_id"] == user_id
                ):
                    incarnation_id = self._incarnation_id(entry)
                    if not target_bound:
                        target_incarnation = incarnation_id
                        target_bound = True
                    elif incarnation_id != target_incarnation:
                        return False, False
                    entries.pop(index)
                    return True, True
            return False, False

        def was_committed(entries: list[dict[str, Any]]) -> bool:
            return not any(
                self._owns(entry)
                and entry.get("template_id") == template_id
                and entry.get("user_id") == user_id
                and self._incarnation_id(entry) == target_incarnation
                for entry in entries
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def increment_use_count(self, template_id: str, user_id: str) -> None:
        mutation_id = uuid.uuid4().hex
        target_incarnation: str | None = None
        target_bound = False

        def apply(entries: list[dict[str, Any]]) -> tuple[None, bool]:
            nonlocal target_bound, target_incarnation
            for index, entry in enumerate(entries):
                if (
                    self._owns(entry)
                    and entry["template_id"] == template_id
                    and entry["user_id"] == user_id
                ):
                    incarnation_id = self._incarnation_id(entry)
                    if not target_bound:
                        target_incarnation = incarnation_id
                        target_bound = True
                    elif incarnation_id != target_incarnation:
                        return None, False
                    if mutation_id in self._mutation_ids(entry):
                        return None, False
                    updated = dict(entry)
                    updated["use_count"] += 1
                    updated["updated_at"] = _now_iso()
                    entries[index] = self._record_mutation(
                        updated,
                        previous=entry,
                        mutation_id=mutation_id,
                    )
                    return None, True
            return None, False

        def was_committed(entries: list[dict[str, Any]]) -> bool:
            return any(
                self._owns(entry)
                and entry.get("template_id") == template_id
                and entry.get("user_id") == user_id
                and self._incarnation_id(entry) == target_incarnation
                and mutation_id in self._mutation_ids(entry)
                for entry in entries
            )

        with self._lock:
            self._mutate(apply, committed=was_committed)
