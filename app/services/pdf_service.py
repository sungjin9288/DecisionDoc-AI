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
import re
from typing import Any

from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Markdown → HTML conversion
# ---------------------------------------------------------------------------

def _markdown_to_html(markdown: str) -> str:
    """Very lightweight markdown → HTML converter."""
    lines = []
    for line in markdown.splitlines():
        s = line.strip()
        if s.startswith("### "):
            lines.append(f"<h3>{_html.escape(s[4:])}</h3>")
        elif s.startswith("## "):
            lines.append(f"<h2>{_html.escape(s[3:])}</h2>")
        elif s.startswith("# "):
            lines.append(f"<h1>{_html.escape(s[2:])}</h1>")
        elif s.startswith(("- ", "* ")):
            text = _html.escape(s[2:])
            text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
            lines.append(f"<li>{text}</li>")
        elif s == "---":
            lines.append("<hr/>")
        elif s == "":
            lines.append("<br/>")
        else:
            text = _html.escape(s)
            text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
            lines.append(f"<p>{text}</p>")
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
        parts.append(f'<h1>{_html.escape(title)}</h1>')

    for i, doc in enumerate(docs):
        if i > 0:
            parts.append('<div class="doc-separator"></div>')
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
