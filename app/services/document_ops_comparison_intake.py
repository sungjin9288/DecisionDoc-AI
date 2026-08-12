"""Deterministic, in-memory intake for DocumentOps text comparison files."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.schemas.document_ops import DocumentOpsComparisonDocumentResponse
from app.services.attachment_service import (
    ALLOWED_EXTENSIONS,
    AttachmentError,
    MAX_CHARS_PER_FILE,
    MAX_FILE_SIZE_BYTES,
    extract_text,
)

MAX_COMPARISON_DOCUMENT_BYTES = MAX_FILE_SIZE_BYTES


class ComparisonDocumentIntakeError(ValueError):
    """A bounded, non-sensitive document intake failure."""


def _safe_filename(filename: str | None) -> str:
    value = str(filename or "").replace("\\", "/")
    basename = Path(value).name.strip()
    basename = re.sub(r"[\x00-\x1f\x7f]", "_", basename)
    if not basename or basename in {".", ".."}:
        raise ComparisonDocumentIntakeError("comparison document filename is required")
    if len(basename) > 255:
        raise ComparisonDocumentIntakeError("comparison document filename is too long")
    return basename


def _validate_input(filename: str, raw: bytes) -> None:
    if not raw:
        raise ComparisonDocumentIntakeError("comparison document is empty")
    if len(raw) > MAX_COMPARISON_DOCUMENT_BYTES:
        raise ComparisonDocumentIntakeError("comparison document exceeds the 20 MB limit")

    extension = Path(filename).suffix.lower()
    if extension == ".hwp":
        raise ComparisonDocumentIntakeError(
            "legacy binary HWP is not supported; convert it to HWPX, PDF, or DOCX",
        )
    if extension not in ALLOWED_EXTENSIONS:
        raise ComparisonDocumentIntakeError("unsupported comparison document type")


def extract_comparison_document(
    *,
    filename: str | None,
    raw: bytes,
) -> DocumentOpsComparisonDocumentResponse:
    """Extract one supported file with the existing local parser only.

    This function deliberately has no provider, runtime, storage, tenant, or
    request dependencies. Passing the sanitized basename to the extractor
    prevents an original path-bearing upload name from entering parser logs.
    """
    safe_filename = _safe_filename(filename)
    _validate_input(safe_filename, raw)
    try:
        extracted_text = extract_text(safe_filename, raw)
    except AttachmentError as exc:
        raise ComparisonDocumentIntakeError("comparison document could not be read") from exc

    if not extracted_text.strip():
        raise ComparisonDocumentIntakeError("comparison document has no readable text")

    source_sha256 = hashlib.sha256(raw).hexdigest()
    extracted_text_bytes = extracted_text.encode("utf-8")
    return DocumentOpsComparisonDocumentResponse(
        filename=safe_filename,
        source_size_bytes=len(raw),
        source_sha256=source_sha256,
        extracted_text=extracted_text,
        extracted_text_sha256=hashlib.sha256(extracted_text_bytes).hexdigest(),
        extracted_char_count=len(extracted_text),
        content_may_be_truncated=len(extracted_text) >= MAX_CHARS_PER_FILE,
    )
