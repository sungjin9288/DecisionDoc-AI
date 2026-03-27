"""hwp_service — build an in-memory hwpx (HancomOffice) file from rendered markdown docs.

hwpx is a ZIP archive containing HWP XML files.
No disk I/O; ``build_hwp`` returns raw bytes.
No external dependencies — uses Python's standard library zipfile module.

Government format improvements:
- Proper ``<hh:styles>`` definitions (본문 / 제목1 / 제목2 / 제목3)
- ``<hh:secPr>`` with A4 page size and configurable margins (hwpunit = 1/3600 inch)
- Optional 공문서 헤더 블록 paragraphs when is_government_format=True
"""
from __future__ import annotations

import html as _html
import re
import zipfile
from io import BytesIO
from typing import Any

# HWPX namespaces
_NS_HH = "http://www.hancom.com/hwpml/2012/core"

# HWP unit: 1/3600 inch.  1 mm ≈ 141.732 hwpunits
# A4: 210mm × 297mm
_MM_TO_HWPU = 141.732  # hwpunits per mm
_A4_W = round(210 * _MM_TO_HWPU)   # 29764
_A4_H = round(297 * _MM_TO_HWPU)   # 42094


def _mm(mm: int | float) -> int:
    return round(mm * _MM_TO_HWPU)


def _escape(text: str) -> str:
    return _html.escape(text, quote=True)


# ---------------------------------------------------------------------------
# XML builders
# ---------------------------------------------------------------------------

def _container_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles>\n'
        '    <rootfile full-path="Contents/header.xml"'
        ' media-type="application/hwp+zip"/>\n'
        '  </rootfiles>\n'
        '</container>'
    )


def _styles_xml(font_name: str = "맑은 고딕",
                font_size_pt: float = 10.5,
                line_spacing_pct: int = 160) -> str:
    """Generate <hh:styles> with 본문/제목1/제목2/제목3 style definitions.

    HWPX font sizes are in 1/100 pt units (hangul height attribute).
    Line spacing values: lineSpacingType="Percent", value = pct × 100.
    """
    body_sz  = round(font_size_pt * 100)           # 10.5pt → 1050
    h1_sz    = round((font_size_pt + 3) * 100)     # ~13.5pt → 1350
    h2_sz    = round((font_size_pt + 1.5) * 100)   # ~12pt   → 1200
    h3_sz    = round(font_size_pt * 100)            # body size, bold
    lsp      = line_spacing_pct * 100               # 160% → 16000

    def _style(style_id: str, name: str, hz_size: int, bold: str = "0") -> str:
        return (
            f'  <hh:style hh:styleId="{style_id}" hh:name="{name}" hh:type="para">\n'
            f'    <hh:paraShape hh:lineSpacingType="Percent" hh:lineSpacing="{lsp}">\n'
            f'      <hh:margin hh:left="0" hh:right="0" hh:prev="0" hh:next="0"/>\n'
            f'    </hh:paraShape>\n'
            f'    <hh:charShape>\n'
            f'      <hh:height hh:hangul="{hz_size}" hh:latin="{round(hz_size * 0.9)}"/>\n'
            f'      <hh:fontRef hh:hangul="{font_name}" hh:latin="Arial" hh:english="Arial"/>\n'
            f'      <hh:bold hh:value="{bold}"/>\n'
            f'      <hh:color hh:foreground="0"/>\n'
            f'    </hh:charShape>\n'
            f'  </hh:style>\n'
        )

    return (
        f'<hh:styles xmlns:hh="{_NS_HH}">\n'
        + _style("0", "본문",  body_sz, "0")
        + _style("1", "제목1", h1_sz,   "1")
        + _style("2", "제목2", h2_sz,   "1")
        + _style("3", "제목3", h3_sz,   "1")
        + "</hh:styles>"
    )


