"""app/storage/bookmark_store.py — G2B announcement bookmarks per user.

Stored as JSON per tenant: data/tenants/{tenant_id}/g2b_bookmarks.json
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from app.storage.base import BaseJsonStore
from app.storage.state_backend import StateBackend, get_state_backend

_log = logging.getLogger("decisiondoc.bookmarks")


class BookmarkStore(BaseJsonStore):
    def __init__(
        self,
        tenant_id: str,
        base_dir: str = "data",
        *,
        backend: StateBackend | None = None,
    ) -> None:
        super().__init__()
        self.tenant_id = tenant_id
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._path = self._base / "tenants" / tenant_id / "g2b_bookmarks.json"
        self._relative_path = str(Path("tenants") / tenant_id / "g2b_bookmarks.json")
        if self._backend.kind == "local":
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _get_path(self) -> Path:
        return self._path

    def _load(self) -> dict | list:
        raw = self._backend.read_text(self._relative_path)
        if raw is None or not raw.strip():
            return self._empty()
        import json
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return self._empty()

    def _save(self, data: dict | list) -> None:
        import json
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        self._backend.write_text(self._relative_path, payload)

    def add(self, user_id: str, announcement: dict) -> dict:
        with self._lock:
            data = self._load()
            if user_id not in data:
                data[user_id] = []
            bid_number = announcement.get("bid_number")
            if not any(b.get("bid_number") == bid_number for b in data[user_id]):
                announcement = dict(announcement)
                announcement["bookmarked_at"] = datetime.now().isoformat()
                data[user_id].insert(0, announcement)
            self._save(data)
        return announcement

    def remove(self, user_id: str, bid_number: str) -> None:
        with self._lock:
            data = self._load()
            if user_id in data:
                data[user_id] = [
                    b for b in data[user_id] if b.get("bid_number") != bid_number
                ]
                self._save(data)

    def get_for_user(self, user_id: str) -> list[dict]:
        with self._lock:
            data = self._load()
        return data.get(user_id, [])

    def is_bookmarked(self, user_id: str, bid_number: str) -> bool:
        return any(b.get("bid_number") == bid_number for b in self.get_for_user(user_id))
