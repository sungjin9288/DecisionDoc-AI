"""Tenant- and project-scoped knowledge state storage."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from app.storage.knowledge.constants import (
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
from app.storage.knowledge.store_state_mixin import KnowledgeStoreStateMixin
from app.storage.knowledge_search import KnowledgeSearchBackend, get_knowledge_search_backend
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
                item.get("doc_id")
                for item in records
                if isinstance(item, dict)
            }
            doc_id = self._new_doc_id(known_ids)
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
            self._save_entry(entry, records)

        _log.info(
            "[Knowledge] Added doc=%s file=%s project=%s",
            doc_id,
            filename,
            self.project_id,
        )
        return entry

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

            style_path = self._style_relative_path(doc_id)
            previous_style = self._read_bytes(style_path)
            self._write_bytes(
                style_path,
                style_raw,
                content_type="application/json; charset=utf-8",
            )
            item["has_style"] = True
            self._replace_with_normalized(item)
            try:
                self._write_index(records)
            except Exception:
                self._restore_object(style_path, previous_style)
                raise
            return True

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
            if "tags" in fields and fields["tags"] is not None:
                item["tags"] = _normalize_list(fields["tags"])
            if "learning_mode" in fields and fields["learning_mode"] is not None:
                item["learning_mode"] = _normalize_learning_mode(fields["learning_mode"])
            if "quality_tier" in fields and fields["quality_tier"] is not None:
                item["quality_tier"] = _normalize_quality_tier(fields["quality_tier"])
            if "applicable_bundles" in fields and fields["applicable_bundles"] is not None:
                item["applicable_bundles"] = _normalize_list(fields["applicable_bundles"])
            if "source_organization" in fields and fields["source_organization"] is not None:
                item["source_organization"] = _normalize_string(fields["source_organization"])
            if "reference_year" in fields:
                item["reference_year"] = _normalize_reference_year(fields["reference_year"])
            if "success_state" in fields and fields["success_state"] is not None:
                item["success_state"] = _normalize_success_state(fields["success_state"])
            if "notes" in fields and fields["notes"] is not None:
                item["notes"] = _normalize_string(fields["notes"])
            if "source_bundle_id" in fields and fields["source_bundle_id"] is not None:
                item["source_bundle_id"] = _normalize_string(fields["source_bundle_id"])
            if "source_request_id" in fields and fields["source_request_id"] is not None:
                item["source_request_id"] = _normalize_string(fields["source_request_id"])
            if "source_doc_type" in fields and fields["source_doc_type"] is not None:
                item["source_doc_type"] = _normalize_string(fields["source_doc_type"])
            self._replace_with_normalized(item)
            self._write_index(records)
            return True

    def delete_document(self, doc_id: str) -> bool:
        """Delete one owned document and its content objects."""
        with self._lock:
            records = self._read_index()
            item = self._find_owned_record(records, doc_id)
            if item is None:
                return False
            records.remove(item)
            self._write_index(records)
            self._delete(self._text_relative_path(doc_id))
            if item.get("has_style"):
                self._delete(self._style_relative_path(doc_id))

        _log.info("[Knowledge] Deleted doc=%s project=%s", doc_id, self.project_id)
        return True

    def list_documents(self) -> list[dict[str, Any]]:
        """Return validated metadata for every owned document."""
        return self._load_index()

    def get_document(self, doc_id: str) -> KnowledgeEntry | None:
        """Return one complete document after revalidating its objects."""
        with self._lock:
            meta = next(
                (item for item in self._load_index() if item.get("doc_id") == doc_id),
                None,
            )
            if meta is None:
                return None
            text = self._read_document_text(meta)
            style = self._read_style(meta)
            return KnowledgeEntry(
                doc_id=doc_id,
                filename=meta.get("filename", ""),
                text=text,
                style_profile=style,
                created_at=meta.get("created_at"),
                tags=meta.get("tags", []),
                learning_mode=meta.get("learning_mode", _LEARNING_MODE_DEFAULT),
                quality_tier=meta.get("quality_tier", _QUALITY_TIER_DEFAULT),
                applicable_bundles=meta.get("applicable_bundles", []),
                source_organization=meta.get("source_organization", ""),
                reference_year=meta.get("reference_year"),
                success_state=meta.get("success_state", "draft"),
                notes=meta.get("notes", ""),
                source_bundle_id=meta.get("source_bundle_id", ""),
                source_request_id=meta.get("source_request_id", ""),
                source_doc_type=meta.get("source_doc_type", ""),
                knowledge_scope=meta.get("knowledge_scope", {}),
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
