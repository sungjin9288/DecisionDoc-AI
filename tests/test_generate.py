import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.providers.factory import get_provider
from app.providers.mock_provider import MockProvider
from app.services.validator import validate_docs


def _create_client(tmp_path, monkeypatch, provider="mock"):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)

    from app.main import create_app

    app = create_app()
    return TestClient(app)


def test_generate_minimal_payload_returns_all_docs(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/generate",
        json={
            "title": "DecisionDoc MVP",
            "goal": "Generate baseline decision docs",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    assert "bundle_id" in body
    assert body["provider"] == "mock"
    assert body["schema_version"] == "v1"
    assert len(body["docs"]) == 4

    for doc in body["docs"]:
        assert isinstance(doc["markdown"], str)
        assert doc["markdown"].strip()

    saved = Path(tmp_path) / f"{body['bundle_id']}.json"
    assert saved.exists()
    saved_body = json.loads(saved.read_text(encoding="utf-8"))
    assert {"adr", "onepager", "eval_plan", "ops_checklist"} <= set(saved_body.keys())


def test_generate_with_mock_provider_ok(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch, provider="mock")
    response = client.post("/generate", json={"title": "mock ok", "goal": "smoke"})
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert len(body["docs"]) == 4
    validate_docs(body["docs"])


def test_missing_required_fields_return_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    no_title = client.post("/generate", json={"goal": "x"})
    no_goal = client.post("/generate", json={"title": "x"})

    assert no_title.status_code == 422
    assert no_goal.status_code == 422


def test_empty_title_or_goal_returns_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    empty_title = client.post("/generate", json={"title": "", "goal": "valid goal"})
    empty_goal = client.post("/generate", json={"title": "valid title", "goal": ""})

    assert empty_title.status_code == 422
    assert empty_goal.status_code == 422


def test_invalid_doc_type_returns_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/generate",
        json={"title": "x", "goal": "y", "doc_types": ["bad_type"]},
    )
    assert response.status_code == 422


def test_empty_doc_types_returns_422(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/generate",
        json={"title": "x", "goal": "y", "doc_types": []},
    )
    assert response.status_code == 422


def test_extremely_long_title_is_accepted(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    long_title = "A" * 5000
    response = client.post(
        "/generate",
        json={"title": long_title, "goal": "validate long title behavior"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == long_title


def test_doc_validation_failure_returns_stable_500_payload(tmp_path, monkeypatch):
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
    assert body["code"] == "DOC_VALIDATION_FAILED"
    assert body["message"] == "Document validation failed."
    assert isinstance(body["request_id"], str)


def test_provider_factory_default_is_mock(monkeypatch):
    monkeypatch.delenv("DECISIONDOC_PROVIDER", raising=False)
    provider = get_provider()
    assert provider.name == "mock"


def test_bundle_schema_required_keys_exist_for_mock_provider():
    provider = MockProvider()
    bundle = provider.generate_bundle(
        {"title": "x", "goal": "y", "doc_types": ["adr", "onepager", "eval_plan", "ops_checklist"]},
        schema_version="v1",
        request_id="req-1",
    )
    assert set(bundle.keys()) == {"adr", "onepager", "eval_plan", "ops_checklist"}


def test_provider_missing_key_returns_500_provider_failed(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = _create_client(tmp_path, monkeypatch, provider="openai")
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "PROVIDER_FAILED"
    assert body["message"] == "Provider request failed."
    assert isinstance(body["request_id"], str)


def test_bundle_schema_validation_missing_required_key_returns_provider_failed(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class InvalidTypedProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id)
            bundle["ops_checklist"]["security"] = [123]
            return bundle

    monkeypatch.setattr(main_module, "get_provider", lambda: InvalidTypedProvider())
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "PROVIDER_FAILED"
    assert body["message"] == "Provider request failed."
    assert isinstance(body["request_id"], str)


@pytest.mark.parametrize("fixture_path", sorted(Path(__file__).parent.joinpath("fixtures").glob("*.json")))
def test_regression_fixtures_generate_valid_docs(tmp_path, monkeypatch, fixture_path):
    client = _create_client(tmp_path, monkeypatch)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    response = client.post("/generate", json=payload)

    assert response.status_code == 200, fixture_path.name
    body = response.json()
    expected_len = len(payload.get("doc_types", ["adr", "onepager", "eval_plan", "ops_checklist"]))
    assert len(body["docs"]) == expected_len

    validate_docs(body["docs"])


def test_generate_export_returns_files_and_writes_markdown(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/generate/export",
        json={"title": "Export Smoke", "goal": "Verify export endpoint"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "request_id" in body
    assert "bundle_id" in body
    assert "export_dir" in body
    assert len(body["files"]) == 4

    export_dir = Path(body["export_dir"])
    assert export_dir.exists()
    assert export_dir.is_dir()

    for item in body["files"]:
        md_path = Path(item["path"])
        assert md_path.exists()
        assert md_path.suffix == ".md"
        assert md_path.read_text(encoding="utf-8").strip()


def test_generate_export_validation_failure_returns_500_and_no_export_dir(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class BrokenMockProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id)
            bundle["adr"]["options"] = ["only one option"]
            return bundle

    monkeypatch.setattr(main_module, "get_provider", lambda: BrokenMockProvider())
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate/export", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "DOC_VALIDATION_FAILED"
    assert body["message"] == "Document validation failed."
    assert isinstance(body["request_id"], str)

    assert not any(Path(tmp_path).glob("*/*.md"))
