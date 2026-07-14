"""Publish an immutable local file without a check-then-replace race."""
from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4


def write_bytes_once(path: Path, content: bytes, *, label: str) -> None:
    """Atomically create a complete file and refuse every overwrite race."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    try:
        with temporary_path.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError as exc:
            raise ValueError(f"refusing to overwrite existing {label}: {path}") from exc
    finally:
        temporary_path.unlink(missing_ok=True)
