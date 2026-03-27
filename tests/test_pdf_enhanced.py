"""Tests for enhanced PDF extraction and /generate/from-pdf endpoint.

Covers:
- extract_pdf_structured() structured output
- _extract_pdf() fallback behaviour
- POST /generate/from-pdf endpoint (success, auth, validation)
- pdf_source prompt injection in build_bundle_prompt
- SKIP_KEYS exclusion of pdf_source / pdf_sections
"""
from __future__ import annotations

import io
import json
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from fastapi.testclient import TestClient
    from app.main import create_app
    return TestClient(create_app())


def _make_char(text: str, top: float, x0: float, size: float, fontname: str = "Arial") -> dict:
    return {"text": text, "top": top, "x0": x0, "size": size, "fontname": fontname}


def _make_mock_page(
    chars: list[dict] | None = None,
    text: str = "Sample text",
    tables: list | None = None,
) -> MagicMock:
    """Build a mock pdfplumber page object."""
    page = MagicMock()
    page.chars = chars if chars is not None else []
    page.extract_text.return_value = text
    page.extract_tables.return_value = tables or []
    return page


def _make_pdfplumber_mock(pages: list[MagicMock]) -> MagicMock:
    """Return a mock pdfplumber module with a fake open() context manager."""
    mock_module = MagicMock()

    mock_pdf = MagicMock()
    mock_pdf.__enter__ = lambda s: s
    mock_pdf.__exit__ = MagicMock(return_value=False)
    mock_pdf.pages = pages

    mock_module.open.return_value = mock_pdf
    return mock_module


# ── Test 1: basic structured extraction ───────────────────────────────────────

def test_extract_pdf_structured_basic():
    """extract_pdf_structured should return all expected keys with reasonable values."""
    from app.services.attachment_service import extract_pdf_structured

    heading_chars = [
        _make_char(c, top=10.0, x0=i * 8.0, size=18.0) for i, c in enumerate("Title")
    ]
    body_chars = [
        _make_char(c, top=30.0, x0=i * 6.0, size=10.0) for i, c in enumerate("Body text here")
    ]

    mock_page = _make_mock_page(chars=heading_chars + body_chars, tables=[])
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = extract_pdf_structured(b"%PDF fake", "test.pdf")

    assert isinstance(result, dict)
    assert "title" in result
    assert "sections" in result
    assert "raw_text" in result
    assert "page_count" in result
    assert "has_tables" in result
    assert isinstance(result["sections"], list)
    assert result["page_count"] == 1
    assert result["has_tables"] is False


# ── Test 2: fallback when chars unavailable ────────────────────────────────────

def test_extract_pdf_fallback():
    """_extract_pdf should fall back to extract_text when chars is empty."""
    from app.services.attachment_service import _extract_pdf

    mock_page = _make_mock_page(chars=[], text="Fallback plain text")
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = _extract_pdf(b"%PDF fake", "fallback.pdf")

    assert "Fallback plain text" in result


# ── Test 3: /generate/from-pdf endpoint success ───────────────────────────────

def test_from_pdf_endpoint_success(tmp_path, monkeypatch):
    """POST /generate/from-pdf should return 200 and a valid GenerateResponse."""
    client = _create_client(tmp_path, monkeypatch)

    structured_result = {
        "title": "Test PDF Title",
        "sections": [{"heading": "Introduction", "content": "Some content"}],
        "raw_text": "Test PDF Title\nIntroduction\nSome content",
        "page_count": 1,
        "has_tables": False,
    }

    with patch(
        "app.routers.generate.extract_pdf_structured",
        return_value=structured_result,
    ):
        fake_pdf = io.BytesIO(b"%PDF-1.4 content")
        response = client.post(
            "/generate/from-pdf",
            data={"doc_types": "adr,onepager", "tenant_id": "default"},
            files={"file": ("test.pdf", fake_pdf, "application/pdf")},
        )

    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    assert "bundle_id" in body
    assert "docs" in body
    assert len(body["docs"]) > 0


# ── Test 4: rejects non-PDF files ─────────────────────────────────────────────

def test_from_pdf_endpoint_rejects_non_pdf(tmp_path, monkeypatch):
    """POST /generate/from-pdf should return 422 for non-PDF uploads."""
    client = _create_client(tmp_path, monkeypatch)

    fake_txt = io.BytesIO(b"This is plain text, not a PDF")
    response = client.post(
        "/generate/from-pdf",
        data={"doc_types": "adr"},
        files={"file": ("document.txt", fake_txt, "text/plain")},
    )

    assert response.status_code == 422
    assert "PDF" in response.json().get("detail", "")


# ── Test 5: rejects files over 20MB ───────────────────────────────────────────

