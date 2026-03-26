"""Tests for POST /generate/pdf endpoint and pdf_service."""
import pytest

from tests.async_helper import run_async

_DOCX_MAGIC = b"%PDF"  # PDF starts with %PDF


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


def test_build_pdf_service_returns_pdf_bytes():
    """build_pdf should return valid PDF bytes (async function, run via asyncio)."""
    from app.services.pdf_service import build_pdf
    docs = [{"doc_type": "adr", "markdown": "# 제목\n\n내용입니다."}]
    pdf_bytes = run_async(build_pdf(docs, title="테스트"))
    assert pdf_bytes[:4] == b"%PDF"


def test_pdf_endpoint_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/pdf", json={"title": "PDF 테스트", "goal": "검증"})
    assert res.status_code == 200


def test_pdf_endpoint_content_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/pdf", json={"title": "t", "goal": "g"})
    assert "application/pdf" in res.headers["content-type"]


def test_pdf_endpoint_content_disposition(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/pdf", json={"title": "한글제목", "goal": "g"})
    assert "attachment" in res.headers.get("content-disposition", "")


def test_pdf_endpoint_returns_pdf_bytes(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/pdf", json={"title": "t", "goal": "g"})
    assert res.content[:4] == b"%PDF"
