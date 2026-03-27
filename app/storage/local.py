import json
import logging
from pathlib import Path
from typing import Any

from app.storage.base import Storage, StorageFailedError, atomic_write_text

_log = logging.getLogger("decisiondoc.storage.local")

_MAX_BUNDLE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB guard-rail


class LocalStorage(Storage):
    def __init__(self, data_dir: Path | str, exports_dir: Path | str | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.exports_dir = Path(exports_dir) if exports_dir is not None else Path("./exports")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

    @property
    def kind(self) -> str:
        return "local"

    def _bundle_path(self, bundle_id: str) -> Path:
        return self.data_dir / f"{bundle_id}.json"

    def _export_path(self, bundle_id: str, doc_type: str) -> Path:
        return self.exports_dir / bundle_id / f"{doc_type}.md"

    def save_bundle(self, bundle_id: str, bundle: dict[str, Any]) -> None:
        path = self._bundle_path(bundle_id)
        self._atomic_write_json(path, bundle)

    def load_bundle(self, bundle_id: str) -> dict[str, Any] | None:
        path = self._bundle_path(bundle_id)
        if not path.exists():
            return None
        try:
            size = path.stat().st_size
            if size > _MAX_BUNDLE_SIZE_BYTES:
                _log.warning(
                    "Bundle file too large to load (%d MB > %d MB limit): %s",
                    size // 1_048_576,
                    _MAX_BUNDLE_SIZE_BYTES // 1_048_576,
                    path,
                )
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _log.warning("Failed to load bundle %s: %s", bundle_id, exc)
            return None

    def save_export(self, bundle_id: str, doc_type: str, markdown: str) -> None:
        path = self._export_path(bundle_id, doc_type)
        self._atomic_write_text(path, markdown)

    def get_export_path(self, bundle_id: str, doc_type: str) -> str:
        return str(self._export_path(bundle_id, doc_type))

    def get_export_dir(self, bundle_id: str) -> str:
        return str(self.exports_dir / bundle_id)

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        try:
            data = json.dumps(payload, ensure_ascii=False, indent=2)
        except (TypeError, ValueError) as exc:
            raise StorageFailedError("Storage operation failed.") from exc
        self._atomic_write_text(path, data)

    def _atomic_write_text(self, path: Path, text: str) -> None:
        try:
            atomic_write_text(path, text)
        except Exception as exc:
            raise StorageFailedError("Storage operation failed.") from exc
