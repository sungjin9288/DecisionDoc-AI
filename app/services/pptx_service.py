"""pptx_service — build in-memory PPTX files from slide structures or rendered docs."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt

from app.services.export_outline import summarize_export_docs
from app.services.export_labels import humanize_doc_type
from app.services.markdown_utils import parse_markdown_blocks

_MAX_SLIDE_LINES = 5
_MAX_TABLE_ROWS = 6


def _clean_slide_text(text: str) -> str:
    return " ".join(str(text).replace("**", "").replace("`", "").split())


def _chunk_lines(lines: list[str], size: int = _MAX_SLIDE_LINES) -> list[list[str]]:
    cleaned = [_clean_slide_text(line) for line in lines if _clean_slide_text(line)]
    if not cleaned:
        return []
    return [cleaned[idx: idx + size] for idx in range(0, len(cleaned), size)]


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


def _render_slide(prs: Presentation, title: str, lines: list[str], notes: str = "") -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = _clean_slide_text(title) or "문서"

    body_tf = slide.placeholders[1].text_frame
    body_tf.clear()
    cleaned_lines = [_clean_slide_text(line) for line in lines if _clean_slide_text(line)]
    if cleaned_lines:
        body_tf.paragraphs[0].text = cleaned_lines[0]
        for line in cleaned_lines[1:]:
            body_tf.add_paragraph().text = line
    else:
        body_tf.paragraphs[0].text = "내용 없음"

    if notes.strip():
        slide.notes_slide.notes_text_frame.text = notes.strip()


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
) -> None:
    tx_box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tx_box.text_frame.text = _clean_slide_text(text)
    _style_text_frame(tx_box.text_frame, font_size_pt=font_size_pt, bold=bold)


def _style_text_frame(text_frame: Any, *, font_size_pt: int = 20, bold: bool = False) -> None:
    for paragraph in text_frame.paragraphs:
        for run in paragraph.runs:
            run.font.size = Pt(font_size_pt)
            run.font.bold = bold


def _render_section_divider(
    prs: Presentation,
    title: str,
    subtitle: str = "",
    meta_lines: list[str] | None = None,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[2])
    slide.shapes.title.text = _clean_slide_text(title) or "섹션"
    if len(slide.placeholders) > 1:
        slide.placeholders[1].text = _clean_slide_text(subtitle) or "핵심 내용을 이어서 설명합니다."
    meta_lines = [_clean_slide_text(line) for line in (meta_lines or []) if _clean_slide_text(line)]
    if meta_lines:
        _add_text_box(
            slide,
            left=0.8,
            top=4.2,
            width=8.0,
            height=1.4,
            text="\n".join(meta_lines),
            font_size_pt=14,
            bold=False,
        )


def _render_agenda_slide(prs: Presentation, title: str, items: list[str]) -> None:
    lines = [f"{idx}. {item}" for idx, item in enumerate(items, start=1) if _clean_slide_text(item)]
    _render_slide(prs, title, lines or ["목차 없음"])


def _render_summary_slide(prs: Presentation, summaries: list[dict[str, str]]) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
    slide.shapes.title.text = "핵심 검토 포인트"

    top = 1.25
    for summary in summaries[:4]:
        _add_text_box(
            slide,
            left=0.65,
            top=top,
            width=8.5,
            height=0.45,
            text=f"문서 {summary['index']} | {summary['label']}",
            font_size_pt=18,
            bold=True,
        )
        _add_text_box(
            slide,
            left=0.85,
            top=top + 0.42,
            width=8.0,
            height=0.55,
            text=summary["lead"],
            font_size_pt=12,
            bold=False,
        )
        _add_text_box(
            slide,
            left=0.85,
            top=top + 0.92,
            width=8.0,
            height=0.35,
            text=f"핵심 섹션: {summary['sections']} / {summary['metrics']}",
            font_size_pt=11,
            bold=False,
        )
        top += 1.32


def _structured_slide_summaries(slide_outline: list[dict[str, Any]]) -> list[dict[str, str]]:
    summaries: list[dict[str, str]] = []
    for idx, item in enumerate(slide_outline[:4], start=1):
        title = _clean_slide_text(item.get("title", "")) or f"슬라이드 {idx}"
        lead = _clean_slide_text(item.get("key_content", "")) or "핵심 메시지 없음"
        lines = [line.strip() for line in str(item.get("key_content", "")).splitlines() if line.strip()]
        metrics = f"핵심 항목 {max(1, len(lines))}개"
        summaries.append(
            {
                "index": f"{idx:02d}",
                "label": title,
                "lead": lead,
                "sections": title,
                "metrics": metrics,
            }
        )
    return summaries


def _render_table_slide(prs: Presentation, title: str, headers: list[str], rows: list[list[str]], subtitle: str = "") -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
    slide.shapes.title.text = _clean_slide_text(title) or "표"

    if subtitle:
        tx_box = slide.shapes.add_textbox(Inches(0.7), Inches(1.15), Inches(8.7), Inches(0.4))
        tx_box.text_frame.text = _clean_slide_text(subtitle)
        _style_text_frame(tx_box.text_frame, font_size_pt=12, bold=False)

    row_count = max(2, len(rows) + 1)
    col_count = max(1, len(headers))
    top = Inches(1.6 if subtitle else 1.3)
    table = slide.shapes.add_table(row_count, col_count, Inches(0.6), top, Inches(8.8), Inches(4.6)).table

    for col_idx, header in enumerate(headers):
        cell = table.cell(0, col_idx)
        cell.text = _clean_slide_text(header)
        _style_text_frame(cell.text_frame, font_size_pt=12, bold=True)

    for row_idx, row in enumerate(rows, start=1):
        for col_idx in range(col_count):
            cell = table.cell(row_idx, col_idx)
            value = row[col_idx] if col_idx < len(row) else ""
            cell.text = _clean_slide_text(value)
            _style_text_frame(cell.text_frame, font_size_pt=11, bold=False)


def build_pptx(
    slide_data: dict[str, Any],
    title: str,
    *,
    include_outline_overview: bool = False,
) -> bytes:
    """Build a PPTX from structured slide data used by presentation_kr."""
    prs = Presentation()
    slide_outline = slide_data.get("slide_outline", []) or []

    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = title
    if len(cover.placeholders) > 1:
        cover.placeholders[1].text = str(slide_data.get("presentation_goal", "")).strip()
    if include_outline_overview and slide_outline:
        top_titles = " · ".join(
            _clean_slide_text(item.get("title", "")) for item in slide_outline[:3] if _clean_slide_text(item.get("title", ""))
        )
        key_point = _clean_slide_text(slide_outline[0].get("key_content", ""))
        if top_titles:
            _add_text_box(
                cover,
                left=0.8,
                top=4.4,
                width=8.0,
                height=0.8,
                text=f"핵심 구성: {top_titles}",
                font_size_pt=15,
                bold=False,
            )
        if key_point:
            _add_text_box(
                cover,
                left=0.8,
                top=5.0,
                width=8.0,
                height=0.8,
                text=f"핵심 포인트: {key_point}",
                font_size_pt=15,
                bold=False,
            )

    if include_outline_overview and slide_outline:
        agenda_items = [
            _clean_slide_text(item.get("title", "")) for item in slide_outline if _clean_slide_text(item.get("title", ""))
        ]
        _render_agenda_slide(prs, "발표 구성", agenda_items)
        _render_summary_slide(prs, _structured_slide_summaries(slide_outline))

    for item in slide_outline:
        if not isinstance(item, dict):
            continue
        raw = str(item.get("key_content", ""))
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        design_tip = str(item.get("design_tip", ""))
        _render_slide(prs, str(item.get("title", "")), lines, notes=design_tip)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()


def build_pptx_from_docs(docs: list[dict[str, Any]], title: str) -> bytes:
    """Build a PPTX deck from rendered markdown docs for non-presentation bundles."""
    prs = Presentation()
    summaries = summarize_export_docs(docs)

    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = title
    if len(cover.placeholders) > 1:
        top_labels = " · ".join(summary["label"] for summary in summaries[:3])
        subtitle = f"{len(docs)}개 문서를 발표 자료 형태로 재구성"
        if top_labels:
            subtitle = f"{subtitle}\n{top_labels}"
        cover.placeholders[1].text = subtitle
    if summaries:
        _add_text_box(
            cover,
            left=0.8,
            top=4.8,
            width=8.0,
            height=1.1,
            text=f"핵심 포인트: {summaries[0]['lead']}",
            font_size_pt=16,
            bold=False,
        )

    doc_titles = [summary["label"] for summary in summaries]
    _render_agenda_slide(prs, "발표 구성", doc_titles)
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
        current_doc_heading = fallback_title
        skip_current_section = False

        def flush_section() -> None:
            nonlocal current_lines
            chunks = _chunk_lines(current_lines)
            if not chunks:
                return
            for idx, chunk in enumerate(chunks, start=1):
                slide_title = current_title if idx == 1 else f"{current_title} ({idx})"
                _render_slide(prs, slide_title, chunk)
            current_lines = []

        _render_section_divider(
            prs,
            current_doc_heading,
            summary["lead"],
            meta_lines=[
                f"핵심 섹션: {summary['sections']}",
                f"구성 특징: {summary['metrics']}",
            ],
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
                    if current_doc_heading == fallback_title:
                        current_doc_heading = heading_text
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
                        _render_table_slide(prs, table_title, headers, chunk, subtitle=fallback_title)
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
