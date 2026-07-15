from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Callable

import pytest

from tests.async_helper import run_async


DOCS = [{"doc_type": "proposal", "markdown": "# 사업 개요\n\n같은 입력입니다."}]
SLIDES = {
    "presentation_goal": "같은 입력입니다.",
    "slide_outline": [
        {
            "title": "사업 개요",
            "key_content": "같은 입력입니다.",
            "visual_direction": "텍스트",
        }
    ],
}


def _build_docx() -> bytes:
    from app.services.docx_service import build_docx

    return build_docx(DOCS, title="재현성 테스트")


def _build_excel() -> bytes:
    from app.services.excel_service import build_excel

    return build_excel(DOCS, title="재현성 테스트")


def _build_pptx() -> bytes:
    from app.services.pptx_service import build_pptx

    return build_pptx(SLIDES, title="재현성 테스트")


@pytest.mark.parametrize(
    ("format_name", "builder"),
    [
        ("docx", _build_docx),
        ("xlsx", _build_excel),
        ("pptx", _build_pptx),
    ],
)
def test_ooxml_exports_are_byte_reproducible(
    format_name: str,
    builder: Callable[[], bytes],
) -> None:
    first = builder()
    second = builder()

    assert first == second, format_name
    with zipfile.ZipFile(BytesIO(first)) as archive:
        assert {entry.date_time for entry in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        assert {entry.external_attr >> 16 for entry in archive.infolist()} == {0o100644}
        if format_name == "xlsx":
            core = archive.read("docProps/core.xml")
            shared_strings = archive.read("xl/sharedStrings.xml")
            assert b"2000-01-01T00:00:00Z" in core
            assert "생성 시각".encode() not in shared_strings


def test_pdf_export_is_byte_reproducible() -> None:
    from app.services.pdf_service import build_pdf

    first = run_async(build_pdf(DOCS, title="재현성 테스트"))
    second = run_async(build_pdf(DOCS, title="재현성 테스트"))

    assert first == second
    assert b"/CreationDate (D:20000101000000+00'00')" in first
    assert b"/ModDate (D:20000101000000+00'00')" in first
