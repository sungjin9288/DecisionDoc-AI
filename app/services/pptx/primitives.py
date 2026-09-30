"""Low-level text/shape/style primitives shared by the pptx slide renderers."""
from __future__ import annotations

import math
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


# Card text boxes are wrapped at the card width; text that would still run past
# the card bottom is shortened with an ellipsis instead of spilling over other
# shapes or off the slide. Width uses 1em for Hangul/CJK and 0.6em otherwise,
# and keeps a margin because PowerPoint breaks Korean lines between words.
_CARD_TEXT_INSET_IN = 0.2
_CARD_BODY_TEXT_OFFSET_IN = 0.53
_CARD_WRAP_MARGIN = 0.9


def _line_height_in(font_size_pt: int) -> float:
    return font_size_pt * 1.2 / 72


def _em_width(text: str) -> float:
    return sum(1.0 if ord(char) >= 0x1100 else 0.6 for char in text)


def _card_height_for(lines: list[str], *, width: float, max_height: float, font_size_pt: int = 11) -> float:
    """Card height that shows every wrapped body line, capped at ``max_height``."""
    per_line = (width - 0.36 - _CARD_TEXT_INSET_IN) * 72 / font_size_pt * _CARD_WRAP_MARGIN
    wrapped = sum(max(1, math.ceil(_em_width(_clean_slide_text(line)) / per_line)) for line in lines if _clean_slide_text(line))
    needed = _CARD_BODY_TEXT_OFFSET_IN + max(1, wrapped) * _line_height_in(font_size_pt) + 0.05
    return round(min(max_height, needed), 2)


def _fit_card_lines(lines: list[str], *, width: float, max_lines: int, font_size_pt: int) -> list[str]:
    """Keep lines that fit ``max_lines`` wrapped lines; the last kept line ends
    with "…" whenever any text is cut or a later line is dropped."""
    per_line = (width - _CARD_TEXT_INSET_IN) * 72 / font_size_pt * _CARD_WRAP_MARGIN
    cleaned = [line for line in (_clean_slide_text(raw) for raw in lines) if line]
    remaining = max(1, max_lines)
    fitted: list[str] = []
    for index, line in enumerate(cleaned):
        needed = max(1, math.ceil(_em_width(line) / per_line))
        more_follow = index < len(cleaned) - 1
        if needed < remaining or (needed == remaining and not more_follow):
            fitted.append(line)
            remaining -= needed
            continue
        budget = remaining * per_line - 1
        shortened = ""
        for char in line:
            if _em_width(shortened + char) > budget:
                break
            shortened += char
        fitted.append(shortened.rstrip() + "…")
        break
    return fitted


def _clean_slide_text(text: str | None) -> str:
    if text is None:
        return ""
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
) -> Any:
    tx_box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tx_box.text_frame.text = _clean_slide_text(text)
    _style_text_frame(tx_box.text_frame, font_size_pt=font_size_pt, bold=bold, color=color, align=align)
    return tx_box


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



def _place_shape(shape: Any, *, top: float, height: float) -> None:
    """Move a shape vertically. A placeholder inherits its geometry from the
    layout, so the inherited left/width are written back with the new values."""
    left, width = shape.left, shape.width
    shape.left, shape.top, shape.width, shape.height = left, Inches(top), width, Inches(height)

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
    fit_text: bool = True,
) -> None:
    """Draw a titled card. ``fit_text`` wraps text inside the card and shortens
    what would still overflow it; ``False`` keeps unwrapped text boxes."""
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
    text_width = width - 0.36
    title_box = _add_text_box(
        slide,
        left=left + 0.18,
        top=top + 0.12,
        width=text_width,
        height=0.35,
        text=(_fit_card_lines([title], width=text_width, max_lines=1, font_size_pt=14) or [""])[0] if fit_text else title,
        font_size_pt=14,
        bold=True,
        color=title_color,
    )
    body_box = slide.shapes.add_textbox(
        Inches(left + 0.18),
        Inches(top + 0.48),
        Inches(text_width),
        # A negative extent makes PowerPoint ask to repair the file.
        Inches(max(height - 0.6, _line_height_in(11) + 0.1)),
    )
    if fit_text:
        title_box.text_frame.word_wrap = True
        body_box.text_frame.word_wrap = True
        max_body_lines = int((height - _CARD_BODY_TEXT_OFFSET_IN) // _line_height_in(11))
        body = _fit_card_lines(
            body if isinstance(body, list) else [body],
            width=text_width,
            max_lines=max_body_lines,
            font_size_pt=11,
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
