from __future__ import annotations

import fcntl
import hashlib
import logging
import os
import stat
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_log = logging.getLogger("decisiondoc.storage.state")
_LOCAL_LOCK_DIRECTORY = ".decisiondoc-state-locks"


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
    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        """Create text only when the state object does not already exist."""
        raise NotImplementedError

    @abstractmethod
    def write_bytes_if_absent(
        self,
        relative_path: str,
        raw: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> bool:
        """Create bytes only when the state object does not already exist."""
        raise NotImplementedError

    @abstractmethod
    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        """Replace text only when the persisted value still equals expected."""
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
        if canonical_path.split("/", 1)[0] == _LOCAL_LOCK_DIRECTORY:
            raise StateBackendError("State path uses a reserved internal prefix.")
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

    @contextmanager
    def _conditional_write_lock(self, path: Path) -> Iterator[None]:
        relative_path = path.relative_to(self._resolved_root).as_posix()
        lock_name = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
        lock_root = self._resolved_root / _LOCAL_LOCK_DIRECTORY
        try:
            if lock_root.is_symlink():
                raise StateBackendError("State lock path contains a symbolic link.")
            lock_root.mkdir(parents=True, exist_ok=True)
            directory_flags = os.O_RDONLY
            directory_flags |= getattr(os, "O_DIRECTORY", 0)
            directory_flags |= getattr(os, "O_NOFOLLOW", 0)
            lock_directory_fd = os.open(lock_root, directory_flags)
            try:
                lock_flags = os.O_RDWR | os.O_CREAT
                lock_flags |= getattr(os, "O_NOFOLLOW", 0)
                lock_fd = os.open(
                    f"{lock_name}.lock",
                    lock_flags,
                    0o600,
                    dir_fd=lock_directory_fd,
                )
                try:
                    if not stat.S_ISREG(os.fstat(lock_fd).st_mode):
                        raise StateBackendError(
                            "State conditional lock must be a regular file."
                        )
                    fcntl.flock(lock_fd, fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(lock_fd, fcntl.LOCK_UN)
                finally:
                    os.close(lock_fd)
            finally:
                os.close(lock_directory_fd)
        except StateBackendError:
            raise
        except OSError as exc:
            raise StateBackendError(
                f"Failed to lock state file for conditional write: {path}"
            ) from exc

    @staticmethod
    def _read_text_path(path: Path) -> str | None:
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise StateBackendError(f"Failed to read state file: {path}") from exc

    @staticmethod
    def _prepare_parent(path: Path) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StateBackendError(
                f"Failed to create state directory: {path.parent}"
            ) from exc

    def exists(self, relative_path: str) -> bool:
        return self._path(relative_path).exists()

    def read_text(self, relative_path: str) -> str | None:
        return self._read_text_path(self._path(relative_path))

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
        with self._conditional_write_lock(path):
            self._prepare_parent(path)
            try:
                atomic_write_text(path, text)
            except OSError as exc:
                raise StateBackendError(f"Failed to write state file: {path}") from exc

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
        with self._conditional_write_lock(path):
            self._prepare_parent(path)
            try:
                atomic_write_bytes(path, raw)
            except OSError as exc:
                raise StateBackendError(f"Failed to write state bytes: {path}") from exc

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        _ = content_type
        from app.storage.base import atomic_write_text

        path = self._path(relative_path)
        with self._conditional_write_lock(path):
            if path.exists():
                return False
            self._prepare_parent(path)
            try:
                atomic_write_text(path, text)
            except OSError as exc:
                raise StateBackendError(
                    f"Failed to conditionally write state file: {path}"
                ) from exc
        return True

    def write_bytes_if_absent(
        self,
        relative_path: str,
        raw: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> bool:
        _ = content_type
        from app.storage.base import atomic_write_bytes

        path = self._path(relative_path)
        with self._conditional_write_lock(path):
            if path.exists():
                return False
            self._prepare_parent(path)
            try:
                atomic_write_bytes(path, raw)
            except OSError as exc:
                raise StateBackendError(
                    f"Failed to conditionally write state bytes: {path}"
                ) from exc
        return True

    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        _ = content_type
        from app.storage.base import atomic_write_text

        path = self._path(relative_path)
        with self._conditional_write_lock(path):
            if self._read_text_path(path) != expected:
                return False
            self._prepare_parent(path)
            try:
                atomic_write_text(path, replacement)
            except OSError as exc:
                raise StateBackendError(
                    f"Failed to conditionally replace state file: {path}"
                ) from exc
        return True

    def delete(self, relative_path: str) -> None:
        path = self._path(relative_path)
        with self._conditional_write_lock(path):
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
            if (
                path == self._resolved_root / _LOCAL_LOCK_DIRECTORY
                or self._resolved_root / _LOCAL_LOCK_DIRECTORY in path.parents
            ):
                continue
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

    @staticmethod
    def _error_code(exc: Exception) -> str:
        response = getattr(exc, "response", None)
        if not isinstance(response, dict):
            return ""
        error = response.get("Error")
        if not isinstance(error, dict):
            return ""
        return str(error.get("Code") or "")

    @classmethod
    def _is_missing(cls, exc: Exception) -> bool:
        return cls._error_code(exc) in {"404", "NoSuchKey", "NotFound"}

    @classmethod
    def _is_conditional_conflict(cls, exc: Exception) -> bool:
        return cls._error_code(exc) in {
            "409",
            "412",
            "ConditionalRequestConflict",
            "PreconditionFailed",
        }

    def exists(self, relative_path: str) -> bool:
        key = self._key(relative_path)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            if self._is_missing(exc):
                return False
            raise StateBackendError(f"Failed to stat state object: {relative_path}") from exc

    def read_text(self, relative_path: str) -> str | None:
        key = self._key(relative_path)
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read().decode("utf-8")
        except Exception as exc:
            if self._is_missing(exc):
                return None
            raise StateBackendError(f"Failed to read state object: {relative_path}") from exc

    def read_bytes(self, relative_path: str) -> bytes | None:
        key = self._key(relative_path)
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        except Exception as exc:
            if self._is_missing(exc):
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

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        key = self._key(relative_path)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=text.encode("utf-8"),
                ContentType=content_type,
                IfNoneMatch="*",
            )
        except Exception as exc:
            if self._is_conditional_conflict(exc):
                return False
            raise StateBackendError(
                f"Failed to conditionally write state object: {relative_path}"
            ) from exc
        return True

    def write_bytes_if_absent(
        self,
        relative_path: str,
        raw: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> bool:
        key = self._key(relative_path)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=raw,
                ContentType=content_type,
                IfNoneMatch="*",
            )
        except Exception as exc:
            if self._is_conditional_conflict(exc):
                return False
            raise StateBackendError(
                f"Failed to conditionally write state bytes: {relative_path}"
            ) from exc
        return True

    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        key = self._key(relative_path)
        try:
            current = self.client.get_object(Bucket=self.bucket, Key=key)
            current_text = current["Body"].read().decode("utf-8")
            etag = current.get("ETag")
            if current_text != expected:
                return False
            if not isinstance(etag, str) or not etag:
                raise StateBackendError(
                    f"S3 state object has no ETag: {relative_path}"
                )
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=replacement.encode("utf-8"),
                ContentType=content_type,
                IfMatch=etag,
            )
        except StateBackendError:
            raise
        except Exception as exc:
            if self._is_missing(exc) or self._is_conditional_conflict(exc):
                return False
            raise StateBackendError(
                f"Failed to conditionally replace state object: {relative_path}"
            ) from exc
        return True

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
