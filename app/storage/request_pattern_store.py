"""Tenant-scoped request pattern evidence."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.storage.conditional_state import mutate_with_retry, persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


class RequestPatternStoreError(RuntimeError):
    """Raised when persisted request pattern evidence cannot be trusted."""


_MAX_MUTATION_ATTEMPTS = 32


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RequestPatternStoreError(
                f"Duplicate key in request pattern state: {key!r}"
            )
        result[key] = value
    return result


class RequestPatternStore:
    """Read and append bundle request evidence owned by one tenant."""

    _RECORD_FIELDS = {
        "record_id",
        "tenant_id",
        "timestamp",
        "raw_input",
        "bundle_id",
        "matched",
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
            Path("tenants") / self._tenant_id / "request_patterns.jsonl"
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
            raise RequestPatternStoreError(f"Invalid request pattern {field_name}")
        return value

    @staticmethod
    def _timestamp(value: object) -> str:
        if not isinstance(value, str) or not value:
            raise RequestPatternStoreError("Invalid request pattern timestamp")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise RequestPatternStoreError("Invalid request pattern timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise RequestPatternStoreError("Invalid request pattern timestamp")
        return value

    @staticmethod
    def _limit(value: object) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("Request pattern limit must be a positive integer")
        return value

    def _owns(self, record: object) -> bool:
        return isinstance(record, dict) and record.get("tenant_id") in {
            None,
            self._tenant_id,
        }

    def _validate_owned(self, record: dict[str, Any], *, legacy: bool) -> None:
        expected_fields = self._RECORD_FIELDS - ({"tenant_id"} if legacy else set())
        if set(record) != expected_fields:
            raise RequestPatternStoreError("Invalid request pattern record fields")
        if not legacy and record.get("tenant_id") != self._tenant_id:
            raise RequestPatternStoreError("Request pattern tenant ownership mismatch")

        self._identifier(record.get("record_id"), field_name="record identity")
        self._timestamp(record.get("timestamp"))
        raw_input = record.get("raw_input")
        if not isinstance(raw_input, str) or len(raw_input) > 200:
            raise RequestPatternStoreError("Invalid request pattern input")
        bundle_id = record.get("bundle_id")
        if bundle_id is not None:
            self._identifier(bundle_id, field_name="bundle identity")
        if not isinstance(record.get("matched"), bool):
            raise RequestPatternStoreError("Invalid request pattern match state")

    def _load(self) -> tuple[str | None, list[dict[str, Any]]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise RequestPatternStoreError(
                "Request pattern state could not be read"
            ) from exc
        if raw is None or raw == "":
            return raw, []
        return raw, self._decode_state(raw)

    @staticmethod
    def _serialize(records: list[dict[str, Any]]) -> str:
        return "".join(
            f"{json.dumps(record, ensure_ascii=False, separators=(',', ':'))}\n"
            for record in records
        )

    def _persist_if_current(
        self,
        expected: str | None,
        records: list[dict[str, Any]],
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> bool:
        for record in records:
            if self._owns(record):
                self._validate_owned(
                    record,
                    legacy="tenant_id" not in record,
                )
        content = self._serialize(records)
        content_type = "application/x-ndjson; charset=utf-8"
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=content,
                decode=self._decode_state,
                committed=committed,
                decode_errors=(RequestPatternStoreError,),
                content_type=content_type,
            )
        except StateBackendError as exc:
            raise RequestPatternStoreError(
                "Request pattern state could not be written"
            ) from exc

    def _decode_state(
        self,
        raw: str,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        owned_record_ids: set[str] = set()
        for line_number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                raise RequestPatternStoreError(
                    f"Invalid blank line in request pattern state at line {line_number}"
                )
            try:
                record = json.loads(line, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError, RequestPatternStoreError) as exc:
                raise RequestPatternStoreError(
                    f"Invalid request pattern state document at line {line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise RequestPatternStoreError(
                    f"Invalid request pattern record at line {line_number}"
                )

            stored_tenant_id = record.get("tenant_id")
            if stored_tenant_id is not None:
                if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                    raise RequestPatternStoreError(
                        "Invalid request pattern tenant identity"
                    )
                if stored_tenant_id != self._tenant_id:
                    records.append(record)
                    continue

            self._validate_owned(record, legacy=stored_tenant_id is None)
            record_id = record["record_id"]
            if record_id in owned_record_ids:
                raise RequestPatternStoreError(
                    f"Duplicate request pattern record identity: {record_id}"
                )
            owned_record_ids.add(record_id)
            records.append(record)
        return records

    def _mutate(
        self,
        change: Callable[
            [list[dict[str, Any]]],
            tuple[Any, bool],
        ],
        *,
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> Any:
        return mutate_with_retry(
            read=self._load,
            change=change,
            persist=self._persist_if_current,
            committed=committed,
            max_attempts=_MAX_MUTATION_ATTEMPTS,
            conflict_error=lambda: RequestPatternStoreError(
                "Request pattern state changed too many times to persist safely"
            ),
        )

    def record_request(
        self,
        raw_input: str,
        bundle_id: str | None,
        matched: bool,
    ) -> str:
        """Append one validated request record and return its identity."""
        if not isinstance(raw_input, str):
            raise ValueError("Request pattern input must be text")
        if bundle_id is not None:
            try:
                self._identifier(bundle_id, field_name="bundle identity")
            except RequestPatternStoreError as exc:
                raise ValueError(str(exc)) from exc
        if not isinstance(matched, bool):
            raise ValueError("Request pattern match state must be boolean")

        record_id = str(uuid.uuid4())
        record = {
            "record_id": record_id,
            "tenant_id": self._tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "raw_input": raw_input[:200],
            "bundle_id": bundle_id,
            "matched": matched,
        }
        self._validate_owned(record, legacy=False)

        def apply(records: list[dict[str, Any]]) -> tuple[str, bool]:
            if any(
                self._owns(existing)
                and existing.get("record_id") == record_id
                for existing in records
            ):
                return record_id, False
            records.append(record)
            return record_id, True

        def was_committed(records: list[dict[str, Any]]) -> bool:
            return any(
                self._owns(existing)
                and existing.get("record_id") == record_id
                for existing in records
            )

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def get_unmatched(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent unmatched records owned by this tenant."""
        limit = self._limit(limit)
        records = [record for record in self._read_all() if not record["matched"]]
        return records[-limit:]

    def get_all(self, limit: int = 200) -> list[dict[str, Any]]:
        """Return the most recent records owned by this tenant."""
        limit = self._limit(limit)
        return self._read_all()[-limit:]

    def clear_unmatched(self) -> int:
        """Remove owned unmatched records while preserving every foreign record."""
        target_record_ids: set[str] | None = None

        def apply(records: list[dict[str, Any]]) -> tuple[int, bool]:
            nonlocal target_record_ids
            if target_record_ids is None:
                target_record_ids = {
                    record["record_id"]
                    for record in records
                    if self._owns(record) and not record["matched"]
                }
            if not target_record_ids:
                return 0, False

            retained = [
                record
                for record in records
                if not (
                    self._owns(record)
                    and record["record_id"] in target_record_ids
                )
            ]
            removed = len(records) - len(retained)
            if removed == 0:
                return 0, False
            records[:] = retained
            return removed, True

        def was_committed(records: list[dict[str, Any]]) -> bool:
            if not target_record_ids:
                return False
            remaining_owned_ids = {
                record["record_id"]
                for record in records
                if self._owns(record)
            }
            return target_record_ids.isdisjoint(remaining_owned_ids)

        with self._lock:
            return self._mutate(apply, committed=was_committed)

    def _read_all(self) -> list[dict[str, Any]]:
        with self._lock:
            _raw, records = self._load()
            return [record for record in records if self._owns(record)]
