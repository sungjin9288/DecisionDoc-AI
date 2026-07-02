"""app/services/attachment/constants.py — shared constants and the
``AttachmentError`` exception used across the attachment extraction package.

Includes per-file/global character caps, file-size limits, supported
extension sets, and legacy-format conversion hints.
"""
from __future__ import annotations

MAX_CHARS_PER_FILE  = 12_000   # ~3 000 tokens per file
MAX_CHARS           = MAX_CHARS_PER_FILE   # backward-compat alias
MAX_TOTAL_CHARS     = 20_000   # hard cap across all files in one request
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB

ALLOWED_EXTENSIONS = {
    ".txt", ".md",
    ".pdf",
    ".docx",
    ".pptx",
    ".hwp", ".hwpx",
    ".xlsx", ".xls",
    ".csv", ".tsv",
    ".json", ".jsonl", ".ndjson",
    ".yaml", ".yml",
    ".xml",
    ".html", ".htm",
    ".rtf",
    ".log", ".ini", ".cfg", ".conf",
    ".odt", ".ods", ".odp",
    ".zip",
}

PLAIN_TEXT_EXTENSIONS = {
    ".txt", ".md", ".log", ".ini", ".cfg", ".conf", ".jsonl", ".ndjson",
}
IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic", ".svg",
}
LEGACY_CONVERSION_HINTS = {
    ".doc": "구형 Word(.doc)는 직접 추출하지 못합니다. DOCX 또는 PDF로 변환해 업로드하세요.",
    ".ppt": "구형 PowerPoint(.ppt)는 직접 추출하지 못합니다. PPTX 또는 PDF로 변환해 업로드하세요.",
    ".xlsb": "바이너리 Excel(.xlsb)는 직접 추출하지 못합니다. XLSX, CSV 또는 PDF로 변환해 업로드하세요.",
    ".pages": "Apple Pages 문서는 직접 추출하지 못합니다. PDF 또는 DOCX로 변환해 업로드하세요.",
    ".numbers": "Apple Numbers 문서는 직접 추출하지 못합니다. XLSX 또는 CSV로 변환해 업로드하세요.",
    ".key": "Apple Keynote 문서는 직접 추출하지 못합니다. PPTX 또는 PDF로 변환해 업로드하세요.",
}
MAX_ZIP_MEMBERS = 20


class AttachmentError(Exception):
    """Raised when a file cannot be read or its format is unsupported."""
