"""Top-level PPTX deck builders: structured slide_outline decks and
markdown-doc-derived decks."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from pptx import Presentation
from pptx.enum.text import PP_ALIGN

from app.services.export_labels import humanize_doc_type
from app.services.export_outline import presentation_points, summarize_export_docs
from app.services.markdown_utils import (
    parse_markdown_blocks,
    slide_outline_layout,
    slide_outline_message,
    slide_outline_visual,
)
from app.services.pptx.basic_slides import (
    _render_agenda_slide,
    _render_section_divider,
    _render_slide,
    _render_summary_slide,
    _render_table_slide,
)
from app.services.pptx.constants import (
    _COLOR_BG_ACCENT,
    _COLOR_BG_DARK,
    _COLOR_CARD,
    _COLOR_CARD_SOFT,
    _COLOR_TEXT_DARK,
    _COLOR_TEXT_LIGHT,
    _MAX_CONTENT_SLIDE_LEN,
    _MAX_CONTENT_SLIDE_LINES,
    _MAX_TABLE_ROWS,
)
from app.services.pptx.primitives import (
    _add_card,
    _chunk_lines,
    _clean_slide_text,
    _expand_slide_line,
    _set_slide_background,
    _style_text_frame,
    _table_block_lines,
)
from app.services.pptx.structured_slide import (
    _render_structured_guided_slide,
    _structured_slide_summaries,
)
from app.services.visual_asset_service import index_visual_assets_by_slide_title


def build_pptx(
    slide_data: dict[str, Any],
    title: str,
    *,
    include_outline_overview: bool = False,
    visual_assets: list[dict[str, Any]] | None = None,
) -> bytes:
    """Build a PPTX from structured slide data used by presentation_kr."""
    prs = Presentation()
    slide_outline = slide_data.get("slide_outline", []) or []
    visual_assets_by_title = index_visual_assets_by_slide_title(visual_assets or [])

    cover = prs.slides.add_slide(prs.slide_layouts[0])
    _set_slide_background(cover, _COLOR_BG_DARK)
    cover.shapes.title.text = title
    _style_text_frame(
        cover.shapes.title.text_frame,
        font_size_pt=30,
        bold=True,
        color=_COLOR_TEXT_LIGHT,
        align=PP_ALIGN.CENTER,
    )
    if len(cover.placeholders) > 1:
        cover.placeholders[1].text = str(slide_data.get("presentation_goal", "")).strip()
        _style_text_frame(
            cover.placeholders[1].text_frame,
            font_size_pt=18,
            color=_COLOR_TEXT_LIGHT,
            align=PP_ALIGN.CENTER,
        )
    if include_outline_overview and slide_outline:
        top_titles = " · ".join(
            _clean_slide_text(item.get("title", "")) for item in slide_outline[:3] if _clean_slide_text(item.get("title", ""))
        )
        key_point = _clean_slide_text(slide_outline[0].get("key_content", ""))
        if top_titles:
            _add_card(
                cover,
                left=0.8,
                top=4.2,
                width=8.0,
                height=0.78,
                title="핵심 구성",
                body=top_titles,
                fill_color=_COLOR_CARD_SOFT,
                title_color=_COLOR_BG_ACCENT,
                body_color=_COLOR_TEXT_DARK,
            )
        if key_point:
            _add_card(
                cover,
                left=0.8,
                top=5.05,
                width=8.0,
                height=0.78,
                title="핵심 포인트",
                body=_clean_slide_text(_expand_slide_line(key_point, max_len=64)[0]),
                fill_color=_COLOR_CARD,
                title_color=_COLOR_BG_ACCENT,
                body_color=_COLOR_TEXT_DARK,
            )

    if include_outline_overview and slide_outline:
        agenda_items = []
        for item in slide_outline:
            item_title = _clean_slide_text(item.get("title", ""))
            if not item_title:
                continue
            detail_points = presentation_points(
                slide_outline_message(item),
                max_len=56,
                max_points=1,
            )
            detail = _clean_slide_text(detail_points[0]) if detail_points else ""
            agenda_items.append({"title": item_title, "detail": detail})
        _render_agenda_slide(prs, "발표 구성", agenda_items)
        _render_summary_slide(prs, _structured_slide_summaries(slide_outline))

    for item in slide_outline:
        if not isinstance(item, dict):
            continue
        design_tip = str(item.get("design_tip", "")).strip()
        notes_parts = [part for part in [
            design_tip,
            f"권장 시각자료: {slide_outline_visual(item)}" if slide_outline_visual(item) else "",
            f"배치 가이드: {slide_outline_layout(item)}" if slide_outline_layout(item) else "",
        ] if part]
        _render_structured_guided_slide(
            prs,
            item,
            notes="\n".join(notes_parts),
            asset=visual_assets_by_title.get(_clean_slide_text(item.get("title", ""))),
        )

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def build_pptx_from_docs(docs: list[dict[str, Any]], title: str) -> bytes:
    """Build a PPTX deck from rendered markdown docs for non-presentation bundles."""
    prs = Presentation()
    summaries = summarize_export_docs(docs)

    cover = prs.slides.add_slide(prs.slide_layouts[0])
    _set_slide_background(cover, _COLOR_BG_DARK)
    cover.shapes.title.text = title
    _style_text_frame(
        cover.shapes.title.text_frame,
        font_size_pt=30,
        bold=True,
        color=_COLOR_TEXT_LIGHT,
        align=PP_ALIGN.CENTER,
    )
    if len(cover.placeholders) > 1:
        top_labels = " · ".join(summary["label"] for summary in summaries[:3])
        subtitle = f"{len(docs)}개 문서를 발표 자료 형태로 재구성"
        if top_labels:
            subtitle = f"{subtitle}\n{top_labels}"
        cover.placeholders[1].text = subtitle
        _style_text_frame(
            cover.placeholders[1].text_frame,
            font_size_pt=18,
            color=_COLOR_TEXT_LIGHT,
            align=PP_ALIGN.CENTER,
        )
    if summaries:
        _add_card(
            cover,
            left=0.8,
            top=4.8,
            width=8.0,
            height=1.1,
            title="핵심 포인트",
            body=summaries[0].get("ppt_lead") or summaries[0]["lead"],
            fill_color=_COLOR_CARD_SOFT,
            title_color=_COLOR_BG_ACCENT,
            body_color=_COLOR_TEXT_DARK,
        )

    agenda_items = [
        {
            "title": summary["label"],
            "detail": summary.get("ppt_lead") or "",
        }
        for summary in summaries
    ]
    _render_agenda_slide(prs, "발표 구성", agenda_items)
    if summaries:
        _render_summary_slide(prs, summaries)

    for idx, doc in enumerate(docs):
        doc_markdown = str(doc.get("markdown", ""))
        doc_type = str(doc.get("doc_type", "document")).strip() or "document"
        blocks = parse_markdown_blocks(doc_markdown)
        summary = summaries[idx]
        fallback_title = humanize_doc_type(doc_type)
        current_title = fallback_title
        current_lines: list[str] = []
        skip_current_section = False
        table_subtitle = _clean_slide_text(summary.get("ppt_lead") or summary["lead"])
        current_doc_heading = next(
            (
                _clean_slide_text(block.get("text", ""))
                for block in blocks
                if block.get("type") == "heading" and _clean_slide_text(block.get("text", ""))
            ),
            fallback_title,
        )

        def flush_section() -> None:
            nonlocal current_lines
            chunks = _chunk_lines(
                current_lines,
                size=_MAX_CONTENT_SLIDE_LINES,
                max_len=_MAX_CONTENT_SLIDE_LEN,
            )
            if not chunks:
                return
            for idx, chunk in enumerate(chunks, start=1):
                slide_title = current_title if idx == 1 else f"{current_title} ({idx})"
                _render_slide(prs, slide_title, chunk)
            current_lines = []

        _render_section_divider(
            prs,
            current_doc_heading,
            summary.get("ppt_lead") or summary["lead"],
            section_lines=summary.get("section_items") or [summary["sections"]],
            metric_lines=summary.get("metric_items") or [summary["metrics"]],
        )

        for block in blocks:
            block_type = block.get("type")
            if block_type == "heading":
                heading_text = _clean_slide_text(block.get("text", ""))
                if heading_text:
                    flush_section()
                    if "PPT 구성 가이드" in heading_text:
                        skip_current_section = True
                        current_title = fallback_title
                        continue
                    skip_current_section = False
                    current_title = heading_text
            elif block_type == "paragraph":
                if skip_current_section:
                    continue
                text = _clean_slide_text(block.get("text", ""))
                if text:
                    current_lines.append(text)
            elif block_type == "list_item":
                if skip_current_section:
                    continue
                text = _clean_slide_text(block.get("text", ""))
                if text:
                    current_lines.append(text)
            elif block_type == "table":
                if skip_current_section:
                    continue
                flush_section()
                headers = [str(header).strip() for header in block.get("headers", [])]
                rows = block.get("rows", []) or []
                if headers and rows:
                    for idx in range(0, len(rows), _MAX_TABLE_ROWS):
                        chunk = rows[idx: idx + _MAX_TABLE_ROWS]
                        table_title = current_title if idx == 0 else f"{current_title} ({idx // _MAX_TABLE_ROWS + 1})"
                        _render_table_slide(prs, table_title, headers, chunk, subtitle=table_subtitle)
                else:
                    current_lines.extend(_table_block_lines(block))
            elif block_type == "hr":
                flush_section()
            elif block_type == "blank" and current_lines:
                # Preserve paragraph boundaries without forcing empty bullets.
                continue

        flush_section()

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()
