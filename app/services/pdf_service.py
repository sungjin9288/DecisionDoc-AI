"""pdf_service — build an in-memory PDF from rendered markdown docs via Playwright.

No disk I/O is performed; ``build_pdf`` returns raw bytes (async).
Requires: playwright (chromium already installed).

Government format (행안부 공문서 표준):
- A4, 맑은 고딕 10.5pt, 줄간격 160%
- 상 30mm / 하 15mm / 좌우 20mm 여백
- 헤더(기관명·분류)  푸터(페이지 번호: n / N)
- 공문서 헤더 블록: 문서번호 / 수신 / 경유 / 제목 / 붙임
- 결재란 표
"""
from __future__ import annotations

import html as _html
from typing import Any

from playwright.async_api import async_playwright

from app.services.export_labels import humanize_doc_type
from app.services.export_outline import summarize_export_docs
from app.services.markdown_utils import parse_markdown_blocks, render_inline_html


# ---------------------------------------------------------------------------
# Markdown → HTML conversion
# ---------------------------------------------------------------------------

def _markdown_to_html(markdown: str) -> str:
    """Very lightweight markdown → HTML converter."""
    lines: list[str] = []
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            lines.append("</ul>")
            in_list = False

    for block in parse_markdown_blocks(markdown):
        block_type = block["type"]
        if block_type == "heading":
            close_list()
            level = min(int(block.get("level", 1)), 3)
            lines.append(f"<h{level}>{_html.escape(block['text'])}</h{level}>")
        elif block_type == "list_item":
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{render_inline_html(block['text'])}</li>")
        elif block_type == "table":
            close_list()
            header_cells = "".join(f"<th>{render_inline_html(cell)}</th>" for cell in block["headers"])
            body_rows = []
            for row in block["rows"]:
                cells = "".join(f"<td>{render_inline_html(cell)}</td>" for cell in row)
                body_rows.append(f"<tr>{cells}</tr>")
            lines.append(
                "<table class='markdown-table'>"
                f"<thead><tr>{header_cells}</tr></thead>"
                f"<tbody>{''.join(body_rows)}</tbody>"
                "</table>"
            )
        elif block_type == "hr":
            close_list()
            lines.append("<hr/>")
        elif block_type == "blank":
            close_list()
            lines.append("<br/>")
        else:
            close_list()
            lines.append(f"<p>{render_inline_html(block['text'])}</p>")
    close_list()
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Government format HTML helpers
# ---------------------------------------------------------------------------

def _gov_header_block_html(title: str, opts: Any) -> str:
    """공문서 헤더 블록 HTML (문서번호/수신/경유/제목/붙임)."""
    rows = []

    if opts.org_name:
        rows.append(
            f'<div class="gov-org">{_html.escape(opts.org_name)}'
            + (f'<span class="gov-dept"> {_html.escape(opts.dept_name)}</span>' if opts.dept_name else "")
            + '</div>'
        )

    rows.append('<hr class="gov-hr"/>')

    if opts.doc_number:
        rows.append(
            f'<div class="gov-row"><span class="gov-label">문서번호</span>'
            f'<span class="gov-value">{_html.escape(opts.doc_number)}</span></div>'
        )
    if opts.recipient:
        rows.append(
            f'<div class="gov-row"><span class="gov-label">수&#8195;&#8195;신</span>'
            f'<span class="gov-value">{_html.escape(opts.recipient)}</span></div>'
        )
    if opts.via:
        rows.append(
            f'<div class="gov-row"><span class="gov-label">경&#8195;&#8195;유</span>'
            f'<span class="gov-value">{_html.escape(opts.via)}</span></div>'
        )

    rows.append(
        f'<div class="gov-row gov-title-row">'
        f'<span class="gov-label">제&#8195;&#8195;목</span>'
        f'<span class="gov-value gov-title-val"><strong>{_html.escape(title)}</strong></span></div>'
    )

    if opts.attachments:
        att_html = " ".join(
            f"{i}. {_html.escape(a)}" for i, a in enumerate(opts.attachments, 1)
        )
        rows.append(
            f'<div class="gov-row"><span class="gov-label">붙&#8195;&#8195;임</span>'
            f'<span class="gov-value">{att_html}</span></div>'
        )

    return "\n".join(rows)


