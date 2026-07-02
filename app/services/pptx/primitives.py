"""Low-level text/shape/style primitives shared by the pptx slide renderers."""
from __future__ import annotations

from typing import Any

from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.services.export_outline import presentation_points
from app.services.pptx.constants import (
    _COLOR_BORDER,
    _COLOR_CARD,
    _COLOR_TEXT_DARK,
    _COLOR_TEXT_MUTED,
    _MAX_SLIDE_LINES,
)


def _clean_slide_text(text: str) -> str:
    return " ".join(str(text).replace("**", "").replace("`", "").split())


def _chunk_lines(lines: list[str], size: int = _MAX_SLIDE_LINES, max_len: int = 78) -> list[list[str]]:
    cleaned: list[str] = []
    for raw in lines:
        cleaned.extend(_expand_slide_line(raw, max_len=max_len))
    if not cleaned:
        return []
    chunk_count = max(1, (len(cleaned) + size - 1) // size)
    balanced_size = max(1, (len(cleaned) + chunk_count - 1) // chunk_count)
    return [cleaned[idx: idx + balanced_size] for idx in range(0, len(cleaned), balanced_size)]


def _expand_slide_line(text: str, max_len: int = 78) -> list[str]:
    cleaned = _clean_slide_text(text)
    if not cleaned:
        return []
    points = presentation_points(cleaned, max_len=max_len, max_points=6)
    if points:
        return points
    if len(cleaned) <= max_len:
        return [cleaned]

    words = cleaned.split()
    parts = []
    current: list[str] = []
    current_len = 0
    for word in words:
        next_len = current_len + len(word) + (1 if current else 0)
        if current and next_len > max_len:
            parts.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len = next_len
    if current:
        parts.append(" ".join(current))
    normalized = [_clean_slide_text(part) for part in parts if _clean_slide_text(part)]
    return normalized[:6]


def _table_block_lines(block: dict[str, Any]) -> list[str]:
    headers = [str(header).strip() for header in block.get("headers", [])]
    rows = block.get("rows", []) or []
    lines: list[str] = []
    for row in rows:
        if not isinstance(row, list):
            continue
        parts: list[str] = []
        for idx, cell in enumerate(row):
            value = _clean_slide_text(cell)
            if not value:
                continue
            header = headers[idx] if idx < len(headers) else f"항목 {idx + 1}"
            parts.append(f"{header}: {value}")
        if parts:
            lines.append(" / ".join(parts))
    return lines


def _add_text_box(
    slide: Any,
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    font_size_pt: int = 14,
    bold: bool = False,
    color: RGBColor | None = None,
    align: PP_ALIGN | None = None,
) -> None:
    tx_box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tx_box.text_frame.text = _clean_slide_text(text)
    _style_text_frame(tx_box.text_frame, font_size_pt=font_size_pt, bold=bold, color=color, align=align)


def _set_text_frame_lines(
    text_frame: Any,
    lines: list[str],
    *,
    font_size_pt: int = 14,
    bold: bool = False,
    color: RGBColor | None = None,
    align: PP_ALIGN | None = None,
) -> None:
    cleaned_lines = [_clean_slide_text(line) for line in lines if _clean_slide_text(line)]
    text_frame.clear()
    if not cleaned_lines:
        cleaned_lines = [""]
    text_frame.paragraphs[0].text = cleaned_lines[0]
    for line in cleaned_lines[1:]:
        text_frame.add_paragraph().text = line
    _style_text_frame(text_frame, font_size_pt=font_size_pt, bold=bold, color=color, align=align)


def _style_text_frame(
    text_frame: Any,
    *,
    font_size_pt: int = 20,
    bold: bool = False,
    color: RGBColor | None = None,
    align: PP_ALIGN | None = None,
) -> None:
    for paragraph in text_frame.paragraphs:
        if align is not None:
            paragraph.alignment = align
        for run in paragraph.runs:
            run.font.size = Pt(font_size_pt)
            run.font.bold = bold
            if color is not None:
                run.font.color.rgb = color


def _set_slide_background(slide: Any, color: RGBColor) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_card(
    slide: Any,
    *,
    left: float,
    top: float,
    width: float,
    height: float,
    title: str,
    body: str | list[str],
    fill_color: RGBColor = _COLOR_CARD,
    title_color: RGBColor = _COLOR_TEXT_DARK,
    body_color: RGBColor = _COLOR_TEXT_MUTED,
) -> None:
    shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE,
        Inches(left),
        Inches(top),
        Inches(width),
        Inches(height),
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.color.rgb = _COLOR_BORDER
    shape.line.width = Pt(1)
    _add_text_box(
        slide,
        left=left + 0.18,
        top=top + 0.12,
        width=width - 0.36,
        height=0.35,
        text=title,
        font_size_pt=14,
        bold=True,
        color=title_color,
    )
    body_box = slide.shapes.add_textbox(
        Inches(left + 0.18),
        Inches(top + 0.48),
        Inches(width - 0.36),
        Inches(height - 0.6),
    )
    if isinstance(body, list):
        _set_text_frame_lines(
            body_box.text_frame,
            body,
            font_size_pt=11,
            color=body_color,
        )
    else:
        body_box.text_frame.text = _clean_slide_text(body)
        _style_text_frame(body_box.text_frame, font_size_pt=11, color=body_color)
