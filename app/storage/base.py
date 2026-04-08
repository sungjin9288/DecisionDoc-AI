from __future__ import annotations

import json
import logging
import os
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
from uuid import uuid4

_log = logging.getLogger("decisiondoc.storage")


class StorageFailedError(Exception):
    pass


def atomic_write_text(path: Path, text: str) -> None:
    """Write *text* to *path* atomically via tmp-file + os.replace.

    Safe against partial writes / crashes — readers always see a
    complete file or the previous version.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex[:12]}")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        _log.warning("Atomic write failed for %s", path, exc_info=True)
        raise
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def atomic_write_bytes(path: Path, raw: bytes) -> None:
    """Write *raw* bytes to *path* atomically via tmp-file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex[:12]}")
    try:
        with tmp.open("wb") as f:
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        _log.warning("Atomic byte write failed for %s", path, exc_info=True)
        raise
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


class BaseJsonStore:
    """Thread-safe JSON file store with atomic writes.

    Subclasses must implement ``_get_path()`` and may override ``_empty()``
    for list-based stores.  All read/write goes through ``_load()``/``_save()``.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _get_path(self) -> Path:
        raise NotImplementedError

    def _empty(self) -> dict | list:
        """Return the default empty value.  Override to return [] for list stores."""
        return {}

    def _load(self) -> dict | list:
        path = self._get_path()
        if not path.exists():
            return self._empty()
        try:
            content = path.read_text(encoding="utf-8")
            if not content.strip():
                return self._empty()
            return json.loads(content)
        except (json.JSONDecodeError, OSError) as e:
            _log.warning("[BaseJsonStore] Load failed %s: %s", path, e)
            return self._empty()

    def _save(self, data: dict | list) -> None:
        """Atomic write — write to temp file then fsync + rename."""
        path = self._get_path()
        atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


class Storage(ABC):
    @property
    @abstractmethod
    def kind(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def save_bundle(self, bundle_id: str, bundle: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def load_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def save_export(self, bundle_id: str, doc_type: str, markdown: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_export_path(self, bundle_id: str, doc_type: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_export_dir(self, bundle_id: str) -> str:
        raise NotImplementedError
