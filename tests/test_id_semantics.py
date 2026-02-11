from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch, provider="mock"):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def test_bundle_id_is_uuid_and_storage_uses_bundle_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/generate", json={"title": "id test", "goal": "bundle id separation"})
    assert response.status_code == 200
    body = response.json()
    bundle_id = body["bundle_id"]
    UUID(bundle_id)
    assert body["request_id"] != bundle_id

    assert (Path(tmp_path) / f"{bundle_id}.json").exists()


def test_request_id_is_trace_id_and_independent_from_bundle_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    request_id = "trace-req-12345"
    response = client.post(
        "/generate/export",
        headers={"X-Request-Id": request_id},
        json={"title": "id separation", "goal": "verify request/bundle ids"},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["request_id"] == request_id
    assert response.headers.get("X-Request-Id") == request_id
    assert body["bundle_id"] != request_id

    export_dir = Path(body["export_dir"])
    assert export_dir.name == body["bundle_id"]
    for item in body["files"]:
        assert body["bundle_id"] in item["path"]