def _approval_block_html(opts: Any) -> str:
    """결재란 HTML 표."""
    approvers: list[tuple[str, str]] = []
    if opts.drafter:
        approvers.append(("기&#8195;안", opts.drafter))
    if opts.reviewer:
        approvers.append(("검&#8195;토", opts.reviewer))
    if opts.approver:
        approvers.append(("결&#8195;재", opts.approver))

    if not approvers:
        return ""

    headers = "".join(f"<th>{role}</th>" for role, _ in approvers)
    names = "".join(
        f'<td><div class="sig-space"></div>{_html.escape(name)}</td>'
        for _, name in approvers
    )
    return (
        f'<div class="approval-block">'
        f'<table class="approval-table">'
        f'<tr class="approval-header">{headers}</tr>'
        f'<tr class="approval-name">{names}</tr>'
        f'</table></div>'
    )


# ---------------------------------------------------------------------------
# Full HTML rendering
# ---------------------------------------------------------------------------

def _build_css(opts: Any | None) -> str:
    """Build page CSS respecting GovDocOptions margins and fonts."""
    top_mm    = opts.top_margin_mm    if opts else 20
    bot_mm    = opts.bottom_margin_mm if opts else 20
    left_mm   = opts.left_margin_mm   if opts else 20
    right_mm  = opts.right_margin_mm  if opts else 20
    font_name = opts.font_name        if opts else "맑은 고딕"
    font_size = opts.font_size_pt     if opts else 10.5
    spacing   = (opts.line_spacing_pct / 100.0) if opts else 1.6

    return f"""
    @font-face {{
        font-family: '맑은 고딕';
        src: local('Malgun Gothic'), local('맑은 고딕');
    }}
    body {{
        font-family: '{font_name}', 'Malgun Gothic', 'Apple SD Gothic Neo',
                     'Nanum Gothic', sans-serif;
        font-size: {font_size}pt;
        line-height: {spacing};
        color: #1a1a1a;
        margin: 0;
        padding: 0;
    }}
    .page-body {{
        margin: {top_mm}mm {right_mm}mm {bot_mm}mm {left_mm}mm;
    }}
    h1 {{ font-size: {font_size + 6:.1f}pt; margin-top: 28px; margin-bottom: 6px; }}
    h2 {{ font-size: {font_size + 3:.1f}pt; margin-top: 20px; margin-bottom: 4px; }}
    h3 {{ font-size: {font_size + 1:.1f}pt; margin-top: 14px; margin-bottom: 4px; }}
    li {{ margin-bottom: 3px; }}
    ul {{ padding-left: 20px; margin: 6px 0; }}
    hr {{ border: none; border-top: 1px solid #ccc; margin: 12px 0; }}
    p {{ margin: 4px 0; }}
    .markdown-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 10px 0 16px;
        font-size: {font_size - 0.2:.1f}pt;
    }}
    .markdown-table th,
    .markdown-table td {{
        border: 1px solid #c9d3e6;
        padding: 6px 8px;
        vertical-align: top;
        text-align: left;
        word-break: break-word;
    }}
    .markdown-table th {{
        background: #eef3fb;
        font-weight: 700;
    }}

    /* 공문서 헤더 블록 */
    .gov-org {{
        text-align: center; font-weight: bold;
        font-size: {font_size + 2:.1f}pt; margin-bottom: 4px;
    }}
    .gov-dept {{ font-weight: normal; font-size: {font_size}pt; }}
    .gov-hr {{ border-top: 1.5px solid #333; margin: 8px 0; }}
    .gov-row {{
        display: flex; margin: 3px 0; line-height: {spacing};
    }}
    .gov-label {{
        font-weight: bold; min-width: 5em; flex-shrink: 0;
    }}
    .gov-value {{ flex: 1; }}
    .gov-title-row .gov-value {{ font-weight: bold; }}

    /* 결재란 */
    .approval-block {{
        display: flex; justify-content: flex-end;
        margin-top: 40px; page-break-inside: avoid;
    }}
    .approval-table {{
        border-collapse: collapse; min-width: 200px;
    }}
    .approval-table th, .approval-table td {{
        border: 1px solid #333;
        padding: 4px 12px;
        text-align: center;
        font-size: {font_size}pt;
    }}
    .approval-table .approval-header th {{
        background: #f0f0f0; font-weight: bold;
    }}
    .sig-space {{ height: 40px; }}

    .doc-separator {{ page-break-before: always; }}
    .export-cover {{
        min-height: 240px;
        border: 1px solid #d8def0;
        border-radius: 20px;
        background: linear-gradient(135deg, #f6f7ff 0%, #eef2ff 100%);
        padding: 28px 30px;
        margin-bottom: 26px;
    }}
    .export-cover .eyebrow {{
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        background: #5b63d3;
        color: white;
        font-size: 9pt;
        font-weight: 700;
        margin-bottom: 10px;
    }}
    .export-cover h1 {{
        margin-top: 0;
        margin-bottom: 8px;
    }}
    .export-cover p {{
        color: #4c5370;
        margin-bottom: 10px;
    }}
    .doc-chip-list {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-top: 12px;
    }}
    .doc-chip {{
        display: inline-block;
        padding: 6px 10px;
        border: 1px solid #cfd7ee;
        border-radius: 999px;
        background: rgba(255,255,255,0.85);
        font-size: 9pt;
        font-weight: 600;
    }}
    .summary-grid {{
        display: grid;
        grid-template-columns: 1fr;
        gap: 12px;
        margin: 18px 0 8px;
    }}
    .summary-card {{
        border: 1px solid #d7ddef;
        border-radius: 16px;
        background: rgba(255,255,255,0.92);
        padding: 14px 16px;
    }}
    .summary-card .kicker {{
        font-size: 8.5pt;
        font-weight: 700;
        color: #5b63d3;
        margin-bottom: 4px;
    }}
    .summary-card h3 {{
        margin: 0 0 6px;
    }}
    .summary-card p {{
        margin: 0 0 6px;
        color: #4d546f;
    }}
    .summary-card .meta {{
        font-size: 9pt;
        color: #6c7390;
    }}
    .doc-section-card {{
        border-bottom: 2px solid #dfe4f3;
        padding-bottom: 8px;
        margin-bottom: 14px;
    }}
    .doc-section-card .section-index {{
        font-size: 9pt;
        font-weight: 700;
        color: #5b63d3;
        margin-bottom: 4px;
    }}
    .doc-section-card h2 {{
        margin: 0 0 4px;
    }}
    .doc-section-card p {{
        margin: 0;
        color: #5f6377;
    }}
    .doc-section-card .meta {{
        margin-top: 6px;
        font-size: 9pt;
        color: #6d7592;
    }}
    """


