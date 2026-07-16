"""Process-local locks for shared state objects."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend


_locks: dict[tuple[Any, ...], threading.RLock] = {}
_locks_guard = threading.Lock()


def state_lock(
    backend: StateBackend,
    *,
    data_dir: Path,
    relative_path: str,
) -> threading.RLock:
    """Return the shared lock for one logical state object."""
    if backend.kind == "local":
        root = Path(getattr(backend, "root", data_dir)).resolve()
        key: tuple[Any, ...] = ("local", root / relative_path)
    elif backend.kind == "s3":
        key = (
            "s3",
            getattr(backend, "bucket", ""),
            getattr(backend, "prefix", ""),
            relative_path,
        )
    else:
        key = (backend.kind, id(backend), relative_path)

    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


def state_backend_identity(
    backend: StateBackend,
    *,
    data_dir: Path,
    explicit_backend: bool,
) -> tuple[Any, ...]:
    """Build a stable cache identity for a configured state backend."""
    if explicit_backend:
        return (backend.kind, id(backend))
    if backend.kind == "s3":
        return (
            "s3",
            getattr(backend, "bucket", ""),
            getattr(backend, "prefix", ""),
        )
    return ("local", data_dir.resolve())
