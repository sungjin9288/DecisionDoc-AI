import logging

import pytest
from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    from app.main import create_app

    return TestClient(create_app())


def test_generate_requires_api_key_when_configured(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post("/generate", json={"title": "t", "goal": "g"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"
    assert body["message"] == "Authentication required."
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_generate_wrong_api_key_returns_401(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "wrong-key"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"


def test_generate_accepts_correct_api_key(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "expected-key"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_health_does_not_require_api_key(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_prod_env_requires_api_key_on_startup(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="DECISIONDOC_API_KEY"):
        create_app()


def test_logs_do_not_expose_api_key(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)
    sentinel = "SUPER_SECRET_API_KEY_VALUE"
    monkeypatch.setenv("DECISIONDOC_API_KEY", sentinel)

    response = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "wrong-key"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 401

    all_logs = "\n".join([caplog.text] + [str(r.msg) for r in caplog.records])
    assert sentinel not in all_logs
    assert "X-DecisionDoc-Api-Key" not in all_logs
