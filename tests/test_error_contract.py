import re

from fastapi.testclient import TestClient


REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def _create_client(tmp_path, monkeypatch, provider="mock"):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def test_request_id_generated_header_present(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    request_id = response.headers.get("X-Request-Id", "")
    assert REQUEST_ID_RE.fullmatch(request_id)


def test_request_id_passthrough(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    request_id = "test-req-1234"
    response = client.get("/health", headers={"X-Request-Id": request_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id") == request_id


def test_provider_failed_error_contract(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _create_client(tmp_path, monkeypatch, provider="openai")
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "PROVIDER_FAILED"
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_storage_failed_error_contract(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_STORAGE", "s3")
    monkeypatch.delenv("DECISIONDOC_S3_BUCKET", raising=False)
    client = _create_client(tmp_path, monkeypatch, provider="mock")
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "STORAGE_FAILED"
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_doc_validation_failed_error_contract(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class BrokenMockProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id)
            bundle["adr"]["options"] = ["only one option"]
            return bundle

    monkeypatch.setattr(main_module, "get_provider", lambda: BrokenMockProvider())
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "DOC_VALIDATION_FAILED"
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_eval_lint_failed_error_contract(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class LintFailMockProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id)
            bundle["onepager"]["problem"] = "TODO improve this section"
            return bundle

    monkeypatch.setattr(main_module, "get_provider", lambda: LintFailMockProvider())
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "EVAL_LINT_FAILED"
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_request_validation_422_error_contract(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/generate", json={"title": "only-title"})
    assert response.status_code == 422
    body = response.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "REQUEST_VALIDATION_FAILED"
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_unauthorized_401_error_contract(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-api-key")
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 401
    body = response.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "UNAUTHORIZED"
    assert body["request_id"] == response.headers.get("X-Request-Id")


def test_maintenance_mode_503_error_contract(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "1")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-api-key")
    response = client.post(
        "/generate",
        headers={"X-DecisionDoc-Api-Key": "test-api-key"},
        json={"title": "x", "goal": "y"},
    )
    assert response.status_code == 503
    body = response.json()
    assert set(body.keys()) == {"code", "message", "request_id"}
    assert body["code"] == "MAINTENANCE_MODE"
    assert body["request_id"] == response.headers.get("X-Request-Id")
