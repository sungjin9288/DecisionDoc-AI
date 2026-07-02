"""excel_service — build an in-memory Excel (.xlsx) from rendered markdown docs.

No disk I/O; ``build_excel`` returns raw bytes.
Requires: xlsxwriter.

Layout:
- 표지 (cover) sheet — title + generation summary.
- 요약 (metadata/summary) sheet — per-document metrics table.
- One sheet per doc_type — markdown rendered with heading/table/list formatting.

Mirrors the markdown parsing approach used by ``docx_service`` (shared
``app.services.markdown_utils.parse_markdown_blocks``) for consistent output
across export formats, and reuses the same doc-summary helpers used by the
DOCX cover page.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import xlsxwriter

from app.services.export_labels import humanize_doc_type
from app.services.export_outline import summarize_export_docs, summarize_export_package
from app.services.markdown_utils import parse_markdown_blocks

# Excel hard limit on a single cell's text length.
_EXCEL_CELL_CHAR_LIMIT = 32767
# Leave room for a truncation marker so the final string still fits the limit.
_CELL_TRUNCATION_SUFFIX = " …(생략됨)"
_MAX_CELL_TEXT = _EXCEL_CELL_CHAR_LIMIT - len(_CELL_TRUNCATION_SUFFIX)

# Characters that are not allowed in Excel worksheet names.
_INVALID_SHEET_CHARS_RE = re.compile(r"[\\/*?:\[\]]")
_MAX_SHEET_NAME_LEN = 31

_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _strip_markdown_emphasis(text: str) -> str:
    """Remove ``**bold**`` markers, leaving plain text for a cell."""
    return _BOLD_RE.sub(r"\1", text)


def _safe_cell_text(text: str) -> str:
    """Clamp text to Excel's per-cell character limit."""
    if len(text) <= _EXCEL_CELL_CHAR_LIMIT:
        return text
    return text[:_MAX_CELL_TEXT].rstrip() + _CELL_TRUNCATION_SUFFIX


def _sanitize_sheet_name(name: str, *, used: set[str]) -> str:
    """Produce a valid, unique Excel worksheet name (<=31 chars, no reserved chars)."""
    cleaned = _INVALID_SHEET_CHARS_RE.sub("_", str(name or "").strip())
    cleaned = cleaned.strip("'") or "문서"
    base = cleaned[:_MAX_SHEET_NAME_LEN] or "문서"

    candidate = base
    suffix = 2
    while candidate.lower() in used:
        tail = f"_{suffix}"
        candidate = f"{base[: _MAX_SHEET_NAME_LEN - len(tail)]}{tail}"
        suffix += 1
    used.add(candidate.lower())
    return candidate


def _sheet_formats(wb: "xlsxwriter.workbook.Workbook") -> dict[str, Any]:
    return {
        "h1": wb.add_format({
            "bold": True, "font_size": 16, "font_color": "#1e3a5f",
            "bottom": 2, "bottom_color": "#1e3a5f", "valign": "vcenter",
            "text_wrap": True,
        }),
        "h2": wb.add_format({
            "bold": True, "font_size": 13, "font_color": "#2d5986", "text_wrap": True,
        }),
        "h3": wb.add_format({
            "bold": True, "font_size": 11, "font_color": "#3a6ea5", "text_wrap": True,
        }),
        "body": wb.add_format({"font_size": 10, "text_wrap": True, "valign": "top"}),
        "bullet": wb.add_format({
            "font_size": 10, "text_wrap": True, "indent": 2, "valign": "top",
        }),
        "hr": wb.add_format({"bottom": 1, "bottom_color": "#cccccc"}),
        "table_header": wb.add_format({
            "bold": True, "font_size": 10, "font_color": "#ffffff",
            "bg_color": "#2d5986", "text_wrap": True, "valign": "vcenter",
            "align": "center", "border": 1, "border_color": "#1e3a5f",
        }),
        "table_cell": wb.add_format({
            "font_size": 10, "text_wrap": True, "valign": "top",
            "border": 1, "border_color": "#cccccc",
        }),
    }


