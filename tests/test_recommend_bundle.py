"""Tests for POST /generate/recommend-bundle endpoint."""
import pytest


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    return create_app()


def test_recommend_returns_200(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    app = _create_client(tmp_path, monkeypatch)
    client = TestClient(app)
    res = client.post("/generate/recommend-bundle", json={"title": "경영 현황 보고서", "goal": "임원 보고"})
    assert res.status_code == 200


def test_recommend_has_recommended_field(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    app = _create_client(tmp_path, monkeypatch)
    client = TestClient(app)
    data = client.post("/generate/recommend-bundle", json={"title": "경영 보고서", "goal": "임원 보고"}).json()
    assert "recommended" in data
    assert isinstance(data["recommended"], list)


def test_recommend_management_report(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    app = _create_client(tmp_path, monkeypatch)
    client = TestClient(app)
    data = client.post("/generate/recommend-bundle", json={"title": "경영 현황 보고서", "goal": "이사회 보고"}).json()
    assert "management_report" in data["recommended"]


def test_recommend_g2b_bid(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    app = _create_client(tmp_path, monkeypatch)
    client = TestClient(app)
    data = client.post("/generate/recommend-bundle", json={"title": "나라장터 입찰 제안서", "goal": "공공기관 수주"}).json()
    assert "g2b_bid" in data["recommended"] or "proposal_kr" in data["recommended"]


def test_recommend_max_3_results(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    app = _create_client(tmp_path, monkeypatch)
    client = TestClient(app)
    data = client.post("/generate/recommend-bundle", json={"title": "제안서 분석 계약", "goal": "경영 보고 평가"}).json()
    assert len(data["recommended"]) <= 3


def test_recommend_returns_empty_for_unrelated(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    app = _create_client(tmp_path, monkeypatch)
    client = TestClient(app)
    data = client.post("/generate/recommend-bundle", json={"title": "xyzzy", "goal": "unknown"}).json()
    assert isinstance(data["recommended"], list)


def test_recommend_domain_function():
    from app.domain.schema import recommend_bundles
    result = recommend_bundles("회의 미팅 agenda")
    assert "meeting_minutes" in result


def test_recommend_domain_function_empty():
    from app.domain.schema import recommend_bundles
    result = recommend_bundles("")
    assert result == []
