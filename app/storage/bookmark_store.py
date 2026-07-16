"""app/storage/bookmark_store.py — G2B announcement bookmarks per user.

Stored as JSON per tenant: data/tenants/{tenant_id}/g2b_bookmarks.json
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.state_backend import (
    StateBackend,
    StateBackendError,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id

_OWNER_KEY = "_bookmark_owner"


class BookmarkStoreError(ValueError):
    """Raised when persisted bookmark state cannot be trusted."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BookmarkStoreError(f"Duplicate key in bookmark state: {key!r}")
        result[key] = value
    return result


def _require_user_id(user_id: object) -> str:
    if not isinstance(user_id, str) or not user_id or user_id != user_id.strip():
        raise ValueError("Invalid user_id")
    return user_id


def _require_bid_number(bid_number: object) -> str:
    if (
        not isinstance(bid_number, str)
        or not bid_number
        or bid_number != bid_number.strip()
    ):
        raise ValueError("Invalid bid_number")
    return bid_number


class BookmarkStore:
    def __init__(
        self,
        base_dir: str = "data",
        *,
        tenant_id: str,
        backend: StateBackend | None = None,
    ) -> None:
        self.tenant_id = require_tenant_id(tenant_id)
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._relative_path = str(
            Path("tenants") / self.tenant_id / "g2b_bookmarks.json"
        )
        self._lock = state_lock(
            self._backend,
            data_dir=self._base,
            relative_path=self._relative_path,
        )

    def _load(self) -> dict[str, Any]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise BookmarkStoreError("Invalid bookmark state document") from exc
        if raw is None:
            return {}
        if not raw.strip():
            raise BookmarkStoreError("Invalid bookmark state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise BookmarkStoreError("Invalid bookmark state document") from exc
        if not isinstance(data, dict):
            raise BookmarkStoreError("Invalid bookmark state document")
        self._validate_state(data)
        return data

    def _save(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            self._backend.write_text(self._relative_path, payload)
        except StateBackendError as exc:
            raise BookmarkStoreError("Failed to persist bookmark state") from exc

    def _validate_state(self, data: dict[str, Any]) -> None:
        for user_id, bookmarks in data.items():
            try:
                _require_user_id(user_id)
            except ValueError as exc:
                raise BookmarkStoreError("Invalid bookmark user identity") from exc
            if not isinstance(bookmarks, list):
                raise BookmarkStoreError("Invalid bookmark collection")

            bid_numbers: set[str] = set()
            for bookmark in bookmarks:
                if not isinstance(bookmark, dict):
                    raise BookmarkStoreError("Invalid bookmark record")
                if not self._owns(bookmark, user_id):
                    continue
                try:
                    bid_number = _require_bid_number(bookmark.get("bid_number"))
                except ValueError as exc:
                    raise BookmarkStoreError("Invalid owned bookmark record") from exc
                bookmarked_at = bookmark.get("bookmarked_at")
                if bookmarked_at is not None and (
                    not isinstance(bookmarked_at, str) or not bookmarked_at
                ):
                    raise BookmarkStoreError("Invalid bookmark timestamp")
                if bid_number in bid_numbers:
                    raise BookmarkStoreError("Duplicate bookmark identity")
                bid_numbers.add(bid_number)

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
        return [bookmark for bookmark in bookmarks if self._owns(bookmark, user_id)]

    def add(self, user_id: str, announcement: dict) -> dict:
        user_id = _require_user_id(user_id)
        if not isinstance(announcement, dict):
            raise ValueError("Invalid announcement")
        bid_number = _require_bid_number(announcement.get("bid_number"))
        with self._lock:
            data = self._load()
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

            bookmarks = data.setdefault(user_id, [])
            stored = dict(announcement)
            stored["bookmarked_at"] = datetime.now(timezone.utc).isoformat()
            stored[_OWNER_KEY] = {
                "tenant_id": self.tenant_id,
                "user_id": user_id,
            }
            bookmarks.insert(0, stored)
            self._save(data)
        return self._public_bookmark(stored)

    def remove(self, user_id: str, bid_number: str) -> None:
        user_id = _require_user_id(user_id)
        bid_number = _require_bid_number(bid_number)
        with self._lock:
            data = self._load()
            bookmarks = data.get(user_id)
            if bookmarks is None:
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
        bid_number = _require_bid_number(bid_number)
        return any(b.get("bid_number") == bid_number for b in self.get_for_user(user_id))