def _write_table_block(
    ws: "xlsxwriter.worksheet.Worksheet",
    formats: dict[str, Any],
    row: int,
    headers: list[str],
    rows: list[list[str]],
) -> int:
    """Write a markdown table block starting at ``row``; return the next free row."""
    for col, header in enumerate(headers):
        ws.write(row, col, _safe_cell_text(_strip_markdown_emphasis(header)), formats["table_header"])
    row += 1

    for data_row in rows:
        for col, value in enumerate(data_row):
            text = _safe_cell_text(_strip_markdown_emphasis(str(value)))
            ws.write(row, col, text, formats["table_cell"])
        row += 1

    return row


def _write_markdown_to_sheet(
    ws: "xlsxwriter.worksheet.Worksheet",
    wb: "xlsxwriter.workbook.Workbook",
    markdown: str,
) -> None:
    """Parse markdown and write it to a worksheet with heading/table/list formatting."""
    formats = _sheet_formats(wb)
    ws.set_column(0, 0, 90)
    for col in range(1, 8):
        ws.set_column(col, col, 28)

    row = 0
    for block in parse_markdown_blocks(markdown or ""):
        block_type = block.get("type")

        if block_type == "heading":
            level = int(block.get("level", 1))
            fmt = {1: formats["h1"], 2: formats["h2"]}.get(level, formats["h3"])
            ws.write(row, 0, _safe_cell_text(block.get("text", "")), fmt)
            if level == 1:
                ws.set_row(row, 26)
            row += 1
        elif block_type == "list_item":
            text = _strip_markdown_emphasis(block.get("text", ""))
            ws.write(row, 0, _safe_cell_text(f"• {text}"), formats["bullet"])
            row += 1
        elif block_type == "table":
            headers = block.get("headers", [])
            rows_ = block.get("rows", [])
            row = _write_table_block(ws, formats, row, headers, rows_)
        elif block_type == "hr":
            ws.write(row, 0, "", formats["hr"])
            row += 1
        elif block_type == "blank":
            row += 1
        else:
            text = _strip_markdown_emphasis(block.get("text", ""))
            ws.write(row, 0, _safe_cell_text(text), formats["body"])
            row += 1

    ws.freeze_panes(1 if row else 0, 0)


