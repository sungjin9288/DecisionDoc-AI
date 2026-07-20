"""app/storage/bookmark_store.py — G2B announcement bookmarks per user.

Stored as JSON per tenant: data/tenants/{tenant_id}/g2b_bookmarks.json
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.storage.conditional_state import persist_text_if_current
from app.storage.state_backend import (
    StateBackend,
    StateBackendError,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id

_OWNER_KEY = "_bookmark_owner"
_BOOKMARK_ID_KEY = "_bookmark_id"
_STATE_METADATA_KEY = ""  # Public user identifiers reject the empty string.
_MUTATION_IDS_KEY = "_bookmark_mutation_ids"
_MAX_MUTATION_ATTEMPTS = 32
_MAX_TRACKED_MUTATIONS = 64
_MutationResult = TypeVar("_MutationResult")


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

    def _read_state(self) -> tuple[str | None, dict[str, Any]]:
        try:
            raw = self._backend.read_text(self._relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise BookmarkStoreError("Invalid bookmark state document") from exc
        if raw is None:
            return None, {}
        if not raw.strip():
            raise BookmarkStoreError("Invalid bookmark state document")
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ValueError) as exc:
            raise BookmarkStoreError("Invalid bookmark state document") from exc
        if not isinstance(data, dict):
            raise BookmarkStoreError("Invalid bookmark state document")
        self._validate_state(data)
        return raw, data

    def _load(self) -> dict[str, Any]:
        return self._read_state()[1]

    @staticmethod
    def _mutation_ids(data: dict[str, Any]) -> list[str]:
        if _STATE_METADATA_KEY not in data:
            return []
        metadata = data[_STATE_METADATA_KEY]
        if not isinstance(metadata, dict) or set(metadata) != {_MUTATION_IDS_KEY}:
            raise BookmarkStoreError("Invalid bookmark mutation history")
        mutation_ids = metadata.get(_MUTATION_IDS_KEY)
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise BookmarkStoreError("Invalid bookmark mutation history")
        return list(mutation_ids)

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        data: dict[str, Any],
        mutation_id: str,
    ) -> bool:
        self._validate_state(data)
        payload = json.dumps(data, ensure_ascii=False, indent=2)

        def decode(raw: str) -> dict[str, Any]:
            if not raw.strip():
                raise BookmarkStoreError("Invalid bookmark state document")
            try:
                observed = json.loads(raw, object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, ValueError) as exc:
                raise BookmarkStoreError("Invalid bookmark state document") from exc
            if not isinstance(observed, dict):
                raise BookmarkStoreError("Invalid bookmark state document")
            self._validate_state(observed)
            return observed

        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._relative_path,
                expected=expected,
                replacement=payload,
                decode=decode,
                committed=lambda observed: mutation_id in self._mutation_ids(observed),
                decode_errors=(BookmarkStoreError,),
            )
        except StateBackendError as exc:
            raise BookmarkStoreError("Failed to persist bookmark state") from exc

    def _mutate(
        self,
        mutation_id: str,
        change: Callable[[dict[str, Any]], tuple[_MutationResult, bool]],
    ) -> _MutationResult:
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, data = self._read_state()
            result, changed = change(data)
            if not changed:
                return result

            mutation_ids = self._mutation_ids(data)
            mutation_ids.append(mutation_id)
            data[_STATE_METADATA_KEY] = {
                _MUTATION_IDS_KEY: mutation_ids[-_MAX_TRACKED_MUTATIONS:]
            }
            if self._persist_if_current(
                expected=expected,
                data=data,
                mutation_id=mutation_id,
            ):
                return result
        raise BookmarkStoreError(
            "Bookmark state changed too many times to persist safely"
        )

    def _validate_state(self, data: dict[str, Any]) -> None:
        self._mutation_ids(data)
        for user_id, bookmarks in data.items():
            if user_id == _STATE_METADATA_KEY:
                continue
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
                bookmark_id = bookmark.get(_BOOKMARK_ID_KEY)
                if bookmark_id is not None and (
                    not isinstance(bookmark_id, str) or not bookmark_id
                ):
                    raise BookmarkStoreError("Invalid bookmark identity")
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
        return {
            key: value
            for key, value in bookmark.items()
            if key not in {_OWNER_KEY, _BOOKMARK_ID_KEY}
        }

    @staticmethod
    def _bookmark_identity(bookmark: dict[str, Any]) -> str:
        bookmark_id = bookmark.get(_BOOKMARK_ID_KEY)
        if isinstance(bookmark_id, str) and bookmark_id:
            return bookmark_id
        legacy_payload = json.dumps(
            bookmark,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"legacy:{hashlib.sha256(legacy_payload.encode()).hexdigest()}"

    def _owned_bookmarks(
        self, data: dict[str, Any], user_id: str
    ) -> list[dict[str, Any]]:
        bookmarks = data.get(user_id, [])
        return [bookmark for bookmark in bookmarks if self._owns(bookmark, user_id)]

    def add(self, user_id: str, announcement: dict) -> dict:
        user_id = _require_user_id(user_id)
        if not isinstance(announcement, dict):
            raise ValueError("Invalid announcement")
        bid_number = _require_bid_number(announcement.get("bid_number"))
        mutation_id = uuid.uuid4().hex
        bookmark_id = str(uuid.uuid4())
        bookmarked_at = datetime.now(timezone.utc).isoformat()

        def add_bookmark(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
            existing = next(
                (
                    bookmark
                    for bookmark in self._owned_bookmarks(data, user_id)
                    if bookmark.get("bid_number") == bid_number
                ),
                None,
            )
            if existing is not None:
                return self._public_bookmark(existing), False

            stored = dict(announcement)
            stored["bookmarked_at"] = bookmarked_at
            stored[_OWNER_KEY] = {
                "tenant_id": self.tenant_id,
                "user_id": user_id,
            }
            stored[_BOOKMARK_ID_KEY] = bookmark_id
            data.setdefault(user_id, []).insert(0, stored)
            return self._public_bookmark(stored), True

        with self._lock:
            return self._mutate(mutation_id, add_bookmark)

    def remove(self, user_id: str, bid_number: str) -> None:
        user_id = _require_user_id(user_id)
        bid_number = _require_bid_number(bid_number)
        mutation_id = uuid.uuid4().hex
        target_identity: str | None = None

        def remove_bookmark(data: dict[str, Any]) -> tuple[None, bool]:
            nonlocal target_identity
            bookmarks = data.get(user_id)
            if bookmarks is None:
                return None, False
            target = next(
                (
                    bookmark
                    for bookmark in bookmarks
                    if self._owns(bookmark, user_id)
                    and bookmark.get("bid_number") == bid_number
                ),
                None,
            )
            if target is None:
                return None, False

            current_identity = self._bookmark_identity(target)
            if target_identity is None:
                target_identity = current_identity
            elif target_identity != current_identity:
                raise BookmarkStoreError("Bookmark identity changed during mutation")
            data[user_id] = [
                bookmark for bookmark in bookmarks if bookmark is not target
            ]
            return None, True

        with self._lock:
            self._mutate(mutation_id, remove_bookmark)

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
        return any(
            b.get("bid_number") == bid_number for b in self.get_for_user(user_id)
        )
