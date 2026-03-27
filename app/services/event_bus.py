"""app/services/event_bus.py — In-memory thread-safe event bus for SSE real-time updates.

Simple design: each SSE connection gets a SimpleQueue. Publishers push events into
all queues for the target tenant. Lost on restart (ephemeral).
"""
from __future__ import annotations

import queue
import threading
from typing import Any


class EventBus:
    """Thread-safe pub/sub for real-time SSE updates."""

    def __init__(self) -> None:
        self._subs: dict[str, list[queue.SimpleQueue]] = {}  # tenant_id → queues
        self._lock = threading.Lock()

    def subscribe(self, tenant_id: str) -> queue.SimpleQueue:
        q: queue.SimpleQueue = queue.SimpleQueue()
        with self._lock:
            self._subs.setdefault(tenant_id, []).append(q)
        return q

    def unsubscribe(self, tenant_id: str, q: queue.SimpleQueue) -> None:
        with self._lock:
            subs = self._subs.get(tenant_id, [])
            try:
                subs.remove(q)
            except ValueError:
                pass

    def publish(self, tenant_id: str, event_type: str, data: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subs.get(tenant_id, []))
        item = {"event_type": event_type, "data": data}
        for q in subs:
            try:
                q.put_nowait(item)
            except Exception:
                pass  # drop on full queue — ephemeral


_bus = EventBus()


def get_event_bus() -> EventBus:
    return _bus