def _render_html(
    docs: list[dict[str, Any]],
    title: str,
    opts: Any | None = None,
) -> str:
    """Build a full HTML document from docs list."""
    css = _build_css(opts)

    # Playwright header/footer templates use separate HTML via API options;
    # these are injected there, not into the page HTML.
    parts = [
        f"<!DOCTYPE html><html lang='ko'>"
        f"<head><meta charset='UTF-8'>"
        f"<style>{css}</style></head>"
        f"<body><div class='page-body'>"
    ]

    if opts and opts.is_government_format:
        parts.append(_gov_header_block_html(title, opts))
        parts.append("<br/>")
    else:
        summaries = summarize_export_docs(docs)
        doc_chips = "".join(
            f"<span class='doc-chip'>{idx}. {_html.escape(humanize_doc_type(str(doc.get('doc_type', 'document'))))}</span>"
            for idx, doc in enumerate(docs, start=1)
        )
        summary_cards = "".join(
            "<article class='summary-card'>"
            f"<div class='kicker'>문서 {summary['index']}</div>"
            f"<h3>{_html.escape(summary['label'])}</h3>"
            f"<p>{_html.escape(summary['lead'])}</p>"
            f"<div class='meta'>핵심 섹션: {_html.escape(summary['sections'])} / {_html.escape(summary['metrics'])}</div>"
            "</article>"
            for summary in summaries
        )
        parts.append(
            "<section class='export-cover'>"
            "<div class='eyebrow'>DecisionDoc AI Export</div>"
            f"<h1>{_html.escape(title)}</h1>"
            "<p><strong>완성형 문서 패키지</strong></p>"
            f"<p>총 {len(docs)}개 문서를 제출용 패키지 형태로 정리했습니다. 각 섹션은 문서 단위로 분리되어 바로 검토·공유할 수 있습니다.</p>"
            f"<div class='doc-chip-list'>{doc_chips}</div>"
            "<div class='summary-grid'>"
            f"{summary_cards}"
            "</div>"
            "</section>"
        )

    for i, doc in enumerate(docs):
        if i > 0:
            parts.append('<div class="doc-separator"></div>')
        if not (opts and opts.is_government_format):
            summary = summarize_export_docs([doc])[0]
            parts.append(
                "<section class='doc-section-card'>"
                f"<div class='section-index'>문서 {i + 1:02d} / {len(docs):02d}</div>"
                f"<h2>{_html.escape(humanize_doc_type(str(doc.get('doc_type', 'document'))))}</h2>"
                f"<p>{_html.escape(summary['lead'])}</p>"
                f"<div class='meta'>핵심 섹션: {_html.escape(summary['sections'])} / {_html.escape(summary['metrics'])}</div>"
                "</section>"
            )
        parts.append(_markdown_to_html(doc.get("markdown", "")))

    if opts and opts.is_government_format:
        parts.append(_approval_block_html(opts))

    parts.append("</div></body></html>")
    return "\n".join(parts)


