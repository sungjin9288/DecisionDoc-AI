"""app/storage/bookmark_store.py — G2B announcement bookmarks per user.

Stored as JSON per tenant: data/tenants/{tenant_id}/g2b_bookmarks.json
"""
import logging
from datetime import datetime
from pathlib import Path

from app.storage.base import BaseJsonStore

_log = logging.getLogger("decisiondoc.bookmarks")


class BookmarkStore(BaseJsonStore):
    def __init__(self, tenant_id: str) -> None:
        super().__init__()
        self.tenant_id = tenant_id
        self._path = Path("data") / "tenants" / tenant_id / "g2b_bookmarks.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _get_path(self) -> Path:
        return self._path

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
