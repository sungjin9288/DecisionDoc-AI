import json
import sys
import types
from pathlib import Path

import pytest

from app.providers.openai_provider import OpenAIProvider
from app.schemas import GenerateRequest
from app.services.generation_service import GenerationService, ProviderFailedError


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


def test_generation_service_autoescape_is_html_only(tmp_path, monkeypatch):
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

    assert service.env.autoescape("sample.md.j2") is False
    assert service.env.autoescape("sample.html") is True


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


def _make_service(tmp_path):
    from app.providers.factory import get_provider

    return GenerationService(
        provider_factory=get_provider,
        template_dir=Path("app/templates/v1"),
        data_dir=Path(tmp_path),
    )


@pytest.mark.parametrize(
    "bad_bundle, expected_fragment",
    [
        # Not a dict at all
        ("not-a-dict", "expected dict, got str"),
        # Missing top-level key
        ({}, "missing top-level key 'adr'"),
        # Top-level key present but not a dict
        ({"adr": "wrong-type", "onepager": {}, "eval_plan": {}, "ops_checklist": {}}, "'adr' must be a dict, got str"),
        # Missing required field inside a section
        (
            {
                "adr": {"options": [], "risks": [], "assumptions": [], "checks": [], "next_actions": []},
                "onepager": {"problem": "", "recommendation": "", "impact": [], "checks": []},
                "eval_plan": {"metrics": [], "test_cases": [], "failure_criteria": [], "monitoring": []},
                "ops_checklist": {"security": [], "reliability": [], "cost": [], "operations": []},
            },
            "missing field 'adr.decision'",
        ),
        # Field present but wrong type (should be string, got int)
        (
            {
                "adr": {
                    "decision": 999,
                    "options": [],
                    "risks": [],
                    "assumptions": [],
                    "checks": [],
                    "next_actions": [],
                },
                "onepager": {"problem": "", "recommendation": "", "impact": [], "checks": []},
                "eval_plan": {"metrics": [], "test_cases": [], "failure_criteria": [], "monitoring": []},
                "ops_checklist": {"security": [], "reliability": [], "cost": [], "operations": []},
            },
            "'adr.decision' must be a string, got int",
        ),
        # Array field present but not a list
        (
            {
                "adr": {
                    "decision": "",
                    "options": "not-a-list",
                    "risks": [],
                    "assumptions": [],
                    "checks": [],
                    "next_actions": [],
                },
                "onepager": {"problem": "", "recommendation": "", "impact": [], "checks": []},
                "eval_plan": {"metrics": [], "test_cases": [], "failure_criteria": [], "monitoring": []},
                "ops_checklist": {"security": [], "reliability": [], "cost": [], "operations": []},
            },
            "'adr.options' must be an array, got str",
        ),
        # Array element is not a string
        (
            {
                "adr": {
                    "decision": "",
                    "options": [42],
                    "risks": [],
                    "assumptions": [],
                    "checks": [],
                    "next_actions": [],
                },
                "onepager": {"problem": "", "recommendation": "", "impact": [], "checks": []},
                "eval_plan": {"metrics": [], "test_cases": [], "failure_criteria": [], "monitoring": []},
                "ops_checklist": {"security": [], "reliability": [], "cost": [], "operations": []},
            },
            "'adr.options[0]' must be a string, got int",
        ),
    ],
)
def test_validate_bundle_schema_error_messages(tmp_path, monkeypatch, bad_bundle, expected_fragment):
    from app.bundle_catalog.registry import get_bundle_spec

    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    service = _make_service(tmp_path)
    bundle_spec = get_bundle_spec("tech_decision")
    with pytest.raises(ProviderFailedError) as exc_info:
        service._validate_bundle_schema(bad_bundle, bundle_spec)
    assert expected_fragment in str(exc_info.value)


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
