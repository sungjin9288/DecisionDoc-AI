"""app/services/attachment/core.py — public API, extension dispatch, and
multi-file orchestration for attachment text extraction.

Supported formats:
- .txt / .md  : read as-is (UTF-8, latin-1 fallback)
- .pdf        : pdfplumber — text layer + table extraction
- .docx       : python-docx — paragraphs + tables in document order
- .hwp / .hwpx: ZIP+XML parsing (HWPX format)
- .xlsx / .xls: openpyxl — sheet/row/cell extraction
- .csv        : stdlib csv module
- .pptx       : python-pptx — slide title + body text extraction
- .json / .yaml / .xml / .html / .rtf : structured text normalization
- .odt / .ods / .odp                   : OpenDocument ZIP+XML extraction
- .zip                                 : supported documents inside ZIP

Per-file cap: MAX_CHARS_PER_FILE (12 000 chars / ~3 000 tokens).
Global cap:   MAX_TOTAL_CHARS   (20 000 chars) across all files in one call.
File size:    MAX_FILE_SIZE_BYTES (20 MB).
"""
from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from app.services.attachment.constants import (
    ALLOWED_EXTENSIONS,
    IMAGE_EXTENSIONS,
    LEGACY_CONVERSION_HINTS,
    MAX_CHARS_PER_FILE,
    MAX_FILE_SIZE_BYTES,
    MAX_TOTAL_CHARS,
    MAX_ZIP_MEMBERS,
    PLAIN_TEXT_EXTENSIONS,
    AttachmentError,
)
from app.services.attachment.format_extractors import (
    _extract_csv,
    _extract_docx,  # noqa: F401 — re-imported for facade parity; dispatch calls via _facade for patchability
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
)
from app.services.attachment.pdf_extraction import (  # noqa: F401 — see _extract_docx note above
    _extract_pdf,
    extract_pdf_structured,
)

_log = logging.getLogger("decisiondoc.attachment")


# ── Public API ────────────────────────────────────────────────────────────────

def extract_text(filename: str, raw: bytes) -> str:
    """Extract plain text from *raw* bytes.

    Args:
        filename: Original filename — used to detect the extension.
        raw:      Raw file bytes.

    Returns:
        Extracted text, truncated to MAX_CHARS_PER_FILE.

    Raises:
        AttachmentError: on unsupported format, missing optional library,
                         parse failure, or file-size limit exceeded.
    """
    if len(raw) > MAX_FILE_SIZE_BYTES:
        mb = len(raw) // (1024 * 1024)
        raise AttachmentError(
            f"{filename}: 파일 크기 {mb} MB 초과 (최대 20 MB)"
        )

    return _extract_by_extension(filename, raw, allow_zip=True)


def extract_text_with_ai_fallback(
    filename: str,
    raw: bytes,
    *,
    provider: Any | None = None,
    request_id: str = "",
) -> str:
    """Extract text locally first, then fall back to provider OCR/vision when needed.

    The local parser remains the source of truth for structured document formats.
    Provider fallback is only attempted for image files or PDFs that look like
    scanned documents with no readable text layer.
    """
    try:
        return extract_text(filename, raw)
    except AttachmentError as exc:
        markitdown_text = _try_markitdown_fallback(filename, raw, exc)
        if markitdown_text:
            return markitdown_text
        if provider is None or not _should_try_provider_fallback(filename, exc):
            raise
        try:
            text = provider.extract_attachment_text(filename, raw, request_id=request_id)
        except Exception as provider_exc:
            raise AttachmentError(
                f"{filename}: 이미지/PDF OCR·비전 추출 실패 ({provider_exc})"
            ) from provider_exc
        if not text.strip():
            raise AttachmentError(f"{filename}: OCR/비전 추출 결과가 비어 있습니다")
        return text[:MAX_CHARS_PER_FILE]


def _try_markitdown_fallback(filename: str, raw: bytes, exc: AttachmentError) -> str | None:
    """Best-effort MarkItDown fallback for already-uploaded file bytes."""
    if _should_try_provider_fallback(filename, exc):
        return None
    try:
        from app.services.markitdown_adapter import (
            MarkItDownAdapterError,
            convert_upload_to_markdown,
            should_try_markitdown,
        )
    except Exception as import_exc:  # pragma: no cover - defensive import boundary
        _log.debug("[Attachment] MarkItDown adapter unavailable: %s", import_exc)
        return None
    if not should_try_markitdown(filename):
        return None
    try:
        return convert_upload_to_markdown(filename, raw)[:MAX_CHARS_PER_FILE]
    except MarkItDownAdapterError as md_exc:
        _log.info("[Attachment] MarkItDown fallback skipped for %s: %s", filename, md_exc)
        return None


def _should_try_provider_fallback(filename: str, exc: AttachmentError) -> bool:
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return True
    if ext == ".pdf" and _is_scanned_pdf_error(exc):
        return True
    return False


def _is_scanned_pdf_error(exc: AttachmentError) -> bool:
    message = str(exc)
    return "스캔 이미지 PDF일 수 있습니다" in message


