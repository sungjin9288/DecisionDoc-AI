"""Durable, tenant-bound source authority for generation export packets.

The packet itself is intentionally non-persisted.  This store retains only the
short-lived rendered source that an independently running app instance needs to
build and verify a packet.  Immutable content-addressed objects hold source
bytes; a tenant-local CAS index is the only mutable authority.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.storage.state_backend import StateBackend, StateBackendError
from app.tenant import require_tenant_id


SOURCE_SCHEMA_VERSION = "generation_export_source_v1"
INDEX_SCHEMA_VERSION = "generation_export_source_index_v1"
SOURCE_TTL_SECONDS = 60 * 60
MAX_REFERENCED_SOURCES = 500
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_REFERENCED_TENANT_BYTES = 64 * 1024 * 1024
MAX_INDEX_WRITE_ATTEMPTS = 32
_CONTENT_TYPE = "application/json; charset=utf-8"
_TTL_NANOSECONDS = SOURCE_TTL_SECONDS * 1_000_000_000


class GenerationExportSourceStoreError(RuntimeError):
    """Raised when export source state is invalid or unavailable."""


class GenerationExportSourceConflictError(GenerationExportSourceStoreError):
    """Raised when a request identity is reused with different source bytes."""


class GenerationExportSourceUnavailableError(GenerationExportSourceStoreError):
    """Raised when a source cannot be safely read or persisted."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise GenerationExportSourceUnavailableError("duplicate JSON key")
        value[key] = item
    return value


