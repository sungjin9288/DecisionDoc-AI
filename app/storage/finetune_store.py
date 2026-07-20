"""Tenant-scoped fine-tune dataset and export storage."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_backend_identity, state_lock
from app.tenant import require_tenant_id


class FineTuneStoreError(RuntimeError):
    """Raised when persisted fine-tune state cannot be trusted."""


@dataclass(frozen=True)
class FineTuneExport:
    filename: str
    record_count: int
    sha256: str
    size_bytes: int


_finetune_stores: dict[tuple[Any, ...], "FineTuneStore"] = {}
_finetune_stores_guard = threading.Lock()
_EXPORT_FILENAME = re.compile(
    r"^export(?:_[A-Za-z0-9_-]+)?_\d{8}T\d{6}(?:\d{6})?Z?\.jsonl$"
)
_SOURCE_VALUES = frozenset({"high_rating", "high_eval_score", "ab_test_winner"})
_MESSAGE_ROLES = frozenset({"system", "user", "assistant"})
_APPEND_ID_FIELD = "_append_id"
_MAX_MUTATION_ATTEMPTS = 32
_DATASET_CONTENT_TYPE = "application/x-ndjson; charset=utf-8"
_MutationResult = TypeVar("_MutationResult")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FineTuneStoreError(f"Duplicate key in fine-tune state: {key!r}")
        result[key] = value
    return result


def _utc_timestamp(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise FineTuneStoreError(f"Invalid fine-tune {field_name}")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FineTuneStoreError(f"Invalid fine-tune {field_name}") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(
        timestamp
    ):
        raise FineTuneStoreError(f"Invalid fine-tune {field_name}")
    return value


class FineTuneStore:
    """Read, collect, and export fine-tune examples for one tenant."""

    _RECORD_FIELDS = {"messages", "metadata"}
    _PRIVATE_RECORD_FIELDS = {_APPEND_ID_FIELD}
    _METADATA_FIELDS = {
        "bundle_id",
        "request_id",
        "heuristic_score",
        "llm_score",
        "user_rating",
        "collected_at",
        "source",
        "tenant_id",
    }
    _INPUT_METADATA_FIELDS = _METADATA_FIELDS - {"collected_at"}
    _REQUIRED_METADATA_FIELDS = {
        "bundle_id",
        "request_id",
        "heuristic_score",
        "collected_at",
        "source",
    }
    _META_FIELDS = {"export_count", "exports", "tenant_id"}
    _EXPORT_FIELDS = {
        "filename",
        "bundle_id",
        "record_count",
        "exported_at",
        "sha256",
        "size_bytes",
    }
    _LEGACY_EXPORT_FIELDS = _EXPORT_FIELDS - {"sha256", "size_bytes"}

    def __init__(
        self,
        data_dir: Path,
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        self._tenant_id = require_tenant_id(tenant_id)
        self._data_dir = Path(data_dir)
        self._relative_dir = str(Path("tenants") / self._tenant_id / "finetune")
        self._dataset_relative_path = f"{self._relative_dir}/dataset.jsonl"
        self._meta_relative_path = f"{self._relative_dir}/metadata.json"
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = state_lock(
            self._backend,
            data_dir=self._data_dir,
            relative_path=f"{self._relative_dir}/authority",
        )

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def backend(self) -> StateBackend:
        return self._backend

    @staticmethod
    def _text(value: object, *, field_name: str) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise FineTuneStoreError(f"Invalid fine-tune {field_name}")
        return value

    @staticmethod
    def _score(
        value: object,
        *,
        field_name: str,
        minimum: float,
        maximum: float,
        allow_none: bool,
    ) -> float | None:
        if value is None and allow_none:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not minimum <= float(value) <= maximum
        ):
            raise FineTuneStoreError(f"Invalid fine-tune {field_name}")
        return float(value)

    def _validate_messages(self, messages: object) -> None:
        if not isinstance(messages, list) or not messages:
            raise FineTuneStoreError("Invalid fine-tune messages")
        for message in messages:
            if not isinstance(message, dict) or set(message) != {"role", "content"}:
                raise FineTuneStoreError("Invalid fine-tune message fields")
            if message.get("role") not in _MESSAGE_ROLES:
                raise FineTuneStoreError("Invalid fine-tune message role")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise FineTuneStoreError("Invalid fine-tune message content")

    def _validate_metadata(self, metadata: dict[str, Any], *, legacy: bool) -> None:
        expected_fields = self._METADATA_FIELDS - ({"tenant_id"} if legacy else set())
        if not self._REQUIRED_METADATA_FIELDS.issubset(metadata) or not set(
            metadata
        ).issubset(expected_fields):
            raise FineTuneStoreError("Invalid fine-tune metadata fields")

        self._text(metadata.get("request_id"), field_name="request identity")
        self._text(metadata.get("bundle_id"), field_name="bundle identity")
        self._score(
            metadata.get("heuristic_score"),
            field_name="heuristic score",
            minimum=0.0,
            maximum=1.0,
            allow_none=False,
        )
        if "llm_score" in metadata:
            self._score(
                metadata.get("llm_score"),
                field_name="LLM score",
                minimum=0.0,
                maximum=5.0,
                allow_none=True,
            )
        if "user_rating" in metadata:
            rating = metadata.get("user_rating")
            if rating is not None and (
                isinstance(rating, bool)
                or not isinstance(rating, int)
                or not 1 <= rating <= 5
            ):
                raise FineTuneStoreError("Invalid fine-tune user rating")
        if metadata.get("source") not in _SOURCE_VALUES:
            raise FineTuneStoreError("Invalid fine-tune source")
        _utc_timestamp(metadata.get("collected_at"), field_name="collection timestamp")
        if not legacy and metadata.get("tenant_id") != self._tenant_id:
            raise FineTuneStoreError("Fine-tune record tenant ownership mismatch")

    def _validate_owned_record(self, record: dict[str, Any], *, legacy: bool) -> None:
        if not self._RECORD_FIELDS.issubset(record) or not set(record).issubset(
            self._RECORD_FIELDS | self._PRIVATE_RECORD_FIELDS
        ):
            raise FineTuneStoreError("Invalid fine-tune record fields")
        self._validate_messages(record.get("messages"))
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            raise FineTuneStoreError("Invalid fine-tune metadata")
        self._validate_metadata(metadata, legacy=legacy)
        append_id = record.get(_APPEND_ID_FIELD)
        if append_id is not None:
            self._text(append_id, field_name="append identity")

    def _owns(self, record: object) -> bool:
        if not isinstance(record, dict) or not isinstance(record.get("metadata"), dict):
            return False
        return record["metadata"].get("tenant_id") in {None, self._tenant_id}

    def _decode_records(self, raw: str) -> list[dict[str, Any]]:
        if raw == "":
            return []

        records: list[dict[str, Any]] = []
        for line_number, line in enumerate(raw.splitlines(), 1):
            if not line.strip():
                raise FineTuneStoreError(
                    f"Invalid blank line in fine-tune state at line {line_number}"
                )
            try:
                record = json.loads(line, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError, FineTuneStoreError) as exc:
                raise FineTuneStoreError(
                    f"Invalid fine-tune state document at line {line_number}"
                ) from exc
            if not isinstance(record, dict) or not isinstance(
                record.get("metadata"), dict
            ):
                raise FineTuneStoreError(
                    f"Invalid fine-tune record at line {line_number}"
                )

            stored_tenant_id = record["metadata"].get("tenant_id")
            if stored_tenant_id is not None:
                if not isinstance(stored_tenant_id, str) or not stored_tenant_id:
                    raise FineTuneStoreError("Invalid fine-tune tenant identity")
                if stored_tenant_id != self._tenant_id:
                    records.append(record)
                    continue
            self._validate_owned_record(record, legacy=stored_tenant_id is None)
            records.append(record)

        request_ids = [
            record["metadata"]["request_id"] for record in records if self._owns(record)
        ]
        if len(request_ids) != len(set(request_ids)):
            raise FineTuneStoreError("Duplicate request identity in fine-tune state")
        append_ids = [
            record[_APPEND_ID_FIELD]
            for record in records
            if self._owns(record) and _APPEND_ID_FIELD in record
        ]
        if len(append_ids) != len(set(append_ids)):
            raise FineTuneStoreError("Duplicate append identity in fine-tune state")
        return records

    def _read_record_state(self) -> tuple[str | None, list[dict[str, Any]]]:
        try:
            raw = self._backend.read_text(self._dataset_relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise FineTuneStoreError("Fine-tune dataset could not be read") from exc
        if raw is None:
            return None, []
        return raw, self._decode_records(raw)

    def _load_records(self) -> list[dict[str, Any]]:
        return self._read_record_state()[1]

    @staticmethod
    def _serialize_records(records: list[dict[str, Any]]) -> str:
        return "".join(
            f"{json.dumps(record, ensure_ascii=False, separators=(',', ':'))}\n"
            for record in records
        )

    def _persist_records_if_current(
        self,
        *,
        expected: str | None,
        replacement: str,
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> bool:
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._dataset_relative_path,
                expected=expected,
                replacement=replacement,
                decode=self._decode_records,
                committed=committed,
                decode_errors=(FineTuneStoreError,),
                content_type=_DATASET_CONTENT_TYPE,
            )
        except StateBackendError as exc:
            raise FineTuneStoreError("Fine-tune dataset could not be written") from exc

    def _mutate_records(
        self,
        change: Callable[
            [str | None, list[dict[str, Any]]],
            tuple[_MutationResult, str | None],
        ],
        *,
        committed: Callable[[list[dict[str, Any]]], bool],
    ) -> _MutationResult:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, records = self._read_record_state()
            result, replacement = change(expected, records)
            if replacement is None:
                return result
            if self._persist_records_if_current(
                expected=expected,
                replacement=replacement,
                committed=committed,
            ):
                return result
        raise FineTuneStoreError(
            "Fine-tune dataset changed too many times to persist safely"
        )

    @staticmethod
    def _public_record(record: dict[str, Any]) -> dict[str, Any]:
        public = dict(record)
        public.pop(_APPEND_ID_FIELD, None)
        return public

    @staticmethod
    def _append_identity(record: dict[str, Any]) -> str:
        append_id = record.get(_APPEND_ID_FIELD)
        if isinstance(append_id, str) and append_id:
            return append_id
        canonical = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"legacy:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

    def _validate_export_entry(self, entry: object) -> None:
        if not isinstance(entry, dict) or set(entry) not in (
            self._EXPORT_FIELDS,
            self._LEGACY_EXPORT_FIELDS,
        ):
            raise FineTuneStoreError("Invalid fine-tune export metadata fields")
        filename = entry.get("filename")
        if (
            not isinstance(filename, str)
            or _EXPORT_FILENAME.fullmatch(filename) is None
        ):
            raise FineTuneStoreError("Invalid fine-tune export filename")
        bundle_id = entry.get("bundle_id")
        if bundle_id is not None:
            self._text(bundle_id, field_name="export bundle identity")
        record_count = entry.get("record_count")
        if (
            isinstance(record_count, bool)
            or not isinstance(record_count, int)
            or record_count < 1
        ):
            raise FineTuneStoreError("Invalid fine-tune export record count")
        _utc_timestamp(entry.get("exported_at"), field_name="export timestamp")
        if "sha256" in entry:
            digest = entry.get("sha256")
            size_bytes = entry.get("size_bytes")
            if (
                not isinstance(digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or isinstance(size_bytes, bool)
                or not isinstance(size_bytes, int)
                or size_bytes <= 0
            ):
                raise FineTuneStoreError("Invalid fine-tune export integrity metadata")

    def _empty_meta(self) -> dict[str, Any]:
        return {"export_count": 0, "exports": [], "tenant_id": self._tenant_id}

    def _decode_meta(self, raw: str) -> dict[str, Any]:
        try:
            meta = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, FineTuneStoreError) as exc:
            raise FineTuneStoreError("Invalid fine-tune metadata document") from exc
        if not isinstance(meta, dict) or not set(meta).issubset(self._META_FIELDS):
            raise FineTuneStoreError("Invalid fine-tune metadata fields")
        if meta.get("tenant_id") not in {None, self._tenant_id}:
            raise FineTuneStoreError("Fine-tune metadata tenant ownership mismatch")
        export_count = meta.get("export_count")
        exports = meta.get("exports")
        if (
            isinstance(export_count, bool)
            or not isinstance(export_count, int)
            or export_count < 0
            or not isinstance(exports, list)
            or export_count != len(exports)
        ):
            raise FineTuneStoreError("Invalid fine-tune export history")
        for entry in exports:
            self._validate_export_entry(entry)
        filenames = [entry["filename"] for entry in exports]
        if len(filenames) != len(set(filenames)):
            raise FineTuneStoreError("Duplicate fine-tune export filename")
        return {**meta, "tenant_id": self._tenant_id}

    def _read_meta_state(self) -> tuple[str | None, dict[str, Any]]:
        try:
            raw = self._backend.read_text(self._meta_relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise FineTuneStoreError("Fine-tune metadata could not be read") from exc
        if raw is None:
            return None, self._empty_meta()
        return raw, self._decode_meta(raw)

    def _load_meta(self) -> dict[str, Any]:
        return self._read_meta_state()[1]

    def _serialize_meta(self, meta: dict[str, Any]) -> str:
        payload = {**meta, "tenant_id": self._tenant_id}
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _persist_meta_if_current(
        self,
        *,
        expected: str | None,
        meta: dict[str, Any],
        committed: Callable[[dict[str, Any]], bool],
    ) -> bool:
        replacement = self._serialize_meta(meta)
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._meta_relative_path,
                expected=expected,
                replacement=replacement,
                decode=self._decode_meta,
                committed=committed,
                decode_errors=(FineTuneStoreError,),
            )
        except StateBackendError as exc:
            raise FineTuneStoreError("Fine-tune metadata could not be written") from exc

    def _mutate_meta(
        self,
        change: Callable[
            [dict[str, Any]],
            tuple[_MutationResult, bool],
        ],
        *,
        committed: Callable[[dict[str, Any]], bool],
    ) -> _MutationResult:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, meta = self._read_meta_state()
            result, changed = change(meta)
            if not changed:
                return result
            if self._persist_meta_if_current(
                expected=expected,
                meta=meta,
                committed=committed,
            ):
                return result
        raise FineTuneStoreError(
            "Fine-tune metadata changed too many times to persist safely"
        )

    def _write_export_once(self, relative_path: str, raw: bytes) -> None:
        try:
            created = self._backend.write_bytes_if_absent(
                relative_path,
                raw,
                content_type="application/x-ndjson",
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_bytes(relative_path)
            except StateBackendError:
                observed = None
            if observed == raw:
                return
            raise FineTuneStoreError("Fine-tune export could not be written") from exc
        if not created:
            raise FineTuneStoreError("Fine-tune export filename is already in use")

    def save_record(
        self,
        messages: list[dict[str, str]],
        metadata: dict[str, Any],
    ) -> bool:
        """Append one validated example, deduplicated by request ID."""
        if not isinstance(metadata, dict) or not set(metadata).issubset(
            self._INPUT_METADATA_FIELDS
        ):
            raise FineTuneStoreError("Invalid fine-tune metadata fields")
        supplied_tenant_id = metadata.get("tenant_id")
        if supplied_tenant_id is not None and supplied_tenant_id != self._tenant_id:
            raise ValueError("Fine-tune record tenant does not match store tenant")

        record = {
            "messages": messages,
            "metadata": {
                **metadata,
                "tenant_id": self._tenant_id,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
            _APPEND_ID_FIELD: uuid.uuid4().hex,
        }
        self._validate_owned_record(record, legacy=False)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        request_id = record["metadata"]["request_id"]

        def apply(
            raw: str | None,
            records: list[dict[str, Any]],
        ) -> tuple[bool, str | None]:
            if any(
                self._owns(existing)
                and existing["metadata"]["request_id"] == request_id
                for existing in records
            ):
                return False, None
            current = raw or ""
            separator = "" if not current or current.endswith("\n") else "\n"
            return True, f"{current}{separator}{line}"

        def was_committed(records: list[dict[str, Any]]) -> bool:
            return any(
                self._owns(existing)
                and existing.get(_APPEND_ID_FIELD) == record[_APPEND_ID_FIELD]
                and existing == record
                for existing in records
            )

        with self._lock:
            self._load_meta()
            return self._mutate_records(apply, committed=was_committed)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            meta = self._load_meta()
            records = [record for record in self._load_records() if self._owns(record)]

        per_bundle: dict[str, int] = {}
        scores: list[float] = []
        last_collected: str | None = None
        for record in records:
            metadata = record["metadata"]
            bundle_id = metadata["bundle_id"]
            per_bundle[bundle_id] = per_bundle.get(bundle_id, 0) + 1
            scores.append(float(metadata["heuristic_score"]))
            timestamp = metadata["collected_at"]
            if last_collected is None or timestamp > last_collected:
                last_collected = timestamp

        return {
            "total_records": len(records),
            "per_bundle_count": per_bundle,
            "avg_heuristic": round(sum(scores) / len(scores), 3) if scores else None,
            "last_collected": last_collected,
            "export_count": meta["export_count"],
        }

    def export_for_training(
        self,
        bundle_id: str | None = None,
        min_records: int = 10,
    ) -> FineTuneExport | None:
        """Write a messages-only JSONL snapshot and bind it to export metadata."""
        if bundle_id is not None:
            self._text(bundle_id, field_name="bundle identity")
        if (
            isinstance(min_records, bool)
            or not isinstance(min_records, int)
            or min_records < 1
        ):
            raise FineTuneStoreError("Invalid fine-tune minimum record count")

        with self._lock:
            self._load_meta()
            records = [record for record in self._load_records() if self._owns(record)]
            filtered = [
                record
                for record in records
                if bundle_id is None or record["metadata"]["bundle_id"] == bundle_id
            ]
            if len(filtered) < min_records:
                return None

            safe_bundle = re.sub(r"[^A-Za-z0-9_-]", "_", bundle_id or "")[:80]
            suffix = f"_{safe_bundle}" if safe_bundle else ""
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            filename = f"export{suffix}_{timestamp}.jsonl"
            raw = "".join(
                f"{json.dumps({'messages': record['messages']}, ensure_ascii=False)}\n"
                for record in filtered
            ).encode("utf-8")
            digest = hashlib.sha256(raw).hexdigest()
            relative_path = f"{self._relative_dir}/{filename}"
            self._write_export_once(relative_path, raw)

            entry = {
                "filename": filename,
                "bundle_id": bundle_id,
                "record_count": len(filtered),
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "sha256": digest,
                "size_bytes": len(raw),
            }
            export = FineTuneExport(filename, len(filtered), digest, len(raw))

            def apply(meta: dict[str, Any]) -> tuple[FineTuneExport, bool]:
                existing = next(
                    (item for item in meta["exports"] if item["filename"] == filename),
                    None,
                )
                if existing is not None:
                    if existing != entry:
                        raise FineTuneStoreError(
                            "Fine-tune export filename has conflicting metadata"
                        )
                    return export, False
                meta["exports"].append(entry)
                meta["export_count"] = len(meta["exports"])
                return export, True

            def was_committed(meta: dict[str, Any]) -> bool:
                return any(item == entry for item in meta["exports"])

            return self._mutate_meta(apply, committed=was_committed)

    def _validate_export_content(self, raw: bytes, *, record_count: int) -> None:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FineTuneStoreError("Invalid fine-tune export encoding") from exc
        lines = text.splitlines()
        if len(lines) != record_count or any(not line.strip() for line in lines):
            raise FineTuneStoreError("Fine-tune export record count mismatch")
        for line in lines:
            try:
                item = json.loads(line, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, TypeError, FineTuneStoreError) as exc:
                raise FineTuneStoreError("Invalid fine-tune export document") from exc
            if not isinstance(item, dict) or set(item) != {"messages"}:
                raise FineTuneStoreError("Invalid fine-tune export fields")
            self._validate_messages(item["messages"])

    def get_export_bytes(self, filename: str) -> bytes | None:
        if (
            not isinstance(filename, str)
            or _EXPORT_FILENAME.fullmatch(filename) is None
        ):
            return None
        with self._lock:
            meta = self._load_meta()
            entry = next(
                (item for item in meta["exports"] if item["filename"] == filename),
                None,
            )
            if entry is None:
                return None
            raw = self._backend.read_bytes(f"{self._relative_dir}/{filename}")
            if raw is None:
                return None
            if "sha256" in entry and (
                len(raw) != entry["size_bytes"]
                or hashlib.sha256(raw).hexdigest() != entry["sha256"]
            ):
                raise FineTuneStoreError("Fine-tune export integrity mismatch")
            self._validate_export_content(raw, record_count=entry["record_count"])
            return raw

    def get_export_path(self, filename: str) -> Path | None:
        """Return a verified local export path for legacy local callers."""
        if self._backend.kind != "local" or self.get_export_bytes(filename) is None:
            return None
        root = Path(getattr(self._backend, "root", self._data_dir))
        return root / self._relative_dir / filename

    def get_records(
        self,
        bundle_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if bundle_id is not None:
            self._text(bundle_id, field_name="bundle identity")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 1000
        ):
            raise FineTuneStoreError("Invalid fine-tune record limit")
        with self._lock:
            records = [record for record in self._load_records() if self._owns(record)]
        if bundle_id is not None:
            records = [
                record
                for record in records
                if record["metadata"]["bundle_id"] == bundle_id
            ]
        return [self._public_record(record) for record in records[-limit:]]

    def clear_dataset(self) -> int:
        """Remove owned records while preserving explicit foreign records."""
        target_append_ids: set[str] | None = None

        def apply(
            _raw: str | None,
            records: list[dict[str, Any]],
        ) -> tuple[int, str | None]:
            nonlocal target_append_ids
            if target_append_ids is None:
                target_append_ids = {
                    self._append_identity(record)
                    for record in records
                    if self._owns(record)
                }
            if not target_append_ids:
                return 0, None
            remaining = [
                record
                for record in records
                if not (
                    self._owns(record)
                    and self._append_identity(record) in target_append_ids
                )
            ]
            removed_count = len(records) - len(remaining)
            if removed_count == 0:
                return len(target_append_ids), None
            return len(target_append_ids), self._serialize_records(remaining)

        def was_committed(records: list[dict[str, Any]]) -> bool:
            return bool(target_append_ids) and not any(
                self._owns(record)
                and self._append_identity(record) in target_append_ids
                for record in records
            )

        with self._lock:
            self._load_meta()
            return self._mutate_records(apply, committed=was_committed)


def get_finetune_store(
    tenant_id: str,
    data_dir: str | Path | None = None,
    *,
    backend: StateBackend | None = None,
) -> FineTuneStore:
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
    with _finetune_stores_guard:
        store = _finetune_stores.get(key)
        if store is None:
            store = FineTuneStore(root, tenant_id=tenant_id, backend=selected_backend)
            _finetune_stores[key] = store
        return store


def clear_finetune_store_cache() -> None:
    with _finetune_stores_guard:
        _finetune_stores.clear()


get_finetune_store.cache_clear = clear_finetune_store_cache  # type: ignore[attr-defined]
