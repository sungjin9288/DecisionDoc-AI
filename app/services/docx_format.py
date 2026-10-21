"""Low-level python-docx formatting helpers shared by the DOCX exporter."""
from __future__ import annotations

from typing import Any

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt


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


def _set_indent(para: Any, block: dict[str, Any], font_size_pt: float) -> None:
    """One Hangul character (one font size) per 개조식 sub-item level."""
    indent = int(block.get("indent", 0) or 0)
    if indent:
        para.paragraph_format.left_indent = Pt(font_size_pt * indent)


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
