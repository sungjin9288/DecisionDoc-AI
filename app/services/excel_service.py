"""excel_service — build an in-memory Excel (.xlsx) from rendered markdown docs.

No disk I/O; ``build_excel`` returns raw bytes.
Requires: xlsxwriter.
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import xlsxwriter


def _write_markdown_to_sheet(
    ws: "xlsxwriter.worksheet.Worksheet",
    wb: "xlsxwriter.workbook.Workbook",
    markdown: str,
) -> None:
    """Parse markdown and write to worksheet with formatting."""
    fmt_h1 = wb.add_format({"bold": True, "font_size": 16, "font_color": "#1e3a5f",
                              "bottom": 2, "bottom_color": "#1e3a5f", "valign": "vcenter"})
    fmt_h2 = wb.add_format({"bold": True, "font_size": 13, "font_color": "#2d5986"})
    fmt_h3 = wb.add_format({"bold": True, "font_size": 11, "font_color": "#3a6ea5"})
    fmt_body = wb.add_format({"font_size": 10, "text_wrap": True})
    fmt_bullet = wb.add_format({"font_size": 10, "text_wrap": True, "indent": 2})

    row = 0
    ws.set_column(0, 0, 80)

    for line in markdown.splitlines():
        s = line.strip()
        if s.startswith("### "):
            ws.write(row, 0, s[4:], fmt_h3)
        elif s.startswith("## "):
            ws.write(row, 0, s[3:], fmt_h2)
        elif s.startswith("# "):
            ws.write(row, 0, s[2:], fmt_h1)
            ws.set_row(row, 24)
        elif s.startswith(("- ", "* ")):
            # strip **bold** markers for plain text in cells
            text = re.sub(r"\*\*([^*]+)\*\*", r"\1", s[2:])
            ws.write(row, 0, f"  • {text}", fmt_bullet)
        elif s == "---":
            ws.write(row, 0, "", wb.add_format({"bottom": 1, "bottom_color": "#cccccc"}))
        elif s == "":
            ws.write(row, 0, "")
        else:
            text = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
            ws.write(row, 0, text, fmt_body)
        row += 1


def build_excel(docs: list[dict[str, Any]], title: str) -> bytes:
    """Build an Excel workbook from a list of rendered docs.

    Args:
        docs: List of {"doc_type": str, "markdown": str}.
        title: Document title (used as the first sheet name).

    Returns:
        Raw bytes of the .xlsx file.
    """
    buf = BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})

    # Cover sheet
    cover_ws = wb.add_worksheet("표지")
    cover_ws.set_column(0, 0, 60)
    fmt_title = wb.add_format({"bold": True, "font_size": 20, "font_color": "#1e3a5f",
                                "align": "center", "valign": "vcenter"})
    cover_ws.set_row(2, 40)
    cover_ws.write(2, 0, title, fmt_title)
    cover_ws.merge_range(2, 0, 2, 1, title, fmt_title)

    for doc in docs:
        # Use doc_type as sheet name (max 31 chars)
        sheet_name = doc.get("doc_type", "문서")[:31]
        ws = wb.add_worksheet(sheet_name)
        _write_markdown_to_sheet(ws, wb, doc.get("markdown", ""))

    wb.close()
    buf.seek(0)
    return buf.getvalue()
