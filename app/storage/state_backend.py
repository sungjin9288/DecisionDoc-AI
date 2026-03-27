from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.storage.state")


class StateBackendError(Exception):
    """Raised when the shared state backend cannot read or write data."""


class StateBackend(ABC):
    @property
    @abstractmethod
    def kind(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def read_text(self, relative_path: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def write_text(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_prefix(self, relative_prefix: str) -> list[str]:
        raise NotImplementedError


class LocalStateBackend(StateBackend):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def kind(self) -> str:
        return "local"

    def _path(self, relative_path: str) -> Path:
        return self.root / relative_path

    def exists(self, relative_path: str) -> bool:
        return self._path(relative_path).exists()

    def read_text(self, relative_path: str) -> str | None:
        path = self._path(relative_path)
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateBackendError(f"Failed to read state file: {path}") from exc

    def write_text(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        _ = content_type
        from app.storage.base import atomic_write_text

        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, text)

    def list_prefix(self, relative_prefix: str) -> list[str]:
        prefix_path = self._path(relative_prefix)
        if prefix_path.is_file():
            return [relative_prefix.rstrip("/")]
        if not prefix_path.exists():
            return []
        return [
            str(path.relative_to(self.root))
            for path in prefix_path.rglob("*")
            if path.is_file()
        ]


class S3StateBackend(StateBackend):
    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "decisiondoc-ai/state/",
        s3_client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix if prefix.endswith("/") else f"{prefix}/"
        self._s3_client = s3_client

    @property
    def kind(self) -> str:
        return "s3"

    @property
    def client(self) -> Any:
        if self._s3_client is not None:
            return self._s3_client
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise StateBackendError("boto3 is required for S3-backed state storage.") from exc
        self._s3_client = boto3.client("s3")
        return self._s3_client

    def _key(self, relative_path: str) -> str:
        return f"{self.prefix}{relative_path.lstrip('/')}"

    def exists(self, relative_path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(relative_path))
            return True
        except Exception as exc:
            response = getattr(exc, "response", None)
            error_code = ""
            if isinstance(response, dict):
                error_code = response.get("Error", {}).get("Code", "")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise StateBackendError(f"Failed to stat state object: {relative_path}") from exc

    def read_text(self, relative_path: str) -> str | None:
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self._key(relative_path))
            return obj["Body"].read().decode("utf-8")
        except Exception as exc:
            response = getattr(exc, "response", None)
            error_code = ""
            if isinstance(response, dict):
                error_code = response.get("Error", {}).get("Code", "")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise StateBackendError(f"Failed to read state object: {relative_path}") from exc

    def write_text(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=self._key(relative_path),
                Body=text.encode("utf-8"),
                ContentType=content_type,
            )
        except Exception as exc:
            raise StateBackendError(f"Failed to write state object: {relative_path}") from exc

    def list_prefix(self, relative_prefix: str) -> list[str]:
        prefix = self._key(relative_prefix)
        try:
            response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)
        except Exception as exc:
            raise StateBackendError(f"Failed to list state prefix: {relative_prefix}") from exc
        contents = response.get("Contents", []) or []
        results: list[str] = []
        for item in contents:
            key = item.get("Key")
            if not key or not key.startswith(self.prefix):
                continue
            results.append(key[len(self.prefix):])
        return results


def get_state_backend(*, data_dir: Path | None = None) -> StateBackend:
    storage_kind = os.getenv("DECISIONDOC_STATE_STORAGE") or os.getenv("DECISIONDOC_STORAGE", "local")
    if storage_kind.lower() == "s3":
        bucket = os.getenv("DECISIONDOC_STATE_S3_BUCKET") or os.getenv("DECISIONDOC_S3_BUCKET", "")
        prefix = os.getenv("DECISIONDOC_STATE_S3_PREFIX", "").strip()
        if not prefix:
            storage_prefix = os.getenv("DECISIONDOC_S3_PREFIX", "decisiondoc-ai/").strip()
            prefix = f"{storage_prefix.rstrip('/')}/state/"
        if not bucket:
            raise StateBackendError("DECISIONDOC_S3_BUCKET is required for S3-backed state storage.")
        return S3StateBackend(bucket=bucket, prefix=prefix)
    resolved_dir = Path(data_dir or os.getenv("DATA_DIR", "./data"))
    return LocalStateBackend(resolved_dir)
