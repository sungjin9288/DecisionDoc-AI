"""Generic slide renderers: content slide, section divider, agenda, summary, table."""
from __future__ import annotations

from pptx import Presentation
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches

from app.services.pptx.constants import (
    _COLOR_BG_ACCENT,
    _COLOR_BG_DARK,
    _COLOR_BG_SOFT,
    _COLOR_CARD,
    _COLOR_CARD_SOFT,
    _COLOR_TEXT_DARK,
    _COLOR_TEXT_LIGHT,
    _COLOR_TEXT_MUTED,
)
from app.services.pptx.primitives import (
    _add_card,
    _clean_slide_text,
    _set_slide_background,
    _style_text_frame,
)
from pptx.dml.color import RGBColor


def _render_slide(
    prs: Presentation,
    title: str,
    lines: list[str],
    notes: str = "",
    guidance_lines: list[str] | None = None,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = _clean_slide_text(title) or "문서"
    _style_text_frame(
        slide.shapes.title.text_frame,
        font_size_pt=26,
        bold=True,
        color=_COLOR_TEXT_DARK,
    )

    body_tf = slide.placeholders[1].text_frame
    body_tf.clear()
    cleaned_lines = [_clean_slide_text(line) for line in lines if _clean_slide_text(line)]
    if cleaned_lines:
        body_tf.paragraphs[0].text = cleaned_lines[0]
        for line in cleaned_lines[1:]:
            body_tf.add_paragraph().text = line
    else:
        body_tf.paragraphs[0].text = "내용 없음"
    _style_text_frame(body_tf, font_size_pt=17, color=_COLOR_TEXT_DARK)

    cleaned_guidance = [_clean_slide_text(line) for line in (guidance_lines or []) if _clean_slide_text(line)]
    if cleaned_guidance:
        _add_card(
            slide,
            left=5.95,
            top=4.55,
            width=3.05,
            height=1.15,
            title="시각자료/배치 가이드",
            body=cleaned_guidance[:3],
            fill_color=_COLOR_CARD_SOFT,
            title_color=_COLOR_BG_ACCENT,
            body_color=_COLOR_TEXT_DARK,
        )

    if notes.strip():
        slide.notes_slide.notes_text_frame.text = notes.strip()


def _render_section_divider(
    prs: Presentation,
    title: str,
    subtitle: str = "",
    section_lines: list[str] | None = None,
    metric_lines: list[str] | None = None,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[2])
    _set_slide_background(slide, _COLOR_BG_DARK)
    slide.shapes.title.text = _clean_slide_text(title) or "섹션"
    _style_text_frame(
        slide.shapes.title.text_frame,
        font_size_pt=28,
        bold=True,
        color=_COLOR_TEXT_LIGHT,
    )
    if len(slide.placeholders) > 1:
        slide.placeholders[1].text = _clean_slide_text(subtitle) or "핵심 내용을 이어서 설명합니다."
        _style_text_frame(
            slide.placeholders[1].text_frame,
            font_size_pt=18,
            color=_COLOR_TEXT_LIGHT,
        )
    section_lines = [_clean_slide_text(line) for line in (section_lines or []) if _clean_slide_text(line)]
    metric_lines = [_clean_slide_text(line) for line in (metric_lines or []) if _clean_slide_text(line)]
    if section_lines or metric_lines:
        _add_card(
            slide,
            left=0.8,
            top=4.2,
            width=4.25,
            height=1.4,
            title="핵심 섹션",
            body=section_lines or ["핵심 섹션 요약"],
            fill_color=_COLOR_CARD_SOFT,
            title_color=_COLOR_TEXT_DARK,
            body_color=_COLOR_TEXT_DARK,
        )
        _add_card(
            slide,
            left=5.15,
            top=4.2,
            width=3.65,
            height=1.4,
            title="구성 지표",
            body=metric_lines or ["구성 지표 없음"],
            fill_color=_COLOR_CARD,
            title_color=_COLOR_BG_ACCENT,
            body_color=_COLOR_TEXT_DARK,
        )


def _render_agenda_slide(prs: Presentation, title: str, items: list[str | dict[str, str]]) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    _set_slide_background(slide, _COLOR_BG_SOFT)
    slide.shapes.title.text = _clean_slide_text(title) or "발표 구성"
    _style_text_frame(
        slide.shapes.title.text_frame,
        font_size_pt=26,
        bold=True,
        color=_COLOR_TEXT_DARK,
    )
    normalized_items: list[dict[str, str]] = []
    for item in items:
        if isinstance(item, dict):
            item_title = _clean_slide_text(item.get("title", ""))
            item_detail = _clean_slide_text(item.get("detail", ""))
        else:
            item_title = _clean_slide_text(item)
            item_detail = ""
        if item_title:
            normalized_items.append({"title": item_title, "detail": item_detail})
    cleaned_items = normalized_items
    if not cleaned_items:
        cleaned_items = [{"title": "목차 없음", "detail": ""}]
    two_col_split = max(1, (len(cleaned_items) + 1) // 2)
    for idx, item in enumerate(cleaned_items[:6], start=1):
        col = 0 if idx <= two_col_split else 1
        row = idx - 1 if col == 0 else idx - 1 - two_col_split
        _add_card(
            slide,
            left=0.7 + (4.5 * col),
            top=1.4 + (0.92 * row),
            width=4.0,
            height=0.9,
            title=f"{idx:02d}",
            body=[item["title"], item["detail"]] if item["detail"] else item["title"],
            fill_color=_COLOR_CARD,
            title_color=_COLOR_BG_ACCENT,
            body_color=_COLOR_TEXT_DARK,
        )


def _render_summary_slide(prs: Presentation, summaries: list[dict[str, str]]) -> None:
    if not summaries:
        return

    page_size = 4
    pages = [summaries[idx: idx + page_size] for idx in range(0, len(summaries), page_size)]
    for page_index, page in enumerate(pages, start=1):
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
        _set_slide_background(slide, _COLOR_BG_SOFT)
        title = "핵심 검토 포인트"
        if len(pages) > 1:
            title = f"{title} ({page_index}/{len(pages)})"
        slide.shapes.title.text = title
        _style_text_frame(
            slide.shapes.title.text_frame,
            font_size_pt=26,
            bold=True,
            color=_COLOR_TEXT_DARK,
        )

        if len(page) <= 2:
            positions = [(0.65, 1.25), (0.65, 2.95)]
            card_width = 8.5
            card_height = 1.45
        else:
            positions = [(0.65, 1.25), (5.0, 1.25), (0.65, 3.15), (5.0, 3.15)]
            card_width = 3.95
            card_height = 1.6

        for summary, (left, top) in zip(page, positions, strict=False):
            metric_items = summary.get("metric_items") or [summary["metrics"]]
            body_lines = [
                summary.get("ppt_lead") or summary["lead"],
                f"핵심 섹션: {summary['sections']}",
                f"구성 지표: {' · '.join(metric_items)}",
            ]
            _add_card(
                slide,
                left=left,
                top=top,
                width=card_width,
                height=card_height,
                title=f"문서 {summary['index']} | {summary['label']}",
                body=body_lines,
                fill_color=_COLOR_CARD,
                title_color=_COLOR_TEXT_DARK,
                body_color=_COLOR_TEXT_MUTED,
            )


def _render_table_slide(prs: Presentation, title: str, headers: list[str], rows: list[list[str]], subtitle: str = "") -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
    _set_slide_background(slide, _COLOR_BG_SOFT)
    slide.shapes.title.text = _clean_slide_text(title) or "표"
    _style_text_frame(
        slide.shapes.title.text_frame,
        font_size_pt=24,
        bold=True,
        color=_COLOR_TEXT_DARK,
    )

    if subtitle:
        tx_box = slide.shapes.add_textbox(Inches(0.7), Inches(1.15), Inches(8.7), Inches(0.4))
        tx_box.text_frame.text = _clean_slide_text(subtitle)
        _style_text_frame(tx_box.text_frame, font_size_pt=12, bold=False, color=_COLOR_TEXT_MUTED)

    row_count = max(2, len(rows) + 1)
    col_count = max(1, len(headers))
    top = Inches(1.6 if subtitle else 1.3)
    table = slide.shapes.add_table(row_count, col_count, Inches(0.6), top, Inches(8.8), Inches(4.6)).table

    for col_idx, header in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = _clean_slide_text(header)
        cell.fill.solid()
        cell.fill.fore_color.rgb = _COLOR_BG_ACCENT
        _style_text_frame(cell.text_frame, font_size_pt=12, bold=True, color=_COLOR_TEXT_LIGHT, align=PP_ALIGN.CENTER)

    for row_idx, row in enumerate(rows, start=1):
        for col_idx in range(col_count):
            cell = table.cell(row_idx, col_idx)
            value = row[col_idx] if col_idx < len(row) else ""
            cell.text = _clean_slide_text(value)
            if row_idx % 2 == 1:
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(250, 250, 255)
            _style_text_frame(cell.text_frame, font_size_pt=11, bold=False, color=_COLOR_TEXT_DARK)
