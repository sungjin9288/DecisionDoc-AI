"""app/storage/history_store.py — Server-side generation history per user.

Max 50 entries per user, stored as JSONL per tenant.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from app.storage.base import atomic_write_text
from app.storage.state_backend import StateBackend, get_state_backend

_log = logging.getLogger("decisiondoc.history")

MAX_HISTORY_PER_USER = 50


@dataclass
class HistoryEntry:
    entry_id: str
    tenant_id: str
    user_id: str
    bundle_id: str
    bundle_name: str
    title: str
    request_id: str
    created_at: str
    bundle_type: str = ""
    project_id: str = ""
    score: float = 0.0
    tags: list = None
    applied_references: list[dict] | None = None
    docs: list[dict] | None = None
    visual_assets: list[dict] | None = None
    knowledge_promoted: bool = False
    knowledge_project_id: str = ""
    knowledge_promoted_at: str = ""
    knowledge_document_count: int = 0
    knowledge_quality_tier: str = ""
    knowledge_success_state: str = ""
    knowledge_documents: list[dict] | None = None


class HistoryStore:
    def __init__(
        self,
        tenant_id: str,
        base_dir: str = "data",
        *,
        backend: StateBackend | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self._lock = threading.Lock()
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._path = self._base / "tenants" / tenant_id / "history.jsonl"
        self._relative_path = str(Path("tenants") / tenant_id / "history.jsonl")
        if self._backend.kind == "local":
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> list[dict]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None or not raw.strip():
            return []
        entries: list[dict] = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        return entries

    def _save(self, entries: list[dict]) -> None:
        text = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
        if self._backend.kind == "local":
            atomic_write_text(self._path, text)
            return
        self._backend.write_text(
            self._relative_path,
            text,
            content_type="application/x-ndjson; charset=utf-8",
        )

    @staticmethod
    def _sanitize_entry(
        entry: dict,
        *,
        include_docs: bool = False,
        include_visual_assets: bool = False,
    ) -> dict:
        item = dict(entry)
        if not include_docs:
            item.pop("docs", None)
        if not include_visual_assets:
            item["visual_asset_count"] = len(item.get("visual_assets") or [])
            item.pop("visual_assets", None)
        return item

    @staticmethod
    def _sanitize_visual_assets(visual_assets: list[dict] | None) -> list[dict]:
        sanitized: list[dict] = []
        for asset in visual_assets or []:
            if not isinstance(asset, dict):
                continue
            sanitized.append({
                "asset_id": str(asset.get("asset_id") or "").strip(),
                "doc_type": str(asset.get("doc_type") or "").strip(),
                "slide_title": str(asset.get("slide_title") or "").strip(),
                "visual_type": str(asset.get("visual_type") or "").strip(),
                "visual_brief": str(asset.get("visual_brief") or "").strip(),
                "layout_hint": str(asset.get("layout_hint") or "").strip(),
                "source_kind": str(asset.get("source_kind") or "").strip(),
                "source_model": str(asset.get("source_model") or "").strip(),
                "prompt": str(asset.get("prompt") or "").strip(),
                "media_type": str(asset.get("media_type") or "").strip(),
                "encoding": str(asset.get("encoding") or "base64").strip() or "base64",
                "content_base64": str(asset.get("content_base64") or "").strip(),
            })
        return sanitized[:12]

    def add(self, entry: HistoryEntry) -> None:
        with self._lock:
            entries = self._load()
            entries.insert(0, {
                "entry_id": entry.entry_id,
                "tenant_id": entry.tenant_id,
                "user_id": entry.user_id,
                "bundle_id": entry.bundle_id,
                "bundle_type": entry.bundle_type or entry.bundle_id,
                "bundle_name": entry.bundle_name,
                "title": entry.title,
                "request_id": entry.request_id,
                "created_at": entry.created_at,
                "project_id": entry.project_id or "",
                "score": entry.score,
                "tags": entry.tags or [],
                "applied_references": entry.applied_references or [],
                "docs": entry.docs or [],
                "visual_assets": self._sanitize_visual_assets(entry.visual_assets),
                "knowledge_promoted": bool(entry.knowledge_promoted),
                "knowledge_project_id": entry.knowledge_project_id or "",
                "knowledge_promoted_at": entry.knowledge_promoted_at or "",
                "knowledge_document_count": int(entry.knowledge_document_count or 0),
                "knowledge_quality_tier": entry.knowledge_quality_tier or "",
                "knowledge_success_state": entry.knowledge_success_state or "",
                "knowledge_documents": entry.knowledge_documents or [],
            })
            # Cap per-user entries
            user_entries = [e for e in entries if e.get("user_id") == entry.user_id]
            other_entries = [e for e in entries if e.get("user_id") != entry.user_id]
            user_entries = user_entries[:MAX_HISTORY_PER_USER]
            self._save(other_entries + user_entries)

    def get_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            entries = self._load()
        return [
            self._sanitize_entry(e)
            for e in entries
            if e.get("user_id") == user_id
        ][:limit]

    def get_entry(self, entry_id: str, user_id: str) -> dict | None:
        with self._lock:
            entries = self._load()
        for entry in entries:
            if entry.get("entry_id") == entry_id and entry.get("user_id") == user_id:
                return self._sanitize_entry(entry, include_docs=True, include_visual_assets=True)
        return None

    def update_visual_assets(self, entry_id: str, user_id: str, visual_assets: list[dict] | None) -> bool:
        with self._lock:
            entries = self._load()
            updated = False
            for entry in entries:
                if entry.get("entry_id") != entry_id or entry.get("user_id") != user_id:
                    continue
                entry["visual_assets"] = self._sanitize_visual_assets(visual_assets)
                updated = True
                break
            if updated:
                self._save(entries)
        return updated

    def delete(self, entry_id: str, user_id: str) -> None:
        with self._lock:
            entries = self._load()
            entries = [
                e for e in entries
                if not (e.get("entry_id") == entry_id and e.get("user_id") == user_id)
            ]
            self._save(entries)

    def toggle_favorite(self, entry_id: str, user_id: str) -> bool:
        """즐겨찾기 토글. 새로운 상태(True=즐겨찾기됨)를 반환합니다."""
        with self._lock:
            entries = self._load()
            new_state = False
            for e in entries:
                if e.get("entry_id") == entry_id and e.get("user_id") == user_id:
                    e["starred"] = not e.get("starred", False)
                    new_state = e["starred"]
                    break
            self._save(entries)
        return new_state

    def mark_promoted(
        self,
        request_id: str,
        *,
        project_id: str,
        document_count: int,
        quality_tier: str,
        success_state: str,
        promoted_at: str,
        knowledge_documents: list[dict] | None = None,
        user_id: str | None = None,
    ) -> int:
        """Mark matching history entries as promoted to the knowledge library.

        Returns the number of updated entries.
        """
        if not request_id:
            return 0
        updated = 0
        with self._lock:
            entries = self._load()
            for entry in entries:
                if entry.get("request_id") != request_id:
                    continue
                if user_id and entry.get("user_id") != user_id:
                    continue
                entry["knowledge_promoted"] = True
                entry["knowledge_project_id"] = project_id
                entry["knowledge_promoted_at"] = promoted_at
                entry["knowledge_document_count"] = int(document_count or 0)
                entry["knowledge_quality_tier"] = str(quality_tier or "")
                entry["knowledge_success_state"] = str(success_state or "")
                entry["knowledge_documents"] = [
                    {
                        "doc_id": str(doc.get("doc_id") or "").strip(),
                        "doc_type": str(doc.get("doc_type") or "").strip(),
                        "filename": str(doc.get("filename") or "").strip(),
                        "quality_tier": str(doc.get("quality_tier") or "").strip(),
                        "success_state": str(doc.get("success_state") or "").strip(),
                    }
                    for doc in (knowledge_documents or [])
                    if isinstance(doc, dict) and str(doc.get("doc_id") or "").strip()
                ]
                updated += 1
            if updated:
                self._save(entries)
        return updated

    def get_favorites(self, user_id: str) -> list[dict]:
        """즐겨찾기된 항목만 반환합니다."""
        with self._lock:
            entries = self._load()
        return [
            self._sanitize_entry(e)
            for e in entries
            if e.get("user_id") == user_id and e.get("starred", False)
        ]

    def search(self, user_id: str, q: str, limit: int = 20) -> list[dict]:
        """제목·번들명·태그로 이력을 검색합니다 (대소문자 무시)."""
        q_lower = q.strip().lower()
        if not q_lower:
            return self.get_for_user(user_id, limit)
        with self._lock:
            entries = self._load()
        results = []
        for e in entries:
            if e.get("user_id") != user_id:
                continue
            haystack = " ".join([
                str(e.get("title", "")),
                str(e.get("bundle_name", "")),
                str(e.get("bundle_id", "")),
                " ".join(e.get("tags") or []),
            ]).lower()
            if q_lower in haystack:
                results.append(self._sanitize_entry(e))
        return results[:limit]
