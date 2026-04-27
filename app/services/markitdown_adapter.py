"""Safe MarkItDown adapter for uploaded document conversion.

The adapter intentionally accepts only bytes already uploaded to DecisionDoc.
It never passes user-controlled paths or URLs to MarkItDown, which keeps the
runtime path aligned with MarkItDown's own security guidance.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

from app.config import (
    get_markitdown_max_chars,
    is_markitdown_enabled,
    is_markitdown_plugins_enabled,
)


class MarkItDownAdapterError(Exception):
    """Raised when MarkItDown conversion is disabled, unavailable, or fails."""


_URL_LIKE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
_SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".xls",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".rtf",
    ".odt",
    ".ods",
    ".odp",
    ".zip",
}


def _safe_filename(filename: str) -> str:
    name = Path(str(filename or "attachment")).name.strip()
    return name or "attachment"


def _is_url_like(value: str) -> bool:
    text = str(value or "").strip()
    return bool(_URL_LIKE_RE.match(text)) or text.startswith("//")


def _load_markitdown() -> tuple[type[Any], type[Any]]:
    try:
        from markitdown import MarkItDown, StreamInfo  # type: ignore
    except ImportError as exc:
        raise MarkItDownAdapterError(
            "markitdown is not installed. Install optional integrations with "
            "`pip install -r requirements-integrations.txt`."
        ) from exc
    return MarkItDown, StreamInfo


def should_try_markitdown(filename: str) -> bool:
    """Return whether the upload is eligible for MarkItDown fallback."""
    if not is_markitdown_enabled():
        return False
    if _is_url_like(filename):
        return False
    return Path(_safe_filename(filename)).suffix.lower() in _SUPPORTED_EXTENSIONS


def convert_upload_to_markdown(filename: str, raw: bytes) -> str:
    """Convert an uploaded file byte stream to Markdown with MarkItDown.

    Args:
        filename: Original upload filename. Only its basename and extension are used.
        raw: Uploaded file bytes.

    Returns:
        Markdown text truncated by `DECISIONDOC_MARKITDOWN_MAX_CHARS`.

    Raises:
        MarkItDownAdapterError: if disabled, unsupported, unavailable, or empty.
    """
    if not is_markitdown_enabled():
        raise MarkItDownAdapterError("MarkItDown fallback is disabled.")
    if _is_url_like(filename):
        raise MarkItDownAdapterError("URL-like upload names are not accepted.")

    safe_name = _safe_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in _SUPPORTED_EXTENSIONS:
        raise MarkItDownAdapterError(f"Unsupported MarkItDown fallback type: {extension}")

    MarkItDown, StreamInfo = _load_markitdown()
    converter = MarkItDown(enable_plugins=is_markitdown_plugins_enabled())
    stream = io.BytesIO(raw)
    try:
        result = converter.convert_stream(
            stream,
            stream_info=StreamInfo(filename=safe_name, extension=extension),
        )
    except Exception as exc:
        raise MarkItDownAdapterError(f"MarkItDown conversion failed: {exc}") from exc

    text = str(getattr(result, "text_content", "") or "").strip()
    if not text:
        raise MarkItDownAdapterError("MarkItDown conversion returned empty text.")
    return text[: max(1, get_markitdown_max_chars())]
