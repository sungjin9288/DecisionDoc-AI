"""Tests for POST /generate/review endpoint."""
import pytest
from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    from app.providers.mock_provider import MockProvider

    app = create_app()
    # The review endpoint reads request.app.state.provider; inject MockProvider
    app.state.provider = MockProvider()
    return TestClient(app)


_SAMPLE_DOC = """## 기술 결정 개요
결제 시스템을 MSA로 전환합니다.
## 배경
현재 모놀리식 아키텍처로 인해 배포 주기가 길고 장애 격리가 어렵습니다.
## 결정
서비스 경계를 Payment, User, Notification 3개로 분리하고, API Gateway 패턴을 적용합니다.
"""


def test_review_returns_200(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/review", json={"content": _SAMPLE_DOC})
    assert res.status_code == 200


def test_review_has_score(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/review", json={"content": _SAMPLE_DOC}).json()
    assert "score" in data
    assert isinstance(data["score"], int)


def test_review_has_grade(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/review", json={"content": _SAMPLE_DOC}).json()
    assert "grade" in data
    assert data["grade"] in {"S", "A", "B", "C", "D"}


def test_review_has_strengths(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/review", json={"content": _SAMPLE_DOC}).json()
    assert "strengths" in data
    assert isinstance(data["strengths"], list)


def test_review_has_improvements(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/review", json={"content": _SAMPLE_DOC}).json()
    assert "improvements" in data
    assert isinstance(data["improvements"], list)


def test_review_has_summary(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/review", json={"content": _SAMPLE_DOC}).json()
    assert "summary" in data
    assert isinstance(data["summary"], str)


def test_review_has_request_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/review", json={"content": _SAMPLE_DOC}).json()
    assert "request_id" in data
    assert data["request_id"]


def test_review_missing_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/review", json={})
    assert res.status_code == 422


def test_review_empty_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post("/generate/review", json={"content": ""})
    assert res.status_code == 422


def test_review_too_long_content(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    huge = "A" * 31000
    res = client.post("/generate/review", json={"content": huge})
    assert res.status_code == 422


def test_review_with_bundle_type(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    res = client.post(
        "/generate/review",
        json={"content": _SAMPLE_DOC, "bundle_type": "tech_decision"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "score" in data
    assert "grade" in data
    assert "strengths" in data
    assert "improvements" in data
    assert "summary" in data


def test_review_score_in_range(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    data = client.post("/generate/review", json={"content": _SAMPLE_DOC}).json()
    assert "score" in data
    score = data["score"]
    assert 0 <= score <= 100