def _build_header_template(opts: Any | None) -> str:
    """Playwright headerTemplate HTML — shows org/classification top-right."""
    parts = []
    if opts and opts.org_name:
        parts.append(_html.escape(opts.org_name))
    if opts and opts.classification:
        parts.append(f"<strong>{_html.escape(opts.classification)}</strong>")

    if not parts:
        return "<span></span>"

    text = "  ".join(parts)
    return (
        f"<div style='font-size:9pt;color:#555;width:100%;"
        f"text-align:right;padding-right:20mm;'>{text}</div>"
    )


def _build_footer_template() -> str:
    """Playwright footerTemplate HTML — centered page n / total."""
    return (
        "<div style='font-size:9pt;color:#555;width:100%;text-align:center;'>"
        "<span class='pageNumber'></span>"
        " / "
        "<span class='totalPages'></span>"
        "</div>"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def build_pdf(
    docs: list[dict[str, Any]],
    title: str,
    gov_options: Any | None = None,
) -> bytes:
    """Build a PDF from a list of rendered docs.

    Args:
        docs: List of {"doc_type": str, "markdown": str}.
        title: Document title.
        gov_options: Optional ``GovDocOptions`` dataclass instance.

    Returns:
        Raw bytes of the PDF file.
    """
    opts = gov_options

    top_mm    = opts.top_margin_mm    if opts else 20
    bot_mm    = opts.bottom_margin_mm if opts else 20
    left_mm   = opts.left_margin_mm   if opts else 20
    right_mm  = opts.right_margin_mm  if opts else 20

    html_content = _render_html(docs, title, opts)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            page = await browser.new_page()
            await page.set_content(html_content, wait_until="domcontentloaded")
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                display_header_footer=True,
                header_template=_build_header_template(opts),
                footer_template=_build_footer_template(),
                margin={
                    "top":    f"{top_mm + 5}mm",
                    "bottom": f"{bot_mm + 5}mm",
                    "left":   f"{left_mm}mm",
                    "right":  f"{right_mm}mm",
                },
            )
        finally:
            await browser.close()

    return pdf_bytes
