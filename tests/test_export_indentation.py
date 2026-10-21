"""Indented sub-items (개조식 위계) stay indented in PDF, DOCX and HWPX."""
from __future__ import annotations

import io
import zipfile

from docx import Document

from app.schemas.visual_assets import GovDocOptions
from app.services.docx_service import build_docx
from app.services.hwp_service import build_hwp
from app.services.markdown_utils import parse_markdown_blocks
from app.services.pdf_service import _markdown_to_html

MARKDOWN = "1. 사업 배경\n  가. 문서가 분산되어 있다.\n    1) 부서 공유폴더\n- 목록 항목\n  - 하위 목록\n\t가. 탭 들여쓰기\n"


def test_parser_records_indent_levels_only_when_indented() -> None:
    blocks = parse_markdown_blocks(MARKDOWN)

    assert blocks[0] == {"type": "paragraph", "text": "1. 사업 배경"}
    assert [block.get("indent") for block in blocks] == [None, 1, 2, None, 1, 2]
    assert blocks[4] == {"type": "list_item", "text": "하위 목록", "indent": 1}


def test_pdf_html_indents_by_one_em_per_level() -> None:
    html = _markdown_to_html(MARKDOWN)

    assert "<p>1. 사업 배경</p>" in html
    assert "<p style='margin-left:1em'>가. 문서가 분산되어 있다.</p>" in html
    assert "<p style='margin-left:2em'>1) 부서 공유폴더</p>" in html
    assert "<li style='margin-left:1em'>하위 목록</li>" in html


def test_docx_indents_by_one_font_size_per_level() -> None:
    content = build_docx([{"doc_type": "body", "markdown": MARKDOWN}], "제목", gov_options=GovDocOptions(package_cover=False))
    paragraphs = {p.text: p for p in Document(io.BytesIO(content)).paragraphs if p.text}

    assert paragraphs["1. 사업 배경"].paragraph_format.left_indent in (None, 0)
    assert paragraphs["가. 문서가 분산되어 있다."].paragraph_format.left_indent.pt == 10.5
    assert paragraphs["1) 부서 공유폴더"].paragraph_format.left_indent.pt == 21.0


def test_hwpx_indents_with_two_half_width_spaces_per_level() -> None:
    content = build_hwp([{"doc_type": "body", "markdown": MARKDOWN}], "제목", gov_options=GovDocOptions(package_cover=False))
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        section = archive.read("Contents/section0.xml").decode("utf-8")

    assert "<hp:t>1. 사업 배경</hp:t>" in section
    assert "<hp:t>  가. 문서가 분산되어 있다.</hp:t>" in section
    assert "<hp:t>    1) 부서 공유폴더</hp:t>" in section