def _write_cover_sheet(
    wb: "xlsxwriter.workbook.Workbook",
    *,
    title: str,
    docs: list[dict[str, Any]],
) -> None:
    ws = wb.add_worksheet("표지")
    ws.set_column(0, 0, 22)
    ws.set_column(1, 1, 60)

    fmt_title = wb.add_format({
        "bold": True, "font_size": 20, "font_color": "#1e3a5f",
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    fmt_label = wb.add_format({"bold": True, "font_size": 10, "font_color": "#333333"})
    fmt_value = wb.add_format({"font_size": 10, "text_wrap": True})

    ws.set_row(2, 40)
    ws.merge_range(2, 0, 2, 1, title or "제목 없음", fmt_title)

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    doc_types = [str(doc.get("doc_type", "문서")) for doc in docs]
    doc_labels = ", ".join(humanize_doc_type(dt) for dt in doc_types) or "없음"

    rows = [
        ("생성 시각", generated_at),
        ("문서 수", f"{len(docs)}개"),
        ("문서 유형", doc_labels),
    ]
    r = 4
    for label, value in rows:
        ws.write(r, 0, label, fmt_label)
        ws.write(r, 1, _safe_cell_text(value), fmt_value)
        r += 1


def _write_summary_rows(
    ws: "xlsxwriter.worksheet.Worksheet",
    *,
    summaries: list[dict[str, Any]],
    fmt_cell: Any,
    fmt_num: Any,
    header_count: int,
) -> None:
    for row_idx, summary in enumerate(summaries, start=1):
        ws.write(row_idx, 0, summary.get("index", str(row_idx)), fmt_num)
        ws.write(row_idx, 1, _safe_cell_text(summary.get("label", "")), fmt_cell)
        ws.write(row_idx, 2, _safe_cell_text(summary.get("lead", "")), fmt_cell)
        ws.write(row_idx, 3, int(summary.get("table_count", 0) or 0), fmt_num)
        ws.write(row_idx, 4, int(summary.get("bullet_count", 0) or 0), fmt_num)
        ws.write(row_idx, 5, int(summary.get("heading_count", 0) or 0), fmt_num)
        ws.write(row_idx, 6, _safe_cell_text(summary.get("sections", "")), fmt_cell)

    if not summaries:
        ws.write(1, 0, "-", fmt_num)
        ws.merge_range(1, 1, 1, header_count - 1, "생성된 문서가 없습니다.", fmt_cell)


def _write_summary_totals_row(
    wb: "xlsxwriter.workbook.Workbook",
    ws: "xlsxwriter.worksheet.Worksheet",
    *,
    docs: list[dict[str, Any]],
    totals_row: int,
) -> None:
    package = summarize_export_package(docs) if docs else {
        "doc_count": "0", "table_total": "0", "bullet_total": "0", "heading_total": "0", "headline": "문서 구성 없음",
    }
    fmt_total_label = wb.add_format({"bold": True, "font_size": 10, "align": "right"})
    fmt_total_value = wb.add_format({"bold": True, "font_size": 10})
    ws.write(totals_row, 0, "", fmt_total_label)
    ws.write(totals_row, 1, "합계", fmt_total_label)
    ws.write(totals_row, 2, f"문서 {package['doc_count']}개", fmt_total_value)
    ws.write(totals_row, 3, package["table_total"], fmt_total_value)
    ws.write(totals_row, 4, package["bullet_total"], fmt_total_value)
    ws.write(totals_row, 5, package["heading_total"], fmt_total_value)
    ws.write(totals_row, 6, _safe_cell_text(package["headline"]), fmt_total_value)


def _write_summary_sheet(
    wb: "xlsxwriter.workbook.Workbook",
    *,
    docs: list[dict[str, Any]],
) -> None:
    """Write a metadata/summary sheet: per-document section/table/bullet counts."""
    ws = wb.add_worksheet("요약")
    headers = ["#", "문서 유형", "제목 리드", "표 수", "목록 수", "헤딩 수", "주요 섹션"]
    widths = [4, 18, 40, 8, 8, 8, 40]
    for col, width in enumerate(widths):
        ws.set_column(col, col, width)

    fmt_header = wb.add_format({
        "bold": True, "font_size": 10, "font_color": "#ffffff",
        "bg_color": "#2d5986", "text_wrap": True, "valign": "vcenter",
        "align": "center", "border": 1, "border_color": "#1e3a5f",
    })
    fmt_cell = wb.add_format({
        "font_size": 10, "text_wrap": True, "valign": "top",
        "border": 1, "border_color": "#cccccc",
    })
    fmt_num = wb.add_format({
        "font_size": 10, "valign": "top", "align": "center",
        "border": 1, "border_color": "#cccccc",
    })

    for col, header in enumerate(headers):
        ws.write(0, col, header, fmt_header)

    summaries = summarize_export_docs(docs) if docs else []
    _write_summary_rows(ws, summaries=summaries, fmt_cell=fmt_cell, fmt_num=fmt_num, header_count=len(headers))
    _write_summary_totals_row(wb, ws, docs=docs, totals_row=len(summaries) + 2)

    ws.freeze_panes(1, 0)
    ws.autofilter(0, 0, max(len(summaries), 1), len(headers) - 1)


def build_excel(docs: list[dict[str, Any]], title: str) -> bytes:
    """Build an Excel workbook from a list of rendered docs.

    Args:
        docs: List of {"doc_type": str, "markdown": str}.
        title: Document title (used on the cover sheet).

    Returns:
        Raw bytes of the .xlsx file.
    """
    docs = docs or []
    buf = BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})

    try:
        _write_cover_sheet(wb, title=title, docs=docs)
        _write_summary_sheet(wb, docs=docs)

        used_sheet_names = {"표지".lower(), "요약".lower()}
        for doc in docs:
            doc_type = doc.get("doc_type", "문서")
            sheet_label = humanize_doc_type(str(doc_type))
            sheet_name = _sanitize_sheet_name(sheet_label, used=used_sheet_names)
            ws = wb.add_worksheet(sheet_name)
            _write_markdown_to_sheet(ws, wb, doc.get("markdown", ""))
    finally:
        wb.close()

    buf.seek(0)
    return buf.getvalue()
