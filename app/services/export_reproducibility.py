"""Stable file metadata for reproducible document exports."""
from __future__ import annotations

import re
import zipfile
from datetime import datetime
from io import BytesIO


ARCHIVE_ENTRY_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
DOCUMENT_CREATED_AT = datetime(2000, 1, 1)
_PDF_DATE = re.compile(rb"/(CreationDate|ModDate) \(D:\d{14}[+-]\d{2}'\d{2}'\)")


def write_archive_entry(
    archive: zipfile.ZipFile,
    path: str,
    content: str | bytes,
    *,
    compress_type: int = zipfile.ZIP_DEFLATED,
) -> None:
    info = zipfile.ZipInfo(path, date_time=ARCHIVE_ENTRY_TIMESTAMP)
    info.compress_type = compress_type
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def normalize_zip_metadata(content: bytes) -> bytes:
    source_buffer = BytesIO(content)
    output_buffer = BytesIO()
    with zipfile.ZipFile(source_buffer) as source, zipfile.ZipFile(output_buffer, "w") as output:
        for entry in source.infolist():
            write_archive_entry(
                output,
                entry.filename,
                source.read(entry),
                compress_type=entry.compress_type,
            )
    return output_buffer.getvalue()


def normalize_pdf_metadata(content: bytes) -> bytes:
    normalized = _PDF_DATE.sub(
        lambda match: b"/" + match.group(1) + b" (D:20000101000000+00'00')",
        content,
    )
    if len(normalized) != len(content):
        raise ValueError("PDF metadata normalization changed the document length")
    return normalized
