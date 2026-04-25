"""Tests for POST /generate/sketch endpoint."""
import pytest
from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.delenv("DECISIONDOC_SEARCH_ENABLED", raising=False)
    from app.main import create_app
    return TestClient(create_app())


def test_sketch_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/sketch", json={"title": "스케치 테스트", "goal": "검증"})
    assert res.status_code == 200


def test_sketch_has_sections(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/sketch", json={"title": "t", "goal": "g"}).json()
    assert "sections" in data
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) > 0


def test_sketch_sections_have_heading_and_bullets(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/sketch", json={"title": "t", "goal": "g"}).json()
    for section in data["sections"]:
        assert "heading" in section
        assert "bullets" in section
        assert isinstance(section["bullets"], list)


def test_sketch_ppt_bundle_has_slides(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post(
        "/generate/sketch",
        json={"title": "발표 자료 테스트", "goal": "PPT 스케치 확인", "bundle_type": "presentation_kr"},
    ).json()
    assert data.get("ppt_slides") is not None
    assert len(data["ppt_slides"]) > 0
    first = data["ppt_slides"][0]
    assert "page" in first
    assert "title" in first
    assert "key_content" in first


def test_sketch_non_ppt_bundle_no_slides(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post(
        "/generate/sketch",
        json={"title": "t", "goal": "g", "bundle_type": "tech_decision"},
    ).json()
    # tech_decision has no slide_outline — ppt_slides should be null/None
    assert data.get("ppt_slides") is None


def test_sketch_has_search_fields(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/sketch", json={"title": "t", "goal": "g"}).json()
    assert "has_search" in data
    assert "search_snippets" in data
    assert isinstance(data["search_snippets"], list)


def test_sketch_accepts_optional_style_profile_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/sketch",
        json={
            "title": "스타일 포함 스케치",
            "goal": "웹 UI payload 호환성 검증",
            "bundle_type": "tech_decision",
            "style_profile_id": "default-consulting",
        },
    )
    assert res.status_code == 200