def test_from_pdf_endpoint_too_large(tmp_path, monkeypatch):
    """POST /generate/from-pdf should return 422 when file exceeds 20MB."""
    client = _create_client(tmp_path, monkeypatch)

    oversized = io.BytesIO(b"A" * (20 * 1024 * 1024 + 1))
    response = client.post(
        "/generate/from-pdf",
        data={"doc_types": "adr"},
        files={"file": ("large.pdf", oversized, "application/pdf")},
    )

    assert response.status_code == 422
    detail = response.json().get("detail", "")
    assert "20MB" in detail or "20 MB" in detail


# ── Test 6: no auth returns 401 ───────────────────────────────────────────────

def test_from_pdf_endpoint_no_auth(tmp_path, monkeypatch):
    """POST /generate/from-pdf should return 401 when API key is required but missing."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "valid-key-abc")

    from fastapi.testclient import TestClient
    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)

    fake_pdf = io.BytesIO(b"%PDF-1.4 content")
    response = client.post(
        "/generate/from-pdf",
        data={"doc_types": "adr"},
        files={"file": ("test.pdf", fake_pdf, "application/pdf")},
    )

    # UnauthorizedError is mapped to 401 by the exception handler
    assert response.status_code == 401


# ── Test 7: pdf_source injected into prompt ───────────────────────────────────

def test_pdf_source_in_prompt():
    """build_bundle_prompt should include pdf_source content in the final prompt."""
    from app.domain.schema import build_bundle_prompt

    requirements = {
        "title": "Decision",
        "goal": "Test",
        "pdf_source": "This is the PDF raw text content that should appear in prompt.",
    }

    prompt = build_bundle_prompt(requirements, schema_version="v1")

    assert "참고 PDF 원문" in prompt
    assert "This is the PDF raw text content" in prompt


# ── Test 8: pdf_source excluded from clean_requirements ───────────────────────

def test_skip_keys_exclude_pdf_source():
    """_clean_requirements_for_prompt should strip pdf_source and pdf_sections."""
    from app.domain.schema import _clean_requirements_for_prompt

    requirements = {
        "title": "My Decision",
        "goal": "Validate skip keys",
        "pdf_source": "large raw text " * 500,
        "pdf_sections": '["Section A", "Section B"]',
        "context": "Some context",
    }

    cleaned = _clean_requirements_for_prompt(requirements)

    assert "pdf_source" not in cleaned
    assert "pdf_sections" not in cleaned
    assert "title" in cleaned
    assert "context" in cleaned


# ── Test 9: structured extraction returns sections list ───────────────────────

def test_structured_has_sections():
    """extract_pdf_structured should return a non-empty sections list for PDFs with headings."""
    from app.services.attachment_service import extract_pdf_structured

    chars = []
    # First heading: large font (24pt) vs body (10pt) → avg ~14pt, 24 > 14*1.2=16.8 → heading
    for i, c in enumerate("Introduction"):
        chars.append(_make_char(c, top=10.0, x0=i * 8.0, size=24.0))
    for i, c in enumerate("Body paragraph text"):
        chars.append(_make_char(c, top=30.0, x0=i * 6.0, size=10.0))
    for i, c in enumerate("Conclusion"):
        chars.append(_make_char(c, top=50.0, x0=i * 8.0, size=24.0))
    for i, c in enumerate("Final remarks"):
        chars.append(_make_char(c, top=70.0, x0=i * 6.0, size=10.0))

    mock_page = _make_mock_page(chars=chars, tables=[])
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = extract_pdf_structured(b"%PDF fake", "sections.pdf")

    assert len(result["sections"]) >= 2
    headings = [s["heading"] for s in result["sections"]]
    assert "Introduction" in headings
    assert "Conclusion" in headings


# ── Test 10: title detection from first large heading ─────────────────────────

def test_structured_title_detection():
    """extract_pdf_structured should detect the first large-font line as the title."""
    from app.services.attachment_service import extract_pdf_structured

    # First line: large font (24pt) only; body at 10pt → avg = mixed
    title_chars = [
        _make_char(c, top=5.0, x0=i * 10.0, size=24.0) for i, c in enumerate("MyDocTitle")
    ]
    body_chars = [
        _make_char(c, top=25.0, x0=i * 6.0, size=10.0) for i, c in enumerate("Normal body")
    ]

    mock_page = _make_mock_page(chars=title_chars + body_chars, tables=[])
    mock_pdfplumber = _make_pdfplumber_mock([mock_page])

    with patch.dict(sys.modules, {"pdfplumber": mock_pdfplumber}):
        result = extract_pdf_structured(b"%PDF fake", "title_test.pdf")

    assert result["title"] == "MyDocTitle"
