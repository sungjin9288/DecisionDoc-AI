from __future__ import annotations

import hashlib
import threading
import time
from pathlib import Path
from typing import Callable

from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class MemoryS3Client:
    """In-memory S3 subset with conditional-write and lost-response behavior."""

    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay
        self._lock = threading.Lock()
        self._before_key_fragment: str | None = None
        self._before_write: Callable[[], None] | None = None
        self._fail_after_key_fragment: str | None = None
        self._after_failed_write: Callable[[], None] | None = None

    @staticmethod
    def _etag(data: bytes) -> str:
        return f'"{hashlib.sha256(data).hexdigest()}"'

    @staticmethod
    def _error(code: str) -> Exception:
        error = RuntimeError(code)
        error.response = {"Error": {"Code": code}}
        return error

    def fail_after_next_conditional_write(
        self,
        *,
        key_fragment: str,
        after_write: Callable[[], None] | None = None,
    ) -> None:
        self._fail_after_key_fragment = key_fragment
        self._after_failed_write = after_write

    def before_next_conditional_write(
        self,
        *,
        key_fragment: str,
        callback: Callable[[], None],
    ) -> None:
        self._before_key_fragment = key_fragment
        self._before_write = callback

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
        IfNoneMatch: str | None = None,
        IfMatch: str | None = None,
    ) -> None:
        _ = ContentType
        with self._lock:
            should_run_before = (
                (IfNoneMatch is not None or IfMatch is not None)
                and self._before_key_fragment is not None
                and self._before_key_fragment in Key
            )
            if should_run_before:
                self._before_key_fragment = None
                before_write = self._before_write
                self._before_write = None
            else:
                before_write = None

        if before_write is not None:
            before_write()

        with self._lock:
            current = self.objects.get((Bucket, Key))
            if IfNoneMatch == "*" and current is not None:
                raise self._error("PreconditionFailed")
            if IfMatch is not None and (
                current is None or self._etag(current) != IfMatch
            ):
                raise self._error("PreconditionFailed")

            self.objects[(Bucket, Key)] = Body
            should_fail = (
                (IfNoneMatch is not None or IfMatch is not None)
                and self._fail_after_key_fragment is not None
                and self._fail_after_key_fragment in Key
            )
            if should_fail:
                self._fail_after_key_fragment = None
                after_write = self._after_failed_write
                self._after_failed_write = None
            else:
                after_write = None

        if not should_fail:
            return
        if after_write is not None:
            after_write()
        raise self._error("InternalError")

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        time.sleep(self.read_delay)
        with self._lock:
            data = self.objects.get((Bucket, Key))
        if data is None:
            raise self._error("NoSuchKey")
        return {"Body": _Body(data), "ETag": self._etag(data)}


class ConflictingLocalBackend(LocalStateBackend):
    """Return a bounded stream of conditional conflicts for one state object."""

    def __init__(self, root: Path, *, conflict_suffix: str) -> None:
        super().__init__(root)
        self.conflict_suffix = conflict_suffix
        self.attempts = 0

    def write_text_if_absent(
        self,
        relative_path: str,
        text: str,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if relative_path.endswith(self.conflict_suffix):
            self.attempts += 1
            return False
        return super().write_text_if_absent(
            relative_path,
            text,
            content_type=content_type,
        )

    def replace_text_if_equal(
        self,
        relative_path: str,
        *,
        expected: str,
        replacement: str,
        content_type: str = "application/json; charset=utf-8",
    ) -> bool:
        if relative_path.endswith(self.conflict_suffix):
            self.attempts += 1
            return False
        return super().replace_text_if_equal(
            relative_path,
            expected=expected,
            replacement=replacement,
            content_type=content_type,
        )


def s3_backend(
    client: MemoryS3Client | None = None,
    *,
    read_delay: float = 0.0,
) -> tuple[S3StateBackend, MemoryS3Client]:
    selected_client = client or MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=selected_client,
    )
    return backend, selected_client
