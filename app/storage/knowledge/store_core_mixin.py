"""app/storage/knowledge/store_core_mixin.py — 초기화 및 CRUD, 내부 파일 I/O 헬퍼.

KnowledgeStore의 쓰기/읽기 기본 동작(add/update/delete/get/list)과
인덱스·atomic write 등 다른 mixin이 공유하는 내부 플럼빙을 담당한다.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import uuid
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

from app.storage.knowledge.constants import (
    _LEARNING_MODE_DEFAULT,
    _QUALITY_TIER_DEFAULT,
    MAX_DOCS_PER_PROJECT,
)
from app.storage.knowledge.entry import KnowledgeEntry
from app.storage.knowledge.normalizers import (
    _extract_report_workflow_id,
    _normalize_learning_mode,
    _normalize_list,
    _normalize_quality_tier,
    _normalize_reference_year,
    _normalize_string,
    _normalize_success_state,
)
from app.storage.knowledge_search import KnowledgeSearchBackend, get_knowledge_search_backend
from app.storage.base import atomic_write_text

_log = logging.getLogger("decisiondoc.knowledge")
_DOC_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
_path_locks: WeakValueDictionary[Path, Any] = WeakValueDictionary()
_path_locks_guard = threading.Lock()


def _lock_for_path(path: Path) -> Any:
    with _path_locks_guard:
        return _path_locks.setdefault(path.resolve(), threading.RLock())


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


class KnowledgeStoreCoreMixin:
    """프로젝트별 문서 지식의 초기화, CRUD, 내부 저장 헬퍼."""

    def __init__(
        self,
        project_id: str,
        data_dir: str | None = None,
        search_backend: KnowledgeSearchBackend | None = None,
        *,
        tenant_id: str = "system",
    ) -> None:
        self.project_id = _storage_component(project_id, "project_id")
        self.tenant_id = _storage_component(tenant_id, "tenant_id")
        self._search_backend = search_backend or get_knowledge_search_backend()
        base = Path(data_dir or os.getenv("DATA_DIR", "data"))
        self._dir = base / "tenants" / self.tenant_id / "knowledge" / self.project_id
        self._index_path = self._dir / "index.json"
        self._lock = _lock_for_path(self._index_path)

    # ── 쓰기 ──────────────────────────────────────────────────────────────────

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
        """문서를 지식 저장소에 추가하고 KnowledgeEntry를 반환."""
        self._ensure_dir()
        doc_id = uuid.uuid4().hex[:12]
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
        with self._lock:
            self._save_entry(entry)
        _log.info(
            "[Knowledge] Added doc=%s file=%s project=%s",
            doc_id, filename, self.project_id,
        )
        return entry

    def update_style(self, doc_id: str, style_profile: dict[str, Any]) -> bool:
        """기존 문서의 스타일 프로필을 업데이트."""
        with self._lock:
            records = self._read_index()
            item = self._find_owned_record(records, doc_id)
            if item is None or not (self._dir / f"{doc_id}.txt").exists():
                return False
            self._atomic_write_json(self._dir / f"{doc_id}_style.json", style_profile)
            item["has_style"] = True
            self._replace_with_normalized(item)
            self._write_index(records)
            return True

    def update_metadata(self, doc_id: str, **fields: Any) -> bool:
        """문서의 학습용 메타데이터를 업데이트."""
        with self._lock:
            records = self._read_index()
            item = self._find_owned_record(records, doc_id)
            if item is None or not (self._dir / f"{doc_id}.txt").exists():
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
        """문서 삭제. 존재하지 않으면 False."""
        with self._lock:
            records = self._read_index()
            if not self._delete_owned_document(records, doc_id):
                return False
            self._write_index(records)
        _log.info("[Knowledge] Deleted doc=%s project=%s", doc_id, self.project_id)
        return True

    # ── 읽기 ──────────────────────────────────────────────────────────────────

    def list_documents(self) -> list[dict[str, Any]]:
        """프로젝트의 모든 문서 메타데이터 목록."""
        return self._load_index()

    def get_document(self, doc_id: str) -> KnowledgeEntry | None:
        """단일 문서 전체 조회. 없으면 None."""
        meta = next(
            (item for item in self._load_index() if item.get("doc_id") == doc_id),
            None,
        )
        if meta is None:
            return None
        txt_path = self._dir / f"{doc_id}.txt"
        if not txt_path.exists():
            return None
        text = txt_path.read_text(encoding="utf-8")
        style_path = self._dir / f"{doc_id}_style.json"
        try:
            style = json.loads(style_path.read_text(encoding="utf-8")) if style_path.exists() else {}
        except (json.JSONDecodeError, OSError):
            style = {}
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
        """Find an approved_output entry created from the same generation request/doc type."""
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
            doc_id = meta.get("doc_id")
            if not doc_id:
                continue
            entry = self.get_document(str(doc_id))
            if entry is not None:
                return entry
        return None

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> list[dict[str, Any]]:
        return [
            self._normalize_meta(item)
            for item in self._owned_records(self._read_index())
        ]

    def _read_index(self) -> list[dict[str, Any]]:
        if not self._index_path.exists():
            return []
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _write_index(self, records: list[dict[str, Any]]) -> None:
        self._atomic_write_json(self._index_path, records)

    def _owns(self, item: dict[str, Any]) -> bool:
        return (
            item.get("tenant_id") in (None, self.tenant_id)
            and item.get("project_id") in (None, self.project_id)
        )

    def _owned_records(
        self,
        records: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for item in records:
            if not self._safe_doc_id(item.get("doc_id")):
                continue
            doc_id = item["doc_id"]
            counts[doc_id] = counts.get(doc_id, 0) + 1
        return [
            item
            for item in records
            if self._owns(item)
            and self._safe_doc_id(item.get("doc_id"))
            and counts[item["doc_id"]] == 1
        ]

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
        matches = [item for item in records if item.get("doc_id") == doc_id]
        if len(matches) != 1 or not self._owns(matches[0]):
            return None
        return matches[0]

    def _replace_with_normalized(self, item: dict[str, Any]) -> None:
        normalized = self._normalize_meta(item)
        item.clear()
        item.update(normalized)

    def _delete_owned_document(
        self,
        records: list[dict[str, Any]],
        doc_id: str,
    ) -> bool:
        item = self._find_owned_record(records, doc_id)
        if item is None:
            return False
        (self._dir / f"{doc_id}.txt").unlink(missing_ok=True)
        (self._dir / f"{doc_id}_style.json").unlink(missing_ok=True)
        records.remove(item)
        return True

    def _save_entry(self, entry: KnowledgeEntry) -> None:
        # 최대 문서 수 초과 시 가장 오래된 것 삭제
        records = self._read_index()
        owned = self._owned_records(records)
        if len(owned) >= MAX_DOCS_PER_PROJECT:
            oldest = min(owned, key=lambda item: item.get("created_at", 0))
            self._delete_owned_document(records, oldest["doc_id"])

        # 텍스트 저장
        self._atomic_write(self._dir / f"{entry.doc_id}.txt", entry.text)

        # 스타일 저장 (있을 때만)
        if entry.style_profile:
            self._atomic_write_json(
                self._dir / f"{entry.doc_id}_style.json", entry.style_profile
            )

        # 인덱스 갱신
        meta = self._normalize_meta(entry.to_meta())
        entry.knowledge_scope = dict(meta.get("knowledge_scope") or {})
        records.append(meta)
        self._write_index(records)

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
        item["knowledge_scope"] = self._build_knowledge_scope(item)
        return item

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

    def _atomic_write(self, path: Path, text: str) -> None:
        atomic_write_text(path, text)

    def _atomic_write_json(self, path: Path, data: Any) -> None:
        self._atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
