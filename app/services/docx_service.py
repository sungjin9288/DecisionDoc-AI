"""docx_service — build an in-memory DOCX from rendered markdown docs.

No disk I/O is performed; ``build_docx`` returns raw bytes.

Government format (행안부 공문서 표준):
- A4 (210×297mm), 맑은 고딕 10.5pt, 줄간격 160%
- 상 30mm / 하 15mm / 좌우 20mm 여백
- 헤더(기관명·문서번호) / 푸터(페이지 번호)
- 공문서 헤더 블록: 문서번호 / 수신 / 경유 / 제목 / 붙임
- 결재란 표
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_run_font(run: Any, font_name: str, font_size_pt: float | None = None) -> None:
    """Set both Latin and East-Asian (CJK) font on a run."""
    run.font.name = font_name
    if font_size_pt:
        run.font.size = Pt(font_size_pt)
    # East-Asian font for Korean characters
    rpr = run._r.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:eastAsia"), font_name)
    rfonts.set(qn("w:cs"), font_name)


def _set_default_font(doc: Document, font_name: str, font_size_pt: float) -> None:
    """Apply Korean-compatible default font to the Normal paragraph style."""
    style = doc.styles["Normal"]
    style.font.name = font_name
    style.font.size = Pt(font_size_pt)
    # East-Asian font
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    rfonts.set(qn("w:eastAsia"), font_name)
    rfonts.set(qn("w:cs"), font_name)


def _set_line_spacing(para: Any, spacing_pct: int) -> None:
    """Set paragraph line spacing as a multiple (percentage / 100)."""
    fmt = para.paragraph_format
    fmt.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
    fmt.line_spacing = spacing_pct / 100.0


def _add_field_code(run: Any, field_code: str) -> None:
    """Insert a Word field code (PAGE, NUMPAGES) into a run."""
    fld_char_begin = OxmlElement("w:fldChar")
    fld_char_begin.set(qn("w:fldCharType"), "begin")
    run._r.append(fld_char_begin)

    instr = OxmlElement("w:instrText")
    instr.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    instr.text = f" {field_code} "
    run._r.append(instr)

    fld_char_end = OxmlElement("w:fldChar")
    fld_char_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_char_end)


def _add_page_number_footer(section: Any, font_name: str = "맑은 고딕") -> None:
    """Add centered 'n / total' page numbers to the section footer."""
    footer = section.footer
    footer.is_linked_to_previous = False
    para = footer.paragraphs[0]
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.clear()

    run = para.add_run()
    _set_run_font(run, font_name)
    _add_field_code(run, "PAGE")

    run_sep = para.add_run(" / ")
    _set_run_font(run_sep, font_name)

    run2 = para.add_run()
    _set_run_font(run2, font_name)
    _add_field_code(run2, "NUMPAGES")


def _add_gov_header(section: Any, opts: Any) -> None:
    """Add a right-aligned header showing org name / classification."""
    header = section.header
    header.is_linked_to_previous = False
    para = header.paragraphs[0]
    para.clear()
    parts = []
    if opts and opts.org_name:
        parts.append(opts.org_name)
    if opts and opts.classification:
        parts.append(opts.classification)
    if parts:
        para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = para.add_run("  ".join(parts))
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
        _set_run_font(run, opts.font_name if opts else "맑은 고딕")


def _add_bold_inline(paragraph: Any, text: str,
                     font_name: str = "맑은 고딕",
                     font_size_pt: float = 10.5) -> None:
    """Parse **bold** spans and add them with appropriate runs."""
    for part in re.split(r"(\*\*[^*]+\*\*)", text):
        if part.startswith("**") and part.endswith("**"):
            run = paragraph.add_run(part[2:-2])
            run.bold = True
        else:
            run = paragraph.add_run(part)
        _set_run_font(run, font_name, font_size_pt)


def _add_markdown_content(doc: Document, markdown: str,
                           font_name: str = "맑은 고딕",
                           font_size_pt: float = 10.5,
                           line_spacing_pct: int = 160) -> None:
    """Convert markdown lines to Word paragraphs/headings/lists."""
    for line in markdown.splitlines():
        s = line.strip()
        if s.startswith("# "):
            p = doc.add_heading(s[2:], level=1)
        elif s.startswith("## "):
            p = doc.add_heading(s[3:], level=2)
        elif s.startswith("### "):
            p = doc.add_heading(s[4:], level=3)
        elif s.startswith(("- ", "* ")):
            p = doc.add_paragraph(style="List Bullet")
            _add_bold_inline(p, s[2:], font_name, font_size_pt)
            _set_line_spacing(p, line_spacing_pct)
            continue
        elif s.startswith("---"):
            p = doc.add_paragraph()
        elif s == "":
            p = doc.add_paragraph()
        else:
            p = doc.add_paragraph()
            _add_bold_inline(p, s, font_name, font_size_pt)
            _set_line_spacing(p, line_spacing_pct)
            continue
        _set_line_spacing(p, line_spacing_pct)


# ---------------------------------------------------------------------------
# Government format helpers
# ---------------------------------------------------------------------------

def _add_gov_doc_header_block(doc: Document, title: str, opts: Any) -> None:
    """행안부 공문서 헤더 블록: 기관명 / 문서번호 / 수신 / 경유 / 제목 / 붙임."""
    fn = opts.font_name
    fs = opts.font_size_pt

    # 기관명 (가운데 정렬, 굵게)
    if opts.org_name:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(opts.org_name)
        run.bold = True
        _set_run_font(run, fn, fs + 2)
        _set_line_spacing(p, opts.line_spacing_pct)

    # 부서명 (가운데 정렬)
    if opts.dept_name:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(opts.dept_name)
        _set_run_font(run, fn, fs)
        _set_line_spacing(p, opts.line_spacing_pct)

    if opts.org_name or opts.dept_name:
        doc.add_paragraph()

    # 구분선
    p = doc.add_paragraph("─" * 60)
    p.runs[0].font.size = Pt(8)
    _set_line_spacing(p, 100)

    # 문서번호
    if opts.doc_number:
        p = doc.add_paragraph()
        r1 = p.add_run("문서번호: ")
        r1.bold = True
        _set_run_font(r1, fn, fs)
        r2 = p.add_run(opts.doc_number)
        _set_run_font(r2, fn, fs)
        _set_line_spacing(p, opts.line_spacing_pct)

    # 수신
    if opts.recipient:
        p = doc.add_paragraph()
        r1 = p.add_run("수\u2003\u2003신: ")
        r1.bold = True
        _set_run_font(r1, fn, fs)
        r2 = p.add_run(opts.recipient)
        _set_run_font(r2, fn, fs)
        _set_line_spacing(p, opts.line_spacing_pct)

    # 경유
    if opts.via:
        p = doc.add_paragraph()
        r1 = p.add_run("경\u2003\u2003유: ")
        r1.bold = True
        _set_run_font(r1, fn, fs)
        r2 = p.add_run(opts.via)
        _set_run_font(r2, fn, fs)
        _set_line_spacing(p, opts.line_spacing_pct)

    # 제목 (굵게)
    p = doc.add_paragraph()
    r1 = p.add_run("제\u2003\u2003목: ")
    r1.bold = True
    _set_run_font(r1, fn, fs)
    r2 = p.add_run(title)
    r2.bold = True
    _set_run_font(r2, fn, fs)
    _set_line_spacing(p, opts.line_spacing_pct)

    doc.add_paragraph()

    # 붙임
    if opts.attachments:
        p = doc.add_paragraph()
        r1 = p.add_run("붙\u2003\u2003임: ")
        r1.bold = True
        _set_run_font(r1, fn, fs)
        for i, att in enumerate(opts.attachments, 1):
            r2 = p.add_run(f"{i}. {att}  ")
            _set_run_font(r2, fn, fs)
        _set_line_spacing(p, opts.line_spacing_pct)

    doc.add_paragraph()


def _add_approval_block(doc: Document, opts: Any) -> None:
    """행안부 공문서 결재란 표를 문서 말미에 추가."""
    approvers: list[tuple[str, str]] = []
    if opts.drafter:
        approvers.append(("기  안", opts.drafter))
    if opts.reviewer:
        approvers.append(("검  토", opts.reviewer))
    if opts.approver:
        approvers.append(("결  재", opts.approver))

    if not approvers:
        return

    doc.add_paragraph()
    p_label = doc.add_paragraph()
    r = p_label.add_run("결  재")
    r.bold = True
    _set_run_font(r, opts.font_name, opts.font_size_pt)
    p_label.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    table = doc.add_table(rows=2, cols=len(approvers))
    try:
        table.style = "Table Grid"
    except Exception:
        pass  # style may not exist in all templates

    # Row 0: role titles
    for col, (role, _) in enumerate(approvers):
        cell = table.cell(0, col)
        cell.text = role
        for para in cell.paragraphs:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in para.runs:
                run.bold = True
                _set_run_font(run, opts.font_name, opts.font_size_pt)

    # Row 1: names with signature space
    for col, (_, name) in enumerate(approvers):
        cell = table.cell(1, col)
        cell.text = ""
        # spacing for signature area
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(30)
        p.paragraph_format.space_after = Pt(5)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(name)
        _set_run_font(run, opts.font_name, opts.font_size_pt)

    # Right-align the table
    tbl_pr = table._tbl.tblPr
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        table._tbl.insert(0, tbl_pr)
    jc = OxmlElement("w:jc")
    jc.set(qn("w:val"), "right")
    tbl_pr.append(jc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_docx(
    docs: list[dict[str, Any]],
    title: str,
    gov_options: Any | None = None,
) -> bytes:
    """Build a DOCX from a list of rendered docs.

    Args:
        docs: List of {"doc_type": str, "markdown": str}.
        title: Document title.
        gov_options: Optional ``GovDocOptions`` dataclass instance.  When
            ``gov_options.is_government_format`` is ``True`` the full 행안부
            공문서 standard layout is applied (margins, header block, approval
            table).  Without gov_options the document uses sensible defaults
            that still produce an A4 document with Korean font.

    Returns:
        Raw bytes of the .docx file.
    """
    opts = gov_options

    # Resolve layout parameters (with fallbacks for no gov_options)
    top_mm    = opts.top_margin_mm    if opts else 30
    bot_mm    = opts.bottom_margin_mm if opts else 15
    left_mm   = opts.left_margin_mm   if opts else 20
    right_mm  = opts.right_margin_mm  if opts else 20
    font_name = opts.font_name        if opts else "맑은 고딕"
    font_size = opts.font_size_pt     if opts else 10.5
    spacing   = opts.line_spacing_pct if opts else 160

    doc = Document()

    # ── Page layout ───────────────────────────────────────────────────────
    section = doc.sections[0]
    section.page_width  = Mm(210)   # A4
    section.page_height = Mm(297)   # A4
    section.top_margin    = Mm(top_mm)
    section.bottom_margin = Mm(bot_mm)
    section.left_margin   = Mm(left_mm)
    section.right_margin  = Mm(right_mm)
    section.header_distance = Mm(10)
    section.footer_distance = Mm(10)

    # ── Default font ──────────────────────────────────────────────────────
    _set_default_font(doc, font_name, font_size)

    # ── Header / Footer ───────────────────────────────────────────────────
    _add_gov_header(section, opts)
    _add_page_number_footer(section, font_name)

    # ── Document body ─────────────────────────────────────────────────────
    if opts and opts.is_government_format:
        _add_gov_doc_header_block(doc, title, opts)
    else:
        doc.add_heading(title, level=0)

    for i, d in enumerate(docs):
        if i > 0:
            doc.add_page_break()
        _add_markdown_content(doc, d.get("markdown", ""), font_name, font_size, spacing)

    # ── Approval block (공문서 전용) ──────────────────────────────────────
    if opts and opts.is_government_format:
        _add_approval_block(doc, opts)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
