from __future__ import annotations

import html
import re
from typing import Any

_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")


def render_inline_html(text: str) -> str:
    """Render a minimal markdown inline subset to HTML."""
    escaped = html.escape(text)
    return _BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def split_table_row(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    cells.append("".join(current).strip())
    return cells


def is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEPARATOR_RE.match(line.strip()))


def parse_markdown_blocks(markdown: str) -> list[dict[str, Any]]:
    """Parse a narrow markdown subset used by bundle templates."""
    lines = markdown.splitlines()
    blocks: list[dict[str, Any]] = []
    idx = 0

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()

        if stripped and "|" in stripped and idx + 1 < len(lines) and is_table_separator(lines[idx + 1]):
            headers = split_table_row(stripped)
            rows: list[list[str]] = []
            idx += 2
            while idx < len(lines):
                row_line = lines[idx].strip()
                if not row_line:
                    break
                if "|" not in row_line or row_line.startswith("#") or row_line.startswith(("- ", "* ")) or row_line == "---":
                    break
                row = split_table_row(row_line)
                if len(row) != len(headers):
                    break
                rows.append(row)
                idx += 1
            blocks.append({"type": "table", "headers": headers, "rows": rows})
            continue

        if stripped.startswith("### "):
            blocks.append({"type": "heading", "level": 3, "text": stripped[4:]})
        elif stripped.startswith("## "):
            blocks.append({"type": "heading", "level": 2, "text": stripped[3:]})
        elif stripped.startswith("# "):
            blocks.append({"type": "heading", "level": 1, "text": stripped[2:]})
        elif stripped.startswith(("- ", "* ")):
            blocks.append({"type": "list_item", "text": stripped[2:]})
        elif stripped == "---":
            blocks.append({"type": "hr"})
        elif stripped == "":
            blocks.append({"type": "blank"})
        else:
            blocks.append({"type": "paragraph", "text": stripped})
        idx += 1

    return blocks


def build_markdown_table(rows: list[Any], headers: list[str]) -> str:
    """Build a markdown table from pipe-delimited or sequence-like rows."""
    if not headers:
        return ""

    def _escape_markdown_cell(value: Any) -> str:
        text = str(value).strip()
        text = text.replace("\\", "\\\\")
        text = text.replace("|", "\\|")
        text = " / ".join(part.strip() for part in text.splitlines() if part.strip())
        return text

    normalized_rows: list[list[str]] = []
    width = len(headers)
    for row in rows or []:
        if isinstance(row, str):
            cells = split_table_row(row) if "|" in row else [row.strip()]
        elif isinstance(row, (list, tuple)):
            cells = [_escape_markdown_cell(cell) for cell in row]
        else:
            cells = [_escape_markdown_cell(row)]

        if len(cells) < width:
            cells.extend([""] * (width - len(cells)))
        normalized_rows.append(cells[:width])

    if not normalized_rows:
        return ""

    header_line = "| " + " | ".join(_escape_markdown_cell(header) for header in headers) + " |"
    separator_line = "| " + " | ".join(["---"] * width) + " |"
    body_lines = ["| " + " | ".join(row) + " |" for row in normalized_rows]
    return "\n".join([header_line, separator_line, *body_lines])


def build_markdown_kv_table(text: str) -> str:
    """Convert labeled lines into a two-column markdown table."""
    rows: list[list[str]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
            clean_key = key.replace("**", "").strip()
            rows.append([clean_key, value.strip()])
        else:
            rows.append([stripped, ""])

    if not rows:
        return text.strip()

    return build_markdown_table(rows, ["항목", "내용"])


def build_slide_outline_table(slides: list[dict[str, Any]]) -> str:
    """Render slide outline objects into a markdown table."""
    rows: list[list[str]] = []
    for slide in slides or []:
        rows.append([
            str(slide.get("page", "")).strip(),
            str(slide.get("title", "")).strip(),
            str(slide.get("key_content", "")).strip(),
            str(slide.get("design_tip", "")).strip(),
        ])

    return build_markdown_table(rows, ["페이지", "슬라이드 제목", "핵심 내용", "디자인 가이드"])
