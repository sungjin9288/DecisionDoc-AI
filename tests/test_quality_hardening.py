import json
import sys
import types
from pathlib import Path

import pytest

from app.providers.openai_provider import OpenAIProvider
from app.schemas import GenerateRequest
from app.services.generation_service import GenerationService


def test_eval_lints_ok_for_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "0")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.providers.factory import get_provider

    service = GenerationService(
        provider_factory=get_provider,
        template_dir=Path("app/templates/v1"),
        data_dir=Path(tmp_path),
    )
    payload = GenerateRequest(title="lint fixture", goal="validate lints do not trigger")
    result = service.generate_documents(payload, request_id="lint-req")
    assert len(result["docs"]) == 4


def test_cache_corruption_is_cache_miss(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    from app.providers.factory import get_provider

    service = GenerationService(
        provider_factory=get_provider,
        template_dir=Path("app/templates/v1"),
        data_dir=Path(tmp_path),
    )
    payload = GenerateRequest(title="cache", goal="corruption handling")
    payload_dict = payload.model_dump(mode="json")
    cache_path = service._cache_path("mock", "v1", payload_dict)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{not-json", encoding="utf-8")

    result = service.generate_documents(payload, request_id="cache-req")
    assert result["metadata"]["cache_hit"] is False

    repaired = json.loads(cache_path.read_text(encoding="utf-8"))
    assert isinstance(repaired, dict)
    assert "adr" in repaired


def test_openai_retries_disabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            _ = kwargs
            return types.SimpleNamespace(
                output_text='{"adr":{"decision":"","options":["a","b"],"risks":[],"assumptions":[],"checks":[],"next_actions":[]},'
                '"onepager":{"problem":"","recommendation":"","impact":[],"checks":[]},'
                '"eval_plan":{"metrics":[],"test_cases":[],"failure_criteria":[],"monitoring":[]},'
                '"ops_checklist":{"security":[],"reliability":[],"cost":[],"operations":[]}}'
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.responses = FakeResponses()

    fake_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_module)

    provider = OpenAIProvider()
    bundle = provider.generate_bundle({"title": "x", "goal": "y"}, schema_version="v1", request_id="req")
    assert captured["max_retries"] == 0
    assert "adr" in bundle
