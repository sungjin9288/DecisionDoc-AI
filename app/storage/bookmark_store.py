"""app/storage/bookmark_store.py — G2B announcement bookmarks per user.

Stored as JSON per tenant: data/tenants/{tenant_id}/g2b_bookmarks.json
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.storage.base import BaseJsonStore
from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id

_log = logging.getLogger("decisiondoc.bookmarks")
_OWNER_KEY = "_bookmark_owner"
_path_locks: dict[Path, threading.Lock] = {}
_path_locks_guard = threading.Lock()


def _lock_for_path(path: Path) -> threading.Lock:
    with _path_locks_guard:
        return _path_locks.setdefault(path.resolve(), threading.Lock())


def _require_user_id(user_id: object) -> str:
    if not isinstance(user_id, str) or not user_id or user_id != user_id.strip():
        raise ValueError("Invalid user_id")
    return user_id


class BookmarkStore(BaseJsonStore):
    def __init__(
        self,
        base_dir: str = "data",
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        super().__init__()
        self.tenant_id = require_tenant_id(tenant_id)
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._path = self._base / "tenants" / self.tenant_id / "g2b_bookmarks.json"
        self._relative_path = str(
            Path("tenants") / self.tenant_id / "g2b_bookmarks.json"
        )
        self._lock = _lock_for_path(self._path)
        if self._backend.kind == "local":
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def _get_path(self) -> Path:
        return self._path

    def _load(self) -> dict[str, Any]:
        raw = self._backend.read_text(self._relative_path)
        if raw is None or not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict | list) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        self._backend.write_text(self._relative_path, payload)

    def _owns(self, bookmark: Any, user_id: str) -> bool:
        if not isinstance(bookmark, dict):
            return False
        if _OWNER_KEY not in bookmark:
            return True
        return bookmark[_OWNER_KEY] == {
            "tenant_id": self.tenant_id,
            "user_id": user_id,
        }

    def _public_bookmark(self, bookmark: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in bookmark.items() if key != _OWNER_KEY}

    def _owned_bookmarks(self, data: dict[str, Any], user_id: str) -> list[dict[str, Any]]:
        bookmarks = data.get(user_id, [])
        if not isinstance(bookmarks, list):
            return []
        return [bookmark for bookmark in bookmarks if self._owns(bookmark, user_id)]

    def add(self, user_id: str, announcement: dict) -> dict:
        user_id = _require_user_id(user_id)
        with self._lock:
            data = self._load()
            bid_number = announcement.get("bid_number")
            existing = next(
                (
                    bookmark
                    for bookmark in self._owned_bookmarks(data, user_id)
                    if bookmark.get("bid_number") == bid_number
                ),
                None,
            )
            if existing is not None:
                return self._public_bookmark(existing)

            bookmarks = data.get(user_id)
            if not isinstance(bookmarks, list):
                bookmarks = []
                data[user_id] = bookmarks
            stored = dict(announcement)
            stored["bookmarked_at"] = datetime.now().isoformat()
            stored[_OWNER_KEY] = {
                "tenant_id": self.tenant_id,
                "user_id": user_id,
            }
            bookmarks.insert(0, stored)
            self._save(data)
        return self._public_bookmark(stored)

    def remove(self, user_id: str, bid_number: str) -> None:
        user_id = _require_user_id(user_id)
        with self._lock:
            data = self._load()
            bookmarks = data.get(user_id)
            if not isinstance(bookmarks, list):
                return
            remaining = [
                bookmark
                for bookmark in bookmarks
                if not (
                    self._owns(bookmark, user_id)
                    and bookmark.get("bid_number") == bid_number
                )
            ]
            if len(remaining) != len(bookmarks):
                data[user_id] = remaining
                self._save(data)

    def get_for_user(self, user_id: str) -> list[dict]:
        user_id = _require_user_id(user_id)
        with self._lock:
            data = self._load()
        return [
            self._public_bookmark(bookmark)
            for bookmark in self._owned_bookmarks(data, user_id)
        ]

    def is_bookmarked(self, user_id: str, bid_number: str) -> bool:
        return any(b.get("bid_number") == bid_number for b in self.get_for_user(user_id))
