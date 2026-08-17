"""Bounded, tenant-scoped in-memory source cache for generation export packets."""
from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_TTL_SECONDS = 60 * 60
DEFAULT_MAX_ENTRIES = 500


@dataclass(frozen=True)
class CachedGenerationExportSource:
    """Immutable cache record; callers receive a deep-copied payload."""

    docs: list[dict[str, Any]]
    title: str
    stored_at: float


class GenerationExportCache:
    """A process-local LRU cache that never shares a source across tenants."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[tuple[str, str], CachedGenerationExportSource] = OrderedDict()
        self._lock = threading.RLock()

    def store(
        self,
        *,
        tenant_id: str,
        request_id: str,
        docs: list[dict[str, Any]],
        title: str,
    ) -> None:
        key = self._key(tenant_id=tenant_id, request_id=request_id)
        now = self._clock()
        entry = CachedGenerationExportSource(
            docs=copy.deepcopy(docs),
            title=copy.deepcopy(title),
            stored_at=now,
        )
        with self._lock:
            self._purge_expired(now)
            self._entries.pop(key, None)
            self._entries[key] = entry
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def get(
        self,
        *,
        tenant_id: str,
        request_id: str,
    ) -> tuple[list[dict[str, Any]], str] | None:
        key = self._key(tenant_id=tenant_id, request_id=request_id)
        now = self._clock()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.get(key)
            if entry is None:
                return None
            self._entries.move_to_end(key)
            return copy.deepcopy(entry.docs), copy.deepcopy(entry.title)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            self._purge_expired(self._clock())
            return len(self._entries)

    @staticmethod
    def _key(*, tenant_id: str, request_id: str) -> tuple[str, str]:
        return str(tenant_id), str(request_id)

    def _purge_expired(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if now - entry.stored_at >= self.ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)


generation_export_cache = GenerationExportCache()
