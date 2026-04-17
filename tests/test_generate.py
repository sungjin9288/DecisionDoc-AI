import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.providers.base import ProviderError
from app.providers.factory import get_provider
from app.providers.mock_provider import MockProvider
from app.services.validator import validate_docs


def _create_client(tmp_path, monkeypatch, provider="mock"):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

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


def test_generate_accepts_optional_style_profile_id(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch, provider="mock")
    response = client.post(
        "/generate",
        json={
            "title": "style profile payload",
            "goal": "web ui compatibility",
            "style_profile_id": "default-consulting",
        },
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


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
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id, bundle_spec=bundle_spec, feedback_hints=feedback_hints)
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


def test_provider_missing_key_raises_at_startup(tmp_path, monkeypatch):
    # Startup fail-fast: missing API key is now caught during create_app(), not at
    # first request. This guards against silent misconfiguration before serving traffic.
    # Patch load_dotenv to prevent the real .env file from overwriting monkeypatched vars.
    monkeypatch.setattr("app.main.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "openai")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        create_app()


def test_claude_provider_missing_key_raises_at_startup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.load_dotenv", lambda *a, **kw: None)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "claude")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.main import create_app

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is required"):
        create_app()


def test_bundle_schema_validation_missing_required_key_returns_provider_failed(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class InvalidTypedProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            raise RuntimeError("provider internal error")

    monkeypatch.setattr(main_module, "get_provider", lambda: InvalidTypedProvider())
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "PROVIDER_FAILED"
    assert body["message"] == "Provider request failed."
    assert isinstance(body["request_id"], str)


def test_provider_rate_limit_returns_503_with_retry_guidance(tmp_path, monkeypatch):
    import app.main as main_module

    class FakeRateLimitError(Exception):
        status_code = 429

        def __init__(self) -> None:
            super().__init__("429 Too Many Requests")
            self.response = type(
                "FakeResponse",
                (),
                {"status_code": 429, "headers": {"retry-after": "12"}},
            )()

    class RateLimitedProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            try:
                raise FakeRateLimitError()
            except Exception as exc:
                raise ProviderError("Provider request failed.") from exc

    monkeypatch.setattr(main_module, "get_provider", lambda: RateLimitedProvider())
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "PROVIDER_FAILED"
    assert body["message"] == "AI provider is temporarily rate limited. 잠시 후 다시 시도하세요."
    assert body["errors"] == ["retry_after_seconds=12"]


def test_provider_quota_exhausted_returns_503_with_quota_guidance(tmp_path, monkeypatch):
    import app.main as main_module

    class FakeQuotaError(Exception):
        status_code = 429

        def __init__(self) -> None:
            super().__init__("insufficient_quota")
            self.body = {"error": {"code": "insufficient_quota", "message": "quota exhausted"}}
            self.response = type(
                "FakeResponse",
                (),
                {"status_code": 429, "headers": {}},
            )()

    class QuotaLimitedProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            try:
                raise FakeQuotaError()
            except Exception as exc:
                raise ProviderError("Provider request failed.") from exc

    monkeypatch.setattr(main_module, "get_provider", lambda: QuotaLimitedProvider())
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate", json={"title": "x", "goal": "y"})
    assert response.status_code == 503
    body = response.json()
    assert body["code"] == "PROVIDER_FAILED"
    assert body["message"] == "AI provider quota is exhausted. 운영 키 또는 과금 한도를 확인하세요."
    assert body["errors"] == ["provider_error_code=insufficient_quota"]


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


def test_corrupt_cache_file_is_removed_and_regenerated(tmp_path, monkeypatch):
    """If the cache file is corrupt, it should be deleted and re-generated on the next call."""
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    client = _create_client(tmp_path, monkeypatch)

    # First call: populate cache
    response1 = client.post("/generate", json={"title": "cache test", "goal": "test"})
    assert response1.status_code == 200

    # Find the cache file and corrupt it
    cache_dir = tmp_path / "cache"
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) >= 1
    cache_file = cache_files[0]
    cache_file.write_text("{corrupted-json-content", encoding="utf-8")

    # Second call: should detect corruption, remove file, and regenerate
    response2 = client.post("/generate", json={"title": "cache test", "goal": "test"})
    assert response2.status_code == 200
    assert response2.json()["provider"] == "mock"

    # The corrupt file should have been replaced with a valid cache
    new_content = cache_file.read_text(encoding="utf-8")
    parsed = json.loads(new_content)
    assert isinstance(parsed, dict)
    assert "adr" in parsed


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


def test_generate_injects_ranked_knowledge_context(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider
    from app.storage.knowledge_store import KnowledgeStore

    captured: dict[str, object] = {}

    class InspectingMockProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            captured["requirements"] = dict(requirements)
            return super().generate_bundle(
                requirements,
                schema_version=schema_version,
                request_id=request_id,
                bundle_spec=bundle_spec,
                feedback_hints=feedback_hints,
            )

    monkeypatch.setattr(main_module, "get_provider", lambda: InspectingMockProvider())
    client = _create_client(tmp_path, monkeypatch)

    store = KnowledgeStore("proj-knowledge", data_dir=str(tmp_path))
    store.add_document(
        "generic-guide.txt",
        "일반 참고문서 내용",
        learning_mode="reference",
        quality_tier="working",
    )
    store.add_document(
        "winning-proposal.docx",
        "파주시 모빌리티 제안 승인본 구조",
        learning_mode="approved_output",
        quality_tier="gold",
        applicable_bundles=["proposal_kr"],
        source_organization="파주시",
        reference_year=2025,
        success_state="approved",
        notes="제안서 구조와 표 구성이 우수함",
    )

    response = client.post(
        "/generate",
        json={
            "title": "파주시 모빌리티 제안",
            "goal": "승인 가능한 제안서 작성",
            "bundle_type": "proposal_kr",
            "project_id": "proj-knowledge",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "applied_references" in body
    assert len(body["applied_references"]) >= 1
    top_ref = body["applied_references"][0]
    assert top_ref["filename"] == "winning-proposal.docx"
    assert top_ref["selection_reason"]
    assert top_ref["bundle_match"] is True
    assert isinstance(top_ref["score_breakdown"], list)
    injected = str(captured["requirements"])
    assert "_knowledge_context" in injected
    assert "winning-proposal.docx" in injected
    assert "우선 적용 문서: proposal_kr" in injected
    assert "품질 등급: gold" in injected


def test_generate_succeeds_when_eval_executor_is_unavailable(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    def _raise_executor_shutdown(*args, **kwargs):  # noqa: ANN001, ARG001
        raise RuntimeError("cannot schedule new futures after shutdown")

    monkeypatch.setattr("app.services.generation_service._eval_executor.submit", _raise_executor_shutdown)

    response = client.post(
        "/generate",
        json={"title": "executor shutdown", "goal": "skip background eval safely"},
    )

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"


def test_generate_export_validation_failure_returns_500_and_no_export_dir(tmp_path, monkeypatch):
    import app.main as main_module
    from app.providers.mock_provider import MockProvider

    class BrokenMockProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id, bundle_spec=None, feedback_hints=""):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id, bundle_spec=bundle_spec, feedback_hints=feedback_hints)
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
