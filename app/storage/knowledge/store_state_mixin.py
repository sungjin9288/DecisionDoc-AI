"""Validation and object I/O for project knowledge state."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from app.storage.conditional_state import persist_text_if_current
from app.storage.knowledge.constants import (
    _LEARNING_MODE_DEFAULT,
    _LEARNING_MODE_LABELS,
    _QUALITY_TIER_DEFAULT,
    _QUALITY_TIER_WEIGHTS,
    _REFERENCE_SUCCESS_WEIGHTS,
)
from app.storage.knowledge.normalizers import (
    _extract_report_workflow_id,
    _normalize_learning_mode,
    _normalize_list,
    _normalize_quality_tier,
    _normalize_reference_year,
    _normalize_string,
    _normalize_success_state,
)
from app.storage.state_backend import StateBackendError

_DOC_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_INCARNATION_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_STYLE_OBJECT_NAME_PATTERN = re.compile(r"^style-[0-9a-f]{32}\.json$")
_INDEX_SCHEMA = "knowledge_index.v2"
_INDEX_FIELDS = {"schema_version", "documents", "_mutation_ids"}
_MAX_MUTATION_ATTEMPTS = 32
_MAX_TRACKED_MUTATIONS = 64
_MutationResult = TypeVar("_MutationResult")
_log = logging.getLogger("decisiondoc.knowledge")


class KnowledgeStoreError(RuntimeError):
    """Raised when persisted project knowledge cannot be trusted."""


@dataclass
class _KnowledgeIndexState:
    records: list[dict[str, Any]]
    mutation_ids: list[str]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise KnowledgeStoreError(f"Duplicate key in knowledge state: {key!r}")
        result[key] = value
    return result


class KnowledgeStoreStateMixin:
    """Validate and persist a knowledge index with bound content objects."""

    _REQUIRED_META_FIELDS = {
        "doc_id",
        "filename",
        "text_len",
        "has_style",
        "created_at",
    }
    _OPTIONAL_META_FIELDS = {
        "tenant_id",
        "project_id",
        "tags",
        "learning_mode",
        "quality_tier",
        "applicable_bundles",
        "source_organization",
        "reference_year",
        "success_state",
        "notes",
        "source_bundle_id",
        "source_request_id",
        "source_doc_type",
        "knowledge_scope",
    }
    _BINDING_FIELDS = {
        "text_sha256",
        "text_size_bytes",
        "style_sha256",
        "style_size_bytes",
    }
    _INTERNAL_META_FIELDS = {
        "_incarnation",
        "_text_object",
        "_style_object",
    }
    _SCOPE_FIELDS = {
        "scope_version",
        "project_id",
        "organization",
        "report_workflow_id",
        "bundle_types",
        "topic_tags",
        "source_bundle_id",
        "source_request_id",
        "source_doc_type",
    }
    _STRING_META_FIELDS = {
        "source_organization",
        "notes",
        "source_bundle_id",
        "source_request_id",
        "source_doc_type",
    }
    _MUTABLE_META_FIELDS = {
        "tags",
        "learning_mode",
        "quality_tier",
        "applicable_bundles",
        "source_organization",
        "reference_year",
        "success_state",
        "notes",
        "source_bundle_id",
        "source_request_id",
        "source_doc_type",
    }

    def _load_index(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._public_meta(self._normalize_meta(item))
                for item in self._owned_records(self._read_index())
            ]

    def _read_index(self) -> list[dict[str, Any]]:
        return self._read_index_state()[1].records

    def _read_index_state(
        self,
        *,
        check_orphans: bool = True,
    ) -> tuple[str | None, _KnowledgeIndexState]:
        raw = self._read_text(self._index_relative_path)
        if raw is None:
            return None, _KnowledgeIndexState(records=[], mutation_ids=[])
        return raw, self._decode_index(raw, check_orphans=check_orphans)

    def _decode_index(
        self,
        raw: str,
        *,
        check_orphans: bool,
    ) -> _KnowledgeIndexState:
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, KnowledgeStoreError) as exc:
            raise KnowledgeStoreError("Invalid knowledge index document") from exc

        if isinstance(data, list):
            records = data
            mutation_ids: list[str] = []
        elif isinstance(data, dict) and set(data) == _INDEX_FIELDS:
            if data.get("schema_version") != _INDEX_SCHEMA:
                raise KnowledgeStoreError("Invalid knowledge index schema")
            records = data.get("documents")
            mutation_ids = self._validate_mutation_ids(data.get("_mutation_ids"))
        else:
            raise KnowledgeStoreError("Invalid knowledge index document")

        if not isinstance(records, list):
            raise KnowledgeStoreError("Knowledge index documents must be a list")
        if not all(isinstance(item, dict) for item in records):
            raise KnowledgeStoreError("Knowledge index contains a non-object record")
        self._validate_index_records(records, check_orphans=check_orphans)
        return _KnowledgeIndexState(records=records, mutation_ids=mutation_ids)

    def _validate_index_records(
        self,
        records: list[dict[str, Any]],
        *,
        check_orphans: bool,
    ) -> None:
        owned_ids: set[str] = set()
        all_ids: list[str] = []
        for item in records:
            if self._safe_doc_id(item.get("doc_id")):
                all_ids.append(item["doc_id"])
            if not self._owns(item):
                continue
            self._validate_owned_meta(item)
            owned_ids.add(item["doc_id"])

        for doc_id in owned_ids:
            if all_ids.count(doc_id) != 1:
                raise KnowledgeStoreError(
                    f"Duplicate knowledge document identity: {doc_id}"
                )

        for item in records:
            if self._owns(item):
                self._validate_owned_content(item)
        if check_orphans:
            self._assert_no_orphan_objects(records)

    @staticmethod
    def _validate_mutation_ids(value: Any) -> list[str]:
        if (
            not isinstance(value, list)
            or len(value) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in value
            )
            or len(value) != len(set(value))
        ):
            raise KnowledgeStoreError("Invalid knowledge index mutation history")
        return list(value)

    def _serialize_index(self, state: _KnowledgeIndexState) -> str:
        self._validate_index_records(state.records, check_orphans=False)
        mutation_ids = self._validate_mutation_ids(state.mutation_ids)
        return self._json_bytes(
            {
                "schema_version": _INDEX_SCHEMA,
                "documents": state.records,
                "_mutation_ids": mutation_ids,
            }
        ).decode("utf-8")

    def _persist_index_if_current(
        self,
        *,
        expected: str | None,
        state: _KnowledgeIndexState,
        mutation_id: str,
    ) -> bool:
        replacement = self._serialize_index(state)
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._index_relative_path,
                expected=expected,
                replacement=replacement,
                decode=lambda raw: self._decode_index(
                    raw,
                    check_orphans=False,
                ),
                committed=lambda observed: mutation_id in observed.mutation_ids,
                decode_errors=(KnowledgeStoreError,),
            )
        except StateBackendError as exc:
            raise KnowledgeStoreError("Knowledge index could not be persisted") from exc

    def _mutate_index(
        self,
        mutation_id: str,
        change: Callable[
            [list[dict[str, Any]]],
            tuple[_MutationResult, bool],
        ],
    ) -> _MutationResult:
        for _attempt in range(_MAX_MUTATION_ATTEMPTS):
            expected, state = self._read_index_state()
            result, changed = change(state.records)
            if not changed:
                return result
            if mutation_id not in state.mutation_ids:
                state.mutation_ids.append(mutation_id)
            state.mutation_ids = state.mutation_ids[-_MAX_TRACKED_MUTATIONS:]
            if self._persist_index_if_current(
                expected=expected,
                state=state,
                mutation_id=mutation_id,
            ):
                return result
        raise KnowledgeStoreError(
            "Knowledge index changed too many times to persist safely"
        )

    def _owns(self, item: dict[str, Any]) -> bool:
        tenant_id = item.get("tenant_id")
        project_id = item.get("project_id")
        if tenant_id is not None and (not isinstance(tenant_id, str) or not tenant_id):
            raise KnowledgeStoreError("Invalid knowledge tenant identity")
        if project_id is not None and (
            not isinstance(project_id, str) or not project_id
        ):
            raise KnowledgeStoreError("Invalid knowledge project identity")
        return tenant_id in (None, self.tenant_id) and project_id in (
            None,
            self.project_id,
        )

    def _owned_records(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [item for item in records if self._owns(item)]

    @staticmethod
    def _safe_doc_id(value: Any) -> bool:
        return isinstance(value, str) and _DOC_ID_PATTERN.fullmatch(value) is not None

    def _find_owned_record(
        self,
        records: list[dict[str, Any]],
        doc_id: str,
    ) -> dict[str, Any] | None:
        if not self._safe_doc_id(doc_id):
            return None
        return next(
            (
                item
                for item in records
                if item.get("doc_id") == doc_id and self._owns(item)
            ),
            None,
        )

    def _replace_with_normalized(self, item: dict[str, Any]) -> None:
        normalized = self._normalize_meta(item)
        item.clear()
        item.update(normalized)

    def _normalize_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        item = dict(meta)
        item["tenant_id"] = self.tenant_id
        item["project_id"] = self.project_id
        item["tags"] = _normalize_list(item.get("tags"))
        item["applicable_bundles"] = _normalize_list(item.get("applicable_bundles"))
        item["source_organization"] = _normalize_string(item.get("source_organization"))
        item["source_bundle_id"] = _normalize_string(item.get("source_bundle_id"))
        item["source_request_id"] = _normalize_string(item.get("source_request_id"))
        item["source_doc_type"] = _normalize_string(item.get("source_doc_type"))
        item["learning_mode"] = _normalize_learning_mode(item.get("learning_mode"))
        item["quality_tier"] = _normalize_quality_tier(item.get("quality_tier"))
        item["reference_year"] = _normalize_reference_year(item.get("reference_year"))
        item["success_state"] = _normalize_success_state(item.get("success_state"))
        item["notes"] = _normalize_string(item.get("notes"))
        item["knowledge_scope"] = self._build_knowledge_scope(item)
        item.update(self._content_bindings(item))
        return item

    def _public_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in meta.items()
            if key not in self._INTERNAL_META_FIELDS
        }

    def _build_knowledge_scope(self, meta: dict[str, Any]) -> dict[str, Any]:
        return {
            "scope_version": "knowledge_scope.v1",
            "project_id": self.project_id,
            "organization": _normalize_string(meta.get("source_organization")),
            "report_workflow_id": _extract_report_workflow_id(
                meta.get("source_request_id"),
                meta.get("source_bundle_id"),
            ),
            "bundle_types": _normalize_list(meta.get("applicable_bundles")),
            "topic_tags": _normalize_list(meta.get("tags")),
            "source_bundle_id": _normalize_string(meta.get("source_bundle_id")),
            "source_request_id": _normalize_string(meta.get("source_request_id")),
            "source_doc_type": _normalize_string(meta.get("source_doc_type")),
        }

    def _validate_owned_meta(self, item: dict[str, Any]) -> None:
        fields = set(item)
        allowed = (
            self._REQUIRED_META_FIELDS
            | self._OPTIONAL_META_FIELDS
            | self._BINDING_FIELDS
            | self._INTERNAL_META_FIELDS
        )
        if not self._REQUIRED_META_FIELDS <= fields or not fields <= allowed:
            raise KnowledgeStoreError("Invalid knowledge metadata fields")
        binding_fields = fields & self._BINDING_FIELDS
        if binding_fields and binding_fields != self._BINDING_FIELDS:
            raise KnowledgeStoreError("Partial knowledge content binding")
        if not self._safe_doc_id(item.get("doc_id")):
            raise KnowledgeStoreError("Invalid knowledge document identity")
        filename = item.get("filename")
        if not isinstance(filename, str) or not filename.strip():
            raise KnowledgeStoreError("Invalid knowledge filename")
        text_len = item.get("text_len")
        if isinstance(text_len, bool) or not isinstance(text_len, int) or text_len < 0:
            raise KnowledgeStoreError("Invalid knowledge text length")
        if not isinstance(item.get("has_style"), bool):
            raise KnowledgeStoreError("Invalid knowledge style state")
        created_at = item.get("created_at")
        if (
            isinstance(created_at, bool)
            or not isinstance(created_at, (int, float))
            or not math.isfinite(created_at)
            or created_at <= 0
        ):
            raise KnowledgeStoreError("Invalid knowledge creation timestamp")

        for field_name in ("tags", "applicable_bundles"):
            if field_name in item:
                self._validate_string_list(item[field_name], field_name)
        if (
            item.get("learning_mode", _LEARNING_MODE_DEFAULT)
            not in _LEARNING_MODE_LABELS
        ):
            raise KnowledgeStoreError("Invalid knowledge learning mode")
        if item.get("quality_tier", _QUALITY_TIER_DEFAULT) not in _QUALITY_TIER_WEIGHTS:
            raise KnowledgeStoreError("Invalid knowledge quality tier")
        if item.get("success_state", "draft") not in _REFERENCE_SUCCESS_WEIGHTS:
            raise KnowledgeStoreError("Invalid knowledge success state")
        for field_name in self._STRING_META_FIELDS:
            if field_name in item and not isinstance(item[field_name], str):
                raise KnowledgeStoreError(f"Invalid knowledge {field_name}")
        reference_year = item.get("reference_year")
        if reference_year is not None and (
            isinstance(reference_year, bool)
            or not isinstance(reference_year, int)
            or not 1900 <= reference_year <= 2100
        ):
            raise KnowledgeStoreError("Invalid knowledge reference year")
        if "knowledge_scope" in item:
            scope = item["knowledge_scope"]
            if not isinstance(scope, dict) or set(scope) != self._SCOPE_FIELDS:
                raise KnowledgeStoreError("Invalid knowledge scope")
            if scope != self._build_knowledge_scope(item):
                raise KnowledgeStoreError("Knowledge scope does not match metadata")
        if binding_fields:
            self._validate_binding_fields(item)
        self._validate_internal_meta(item)

    def _validate_internal_meta(self, item: dict[str, Any]) -> None:
        incarnation = item.get("_incarnation")
        if incarnation is not None and (
            not isinstance(incarnation, str)
            or _INCARNATION_PATTERN.fullmatch(incarnation) is None
        ):
            raise KnowledgeStoreError("Invalid knowledge document incarnation")

        text_object = item.get("_text_object")
        style_object = item.get("_style_object")
        if (
            text_object is not None or style_object is not None
        ) and incarnation is None:
            raise KnowledgeStoreError("Knowledge object binding has no incarnation")
        if text_object is not None:
            expected = f"objects/{item['doc_id']}/{incarnation}/content.txt"
            if text_object != expected:
                raise KnowledgeStoreError("Invalid knowledge text object binding")
        if style_object is not None:
            prefix = f"objects/{item['doc_id']}/{incarnation}/"
            if (
                not isinstance(style_object, str)
                or not style_object.startswith(prefix)
                or _STYLE_OBJECT_NAME_PATTERN.fullmatch(
                    style_object.removeprefix(prefix)
                )
                is None
            ):
                raise KnowledgeStoreError("Invalid knowledge style object binding")
        if not item["has_style"] and style_object is not None:
            raise KnowledgeStoreError("Unexpected knowledge style object binding")

    @staticmethod
    def _validate_string_list(value: Any, field_name: str) -> None:
        if not isinstance(value, list):
            raise KnowledgeStoreError(f"Invalid knowledge {field_name}")
        if any(
            not isinstance(item, str) or not item or item != item.strip()
            for item in value
        ) or len(value) != len(set(value)):
            raise KnowledgeStoreError(f"Invalid knowledge {field_name}")

    def _validate_binding_fields(self, item: dict[str, Any]) -> None:
        text_sha256 = item.get("text_sha256")
        text_size = item.get("text_size_bytes")
        if not isinstance(text_sha256, str) or not _SHA256_PATTERN.fullmatch(
            text_sha256
        ):
            raise KnowledgeStoreError("Invalid knowledge text hash")
        if (
            isinstance(text_size, bool)
            or not isinstance(text_size, int)
            or text_size < 0
        ):
            raise KnowledgeStoreError("Invalid knowledge text size")

        style_sha256 = item.get("style_sha256")
        style_size = item.get("style_size_bytes")
        if item["has_style"]:
            if not isinstance(style_sha256, str) or not _SHA256_PATTERN.fullmatch(
                style_sha256
            ):
                raise KnowledgeStoreError("Invalid knowledge style hash")
            if (
                isinstance(style_size, bool)
                or not isinstance(style_size, int)
                or style_size <= 0
            ):
                raise KnowledgeStoreError("Invalid knowledge style size")
        elif style_sha256 is not None or style_size != 0:
            raise KnowledgeStoreError("Unexpected knowledge style binding")

    def _validate_owned_content(self, item: dict[str, Any]) -> None:
        bindings = self._content_bindings(item)
        if self._BINDING_FIELDS <= set(item):
            for field_name, expected in bindings.items():
                if item.get(field_name) != expected:
                    raise KnowledgeStoreError(
                        f"Knowledge content binding mismatch: {field_name}"
                    )

    def _content_bindings(self, item: dict[str, Any]) -> dict[str, Any]:
        text_raw = self._read_required_bytes(
            self._text_path_for(item),
            "Knowledge document content is missing",
        )
        text = self._decode_text(text_raw, "Knowledge document content is not UTF-8")
        if len(text) != item["text_len"]:
            raise KnowledgeStoreError("Knowledge document text length mismatch")

        style_raw = self._read_bytes(self._style_path_for(item))
        if item["has_style"]:
            if style_raw is None:
                raise KnowledgeStoreError("Knowledge style object is missing")
            self._parse_json_object(style_raw, "Invalid knowledge style object")
            style_sha256: str | None = hashlib.sha256(style_raw).hexdigest()
            style_size = len(style_raw)
        else:
            if style_raw is not None:
                raise KnowledgeStoreError("Unexpected knowledge style object")
            style_sha256 = None
            style_size = 0

        return {
            "text_sha256": hashlib.sha256(text_raw).hexdigest(),
            "text_size_bytes": len(text_raw),
            "style_sha256": style_sha256,
            "style_size_bytes": style_size,
        }

    def _read_document_text(self, meta: dict[str, Any]) -> str:
        bound_meta = self._bound_meta(meta)
        raw = self._read_required_bytes(
            self._text_path_for(bound_meta),
            "Knowledge document content is missing",
        )
        return self._decode_text(raw, "Knowledge document content is not UTF-8")

    def _read_style(self, meta: dict[str, Any]) -> dict[str, Any]:
        if not meta.get("has_style"):
            return {}
        bound_meta = self._bound_meta(meta)
        raw = self._read_required_bytes(
            self._style_path_for(bound_meta),
            "Knowledge style object is missing",
        )
        return self._parse_json_object(raw, "Invalid knowledge style object")

    def _bound_meta(self, meta: dict[str, Any]) -> dict[str, Any]:
        if self._INTERNAL_META_FIELDS & set(meta):
            return meta
        current = self._find_owned_record(
            self._read_index(),
            meta.get("doc_id", ""),
        )
        if current is None:
            raise KnowledgeStoreError("Knowledge document metadata is missing")
        return current

    def _assert_no_orphan_objects(self, records: list[dict[str, Any]]) -> None:
        """Reject unbound legacy objects while versioned objects remain inert."""
        owned_paths = {
            path
            for item in records
            if self._owns(item)
            for path in self._object_paths_for(item)
        }
        foreign_ids = {
            item["doc_id"]
            for item in records
            if self._safe_doc_id(item.get("doc_id")) and not self._owns(item)
        }
        try:
            paths = self._backend.list_prefix(self._relative_dir)
        except StateBackendError as exc:
            raise KnowledgeStoreError("Knowledge objects could not be listed") from exc
        prefix = f"{self._relative_dir}/"
        for relative_path in paths:
            if not relative_path.startswith(prefix):
                continue
            name = relative_path[len(prefix) :]
            if "/" in name or name == "index.json":
                continue
            if name.endswith("_style.json"):
                doc_id = name.removesuffix("_style.json")
            elif name.endswith(".txt"):
                doc_id = name.removesuffix(".txt")
            else:
                continue
            if (
                self._safe_doc_id(doc_id)
                and relative_path not in owned_paths
                and doc_id not in foreign_ids
            ):
                raise KnowledgeStoreError(
                    f"Orphan knowledge content object detected: {name}"
                )

    def _record_identity(self, item: dict[str, Any]) -> str:
        incarnation = item.get("_incarnation")
        if isinstance(incarnation, str) and _INCARNATION_PATTERN.fullmatch(incarnation):
            return incarnation
        text_sha256 = item.get("text_sha256")
        if not isinstance(text_sha256, str):
            text_sha256 = self._content_bindings(item)["text_sha256"]
        seed = self._json_bytes(
            [
                self.tenant_id,
                self.project_id,
                item.get("doc_id"),
                item.get("created_at"),
                text_sha256,
            ]
        )
        return hashlib.sha256(seed).hexdigest()[:32]

    def _new_text_object(self, doc_id: str, incarnation: str) -> str:
        return f"objects/{doc_id}/{incarnation}/content.txt"

    def _new_style_object(
        self,
        doc_id: str,
        incarnation: str,
        mutation_id: str,
    ) -> str:
        return f"objects/{doc_id}/{incarnation}/style-{mutation_id}.json"

    def _object_relative_path(self, object_name: str) -> str:
        return f"{self._relative_dir}/{object_name}"

    def _text_path_for(self, item: dict[str, Any]) -> str:
        object_name = item.get("_text_object")
        if isinstance(object_name, str):
            return self._object_relative_path(object_name)
        return self._text_relative_path(item["doc_id"])

    def _style_path_for(self, item: dict[str, Any]) -> str:
        object_name = item.get("_style_object")
        if isinstance(object_name, str):
            return self._object_relative_path(object_name)
        return self._style_relative_path(item["doc_id"])

    def _object_paths_for(self, item: dict[str, Any]) -> list[str]:
        paths = [self._text_path_for(item)]
        if item.get("has_style"):
            paths.append(self._style_path_for(item))
        return paths

    def _publish_immutable_bytes(
        self,
        relative_path: str,
        raw: bytes,
        *,
        content_type: str,
    ) -> None:
        try:
            created = self._backend.write_bytes_if_absent(
                relative_path,
                raw,
                content_type=content_type,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_bytes(relative_path)
            except StateBackendError:
                observed = None
            if observed == raw:
                return
            raise KnowledgeStoreError(
                "Knowledge artifact could not be published"
            ) from exc
        if created:
            return
        try:
            observed = self._backend.read_bytes(relative_path)
        except StateBackendError as exc:
            raise KnowledgeStoreError(
                "Knowledge artifact could not be verified"
            ) from exc
        if observed != raw:
            raise KnowledgeStoreError("Knowledge artifact identity collision")

    def _cleanup_unreferenced(self, paths: list[str]) -> None:
        if not paths:
            return
        try:
            _, state = self._read_index_state(check_orphans=False)
        except KnowledgeStoreError:
            return
        referenced = {
            path
            for item in self._owned_records(state.records)
            for path in self._object_paths_for(item)
        }
        for relative_path in dict.fromkeys(paths):
            if relative_path in referenced:
                continue
            try:
                self._delete(relative_path)
            except KnowledgeStoreError:
                _log.warning(
                    "[Knowledge] Could not clean unreferenced object path=%s",
                    relative_path,
                )

    @staticmethod
    def _new_doc_id(known_ids: set[Any]) -> str:
        for _attempt in range(10):
            doc_id = uuid.uuid4().hex[:12]
            if doc_id not in known_ids:
                return doc_id
        raise KnowledgeStoreError(
            "Could not allocate a unique knowledge document identity"
        )

    def _text_relative_path(self, doc_id: str) -> str:
        return f"{self._relative_dir}/{doc_id}.txt"

    def _style_relative_path(self, doc_id: str) -> str:
        return f"{self._relative_dir}/{doc_id}_style.json"

    def _read_text(self, relative_path: str) -> str | None:
        try:
            return self._backend.read_text(relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise KnowledgeStoreError("Knowledge state could not be read") from exc

    def _read_bytes(self, relative_path: str) -> bytes | None:
        try:
            return self._backend.read_bytes(relative_path)
        except StateBackendError as exc:
            raise KnowledgeStoreError("Knowledge state could not be read") from exc

    def _read_required_bytes(self, relative_path: str, message: str) -> bytes:
        raw = self._read_bytes(relative_path)
        if raw is None:
            raise KnowledgeStoreError(message)
        return raw

    def _delete(self, relative_path: str) -> None:
        try:
            self._backend.delete(relative_path)
        except StateBackendError as exc:
            raise KnowledgeStoreError("Knowledge state could not be deleted") from exc

    @staticmethod
    def _decode_text(raw: bytes, message: str) -> str:
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise KnowledgeStoreError(message) from exc

    @classmethod
    def _parse_json_object(cls, raw: bytes, message: str) -> dict[str, Any]:
        text = cls._decode_text(raw, message)
        try:
            value = json.loads(text, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, KnowledgeStoreError) as exc:
            raise KnowledgeStoreError(message) from exc
        if not isinstance(value, dict):
            raise KnowledgeStoreError(message)
        return value

    @staticmethod
    def _json_bytes(data: Any, *, caller_input: bool = False) -> bytes:
        try:
            text = json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            if caller_input:
                raise ValueError("Knowledge data must be JSON serializable") from exc
            raise KnowledgeStoreError(
                "Knowledge state could not be serialized"
            ) from exc
        return text.encode("utf-8")
