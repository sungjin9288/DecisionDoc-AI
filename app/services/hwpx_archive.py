"""Deterministic ZIP entry writing for HWPX exports."""
from __future__ import annotations

import zipfile


ENTRY_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def write_archive_entry(
    archive: zipfile.ZipFile,
    path: str,
    content: str | bytes,
    *,
    compress_type: int = zipfile.ZIP_DEFLATED,
) -> None:
    info = zipfile.ZipInfo(path, date_time=ENTRY_TIMESTAMP)
    info.compress_type = compress_type
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)
