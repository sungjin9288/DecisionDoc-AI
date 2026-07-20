"""Tenant- and project-scoped knowledge state storage."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from app.storage.knowledge.constants import (
    MAX_DOCS_PER_PROJECT,
    _LEARNING_MODE_DEFAULT,
    _QUALITY_TIER_DEFAULT,
)
from app.storage.knowledge.entry import KnowledgeEntry
from app.storage.knowledge.normalizers import (
    _normalize_learning_mode,
    _normalize_list,
    _normalize_quality_tier,
    _normalize_reference_year,
    _normalize_string,
    _normalize_success_state,
)
from app.storage.knowledge.store_state_mixin import (
    KnowledgeStoreError,
    KnowledgeStoreStateMixin,
)
from app.storage.knowledge_search import (
    KnowledgeSearchBackend,
    get_knowledge_search_backend,
)
from app.storage.state_backend import StateBackend, get_state_backend
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


_log = logging.getLogger("decisiondoc.knowledge")


def _storage_component(value: str, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
    ):
        raise ValueError(f"Invalid {label}")
    return value


class KnowledgeStoreCoreMixin(KnowledgeStoreStateMixin):
    """Store project knowledge as an index with bound content objects."""

    def __init__(
        self,
        project_id: str,
        data_dir: str | None = None,
        search_backend: KnowledgeSearchBackend | None = None,
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        self.project_id = _storage_component(project_id, "project_id")
        self.tenant_id = require_tenant_id(tenant_id)
        self._search_backend = search_backend or get_knowledge_search_backend()
        self._data_dir = Path(data_dir or os.getenv("DATA_DIR", "data"))
        self._relative_dir = str(
            Path("tenants") / self.tenant_id / "knowledge" / self.project_id
        )
        self._index_relative_path = f"{self._relative_dir}/index.json"
        self._backend = backend or get_state_backend(data_dir=self._data_dir)
        self._lock = state_lock(
            self._backend,
            data_dir=self._data_dir,
            relative_path=self._index_relative_path,
        )

    def add_document(
        self,
        filename: str,
        text: str,
        style_profile: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        learning_mode: str = _LEARNING_MODE_DEFAULT,
        quality_tier: str = _QUALITY_TIER_DEFAULT,
        applicable_bundles: list[str] | None = None,
        source_organization: str = "",
        reference_year: int | None = None,
        success_state: str = "draft",
        notes: str = "",
        source_bundle_id: str = "",
        source_request_id: str = "",
        source_doc_type: str = "",
    ) -> KnowledgeEntry:
        """Add one document and return its tenant-owned entry."""
        if not isinstance(filename, str) or not filename.strip():
            raise ValueError("Knowledge filename must be non-empty text")
        if not isinstance(text, str):
            raise ValueError("Knowledge document content must be text")
        if style_profile is not None and not isinstance(style_profile, dict):
            raise ValueError("Knowledge style profile must be an object")
        if style_profile is not None:
            self._json_bytes(style_profile, caller_input=True)

        with self._lock:
            records = self._read_index()
            known_ids = {
                item.get("doc_id") for item in records if isinstance(item, dict)
            }
            doc_id = self._new_doc_id(known_ids)
            mutation_id = uuid.uuid4().hex
            incarnation = uuid.uuid4().hex
            entry = KnowledgeEntry(
                doc_id=doc_id,
                filename=filename,
                text=text,
                style_profile=style_profile,
                tags=tags,
                learning_mode=learning_mode,
                quality_tier=quality_tier,
                applicable_bundles=applicable_bundles,
                source_organization=source_organization,
                reference_year=reference_year,
                success_state=success_state,
                notes=notes,
                source_bundle_id=source_bundle_id,
                source_request_id=source_request_id,
                source_doc_type=source_doc_type,
                tenant_id=self.tenant_id,
                project_id=self.project_id,
            )
            meta = entry.to_meta()
            meta["_incarnation"] = incarnation
            meta["_text_object"] = self._new_text_object(doc_id, incarnation)
            if entry.style_profile:
                meta["_style_object"] = self._new_style_object(
                    doc_id,
                    incarnation,
                    mutation_id,
                )

            published_paths: list[str] = []
            try:
                text_path = self._text_path_for(meta)
                published_paths.append(text_path)
                self._publish_immutable_bytes(
                    text_path,
                    entry.text.encode("utf-8"),
                    content_type="text/plain; charset=utf-8",
                )
                if entry.style_profile:
                    style_path = self._style_path_for(meta)
                    published_paths.append(style_path)
                    self._publish_immutable_bytes(
                        style_path,
                        self._json_bytes(entry.style_profile),
                        content_type="application/json; charset=utf-8",
                    )

                def append_entry(
                    current: list[dict[str, Any]],
                ) -> tuple[tuple[KnowledgeEntry, list[str]], bool]:
                    if any(item.get("doc_id") == doc_id for item in current):
                        raise KnowledgeStoreError(
                            "Duplicate knowledge document identity"
                        )
                    retired_paths: list[str] = []
                    owned = self._owned_records(current)
                    if len(owned) >= MAX_DOCS_PER_PROJECT:
                        evicted = min(owned, key=lambda item: item["created_at"])
                        retired_paths.extend(self._object_paths_for(evicted))
                        current.remove(evicted)
                    normalized = self._normalize_meta(meta)
                    entry.knowledge_scope = dict(normalized["knowledge_scope"])
                    current.append(normalized)
                    return (entry, retired_paths), True

                saved_entry, retired_paths = self._mutate_index(
                    mutation_id,
                    append_entry,
                )
            except Exception:
                self._cleanup_unreferenced(published_paths)
                raise
            self._cleanup_unreferenced(retired_paths)

        _log.info(
            "[Knowledge] Added doc=%s file=%s project=%s",
            doc_id,
            filename,
            self.project_id,
        )
        return saved_entry

    def update_style(self, doc_id: str, style_profile: dict[str, Any]) -> bool:
        """Replace one document style while preserving index consistency."""
        if not isinstance(style_profile, dict):
            raise ValueError("Knowledge style profile must be an object")
        style_raw = self._json_bytes(style_profile, caller_input=True)

        with self._lock:
            records = self._read_index()
            item = self._find_owned_record(records, doc_id)
            if item is None:
                return False
            if item.get("has_style") and self._read_style(item) == style_profile:
                return True

            target_identity = self._record_identity(item)
            mutation_id = uuid.uuid4().hex
            style_object = self._new_style_object(
                doc_id,
                target_identity,
                mutation_id,
            )
            style_path = self._object_relative_path(style_object)

            def replace_style(
                current: list[dict[str, Any]],
            ) -> tuple[tuple[bool, list[str]], bool]:
                current_item = self._find_owned_record(current, doc_id)
                if current_item is None:
                    return (False, []), False
                if self._record_identity(current_item) != target_identity:
                    raise KnowledgeStoreError(
                        "Knowledge document identity changed during style update"
                    )
                retired_paths = (
                    [self._style_path_for(current_item)]
                    if current_item.get("has_style")
                    else []
                )
                current_item["_incarnation"] = target_identity
                current_item["_style_object"] = style_object
                current_item["has_style"] = True
                self._replace_with_normalized(current_item)
                return (True, retired_paths), True

            try:
                self._publish_immutable_bytes(
                    style_path,
                    style_raw,
                    content_type="application/json; charset=utf-8",
                )
                updated, retired_paths = self._mutate_index(
                    mutation_id,
                    replace_style,
                )
            except Exception:
                self._cleanup_unreferenced([style_path])
                raise
            if not updated:
                self._cleanup_unreferenced([style_path])
                return False
            self._cleanup_unreferenced(retired_paths)
            return updated

    def update_metadata(self, doc_id: str, **fields: Any) -> bool:
        """Update supported learning metadata for one document."""
        unknown_fields = set(fields) - self._MUTABLE_META_FIELDS
        if unknown_fields:
            names = ", ".join(sorted(unknown_fields))
            raise ValueError(f"Unknown knowledge metadata fields: {names}")

        with self._lock:
            records = self._read_index()
            item = self._find_owned_record(records, doc_id)
            if item is None:
                return False
            target_identity = self._record_identity(item)
            mutation_id = uuid.uuid4().hex

            def update(
                current: list[dict[str, Any]],
            ) -> tuple[bool, bool]:
                current_item = self._find_owned_record(current, doc_id)
                if current_item is None:
                    return False, False
                if self._record_identity(current_item) != target_identity:
                    raise KnowledgeStoreError(
                        "Knowledge document identity changed during metadata update"
                    )
                previous = dict(current_item)
                current_item["_incarnation"] = target_identity
                if "tags" in fields and fields["tags"] is not None:
                    current_item["tags"] = _normalize_list(fields["tags"])
                if "learning_mode" in fields and fields["learning_mode"] is not None:
                    current_item["learning_mode"] = _normalize_learning_mode(
                        fields["learning_mode"]
                    )
                if "quality_tier" in fields and fields["quality_tier"] is not None:
                    current_item["quality_tier"] = _normalize_quality_tier(
                        fields["quality_tier"]
                    )
                if (
                    "applicable_bundles" in fields
                    and fields["applicable_bundles"] is not None
                ):
                    current_item["applicable_bundles"] = _normalize_list(
                        fields["applicable_bundles"]
                    )
                if (
                    "source_organization" in fields
                    and fields["source_organization"] is not None
                ):
                    current_item["source_organization"] = _normalize_string(
                        fields["source_organization"]
                    )
                if "reference_year" in fields:
                    current_item["reference_year"] = _normalize_reference_year(
                        fields["reference_year"]
                    )
                if "success_state" in fields and fields["success_state"] is not None:
                    current_item["success_state"] = _normalize_success_state(
                        fields["success_state"]
                    )
                if "notes" in fields and fields["notes"] is not None:
                    current_item["notes"] = _normalize_string(fields["notes"])
                if (
                    "source_bundle_id" in fields
                    and fields["source_bundle_id"] is not None
                ):
                    current_item["source_bundle_id"] = _normalize_string(
                        fields["source_bundle_id"]
                    )
                if (
                    "source_request_id" in fields
                    and fields["source_request_id"] is not None
                ):
                    current_item["source_request_id"] = _normalize_string(
                        fields["source_request_id"]
                    )
                if (
                    "source_doc_type" in fields
                    and fields["source_doc_type"] is not None
                ):
                    current_item["source_doc_type"] = _normalize_string(
                        fields["source_doc_type"]
                    )
                self._replace_with_normalized(current_item)
                return True, current_item != previous

            return self._mutate_index(mutation_id, update)

    def delete_document(self, doc_id: str) -> bool:
        """Delete one owned document and its content objects."""
        with self._lock:
            records = self._read_index()
            item = self._find_owned_record(records, doc_id)
            if item is None:
                return False
            target_identity = self._record_identity(item)
            mutation_id = uuid.uuid4().hex

            def remove(
                current: list[dict[str, Any]],
            ) -> tuple[tuple[bool, list[str]], bool]:
                current_item = self._find_owned_record(current, doc_id)
                if current_item is None:
                    return (False, []), False
                if self._record_identity(current_item) != target_identity:
                    raise KnowledgeStoreError(
                        "Knowledge document identity changed during deletion"
                    )
                retired_paths = self._object_paths_for(current_item)
                current.remove(current_item)
                return (True, retired_paths), True

            deleted, retired_paths = self._mutate_index(
                mutation_id,
                remove,
            )
            if deleted:
                self._cleanup_unreferenced(retired_paths)

        _log.info("[Knowledge] Deleted doc=%s project=%s", doc_id, self.project_id)
        return deleted

    def list_documents(self) -> list[dict[str, Any]]:
        """Return validated metadata for every owned document."""
        return self._load_index()

    def get_document(self, doc_id: str) -> KnowledgeEntry | None:
        """Return one complete document after revalidating its objects."""
        with self._lock:
            meta = next(
                (
                    self._normalize_meta(item)
                    for item in self._owned_records(self._read_index())
                    if item.get("doc_id") == doc_id
                ),
                None,
            )
            if meta is None:
                return None
            text = self._read_document_text(meta)
            style = self._read_style(meta)
            public_meta = self._public_meta(meta)
            return KnowledgeEntry(
                doc_id=doc_id,
                filename=public_meta.get("filename", ""),
                text=text,
                style_profile=style,
                created_at=public_meta.get("created_at"),
                tags=public_meta.get("tags", []),
                learning_mode=public_meta.get("learning_mode", _LEARNING_MODE_DEFAULT),
                quality_tier=public_meta.get("quality_tier", _QUALITY_TIER_DEFAULT),
                applicable_bundles=public_meta.get("applicable_bundles", []),
                source_organization=public_meta.get("source_organization", ""),
                reference_year=public_meta.get("reference_year"),
                success_state=public_meta.get("success_state", "draft"),
                notes=public_meta.get("notes", ""),
                source_bundle_id=public_meta.get("source_bundle_id", ""),
                source_request_id=public_meta.get("source_request_id", ""),
                source_doc_type=public_meta.get("source_doc_type", ""),
                knowledge_scope=public_meta.get("knowledge_scope", {}),
                tenant_id=self.tenant_id,
                project_id=self.project_id,
            )

    def find_promoted_document(
        self,
        *,
        source_request_id: str,
        source_doc_type: str,
        source_bundle_id: str = "",
    ) -> KnowledgeEntry | None:
        """Find an approved output created from the same source document."""
        request_id = _normalize_string(source_request_id)
        doc_type = _normalize_string(source_doc_type)
        bundle_id = _normalize_string(source_bundle_id)
        if not request_id or not doc_type:
            return None
        for meta in self._load_index():
            if meta.get("learning_mode") != "approved_output":
                continue
            if _normalize_string(meta.get("source_request_id")) != request_id:
                continue
            if _normalize_string(meta.get("source_doc_type")) != doc_type:
                continue
            meta_bundle_id = _normalize_string(meta.get("source_bundle_id"))
            if bundle_id and meta_bundle_id and meta_bundle_id != bundle_id:
                continue
            return self.get_document(meta["doc_id"])
        return None