def _extract_by_extension(filename: str, raw: bytes, *, allow_zip: bool) -> str:
    ext = Path(filename).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        raise AttachmentError(
            f"{filename}: 이미지 파일은 아직 본문 OCR/비전 분석을 지원하지 않습니다. "
            "이미지를 PDF/DOCX/PPTX에 포함하거나 설명 텍스트를 함께 업로드하세요."
        )
    if ext in LEGACY_CONVERSION_HINTS:
        raise AttachmentError(f"{filename}: {LEGACY_CONVERSION_HINTS[ext]}")
    if ext not in ALLOWED_EXTENSIONS:
        raise AttachmentError(
            f"지원하지 않는 파일 형식입니다: '{ext}'. "
            f"지원 형식: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    try:
        if ext == ".pdf":
            # Imported lazily so `monkeypatch.setattr("app.services.attachment_service._extract_pdf", ...)`
            # (a patch target predating the package split) still takes effect here.
            import app.services.attachment_service as _facade
            return _facade._extract_pdf(raw, filename)
        if ext == ".docx":
            import app.services.attachment_service as _facade
            return _facade._extract_docx(raw, filename)
        if ext == ".pptx":
            return _extract_pptx(raw, filename)
        if ext in (".hwp", ".hwpx"):
            return _extract_hwpx(raw, filename)
        if ext in (".xlsx", ".xls"):
            return _extract_excel(raw, filename)
        if ext in (".csv", ".tsv"):
            return _extract_csv(raw, delimiter="\t" if ext == ".tsv" else ",")
        if ext == ".json":
            return _extract_json(raw, filename)
        if ext in (".yaml", ".yml"):
            return _extract_yaml(raw, filename)
        if ext == ".xml":
            return _extract_xml(raw, filename)
        if ext in (".html", ".htm"):
            return _extract_html(raw)
        if ext == ".rtf":
            return _extract_rtf(raw)
        if ext in PLAIN_TEXT_EXTENSIONS:
            return _extract_plain(raw)
        if ext in (".odt", ".ods", ".odp"):
            return _extract_opendocument(raw, filename)
        if ext == ".zip":
            if not allow_zip:
                raise AttachmentError(f"{filename}: ZIP 내부의 중첩 ZIP은 처리하지 않습니다")
            return _extract_zip(raw, filename)
        return _extract_plain(raw)
    except AttachmentError:
        raise
    except Exception as exc:
        _log.error("[Attachment] Failed to parse %s: %s", filename, exc)
        raise AttachmentError(f"{filename} 파싱 실패: {exc}") from exc


def extract_multiple(
    files: list[tuple[str, bytes]],
    *,
    provider: Any | None = None,
    request_id: str = "",
) -> str:
    """Extract text from multiple files with a global character cap.

    Files that fail to parse emit a warning line instead of raising so that
    a single bad file does not block the rest.

    Args:
        files: List of ``(filename, raw_bytes)`` pairs.

    Returns:
        Structured text blocks separated by ``\\n\\n---\\n\\n``.
    """
    parts: list[str] = []
    total = 0

    for filename, raw in files:
        try:
            text = extract_text_with_ai_fallback(
                filename,
                raw,
                provider=provider,
                request_id=request_id,
            )
        except AttachmentError as exc:
            parts.append(f"[첨부파일: {filename}]\n⚠️ {exc}")
            _log.warning("[Attachment] %s", exc)
            continue

        remaining = MAX_TOTAL_CHARS - total
        if remaining <= 0:
            _log.warning(
                "[Attachment] Skipping %s: total char limit reached", filename
            )
            break
        if len(text) > remaining:
            if remaining > 500:
                text = text[:remaining] + "\n...(이하 생략)"
            else:
                _log.warning(
                    "[Attachment] Skipping %s: total char limit reached", filename
                )
                break

        parts.append(f"[첨부파일: {filename}]\n{text}")
        total += len(text)

    return "\n\n---\n\n".join(parts)


# ── ZIP archive traversal (mutually recursive with _extract_by_extension) ──────

def _extract_zip(raw: bytes, filename: str) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            if not infos:
                raise AttachmentError(f"{filename}: ZIP 안에 읽을 파일이 없습니다")

            parts: list[str] = []
            for info in infos[:MAX_ZIP_MEMBERS]:
                inner_name = Path(info.filename).name or info.filename
                inner_ext = Path(inner_name).suffix.lower()
                if inner_ext == ".zip":
                    parts.append(f"[압축 내부 파일: {info.filename}]\n⚠️ 중첩 ZIP은 건너뜁니다.")
                    continue
                if inner_ext in IMAGE_EXTENSIONS:
                    parts.append(
                        f"[압축 내부 파일: {info.filename}]\n⚠️ 이미지 파일은 OCR/비전 분석을 아직 지원하지 않아 건너뜁니다."
                    )
                    continue
                if inner_ext in LEGACY_CONVERSION_HINTS:
                    parts.append(f"[압축 내부 파일: {info.filename}]\n⚠️ {LEGACY_CONVERSION_HINTS[inner_ext]}")
                    continue
                if inner_ext not in ALLOWED_EXTENSIONS:
                    parts.append(f"[압축 내부 파일: {info.filename}]\n⚠️ 지원하지 않는 형식이라 건너뜁니다.")
                    continue
                if info.file_size > MAX_FILE_SIZE_BYTES:
                    parts.append(
                        f"[압축 내부 파일: {info.filename}]\n⚠️ 파일 크기가 20 MB를 초과해 건너뜁니다."
                    )
                    continue

                inner_raw = zf.read(info)
                try:
                    text = _extract_by_extension(inner_name, inner_raw, allow_zip=False)
                except AttachmentError as exc:
                    parts.append(f"[압축 내부 파일: {info.filename}]\n⚠️ {exc}")
                    continue
                parts.append(f"[압축 내부 파일: {info.filename}]\n{text}")
    except zipfile.BadZipFile as exc:
        raise AttachmentError(f"{filename}: 유효하지 않은 ZIP 파일입니다") from exc

    result = "\n\n---\n\n".join(parts)
    if not result.strip():
        raise AttachmentError(f"{filename}: ZIP 안에서 읽을 수 있는 텍스트를 찾지 못했습니다")
    return result[:MAX_CHARS_PER_FILE]
