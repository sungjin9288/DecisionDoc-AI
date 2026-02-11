import json
import os
from pathlib import Path
from uuid import uuid4
from typing import Any

from app.storage.base import Storage, StorageFailedError


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
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
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
            self._atomic_write_text(path, data)
        except Exception as exc:
            raise StorageFailedError("Storage operation failed.") from exc

    def _atomic_write_text(self, path: Path, text: str) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
            with tmp.open("w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception as exc:
            raise StorageFailedError("Storage operation failed.") from exc
