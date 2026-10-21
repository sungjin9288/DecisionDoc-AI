from __future__ import annotations

import html
import re
from string import punctuation
from typing import Any

_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_ATX_HEADING_RE = re.compile(r"^(#{1,6})(\s+\S.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_DEEP_HEADING_RE = re.compile(r"^#{4,6}\s+(\S.*)$")
_SPACES_PER_INDENT = 2
_MAX_INDENT = 4
_MAX_HEADING_LEVEL = 6


def render_inline_html(text: str) -> str:
    """Render a minimal markdown inline subset to HTML."""
    escaped = html.escape(text)
    return _BOLD_RE.sub(r"<strong>\1</strong>", escaped)


def split_table_row(line: str) -> list[str]:
    """Split a markdown table row into trimmed cells."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for index, char in enumerate(text):
        if escaped:
            if char not in punctuation:
                current.append("\\")
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            cells.append("".join(current).strip())
            if index == len(text) - 1:
                return cells
            current = []
            continue
        current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def is_table_separator(line: str) -> bool:
    return bool(_TABLE_SEPARATOR_RE.match(line.strip()))


def _indent_level(raw: str) -> int:
    """Two leading spaces (half a tab) per level, as 개조식 sub-items are written."""
    expanded = raw.expandtabs(4)
    return min((len(expanded) - len(expanded.lstrip(" "))) // _SPACES_PER_INDENT, _MAX_INDENT)


def _with_indent(block: dict[str, Any], raw: str) -> dict[str, Any]:
    level = _indent_level(raw)
    return {**block, "indent": level} if level else block


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

        deep_heading = _DEEP_HEADING_RE.match(stripped)
        if deep_heading:
            # Export styles stop at level 3; deeper headings must not leak as literal '#'.
            blocks.append({"type": "heading", "level": 3, "text": deep_heading.group(1)})
        elif stripped.startswith("### "):
            blocks.append({"type": "heading", "level": 3, "text": stripped[4:]})
        elif stripped.startswith("## "):
            blocks.append({"type": "heading", "level": 2, "text": stripped[3:]})
        elif stripped.startswith("# "):
            blocks.append({"type": "heading", "level": 1, "text": stripped[2:]})
        elif stripped.startswith(("- ", "* ")):
            blocks.append(_with_indent({"type": "list_item", "text": stripped[2:]}, raw))
        elif stripped == "---":
            blocks.append({"type": "hr"})
        elif stripped == "":
            blocks.append({"type": "blank"})
        else:
            blocks.append(_with_indent({"type": "paragraph", "text": stripped}, raw))
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
            cells = list(row)
        else:
            cells = [row]

        if len(cells) < width:
            cells.extend([""] * (width - len(cells)))
        normalized_rows.append([_escape_markdown_cell(cell) for cell in cells[:width]])

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


def _outline_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _outline_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        normalized = _outline_text(item)
        if normalized:
            rows.append(normalized)
    return rows


def slide_outline_message(slide: dict[str, Any]) -> str:
    return _outline_text(slide.get("core_message") or slide.get("message") or slide.get("key_message") or slide.get("key_content"))


def slide_outline_evidence(slide: dict[str, Any]) -> list[str]:
    explicit: list[str] = []
    for key in ("evidence_points", "required_evidence", "source_refs", "reference_refs"):
        explicit.extend(_outline_list(slide.get(key)))
    if explicit:
        deduped: list[str] = []
        for item in explicit:
            if item not in deduped:
                deduped.append(item)
            if len(deduped) >= 4:
                break
        return deduped

    raw = _outline_text(slide.get("key_content"))
    if not raw:
        return []

    parts = [
        item.strip()
        for item in re.split(r"\n+| \+ | / | · |, ", raw)
        if item.strip()
    ]
    deduped: list[str] = []
    for part in parts:
        normalized = _outline_text(part)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
        if len(deduped) >= 3:
            break
    return deduped


def slide_outline_visual(slide: dict[str, Any]) -> str:
    visual_type = _outline_text(slide.get("visual_type"))
    visual_brief = _outline_text(slide.get("visual_brief") or slide.get("visual") or slide.get("visual_spec"))
    if visual_type and visual_brief:
        return f"{visual_type} — {visual_brief}"
    if visual_brief:
        return visual_brief
    if visual_type:
        return visual_type

    design_tip = _outline_text(slide.get("design_tip"))
    keyword_pairs = (
        ("프로세스 흐름도", "프로세스 흐름도"),
        ("흐름도", "프로세스 흐름도"),
        ("조직도", "조직도"),
        ("타임라인", "타임라인"),
        ("간트", "간트 차트"),
        ("차트", "차트"),
        ("그래프", "그래프"),
        ("표", "비교 표"),
        ("매트릭스", "매트릭스"),
        ("와이어프레임", "와이어프레임"),
        ("스크린샷", "스크린샷"),
        ("목업", "화면 목업"),
        ("지도", "지도"),
        ("사진", "현장 사진"),
        ("아이콘", "아이콘 카드"),
        ("로고", "로고/브랜드 카드"),
    )
    for keyword, label in keyword_pairs:
        if keyword in design_tip:
            return label
    return ""


def slide_outline_layout(slide: dict[str, Any]) -> str:
    return _outline_text(slide.get("layout_hint") or slide.get("layout") or slide.get("design_tip"))


def build_slide_outline_table(slides: list[dict[str, Any]]) -> str:
    """Render slide outline objects into a markdown table."""
    rows: list[list[str]] = []
    for slide in slides or []:
        evidence = " · ".join(slide_outline_evidence(slide))
        rows.append([
            str(slide.get("page", "")).strip(),
            str(slide.get("title", "")).strip(),
            slide_outline_message(slide),
            evidence,
            slide_outline_visual(slide),
            slide_outline_layout(slide),
        ])

    return build_markdown_table(
        rows,
        ["페이지", "슬라이드 제목", "핵심 메시지", "입증 포인트", "권장 시각자료", "배치 가이드"],
    )


def nest_markdown_headings(text: str, min_level: int = 3) -> str:
    """Shift headings in pasted text so they nest under the template's own section.

    User context such as notes or RFP excerpts can carry its own ``#``/``##``
    headings; rendered as-is they would become siblings of the document's
    sections. Relative levels are kept, fenced code is left alone.
    """
    lines = text.splitlines()
    in_fence = False
    heading_rows: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else _ATX_HEADING_RE.match(line)
        if match:
            heading_rows.append((index, len(match.group(1)), match.group(2)))
    if not heading_rows:
        return text
    shift = max(0, min_level - min(level for _, level, _ in heading_rows))
    nested = list(lines)
    for index, level, rest in heading_rows:
        nested[index] = "#" * min(_MAX_HEADING_LEVEL, level + shift) + rest
    return "\n".join(nested)