def _header_xml(
    title: str,
    font_name: str = "맑은 고딕",
    font_size_pt: float = 10.5,
    line_spacing_pct: int = 160,
) -> str:
    """HWPX header.xml — document metadata and style definitions."""
    styles = _styles_xml(font_name, font_size_pt, line_spacing_pct)
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<hh:head xmlns:hh="{_NS_HH}">\n'
        f'  <hh:beginNum hh:page="1" hh:footnote="1"/>\n'
        f'  <hh:refList>\n'
        f'    <hh:fontfaces>\n'
        f'      <hh:fontface hh:lang="Hangul">\n'
        f'        <hh:font hh:name="{_escape(font_name)}" hh:type="TTF" hh:isEmbedded="0"/>\n'
        f'      </hh:fontface>\n'
        f'      <hh:fontface hh:lang="Latin">\n'
        f'        <hh:font hh:name="Arial" hh:type="TTF" hh:isEmbedded="0"/>\n'
        f'      </hh:fontface>\n'
        f'    </hh:fontfaces>\n'
        f'    <hh:borderFills/>\n'
        f'    <hh:charProperties/>\n'
        f'    <hh:tabProperties/>\n'
        f'    <hh:numberings/>\n'
        f'    <hh:bullets/>\n'
        f'    <hh:paraProperties/>\n'
        f'    {styles}\n'
        f'  </hh:refList>\n'
        f'  <hh:compatible/>\n'
        f'  <hh:docOption/>\n'
        f'  <hh:trackChanges/>\n'
        f'</hh:head>'
    )


def _para_xml(text: str, style: str = "본문") -> str:
    """Wrap text in an HWPX paragraph element."""
    escaped = _escape(text)
    return (
        f'  <hh:p>\n'
        f'    <hh:pPr>\n'
        f'      <hh:paraStyle hh:styleIDRef="{style}"/>\n'
        f'    </hh:pPr>\n'
        f'    <hh:run>\n'
        f'      <hh:rPr/>\n'
        f'      <hh:t>{escaped}</hh:t>\n'
        f'    </hh:run>\n'
        f'  </hh:p>'
    )


def _gov_header_paras(title: str, opts: Any) -> list[str]:
    """Generate HWPX paragraph elements for the 공문서 헤더 블록."""
    paras: list[str] = []

    if opts.org_name:
        paras.append(_para_xml(opts.org_name, "제목1"))
    if opts.dept_name:
        paras.append(_para_xml(opts.dept_name, "제목2"))
    if opts.org_name or opts.dept_name:
        paras.append(_para_xml(""))
    paras.append(_para_xml("─" * 50, "본문"))
    if opts.doc_number:
        paras.append(_para_xml(f"문서번호: {opts.doc_number}", "본문"))
    if opts.recipient:
        paras.append(_para_xml(f"수\u2003\u2003신: {opts.recipient}", "본문"))
    if opts.via:
        paras.append(_para_xml(f"경\u2003\u2003유: {opts.via}", "본문"))
    paras.append(_para_xml(f"제\u2003\u2003목: {title}", "제목3"))
    paras.append(_para_xml(""))
    if opts.attachments:
        att_line = "  ".join(f"{i}. {a}" for i, a in enumerate(opts.attachments, 1))
        paras.append(_para_xml(f"붙\u2003\u2003임: {att_line}", "본문"))
    paras.append(_para_xml(""))

    return paras


