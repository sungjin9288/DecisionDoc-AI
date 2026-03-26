"""Tests for POST /generate/pptx endpoint."""
from io import BytesIO

from fastapi.testclient import TestClient

_PPTX_MAGIC = b"PK\x03\x04"  # ZIP/OOXML magic bytes — all .pptx files start with this


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    return TestClient(create_app())


def test_pptx_returns_binary_for_presentation_kr(tmp_path, monkeypatch):
    """Endpoint returns a valid PPTX binary for presentation_kr bundles."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "AI 발표", "goal": "핵심 전달", "bundle_type": "presentation_kr"},
    )
    assert res.status_code == 200
    assert "presentation" in res.headers["content-type"]
    assert "attachment" in res.headers.get("content-disposition", "")
    assert res.content[:4] == _PPTX_MAGIC


def test_pptx_returns_422_for_wrong_bundle(tmp_path, monkeypatch):
    """Non-presentation bundles return 422 with BUNDLE_NOT_SUPPORTED code."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "기술 결정", "goal": "아키텍처 선택", "bundle_type": "tech_decision"},
    )
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "BUNDLE_NOT_SUPPORTED"
    assert "request_id" in body


def test_pptx_default_bundle_is_rejected(tmp_path, monkeypatch):
    """Omitting bundle_type defaults to tech_decision and should be rejected."""
    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "테스트 결정", "goal": "테스트 목표"},
    )
    assert res.status_code == 422
    assert res.json()["code"] == "BUNDLE_NOT_SUPPORTED"


def test_pptx_slide_count(tmp_path, monkeypatch):
    """Mock builder returns 5 slides → cover(1) + 5 content = 6 slides total."""
    from pptx import Presentation

    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/pptx",
        json={"title": "슬라이드 카운트 테스트", "goal": "슬라이드 수 확인", "bundle_type": "presentation_kr"},
    )
    assert res.status_code == 200
    prs = Presentation(BytesIO(res.content))
    assert len(prs.slides) == 6  # 1 cover + 5 from mock outline
