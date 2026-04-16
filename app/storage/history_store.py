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
    score: float = 0.0
    tags: list = None
    applied_references: list[dict] | None = None


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

    def add(self, entry: HistoryEntry) -> None:
        with self._lock:
            entries = self._load()
            entries.insert(0, {
                "entry_id": entry.entry_id,
                "tenant_id": entry.tenant_id,
                "user_id": entry.user_id,
                "bundle_id": entry.bundle_id,
                "bundle_name": entry.bundle_name,
                "title": entry.title,
                "request_id": entry.request_id,
                "created_at": entry.created_at,
                "score": entry.score,
                "tags": entry.tags or [],
                "applied_references": entry.applied_references or [],
            })
            # Cap per-user entries
            user_entries = [e for e in entries if e.get("user_id") == entry.user_id]
            other_entries = [e for e in entries if e.get("user_id") != entry.user_id]
            user_entries = user_entries[:MAX_HISTORY_PER_USER]
            self._save(other_entries + user_entries)

    def get_for_user(self, user_id: str, limit: int = 20) -> list[dict]:
        with self._lock:
            entries = self._load()
        return [e for e in entries if e.get("user_id") == user_id][:limit]

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

    def get_favorites(self, user_id: str) -> list[dict]:
        """즐겨찾기된 항목만 반환합니다."""
        with self._lock:
            entries = self._load()
        return [
            e for e in entries
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
                results.append(e)
        return results[:limit]
