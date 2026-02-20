from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def test_maintenance_blocks_generate(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "1")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "expected-key"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "MAINTENANCE_MODE"
    assert body["message"] == "Service temporarily unavailable."
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_maintenance_blocks_generate_export(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "true")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "expected-key")

    response = client.post(
        "/generate/export",
        headers={"X-DecisionDoc-Api-Key": "expected-key"},
        json={"title": "t", "goal": "g"},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "MAINTENANCE_MODE"
    assert body["message"] == "Service temporarily unavailable."
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_maintenance_does_not_block_health(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "1")

    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["maintenance"] is True
