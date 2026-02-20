import logging

import pytest
from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch, *, cors_enabled="0", cors_allow_origins=None):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("DECISIONDOC_CORS_ENABLED", cors_enabled)
    if cors_allow_origins is None:
        monkeypatch.delenv("DECISIONDOC_CORS_ALLOW_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("DECISIONDOC_CORS_ALLOW_ORIGINS", cors_allow_origins)
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


def test_auth_legacy_decisiondoc_api_key_still_works(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "expected-key"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_auth_accepts_any_key_from_decisiondoc_api_keys(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "k1, k2")

    response_k1 = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "k1"},
        json={"title": "t", "goal": "g"},
    )
    response_k2 = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "k2"},
        json={"title": "t", "goal": "g"},
    )
    response_wrong = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "k3"},
        json={"title": "t", "goal": "g"},
    )

    assert response_k1.status_code == 200
    assert response_k2.status_code == 200
    assert response_wrong.status_code == 401
    assert response_wrong.json()["code"] == "UNAUTHORIZED"


def test_generate_export_requires_api_key_when_configured(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post("/generate/export", json={"title": "t", "goal": "g"})
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"
    assert body["message"] == "Authentication required."
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_generate_export_wrong_api_key_returns_401(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post(
        "/generate/export",
        headers={"X-DecisionDoc-Api-Key": "wrong-key"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "UNAUTHORIZED"


def test_generate_export_accepts_correct_api_key(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post(
        "/generate/export",
        headers={"X-DecisionDoc-Api-Key": "expected-key"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert len(body["files"]) == 4


def test_health_does_not_require_api_key(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_options_preflight_with_cors_enabled_returns_cors_headers(tmp_path, monkeypatch):
    client = _create_client(
        tmp_path,
        monkeypatch,
        cors_enabled="1",
        cors_allow_origins="https://example.com",
    )
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "k1,k2")

    response = client.options(
        "/generate",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "X-DecisionDoc-Api-Key,Content-Type",
        },
    )

    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "https://example.com"


def test_options_does_not_return_401_without_cors_middleware(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")
    client = _create_client(tmp_path, monkeypatch)

    response = client.options("/generate")
    assert response.status_code != 401


def test_prod_env_requires_api_key_on_startup(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="API key"):
        create_app()


def test_prod_env_accepts_decisiondoc_api_keys_on_startup(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "k1,k2")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    from app.main import create_app

    create_app()


def test_docs_and_openapi_disabled_in_prod(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_ENV", "prod")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    from app.main import create_app

    client = TestClient(create_app())
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_logs_do_not_expose_api_key(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)
    sentinel_key = "SUPER_SECRET_API_KEY_VALUE"
    sentinel_body = "SUPER_SECRET_DO_NOT_LOG"
    monkeypatch.setenv("DECISIONDOC_API_KEYS", f"{sentinel_key},backup-key")

    response = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "wrong-key"},
        json={"title": sentinel_body, "goal": sentinel_body, "context": sentinel_body},
    )
    assert response.status_code == 401

    all_logs = "\n".join([caplog.text] + [str(r.msg) for r in caplog.records])
    assert sentinel_key not in all_logs
    assert sentinel_body not in all_logs
    assert "X-DecisionDoc-Api-Key" not in all_logs
    assert "DECISIONDOC_API_KEY" not in all_logs
    assert "DECISIONDOC_API_KEYS" not in all_logs
