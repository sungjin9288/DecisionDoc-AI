from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.storage.state")


class StateBackendError(Exception):
    """Raised when the shared state backend cannot read or write data."""


def _canonical_relative_path(relative_path: str) -> str:
    if not isinstance(relative_path, str) or not relative_path:
        raise StateBackendError("State path must be a non-empty relative path.")
    if relative_path != relative_path.strip():
        raise StateBackendError("State path must not contain leading or trailing whitespace.")
    has_control_character = any(
        ord(character) < 32 or ord(character) == 127
        for character in relative_path
    )
    if has_control_character or "\\" in relative_path or relative_path.startswith("/"):
        raise StateBackendError("State path must be a canonical relative path.")

    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise StateBackendError("State path must be a canonical relative path.")
    return relative_path


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
    def read_bytes(self, relative_path: str) -> bytes | None:
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
    def write_bytes(
        self,
        relative_path: str,
        raw: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, relative_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_prefix(self, relative_prefix: str) -> list[str]:
        raise NotImplementedError


class LocalStateBackend(StateBackend):
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._resolved_root = self.root.resolve()

    @property
    def kind(self) -> str:
        return "local"

    def _path(self, relative_path: str) -> Path:
        canonical_path = _canonical_relative_path(relative_path)
        candidate = self._resolved_root / canonical_path
        current = self._resolved_root
        for part in canonical_path.split("/"):
            current /= part
            if current.is_symlink():
                raise StateBackendError("State path contains a symbolic link.")

        path = candidate.resolve()
        if not path.is_relative_to(self._resolved_root):
            raise StateBackendError("State path escapes the configured local root.")
        return path

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

    def read_bytes(self, relative_path: str) -> bytes | None:
        path = self._path(relative_path)
        if not path.exists():
            return None
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StateBackendError(f"Failed to read state bytes: {path}") from exc

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

    def write_bytes(
        self,
        relative_path: str,
        raw: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        _ = content_type
        from app.storage.base import atomic_write_bytes

        path = self._path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(path, raw)

    def delete(self, relative_path: str) -> None:
        path = self._path(relative_path)
        if not path.exists():
            return
        if not path.is_file():
            raise StateBackendError(f"State path is not a file: {path}")
        try:
            path.unlink()
        except OSError as exc:
            raise StateBackendError(f"Failed to delete state file: {path}") from exc

    def list_prefix(self, relative_prefix: str) -> list[str]:
        prefix_path = self._path(relative_prefix)
        if prefix_path.is_file():
            return [_canonical_relative_path(relative_prefix)]
        if not prefix_path.exists():
            return []

        results: list[str] = []
        for path in prefix_path.rglob("*"):
            if path.is_symlink():
                raise StateBackendError("State prefix contains a symbolic link.")
            if path.is_file():
                results.append(path.relative_to(self._resolved_root).as_posix())
        return sorted(results)


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
        return f"{self.prefix}{_canonical_relative_path(relative_path)}"

    def exists(self, relative_path: str) -> bool:
        key = self._key(relative_path)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
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
        key = self._key(relative_path)
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read().decode("utf-8")
        except Exception as exc:
            response = getattr(exc, "response", None)
            error_code = ""
            if isinstance(response, dict):
                error_code = response.get("Error", {}).get("Code", "")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise StateBackendError(f"Failed to read state object: {relative_path}") from exc

    def read_bytes(self, relative_path: str) -> bytes | None:
        key = self._key(relative_path)
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        except Exception as exc:
            response = getattr(exc, "response", None)
            error_code = ""
            if isinstance(response, dict):
                error_code = response.get("Error", {}).get("Code", "")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise StateBackendError(f"Failed to read state bytes: {relative_path}") from exc

    def write_text(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        key = self._key(relative_path)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=text.encode("utf-8"),
                ContentType=content_type,
            )
        except Exception as exc:
            raise StateBackendError(f"Failed to write state object: {relative_path}") from exc

    def write_bytes(
        self,
        relative_path: str,
        raw: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> None:
        key = self._key(relative_path)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=raw,
                ContentType=content_type,
            )
        except Exception as exc:
            raise StateBackendError(f"Failed to write state bytes: {relative_path}") from exc

    def delete(self, relative_path: str) -> None:
        key = self._key(relative_path)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise StateBackendError(f"Failed to delete state object: {relative_path}") from exc

    def list_prefix(self, relative_prefix: str) -> list[str]:
        canonical_prefix = _canonical_relative_path(relative_prefix)
        object_prefix = self._key(canonical_prefix)
        continuation_token: str | None = None
        seen_tokens: set[str] = set()
        results: set[str] = set()

        while True:
            request: dict[str, Any] = {
                "Bucket": self.bucket,
                "Prefix": object_prefix,
            }
            if continuation_token is not None:
                request["ContinuationToken"] = continuation_token
            try:
                response = self.client.list_objects_v2(**request)
            except Exception as exc:
                raise StateBackendError(
                    f"Failed to list state prefix: {relative_prefix}"
                ) from exc

            for item in response.get("Contents", []) or []:
                key = item.get("Key")
                if not isinstance(key, str) or not key.startswith(self.prefix):
                    continue
                if key.endswith("/"):
                    continue
                relative_path = _canonical_relative_path(key[len(self.prefix):])
                if (
                    relative_path == canonical_prefix
                    or relative_path.startswith(f"{canonical_prefix}/")
                ):
                    results.add(relative_path)

            if not response.get("IsTruncated"):
                break
            next_token = response.get("NextContinuationToken")
            if (
                not isinstance(next_token, str)
                or not next_token
                or next_token in seen_tokens
            ):
                raise StateBackendError("S3 state listing returned an invalid continuation token.")
            seen_tokens.add(next_token)
            continuation_token = next_token

        return sorted(results)


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
