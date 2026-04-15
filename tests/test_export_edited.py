"""Tests for POST /generate/export-edited endpoint.

The endpoint accepts pre-rendered (possibly user-edited) docs and converts them
to the requested file format without re-running LLM generation.
Supported formats: docx, pdf, excel, hwp, pptx.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from io import BytesIO
from pptx import Presentation

_ZIP_MAGIC  = b"PK\x03\x04"   # OOXML (.docx / .xlsx) and hwpx
_PDF_MAGIC  = b"%PDF"


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY",  raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return TestClient(create_app())


_SAMPLE_DOCS = [
    {"doc_type": "adr",      "markdown": "# 결정\n\n## 배경\n\n배경 내용입니다.\n\n- 항목 1\n- 항목 2"},
    {"doc_type": "onepager", "markdown": "## 요약\n\n**핵심 포인트**: 테스트 문서입니다."},
]


# ── /generate/export-edited — docx ─────────────────────────────────────────

def test_export_edited_docx_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "docx",
        "title": "편집된 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.status_code == 200


def test_export_edited_docx_content_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "docx",
        "title": "편집된 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert "wordprocessingml" in res.headers["content-type"]


def test_export_edited_docx_valid_bytes(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "docx",
        "title": "편집된 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.content[:4] == _ZIP_MAGIC


# ── /generate/export-edited — excel ────────────────────────────────────────

def test_export_edited_excel_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "excel",
        "title": "엑셀 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.status_code == 200


def test_export_edited_excel_valid_bytes(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "excel",
        "title": "엑셀 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.content[:4] == _ZIP_MAGIC


# ── /generate/export-edited — hwp ──────────────────────────────────────────

def test_export_edited_hwp_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "hwp",
        "title": "한글 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.status_code == 200


def test_export_edited_hwp_valid_bytes(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "hwp",
        "title": "한글 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.content[:4] == _ZIP_MAGIC  # hwpx is ZIP-based


# ── /generate/export-edited — pdf ──────────────────────────────────────────

def test_export_edited_pdf_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "pdf",
        "title": "PDF 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.status_code == 200


def test_export_edited_pdf_content_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "pdf",
        "title": "PDF 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.headers["content-type"] == "application/pdf"


def test_export_edited_pdf_valid_bytes(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "pdf",
        "title": "PDF 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.content[:4] == _PDF_MAGIC


# ── /generate/export-edited — pptx ─────────────────────────────────────────

def test_export_edited_pptx_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "pptx",
        "title": "PPT 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.status_code == 200


def test_export_edited_pptx_content_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "pptx",
        "title": "PPT 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert "presentationml.presentation" in res.headers["content-type"]


def test_export_edited_pptx_valid_bytes(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "pptx",
        "title": "PPT 편집 문서",
        "docs": _SAMPLE_DOCS,
    })
    assert res.content[:4] == _ZIP_MAGIC


def test_export_edited_pptx_skips_ppt_guide_sections(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    docs = [
        {
            "doc_type": "proposal_kr",
            "markdown": (
                "# 사업 이해\n\n"
                "## 제안 요약\n\n핵심 요약입니다.\n\n"
                "## PPT 구성 가이드\n\n- 발표용 메모 1\n- 발표용 메모 2\n"
            ),
        }
    ]
    res = client.post("/generate/export-edited", json={
        "format": "pptx",
        "title": "PPT 편집 문서",
        "docs": docs,
    })
    assert res.status_code == 200
    prs = Presentation(BytesIO(res.content))
    titles = [slide.shapes.title.text for slide in prs.slides if getattr(slide.shapes, "title", None)]
    assert "제안 요약" in titles
    assert not any("PPT 구성 가이드" in title for title in titles)


# ── edge-cases & validation ─────────────────────────────────────────────────

def test_export_edited_unsupported_format_returns_400(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "pages",
        "title": "테스트",
        "docs": _SAMPLE_DOCS,
    })
    assert res.status_code == 400


def test_export_edited_empty_docs_still_returns_file(tmp_path, monkeypatch):
    """Endpoint must not crash when docs list is empty — returns a minimal file."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "docx",
        "title": "빈 문서",
        "docs": [],
    })
    assert res.status_code == 200
    assert res.content[:4] == _ZIP_MAGIC


def test_export_edited_content_disposition_filename(tmp_path, monkeypatch):
    """Content-Disposition header must carry the document title as filename."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/export-edited", json={
        "format": "docx",
        "title": "편집 문서 제목",
        "docs": _SAMPLE_DOCS,
    })
    assert res.status_code == 200
    disp = res.headers.get("content-disposition", "")
    assert "document.docx" in disp


def test_export_edited_no_llm_call(tmp_path, monkeypatch):
    """Export-edited must NOT call the LLM — verify by counting generate calls."""
    call_count = {"n": 0}
    _original_generate = None

    def _patched_generate(*args, **kwargs):
        call_count["n"] += 1
        return _original_generate(*args, **kwargs)

    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY",  raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.providers.mock_provider import MockProvider
    _original_generate = MockProvider.generate_bundle
    monkeypatch.setattr(MockProvider, "generate_bundle", _patched_generate)

    from app.main import create_app
    client = TestClient(create_app())
    client.post("/generate/export-edited", json={
        "format": "docx",
        "title": "테스트",
        "docs": _SAMPLE_DOCS,
    })
    assert call_count["n"] == 0, "export-edited must not invoke generate_bundle"
