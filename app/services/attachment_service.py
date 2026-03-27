"""app/services/attachment_service.py — Extract plain text from uploaded files.

Supported formats:
- .txt / .md  : read as-is (UTF-8, latin-1 fallback)
- .pdf        : pdfplumber — text layer + table extraction
- .docx       : python-docx — paragraphs + tables in document order
- .hwp / .hwpx: ZIP+XML parsing (HWPX format)
- .xlsx / .xls: openpyxl — sheet/row/cell extraction
- .csv        : stdlib csv module
- .pptx       : python-pptx — slide title + body text extraction

Per-file cap: MAX_CHARS_PER_FILE (12 000 chars / ~3 000 tokens).
Global cap:   MAX_TOTAL_CHARS   (20 000 chars) across all files in one call.
File size:    MAX_FILE_SIZE_BYTES (20 MB).
"""
from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from pathlib import Path

_log = logging.getLogger("decisiondoc.attachment")

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
    ".csv",
}


class AttachmentError(Exception):
    """Raised when a file cannot be read or its format is unsupported."""


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

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise AttachmentError(
            f"지원하지 않는 파일 형식입니다: '{ext}'. "
            f"지원 형식: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    try:
        if ext == ".pdf":
            return _extract_pdf(raw, filename)
        if ext == ".docx":
            return _extract_docx(raw, filename)
        if ext == ".pptx":
            return _extract_pptx(raw, filename)
        if ext in (".hwp", ".hwpx"):
            return _extract_hwpx(raw, filename)
        if ext in (".xlsx", ".xls"):
            return _extract_excel(raw, filename)
        if ext == ".csv":
            return _extract_csv(raw)
        # .txt / .md
        return _extract_plain(raw)
    except AttachmentError:
        raise
    except Exception as exc:
        _log.error("[Attachment] Failed to parse %s: %s", filename, exc)
        raise AttachmentError(f"{filename} 파싱 실패: {exc}") from exc


def extract_multiple(files: list[tuple[str, bytes]]) -> str:
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
            text = extract_text(filename, raw)
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


# ── Internal helpers ──────────────────────────────────────────────────────────

def _extract_pdf(raw: bytes, filename: str) -> str:
    """Extract structured text from PDF using pdfplumber.

    Uses per-character font metadata when available to mark headings and bold
    text. Falls back to ``extract_text()`` when char-level data is unavailable.
    Tables are preserved as ``[표]\\n...`` blocks. Section boundaries are marked
    with ``---`` dividers.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise AttachmentError(
            "PDF 파싱 라이브러리가 설치되어 있지 않습니다. "
            "'pip install pdfplumber'를 실행하세요."
        ) from exc

    sections: list[str] = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        prev_had_content = False
        for page in pdf.pages:
            # ── Tables ────────────────────────────────────────────────────────
            for table in page.extract_tables() or []:
                if not table:
                    continue
                rows = []
                for row in table:
                    cells = [str(c or "").strip() for c in row]
                    if any(cells):
                        rows.append(" | ".join(cells))
                if rows:
                    sections.append("[표]\n" + "\n".join(rows))

            # ── Char-level structured extraction ──────────────────────────────
            try:
                chars = page.chars
                if not chars:
                    raise ValueError("no chars")

                # Compute average font size for the page
                sizes = [ch.get("size", 0) for ch in chars if ch.get("size")]
                avg_size = sum(sizes) / len(sizes) if sizes else 0.0

                # Group chars into lines by their top coordinate (y)
                lines: dict[float, list[dict]] = {}
                for ch in chars:
                    y = round(ch.get("top", 0), 1)
                    lines.setdefault(y, []).append(ch)

                page_parts: list[str] = []
                for y_key in sorted(lines):
                    line_chars = sorted(lines[y_key], key=lambda c: c.get("x0", 0))
                    line_text = "".join(c.get("text", "") for c in line_chars).strip()
                    if not line_text:
                        continue

                    # Determine dominant font size + bold for the line
                    line_sizes = [c.get("size", 0) for c in line_chars if c.get("size")]
                    line_avg_size = sum(line_sizes) / len(line_sizes) if line_sizes else 0.0
                    is_bold = any("Bold" in (c.get("fontname") or "") for c in line_chars)
                    is_heading = avg_size > 0 and line_avg_size > avg_size * 1.2

                    if is_heading:
                        page_parts.append(f"## {line_text}")
                    elif is_bold:
                        page_parts.append(f"**{line_text}**")
                    else:
                        page_parts.append(line_text)

                if page_parts:
                    page_text = "\n".join(page_parts)
                    if prev_had_content:
                        sections.append("---")
                    sections.append(page_text)
                    prev_had_content = True

            except Exception:
                # Fallback: use plain extract_text()
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text and text.strip():
                    if prev_had_content:
                        sections.append("---")
                    sections.append(text.strip())
                    prev_had_content = True

    result = "\n\n".join(sections)
    if not result.strip():
        raise AttachmentError(
            f"{filename}: 텍스트를 추출할 수 없습니다 "
            "(스캔 이미지 PDF일 수 있습니다)"
        )
    return result[:MAX_CHARS_PER_FILE]


def extract_pdf_structured(raw: bytes, filename: str) -> dict:
    """Extract structured content from a PDF file.

    Uses pdfplumber char-level data to detect headings and build a section
    hierarchy. Falls back gracefully when char-level extraction is unavailable.

    Args:
        raw:      Raw PDF bytes.
        filename: Original filename (used in error messages).

    Returns:
        A dict with the following keys:

        * ``title``      — First detected heading (str, empty if none found).
        * ``sections``   — List of ``{"heading": str, "content": str}`` dicts.
        * ``raw_text``   — Full extracted text (plain, no markdown markup).
        * ``page_count`` — Number of pages in the PDF.
        * ``has_tables`` — True if at least one table was found.

    Raises:
        AttachmentError: When pdfplumber is not installed or the file cannot
                         be parsed.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise AttachmentError(
            "PDF 파싱 라이브러리가 설치되어 있지 않습니다. "
            "'pip install pdfplumber'를 실행하세요."
        ) from exc

    page_count = 0
    has_tables = False
    raw_text_parts: list[str] = []

    # Sections built incrementally: current heading + accumulated body lines
    detected_sections: list[dict] = []
    current_heading: str = ""
    current_body_lines: list[str] = []

    def _flush_section() -> None:
        nonlocal current_heading, current_body_lines
        content = "\n".join(current_body_lines).strip()
        if current_heading or content:
            detected_sections.append({"heading": current_heading, "content": content})
        current_heading = ""
        current_body_lines = []

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            # Check for tables
            tables = page.extract_tables() or []
            if tables:
                has_tables = True
            for table in tables:
                if not table:
                    continue
                rows = []
                for row in table:
                    cells = [str(c or "").strip() for c in row]
                    if any(cells):
                        rows.append(" | ".join(cells))
                if rows:
                    raw_text_parts.append("\n".join(rows))

            # Char-level extraction for heading detection
            try:
                chars = page.chars
                if not chars:
                    raise ValueError("no chars")

                sizes = [ch.get("size", 0) for ch in chars if ch.get("size")]
                avg_size = sum(sizes) / len(sizes) if sizes else 0.0

                lines: dict[float, list[dict]] = {}
                for ch in chars:
                    y = round(ch.get("top", 0), 1)
                    lines.setdefault(y, []).append(ch)

                for y_key in sorted(lines):
                    line_chars = sorted(lines[y_key], key=lambda c: c.get("x0", 0))
                    line_text = "".join(c.get("text", "") for c in line_chars).strip()
                    if not line_text:
                        continue

                    raw_text_parts.append(line_text)

                    line_sizes = [c.get("size", 0) for c in line_chars if c.get("size")]
                    line_avg_size = sum(line_sizes) / len(line_sizes) if line_sizes else 0.0
                    is_heading = avg_size > 0 and line_avg_size > avg_size * 1.2

                    if is_heading:
                        _flush_section()
                        current_heading = line_text
                    else:
                        current_body_lines.append(line_text)

            except Exception:
                # Fallback to plain text
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text and text.strip():
                    raw_text_parts.append(text.strip())
                    current_body_lines.append(text.strip())

    _flush_section()

    raw_text = "\n".join(raw_text_parts).strip()

    # Derive title: first heading, or first non-empty line of raw_text
    title = ""
    if detected_sections and detected_sections[0]["heading"]:
        title = detected_sections[0]["heading"]
    elif raw_text:
        title = raw_text.splitlines()[0].strip()

    return {
        "title": title,
        "sections": detected_sections,
        "raw_text": raw_text,
        "page_count": page_count,
        "has_tables": has_tables,
    }


def _extract_docx(raw: bytes, filename: str) -> str:
    """Extract text from DOCX including tables, preserving document order."""
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError as exc:
        raise AttachmentError(
            "DOCX 파싱 라이브러리가 설치되어 있지 않습니다. "
            "'pip install python-docx'를 실행하세요."
        ) from exc

    doc = Document(io.BytesIO(raw))
    sections: list[str] = []

    for block in doc.element.body:
        tag = block.tag.split("}")[-1] if "}" in block.tag else block.tag

        if tag == "p":
            para = Paragraph(block, doc)
            text = para.text.strip()
            if text:
                sections.append(text)

        elif tag == "tbl":
            table = Table(block, doc)
            rows = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                sections.append("[표]\n" + "\n".join(rows))

    return "\n".join(sections)[:MAX_CHARS_PER_FILE]


def _extract_hwpx(raw: bytes, filename: str) -> str:
    """Extract text from HWPX (ZIP + XML format)."""
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            section_files = sorted(
                f for f in zf.namelist()
                if re.match(r"Contents/section\d+\.xml", f)
            )
            if not section_files:
                raise AttachmentError(
                    f"{filename}: HWPX 섹션 파일을 찾을 수 없습니다"
                )
            texts: list[str] = []
            for sf in section_files:
                xml = zf.read(sf).decode("utf-8", errors="ignore")
                # <hh:t> or <t> tags carry the visible text
                matches = re.findall(
                    r"<(?:hh:)?t[^>]*>([^<]+)</(?:hh:)?t>", xml
                )
                texts.extend(m.strip() for m in matches if m.strip())

    except zipfile.BadZipFile as exc:
        raise AttachmentError(
            f"{filename}: 유효하지 않은 HWP 파일입니다"
        ) from exc

    result = "\n".join(texts)
    if not result:
        raise AttachmentError(f"{filename}: 텍스트를 추출할 수 없습니다")
    return result[:MAX_CHARS_PER_FILE]


def _extract_excel(raw: bytes, filename: str) -> str:
    """Extract text from Excel (.xlsx / .xls) via openpyxl."""
    try:
        import openpyxl
    except ImportError as exc:
        raise AttachmentError(
            "Excel 파싱 라이브러리가 설치되어 있지 않습니다. "
            "'pip install openpyxl'를 실행하세요."
        ) from exc

    wb = openpyxl.load_workbook(
        io.BytesIO(raw), read_only=True, data_only=True
    )
    sheets: list[str] = []
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows: list[str] = []
        for row in ws.iter_rows(values_only=True):
            cells = [str(c).strip() if c is not None else "" for c in row]
            if any(c for c in cells if c):
                rows.append(" | ".join(cells))
        if rows:
            sheets.append(f"[시트: {sheet_name}]\n" + "\n".join(rows))
    wb.close()

    return "\n\n".join(sheets)[:MAX_CHARS_PER_FILE]


def _extract_csv(raw: bytes) -> str:
    """Extract text from CSV."""
    text = raw.decode("utf-8", errors="ignore")
    reader = csv.reader(io.StringIO(text))
    rows = [" | ".join(row) for row in reader if any(row)]
    return "\n".join(rows)[:MAX_CHARS_PER_FILE]


def _extract_pptx(raw: bytes, filename: str) -> str:
    """Extract text from PPTX — slide title + body text in slide order."""
    try:
        from pptx import Presentation
        from pptx.util import Pt  # noqa: F401 — confirms pptx is available
    except ImportError as exc:
        raise AttachmentError(
            "PPTX 파싱 라이브러리가 설치되어 있지 않습니다. "
            "'pip install python-pptx'를 실행하세요."
        ) from exc

    prs = Presentation(io.BytesIO(raw))
    slides: list[str] = []

    for i, slide in enumerate(prs.slides, start=1):
        parts: list[str] = []
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                text = "".join(run.text for run in para.runs).strip()
                if text:
                    parts.append(text)
        if parts:
            slides.append(f"[슬라이드 {i}]\n" + "\n".join(parts))

    result = "\n\n".join(slides)
    if not result.strip():
        raise AttachmentError(f"{filename}: 텍스트를 추출할 수 없습니다")
    return result[:MAX_CHARS_PER_FILE]


def _extract_plain(raw: bytes) -> str:
    """Extract plain text (.txt / .md)."""
    try:
        return raw.decode("utf-8")[:MAX_CHARS_PER_FILE]
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="replace")[:MAX_CHARS_PER_FILE]