def _reject_nonfinite(value: str) -> None:
    raise GenerationExportSourceUnavailableError(f"invalid JSON number: {value}")


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise GenerationExportSourceUnavailableError("source is not JSON-compatible") from exc


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _valid_request_id(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 200:
        raise ValueError("invalid generation export request ID")
    return value


@dataclass(frozen=True)
class _SourceReference:
    request_id: str
    object_sha256: str
    object_size_bytes: int
    stored_at_unix_ns: int


class GenerationExportSourceStore:
    """Persist bounded export sources using immutable objects and a CAS index."""

    def __init__(
        self,
        *,
        backend: StateBackend,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._backend = backend
        self._clock = clock

    def index_path(self, *, tenant_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        return f"tenants/{tenant_id}/generation_export_sources/index.json"

    def object_path(self, *, tenant_id: str, object_sha256: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        if not self._is_sha256(object_sha256):
            raise ValueError("invalid generation export source digest")
        return f"tenants/{tenant_id}/generation_export_sources/objects/{object_sha256}.json"

    def store(
        self,
        *,
        tenant_id: str,
        request_id: str,
        docs: list[dict[str, Any]],
        title: str,
    ) -> None:
        """Persist one source exactly once, or reject identity/content drift."""
        try:
            tenant_id = require_tenant_id(tenant_id)
            request_id = _valid_request_id(request_id)
            object_raw = self._encode_object(tenant_id=tenant_id, docs=docs, title=title)
        except (TypeError, ValueError, GenerationExportSourceUnavailableError) as exc:
            raise GenerationExportSourceUnavailableError("export source is invalid") from exc

        object_sha256 = _sha256(object_raw)
        object_size_bytes = len(object_raw)
        index_path = self.index_path(tenant_id=tenant_id)
        object_written = False

        for _ in range(MAX_INDEX_WRITE_ATTEMPTS):
            attempt_now_unix_ns = self._now_unix_ns()
            raw_index, references = self._read_index(index_path, tenant_id=tenant_id)
            active_references = self._active_references(
                references, now_unix_ns=attempt_now_unix_ns
            )
            existing = self._reference_for_request(active_references, request_id=request_id)
            if existing is not None:
                existing_raw = self._read_object(tenant_id=tenant_id, reference=existing)
                if existing.object_sha256 == object_sha256 and existing_raw == object_raw:
                    return
                raise GenerationExportSourceConflictError(
                    "generation export request identity already has different source bytes"
                )

            if not object_written:
                self._write_object_if_absent(
                    tenant_id=tenant_id,
                    object_sha256=object_sha256,
                    object_raw=object_raw,
                )
                object_written = True

            candidate = self._bounded_references(
                [
                    *active_references,
                    _SourceReference(
                        request_id=request_id,
                        object_sha256=object_sha256,
                        object_size_bytes=object_size_bytes,
                        stored_at_unix_ns=attempt_now_unix_ns,
                    ),
                ]
            )
            replacement = self._serialize_index(tenant_id=tenant_id, references=candidate)
            try:
                persisted = (
                    self._backend.write_text_if_absent(
                        index_path,
                        replacement,
                        content_type=_CONTENT_TYPE,
                    )
                    if raw_index is None
                    else self._backend.replace_text_if_equal(
                        index_path,
                        expected=raw_index,
                        replacement=replacement,
                        content_type=_CONTENT_TYPE,
                    )
                )
            except StateBackendError as exc:
                if self._reconcile_failed_index_write(
                    index_path=index_path,
                    tenant_id=tenant_id,
                    request_id=request_id,
                    object_sha256=object_sha256,
                    object_raw=object_raw,
                    now_unix_ns=attempt_now_unix_ns,
                ):
                    return
                raise GenerationExportSourceUnavailableError(
                    "export source index could not be persisted"
                ) from exc
            if persisted:
                return

        raise GenerationExportSourceUnavailableError("export source index update conflicted")

    def get(
        self,
        *,
        tenant_id: str,
        request_id: str,
    ) -> tuple[list[dict[str, Any]], str] | None:
        """Return an active tenant source, or None without presence disclosure."""
        try:
            tenant_id = require_tenant_id(tenant_id)
            request_id = _valid_request_id(request_id)
        except (TypeError, ValueError):
            return None

        index_path = self.index_path(tenant_id=tenant_id)
        _, references = self._read_index(index_path, tenant_id=tenant_id)
        reference = self._reference_for_request(
            self._active_references(references, now_unix_ns=self._now_unix_ns()),
            request_id=request_id,
        )
        if reference is None:
            return None
        raw = self._read_object(tenant_id=tenant_id, reference=reference)
        source = self._decode_object(raw, tenant_id=tenant_id)
        return source["docs"], source["title"]

    def _reconcile_failed_index_write(
        self,
        *,
        index_path: str,
        tenant_id: str,
        request_id: str,
        object_sha256: str,
        object_raw: bytes,
        now_unix_ns: int,
    ) -> bool:
        """Accept a lost write response only when read-back proves exact success."""
        try:
            _, references = self._read_index(index_path, tenant_id=tenant_id)
            reference = self._reference_for_request(
                self._active_references(references, now_unix_ns=now_unix_ns),
                request_id=request_id,
            )
            if reference is None or reference.object_sha256 != object_sha256:
                return False
            if self._read_object(tenant_id=tenant_id, reference=reference) == object_raw:
                return True
        except GenerationExportSourceStoreError:
            return False
        return False

    def _write_object_if_absent(
        self,
        *,
        tenant_id: str,
        object_sha256: str,
        object_raw: bytes,
    ) -> None:
        path = self.object_path(tenant_id=tenant_id, object_sha256=object_sha256)
        try:
            created = self._backend.write_bytes_if_absent(
                path,
                object_raw,
                content_type=_CONTENT_TYPE,
            )
        except StateBackendError as exc:
            try:
                existing = self._backend.read_bytes(path)
            except StateBackendError as read_exc:
                raise GenerationExportSourceUnavailableError(
                    "export source object could not be persisted"
                ) from read_exc
            if existing == object_raw:
                return
            raise GenerationExportSourceUnavailableError(
                "export source object could not be persisted"
            ) from exc
        if created:
            return
        try:
            existing = self._backend.read_bytes(path)
        except StateBackendError as exc:
            raise GenerationExportSourceUnavailableError(
                "export source object could not be verified"
            ) from exc
        if existing != object_raw:
            raise GenerationExportSourceUnavailableError("export source object is not immutable")

    def _read_index(
        self,
        index_path: str,
        *,
        tenant_id: str,
    ) -> tuple[str | None, list[_SourceReference]]:
        try:
            raw = self._backend.read_text(index_path)
        except (StateBackendError, UnicodeError) as exc:
            raise GenerationExportSourceUnavailableError(
                "export source index could not be read"
            ) from exc
        if raw is None:
            return None, []
        if not raw:
            raise GenerationExportSourceUnavailableError("export source index is blank")
        try:
            value = json.loads(
                raw,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_nonfinite,
            )
            references = self._decode_index(value, tenant_id=tenant_id)
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
            GenerationExportSourceStoreError,
        ) as exc:
            raise GenerationExportSourceUnavailableError("export source index is invalid") from exc
        return raw, references

    def _read_object(
        self,
        *,
        tenant_id: str,
        reference: _SourceReference,
    ) -> bytes:
        path = self.object_path(tenant_id=tenant_id, object_sha256=reference.object_sha256)
        try:
            raw = self._backend.read_bytes(path)
        except StateBackendError as exc:
            raise GenerationExportSourceUnavailableError(
                "export source object could not be read"
            ) from exc
        if (
            raw is None
            or len(raw) != reference.object_size_bytes
            or _sha256(raw) != reference.object_sha256
        ):
            raise GenerationExportSourceUnavailableError("export source object is unavailable")
        self._decode_object(raw, tenant_id=tenant_id)
        return raw

    def _encode_object(
        self,
        *,
        tenant_id: str,
        docs: list[dict[str, Any]],
        title: str,
    ) -> bytes:
        if not isinstance(title, str) or not title:
            raise ValueError("title must be a non-empty string")
        if not isinstance(docs, list) or not docs or any(not isinstance(doc, dict) for doc in docs):
            raise ValueError("docs must be a non-empty list of objects")
        raw = _canonical_json(
            {
                "docs": docs,
                "schema_version": SOURCE_SCHEMA_VERSION,
                "tenant_id": tenant_id,
                "title": title,
            }
        ).encode("utf-8")
        if len(raw) > MAX_SOURCE_BYTES:
            raise ValueError("source exceeds the maximum size")
        return raw

    def _decode_object(self, raw: bytes, *, tenant_id: str) -> dict[str, Any]:
        if not raw or len(raw) > MAX_SOURCE_BYTES:
            raise GenerationExportSourceUnavailableError("export source object is invalid")
        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_nonfinite,
            )
        except (
            UnicodeDecodeError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            GenerationExportSourceStoreError,
        ) as exc:
            raise GenerationExportSourceUnavailableError("export source object is invalid") from exc
        if (
            not isinstance(value, dict)
            or set(value) != {"docs", "schema_version", "tenant_id", "title"}
            or value.get("schema_version") != SOURCE_SCHEMA_VERSION
            or value.get("tenant_id") != tenant_id
            or not isinstance(value.get("title"), str)
            or not value["title"]
            or not isinstance(value.get("docs"), list)
            or not value["docs"]
            or any(not isinstance(doc, dict) for doc in value["docs"])
        ):
            raise GenerationExportSourceUnavailableError("export source object is invalid")
        if _canonical_json(value).encode("utf-8") != raw:
            raise GenerationExportSourceUnavailableError("export source object is not canonical")
        return value

    def _decode_index(self, value: Any, *, tenant_id: str) -> list[_SourceReference]:
        if (
            not isinstance(value, dict)
            or set(value) != {"schema_version", "sources", "tenant_id"}
            or value.get("schema_version") != INDEX_SCHEMA_VERSION
            or value.get("tenant_id") != tenant_id
            or not isinstance(value.get("sources"), list)
        ):
            raise GenerationExportSourceUnavailableError("export source index is invalid")
        references: list[_SourceReference] = []
        request_ids: set[str] = set()
        for item in value["sources"]:
            if not isinstance(item, dict) or set(item) != {
                "object_sha256",
                "object_size_bytes",
                "request_id",
                "stored_at_unix_ns",
            }:
                raise GenerationExportSourceUnavailableError("export source index is invalid")
            request_id = _valid_request_id(item.get("request_id"))
            size = item.get("object_size_bytes")
            stored_at = item.get("stored_at_unix_ns")
            digest = item.get("object_sha256")
            if (
                request_id in request_ids
                or not self._is_sha256(digest)
                or not isinstance(size, int)
                or isinstance(size, bool)
                or not 0 < size <= MAX_SOURCE_BYTES
                or not isinstance(stored_at, int)
                or isinstance(stored_at, bool)
                or stored_at < 0
            ):
                raise GenerationExportSourceUnavailableError("export source index is invalid")
            request_ids.add(request_id)
            references.append(
                _SourceReference(
                    request_id=request_id,
                    object_sha256=digest,
                    object_size_bytes=size,
                    stored_at_unix_ns=stored_at,
                )
            )
        if len(references) > MAX_REFERENCED_SOURCES:
            raise GenerationExportSourceUnavailableError("export source index exceeds entry limit")
        if sum(item.object_size_bytes for item in references) > MAX_REFERENCED_TENANT_BYTES:
            raise GenerationExportSourceUnavailableError("export source index exceeds byte limit")
        if references != self._ordered_references(references):
            raise GenerationExportSourceUnavailableError("export source index ordering is invalid")
        return references

    def _serialize_index(
        self,
        *,
        tenant_id: str,
        references: list[_SourceReference],
    ) -> str:
        return _canonical_json(
            {
                "schema_version": INDEX_SCHEMA_VERSION,
                "sources": [
                    {
                        "object_sha256": item.object_sha256,
                        "object_size_bytes": item.object_size_bytes,
                        "request_id": item.request_id,
                        "stored_at_unix_ns": item.stored_at_unix_ns,
                    }
                    for item in self._ordered_references(references)
                ],
                "tenant_id": tenant_id,
            }
        )

    def _active_references(
        self,
        references: list[_SourceReference],
        *,
        now_unix_ns: int,
    ) -> list[_SourceReference]:
        deadline = now_unix_ns - _TTL_NANOSECONDS
        return [item for item in references if item.stored_at_unix_ns > deadline]

    @staticmethod
    def _ordered_references(references: list[_SourceReference]) -> list[_SourceReference]:
        return sorted(
            references,
            key=lambda item: (item.stored_at_unix_ns, item.request_id, item.object_sha256),
        )

    def _bounded_references(self, references: list[_SourceReference]) -> list[_SourceReference]:
        bounded = self._ordered_references(references)
        total_bytes = sum(item.object_size_bytes for item in bounded)
        while (
            len(bounded) > MAX_REFERENCED_SOURCES
            or total_bytes > MAX_REFERENCED_TENANT_BYTES
        ):
            evicted = bounded.pop(0)
            total_bytes -= evicted.object_size_bytes
        return bounded

    @staticmethod
    def _reference_for_request(
        references: list[_SourceReference],
        *,
        request_id: str,
    ) -> _SourceReference | None:
        for reference in references:
            if reference.request_id == request_id:
                return reference
        return None

    def _now_unix_ns(self) -> int:
        value = self._clock()
        if not isinstance(value, (float, int)) or isinstance(value, bool) or value < 0:
            raise GenerationExportSourceUnavailableError("export source clock is invalid")
        return int(value * 1_000_000_000)

    @staticmethod
    def _is_sha256(value: Any) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(character in "0123456789abcdef" for character in value)
        )
