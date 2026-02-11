import json
from pathlib import Path

from app.providers.mock_provider import MockProvider
from app.providers.stabilizer import stabilize_bundle
from app.schemas import GenerateRequest
from app.services.generation_service import GenerationService


def test_stabilizer_adds_missing_top_level_keys():
    bundle = {"adr": {"decision": "x", "options": [], "risks": [], "assumptions": [], "checks": [], "next_actions": []}}
    stabilized = stabilize_bundle(bundle)
    assert {"adr", "onepager", "eval_plan", "ops_checklist"} <= set(stabilized.keys())


def test_stabilizer_coerces_wrong_section_types():
    bundle = {
        "adr": [],
        "onepager": "bad",
        "eval_plan": None,
        "ops_checklist": 123,
    }
    stabilized = stabilize_bundle(bundle)
    assert isinstance(stabilized["adr"], dict)
    assert isinstance(stabilized["onepager"], dict)
    assert isinstance(stabilized["eval_plan"], dict)
    assert isinstance(stabilized["ops_checklist"], dict)


def test_internal_marker_does_not_leak_to_cache_or_render(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")

    class MarkerProvider(MockProvider):
        def generate_bundle(self, requirements, *, schema_version, request_id):  # noqa: ANN001
            bundle = super().generate_bundle(requirements, schema_version=schema_version, request_id=request_id)
            bundle["_stabilized"] = {"patched": ["forced"]}
            return bundle

    service = GenerationService(
        provider_factory=lambda: MarkerProvider(),
        template_dir=Path("app/templates/v1"),
        data_dir=tmp_path,
    )
    req = GenerateRequest(title="stabilizer", goal="leak test")
    result = service.generate_documents(req, request_id="req-stabilizer")

    assert "_stabilized" not in result["raw_bundle"]
    for doc in result["docs"]:
        assert "_stabilized" not in doc["markdown"]

    cache_files = list((tmp_path / "cache").glob("*.json"))
    assert cache_files
    cache_text = cache_files[0].read_text(encoding="utf-8")
    cache_json = json.loads(cache_text)
    assert "_stabilized" not in cache_json
