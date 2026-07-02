"""app/services/attachment/pdf_extraction.py — PDF text extraction via pdfplumber.

Provides both the flat-text extractor (``_extract_pdf``) used by
``extract_text`` and the structured extractor (``extract_pdf_structured``)
that builds a title/section hierarchy from heading-size heuristics. Both
share char-level line reconstruction helpers at the bottom of this module.
"""
from __future__ import annotations

import io
import logging
from typing import Any

from app.services.attachment.constants import MAX_CHARS_PER_FILE, AttachmentError

_log = logging.getLogger("decisiondoc.attachment")


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
                    line_text = _reconstruct_pdf_line_text(line_chars)
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
        * ``pages``      — List of per-page dicts with text/headings/table flags.

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
    page_summaries: list[dict[str, Any]] = []

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
        for page_index, page in enumerate(pdf.pages, start=1):
            page_line_texts: list[str] = []
            page_headings: list[str] = []
            # Check for tables
            tables = page.extract_tables() or []
            page_has_tables = bool(tables)
            if page_has_tables:
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
                    page_line_texts.extend(rows)

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
                    line_text = _reconstruct_pdf_line_text(line_chars)
                    if not line_text:
                        continue

                    raw_text_parts.append(line_text)
                    page_line_texts.append(line_text)

                    line_sizes = [c.get("size", 0) for c in line_chars if c.get("size")]
                    line_avg_size = sum(line_sizes) / len(line_sizes) if line_sizes else 0.0
                    is_heading = avg_size > 0 and line_avg_size > avg_size * 1.2

                    if is_heading:
                        _flush_section()
                        current_heading = line_text
                        page_headings.append(line_text)
                    else:
                        current_body_lines.append(line_text)

            except Exception:
                # Fallback to plain text
                text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if text and text.strip():
                    raw_text_parts.append(text.strip())
                    current_body_lines.append(text.strip())
                    page_line_texts.extend(line.strip() for line in text.splitlines() if line.strip())

            page_preview = " ".join(page_line_texts[:8]).strip()
            page_summaries.append(
                {
                    "page": page_index,
                    "headings": page_headings[:6],
                    "preview": page_preview[:300],
                    "has_tables": page_has_tables,
                }
            )

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
        "pages": page_summaries,
    }


def _reconstruct_pdf_line_text(line_chars: list[dict]) -> str:
    if not line_chars:
        return ""

    pieces: list[str] = []
    prev_char: dict | None = None
    for char in line_chars:
        text = str(char.get("text", ""))
        if not text:
            continue
        if prev_char is not None and _should_insert_pdf_space(prev_char, char):
            pieces.append(" ")
        pieces.append(text)
        prev_char = char
    return "".join(pieces).strip()


def _should_insert_pdf_space(prev_char: dict, curr_char: dict) -> bool:
    prev_text = str(prev_char.get("text", ""))
    curr_text = str(curr_char.get("text", ""))
    if not prev_text or not curr_text:
        return False
    if prev_text.isspace() or curr_text.isspace():
        return False

    prev_x1 = float(prev_char.get("x1", prev_char.get("x0", 0.0) + _pdf_char_width(prev_char)))
    curr_x0 = float(curr_char.get("x0", 0.0))
    gap = curr_x0 - prev_x1
    if gap <= 0:
        return False

    width_threshold = min(_pdf_char_width(prev_char), _pdf_char_width(curr_char)) * 0.25
    absolute_threshold = 1.8
    return gap >= max(absolute_threshold, width_threshold)


def _pdf_char_width(char: dict) -> float:
    x0 = float(char.get("x0", 0.0))
    x1 = float(char.get("x1", x0))
    width = x1 - x0
    if width > 0:
        return width

    text = str(char.get("text", ""))
    size = float(char.get("size", 0.0) or 0.0)
    if not size:
        return 0.0
    if any("가" <= ch <= "힣" or "一" <= ch <= "鿿" for ch in text):
        return size * 0.88
    if text.isalnum():
        return size * 0.58
    return size * 0.42