def _section_xml(
    docs: list[dict[str, Any]],
    title: str,
    opts: Any | None,
    top_mm: int,
    bot_mm: int,
    left_mm: int,
    right_mm: int,
) -> str:
    """Build the body section XML with page layout and paragraph content."""
    paras: list[str] = []

    # 공문서 헤더 블록
    if opts and opts.is_government_format:
        paras.extend(_gov_header_paras(title, opts))
    else:
        paras.append(_para_xml(title, "제목1"))
        paras.append(_para_xml(""))

    # Content
    for i, doc in enumerate(docs):
        if i > 0:
            paras.append(_para_xml("─" * 40, "본문"))
        for line in doc.get("markdown", "").splitlines():
            s = line.strip()
            if s.startswith("### "):
                paras.append(_para_xml(s[4:], "제목3"))
            elif s.startswith("## "):
                paras.append(_para_xml(s[3:], "제목2"))
            elif s.startswith("# "):
                paras.append(_para_xml(s[2:], "제목1"))
            elif s.startswith(("- ", "* ")):
                text = re.sub(r"\*\*([^*]+)\*\*", r"\1", s[2:])
                paras.append(_para_xml(f"• {text}", "본문"))
            elif s == "---":
                paras.append(_para_xml("", "본문"))
            else:
                text = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
                paras.append(_para_xml(text, "본문"))

    # 결재란 (텍스트 형태 — HWP에서 표 그리기는 별도 spec 필요)
    if opts and opts.is_government_format:
        approvers: list[tuple[str, str]] = []
        if opts.drafter:
            approvers.append(("기안", opts.drafter))
        if opts.reviewer:
            approvers.append(("검토", opts.reviewer))
        if opts.approver:
            approvers.append(("결재", opts.approver))
        if approvers:
            paras.append(_para_xml(""))
            roles = "   ".join(f"{role}: {name}" for role, name in approvers)
            paras.append(_para_xml(f"[결재란] {roles}", "본문"))

    body = "\n".join(paras)

    # Page layout in hwpunits
    w  = _A4_W
    h  = _A4_H
    ml = _mm(left_mm)
    mr = _mm(right_mm)
    mt = _mm(top_mm)
    mb = _mm(bot_mm)
    hd = _mm(10)   # header distance 10mm
    ft = _mm(10)   # footer distance 10mm

    sec_pr = (
        f'  <hh:secPr>\n'
        f'    <hh:pageSize hh:width="{w}" hh:height="{h}" hh:orientation="Portrait"/>\n'
        f'    <hh:pageMargin hh:left="{ml}" hh:right="{mr}" '
        f'hh:top="{mt}" hh:bottom="{mb}" '
        f'hh:header="{hd}" hh:footer="{ft}" hh:gutter="0"/>\n'
        f'  </hh:secPr>\n'
    )

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<hh:sec xmlns:hh="{_NS_HH}">\n'
        f'{sec_pr}'
        f'{body}\n'
        f'</hh:sec>'
    )


def _settings_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<hh:settings xmlns:hh="{_NS_HH}">\n'
        '  <hh:startNum>\n'
        '    <hh:page hh:startNum="1"/>\n'
        '  </hh:startNum>\n'
        '</hh:settings>'
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_hwp(
    docs: list[dict[str, Any]],
    title: str,
    gov_options: Any | None = None,
) -> bytes:
    """Build an hwpx file from a list of rendered docs.

    Args:
        docs: List of {"doc_type": str, "markdown": str}.
        title: Document title.
        gov_options: Optional ``GovDocOptions`` dataclass instance.

    Returns:
        Raw bytes of the .hwpx file (ZIP archive).
    """
    opts = gov_options

    top_mm    = opts.top_margin_mm    if opts else 30
    bot_mm    = opts.bottom_margin_mm if opts else 15
    left_mm   = opts.left_margin_mm   if opts else 20
    right_mm  = opts.right_margin_mm  if opts else 20
    font_name = opts.font_name        if opts else "맑은 고딕"
    font_size = opts.font_size_pt     if opts else 10.5
    spacing   = opts.line_spacing_pct if opts else 160

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype MUST be stored uncompressed (per hwpx spec)
        zi = zipfile.ZipInfo("mimetype")
        zi.compress_type = zipfile.ZIP_STORED
        zf.writestr(zi, "application/hwp+zip")
        zf.writestr("META-INF/container.xml", _container_xml())
        zf.writestr(
            "Contents/header.xml",
            _header_xml(title, font_name, font_size, spacing),
        )
        zf.writestr(
            "Contents/section0.xml",
            _section_xml(docs, title, opts, top_mm, bot_mm, left_mm, right_mm),
        )
        zf.writestr("Contents/settings.xml", _settings_xml())
    return buf.getvalue()
