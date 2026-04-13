from __future__ import annotations

import io

from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    return TestClient(create_app())


def test_generate_from_documents_success(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/from-documents",
        data={
            "doc_types": "adr,onepager",
            "goal": "업로드 문서를 기반으로 초안을 생성한다.",
        },
        files={"files": ("notes.txt", io.BytesIO(b"decision context"), "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "notes"
    assert [doc["doc_type"] for doc in body["docs"]] == ["adr", "onepager"]


def test_generate_from_documents_rejects_invalid_extension(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate/from-documents",
        data={"doc_types": "adr"},
        files={"files": ("malware.exe", io.BytesIO(b"not allowed"), "application/octet-stream")},
    )

    assert response.status_code == 422
    assert "지원하지 않는 파일 형식" in response.json()["detail"]


def test_generate_from_documents_requires_api_key_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "valid-key-abc")

    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/generate/from-documents",
        data={"doc_types": "adr"},
        files={"files": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )

    assert response.status_code == 401


def test_generate_from_documents_allows_bearer_auth_without_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEYS", "valid-key-abc")

    from app.main import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    register = client.post(
        "/auth/register",
        json={
            "username": "upload-admin",
            "display_name": "Upload Admin",
            "email": "upload-admin@example.com",
            "password": "UploadAdmin1!",
        },
    )

    assert register.status_code == 200
    token = register.json()["access_token"]

    response = client.post(
        "/generate/from-documents",
        headers={"Authorization": f"Bearer {token}"},
        data={"doc_types": "adr,onepager"},
        files={"files": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )

    assert response.status_code == 200
    assert [doc["doc_type"] for doc in response.json()["docs"]] == ["adr", "onepager"]
