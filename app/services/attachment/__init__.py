"""attachment_service — extract plain text from uploaded files.

The implementation lives in this package, split into focused modules:

- ``constants``: shared size caps, allowed/legacy extension sets, and the
  ``AttachmentError`` exception.
- ``pdf_extraction``: pdfplumber-based PDF extraction — both the flat-text
  extractor (``_extract_pdf``) and the structured extractor
  (``extract_pdf_structured``), plus char-level line reconstruction helpers.
- ``format_extractors``: all non-PDF format extractors — DOCX, PPTX, HWPX,
  Excel, CSV/TSV, JSON, YAML, XML, HTML, RTF, OpenDocument, plain text.
- ``core``: public API (``extract_text``, ``extract_text_with_ai_fallback``,
  ``extract_multiple``), extension dispatch (``_extract_by_extension``), and
  ZIP archive traversal (``_extract_zip``, mutually recursive with the
  dispatch function).

This package re-exports the full public and internal API so existing
``from app.services.attachment_service import X`` imports keep working
unchanged.
"""
from __future__ import annotations

from app.services.attachment.constants import (
    ALLOWED_EXTENSIONS,
    IMAGE_EXTENSIONS,
    LEGACY_CONVERSION_HINTS,
    MAX_CHARS,
    MAX_CHARS_PER_FILE,
    MAX_FILE_SIZE_BYTES,
    MAX_TOTAL_CHARS,
    MAX_ZIP_MEMBERS,
    PLAIN_TEXT_EXTENSIONS,
    AttachmentError,
)
from app.services.attachment.pdf_extraction import (
    _extract_pdf,
    _pdf_char_width,
    _reconstruct_pdf_line_text,
    _should_insert_pdf_space,
    extract_pdf_structured,
)
from app.services.attachment.format_extractors import (
    _decode_rtf_unicode,
    _extract_csv,
    _extract_docx,
    _extract_excel,
    _extract_html,
    _extract_hwpx,
    _extract_json,
    _extract_opendocument,
    _extract_plain,
    _extract_pptx,
    _extract_rtf,
    _extract_xml,
    _extract_yaml,
    _local_name,
)
from app.services.attachment.core import (
    _extract_by_extension,
    _extract_zip,
    _is_scanned_pdf_error,
    _log,
    _should_try_provider_fallback,
    _try_markitdown_fallback,
    extract_multiple,
    extract_text,
    extract_text_with_ai_fallback,
)

__all__ = [
    "AttachmentError",
    "MAX_CHARS_PER_FILE",
    "MAX_CHARS",
    "MAX_TOTAL_CHARS",
    "MAX_FILE_SIZE_BYTES",
    "ALLOWED_EXTENSIONS",
    "PLAIN_TEXT_EXTENSIONS",
    "IMAGE_EXTENSIONS",
    "LEGACY_CONVERSION_HINTS",
    "MAX_ZIP_MEMBERS",
    "extract_text",
    "extract_text_with_ai_fallback",
    "extract_multiple",
    "extract_pdf_structured",
]
