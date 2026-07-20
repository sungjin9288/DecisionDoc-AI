"""Tenant-scoped user feedback storage."""

from __future__ import annotations

import json
import math
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_backend_identity, state_lock
from app.tenant import require_tenant_id


class FeedbackStoreError(RuntimeError):
    """Raised when persisted feedback state cannot be trusted."""


_feedback_stores: dict[tuple[Any, ...], "FeedbackStore"] = {}
_feedback_stores_guard = threading.Lock()
_MAX_APPEND_ATTEMPTS = 32
_FEEDBACK_CONTENT_TYPE = "application/x-ndjson; charset=utf-8"


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FeedbackStoreError(f"Duplicate key in feedback state: {key!r}")
        result[key] = value
    return result


class FeedbackStore:
    """Read and append feedback for one tenant."""

    _RECORD_FIELDS = {
        "feedback_id",
        "tenant_id",
        "timestamp",
        "bundle_id",
        "bundle_type",
        "rating",
        "comment",
        "docs",
        "request_id",
        "title",
    }
    _INPUT_FIELDS = _RECORD_FIELDS - {"feedback_id", "timestamp"}
    _REQUIRED_FIELDS = {"feedback_id", "timestamp", "bundle_type", "rating"}

    def __init__(
        self,
        data_dir: Path,
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir)
        self._relative_path = str(Path("tenants") / self._tenant_id / "feedback.jsonl")
        self._path = self._data_dir / self._relative_path
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = state_lock(
            self._backend,
            data_dir=self._data_dir,
            relative_path=self._relative_path,
        )

    @staticmethod
    def _string(value: object, *, field_name: str, allow_empty: bool = False) -> str:
        if not isinstance(value, str):
            raise FeedbackStoreError(f"Invalid feedback {field_name}")
        if not allow_empty and not value:
            raise FeedbackStoreError(f"Invalid feedback {field_name}")
        if value != value.strip() or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise FeedbackStoreError(f"Invalid feedback {field_name}")
        return value

    def _owns(self, record: object) -> bool:
        return isinstance(record, dict) and record.get("tenant_id") in {
            None,
            self._tenant_id,
        }

    def _validate_docs(self, value: object) -> None:
        if not isinstance(value, list):
            raise FeedbackStoreError("Invalid feedback documents")
        for document in value:
            if not isinstance(document, dict):
                raise FeedbackStoreError("Invalid feedback document")
            doc_type = document.get("doc_type")
            markdown = document.get("markdown")
            if not isinstance(doc_type, str) or not doc_type:
                raise FeedbackStoreError("Invalid feedback document type")
            if not isinstance(markdown, str):
                raise FeedbackStoreError("Invalid feedback document markdown")

    def _validate_owned(self, record: dict[str, Any], *, legacy: bool) -> None:
        expected_fields = self._RECORD_FIELDS - ({"tenant_id"} if legacy else set())
        if not self._REQUIRED_FIELDS.issubset(record) or not set(record).issubset(
            expected_fields
        ):
            raise FeedbackStoreError("Invalid feedback record fields")

        self._string(record.get("feedback_id"), field_name="identity")
        self._string(record.get("bundle_type"), field_name="bundle type")
        if not legacy and record.get("tenant_id") != self._tenant_id:
            raise FeedbackStoreError("Feedback tenant ownership mismatch")

        rating = record.get("rating")
        if (
            isinstance(rating, bool)
            or not isinstance(rating, int)
            or not 1 <= rating <= 5
        ):
            raise FeedbackStoreError("Invalid feedback rating")
        timestamp = record.get("timestamp")
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not math.isfinite(timestamp)
            or timestamp < 0
        ):
            raise FeedbackStoreError("Invalid feedback timestamp")

        for field_name in ("bundle_id", "request_id"):
            if field_name in record:
                self._string(
                    record[field_name],
                    field_name=field_name.replace("_", " "),
                    allow_empty=True,
                )
        for field_name in ("comment", "title"):
            if field_name in record:
                if not isinstance(record[field_name], str):
                    raise FeedbackStoreError(f"Invalid feedback {field_name}")
        if "docs" in record:
            self._validate_docs(record["docs"])

    def _decode_state(self, raw: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        owned_feedback_ids: set[str] = set()
        for line_number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                raise FeedbackStoreError(
                    f"Invalid blank line in feedback state at line {line_number}"
                )
            try:
                record = json.loads(line, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError, FeedbackStoreError) as exc:
                raise FeedbackStoreError(
                    f"Invalid feedback state document at line {line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise FeedbackStoreError(
                    f"Invalid feedback record at line {line_number}"
                )

            stored_tenant_id = record.get("tenant_id")
            if stored_tenant_id is not None:
                if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                    raise FeedbackStoreError("Invalid feedback tenant identity")
                if stored_tenant_id != self._tenant_id:
                    records.append(record)
                    continue
            self._validate_owned(record, legacy=stored_tenant_id is None)
            feedback_id = record["feedback_id"]
            if feedback_id in owned_feedback_ids:
                raise FeedbackStoreError(f"Duplicate feedback identity: {feedback_id}")
            owned_feedback_ids.add(feedback_id)
            records.append(record)
        return records

    def _read_state(self) -> tuple[str | None, list[dict[str, Any]]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise FeedbackStoreError("Feedback state could not be read") from exc
        if raw is None or raw == "":
            return raw, []
        return raw, self._decode_state(raw)

    def _load(self) -> list[dict[str, Any]]:
        return self._read_state()[1]

    def _append_if_current(
        self,
        *,
        expected: str | None,
        replacement: str,
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> bool:
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=replacement,
                decode=self._decode_state,
                committed=committed,
                decode_errors=(FeedbackStoreError,),
                content_type=_FEEDBACK_CONTENT_TYPE,
            )
        except StateBackendError as exc:
            raise FeedbackStoreError("Feedback state could not be written") from exc

    def _validated_input(self, feedback: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(feedback, dict) or not set(feedback).issubset(
            self._INPUT_FIELDS
        ):
            raise ValueError("Invalid feedback fields")
        supplied_tenant_id = feedback.get("tenant_id")
        if supplied_tenant_id is not None and supplied_tenant_id != self._tenant_id:
            raise ValueError("Feedback tenant does not match store tenant")

        record = {
            **feedback,
            "feedback_id": str(uuid.uuid4()),
            "tenant_id": self._tenant_id,
            "timestamp": time.time(),
        }
        try:
            self._validate_owned(record, legacy=False)
        except FeedbackStoreError as exc:
            raise ValueError(str(exc)) from exc
        return record

    def save(self, feedback: dict[str, Any]) -> str:
        """Append one validated feedback record with worker-safe CAS."""
        record = self._validated_input(feedback)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"

        def was_committed(records: list[dict[str, Any]]) -> bool:
            return any(self._owns(item) and item == record for item in records)

        with self._lock:
            for _ in range(_MAX_APPEND_ATTEMPTS):
                raw, records = self._read_state()
                if any(
                    self._owns(item)
                    and item.get("feedback_id") == record["feedback_id"]
                    for item in records
                ):
                    raise FeedbackStoreError("Duplicate feedback identity")
                current = raw or ""
                separator = "" if not current or current.endswith("\n") else "\n"
                replacement = f"{current}{separator}{line}"
                if self._append_if_current(
                    expected=raw,
                    replacement=replacement,
                    committed=was_committed,
                ):
                    return record["feedback_id"]

        raise FeedbackStoreError(
            "Feedback state changed too many times to append safely"
        )

    def save_feedback(self, feedback: dict[str, Any]) -> str:
        """Save feedback while supplying an empty document list when omitted."""
        enriched = dict(feedback)
        enriched.setdefault("docs", [])
        return self.save(enriched)

    def get_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [record for record in self._load() if self._owns(record)]

    def get_low_rated(
        self,
        bundle_type: str,
        max_rating: int = 2,
    ) -> list[dict[str, Any]]:
        with self._lock:
            records = self._load()
        return [
            record
            for record in records
            if self._owns(record)
            and record["bundle_type"] == bundle_type
            and record["rating"] <= max_rating
        ]

    def get_high_rated_examples(
        self,
        bundle_type: str,
        min_rating: int = 4,
        limit: int = 2,
        doc_content_limit: int = 800,
    ) -> list[dict[str, Any]]:
        """Return recent high-rated examples in prompt-ready form."""
        with self._lock:
            records = self._load()

        selected = [
            record
            for record in reversed(records)
            if self._owns(record)
            and record["bundle_type"] == bundle_type
            and record["rating"] >= min_rating
        ][:limit]

        results: list[dict[str, Any]] = []
        for record in selected:
            documents: dict[str, Any] = {}
            for document in record.get("docs", []):
                doc_type = document["doc_type"]
                markdown = document["markdown"]
                heading = doc_type
                for line in markdown.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("## ") or stripped.startswith("# "):
                        heading = stripped.lstrip("#").strip()
                        break
                documents[doc_type] = {
                    "heading": heading,
                    "content": markdown[:doc_content_limit].strip(),
                }
            results.append(
                {
                    "rating": record["rating"],
                    "comment": record.get("comment", ""),
                    "title": record.get("title", ""),
                    "bundle_id": record.get("bundle_id", record["bundle_type"]),
                    "timestamp": record["timestamp"],
                    "docs": documents,
                }
            )
        return results


def get_feedback_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> FeedbackStore:
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
    with _feedback_stores_guard:
        store = _feedback_stores.get(key)
        if store is None:
            store = FeedbackStore(
                root,
                tenant_id=tenant_id,
                backend=selected_backend,
            )
            _feedback_stores[key] = store
        return store


def clear_feedback_store_cache() -> None:
    with _feedback_stores_guard:
        _feedback_stores.clear()
