"""tests/test_style_system.py — Tests for custom tone/style learning system.

Coverage (24 tests):
  StyleStore unit   : create, get, get_default, list_by_tenant, first-auto-default,
                      set_default, update_tone_guide, bundle_override crud,
                      add_example, remove_example, delete
  style_analyzer    : build_style_prompt with tone guide, with bundle override,
                      empty profile → "", no-content tone → "",
                      analyze_document_style mock provider (happy + fallback)
  API endpoints     : create profile, list, get detail, set default,
                      update tone, set/remove bundle override, delete
  Style injection   : build_bundle_prompt includes style block when default exists
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.async_helper import run_async


# ── Client factory ─────────────────────────────────────────────────────────────


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app())


# ── StyleStore unit tests ──────────────────────────────────────────────────────


def test_style_store_create(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    profile = store.create("t1", "표준체", "우리 회사 표준 문체", "user-1")
    assert profile.profile_id
    assert profile.name == "표준체"
    assert profile.description == "우리 회사 표준 문체"
    assert profile.created_by == "user-1"
    assert profile.is_default is True  # first profile auto-set as default


def test_style_store_get(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    created = store.create("t1", "A", "", "u1")
    found = store.get(created.profile_id)
    assert found is not None
    assert found.profile_id == created.profile_id
    assert store.get("nonexistent-id") is None


def test_style_store_get_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    p1 = store.create("t1", "First", "", "u1")
    p2 = store.create("t1", "Second", "", "u1")
    # First is auto-default; second should not be
    default = store.get_default("t1")
    assert default is not None
    assert default.profile_id == p1.profile_id


def test_style_store_list_by_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("multi")
    store.create("tenant_a", "A1", "", "u1")
    store.create("tenant_a", "A2", "", "u1")
    store.create("tenant_b", "B1", "", "u2")
    assert len(store.list_by_tenant("tenant_a")) == 2
    assert len(store.list_by_tenant("tenant_b")) == 1
    assert store.list_by_tenant("no_tenant") == []


def test_style_store_set_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    p1 = store.create("t1", "First", "", "u1")
    p2 = store.create("t1", "Second", "", "u1")

    store.set_default(p2.profile_id)
    assert store.get(p2.profile_id).is_default is True
    assert store.get(p1.profile_id).is_default is False
    assert store.get_default("t1").profile_id == p2.profile_id


def test_style_store_update_tone_guide(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, ToneGuide

    store = StyleStore("t1")
    profile = store.create("t1", "A", "", "u1")
    tone = ToneGuide(
        formality="합쇼체",
        density="상세하게",
        perspective="기관명칭",
        custom_rules=["수치 포함 필수"],
        forbidden_words=["~것 같습니다"],
        preferred_words=["추진합니다"],
    )
    updated = store.update_tone_guide(profile.profile_id, tone)
    assert updated.tone_guide.formality == "합쇼체"
    assert updated.tone_guide.density == "상세하게"
    assert "수치 포함 필수" in updated.tone_guide.custom_rules
    assert "추진합니다" in updated.tone_guide.preferred_words


def test_style_store_bundle_override_set_and_remove(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, ToneGuide

    store = StyleStore("t1")
    profile = store.create("t1", "A", "", "u1")
    override_tone = ToneGuide(formality="해요체", density="간결하게")
    store.set_bundle_override(profile.profile_id, "proposal_kr", override_tone)

    reloaded = store.get(profile.profile_id)
    assert "proposal_kr" in reloaded.bundle_overrides
    assert reloaded.bundle_overrides["proposal_kr"].formality == "해요체"

    store.remove_bundle_override(profile.profile_id, "proposal_kr")
    reloaded2 = store.get(profile.profile_id)
    assert "proposal_kr" not in reloaded2.bundle_overrides


def test_style_store_add_and_remove_example(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, StyleExample
    import uuid

    store = StyleStore("t1")
    profile = store.create("t1", "A", "", "u1")
    example = StyleExample(
        example_id=str(uuid.uuid4()),
        source_filename="report.pdf",
        bundle_id=None,
        extracted_patterns=["~합니다"],
        sample_sentences=["우리는 추진합니다."],
        uploaded_at="2026-01-01T00:00:00Z",
        uploaded_by="u1",
    )
    store.add_example(profile.profile_id, example)
    reloaded = store.get(profile.profile_id)
    assert len(reloaded.examples) == 1
    assert reloaded.examples[0].source_filename == "report.pdf"

    store.remove_example(profile.profile_id, example.example_id)
    reloaded2 = store.get(profile.profile_id)
    assert len(reloaded2.examples) == 0


def test_style_store_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    profile = store.create("t1", "ToDelete", "", "u1")
    assert store.get(profile.profile_id) is not None
    store.delete(profile.profile_id)
    assert store.get(profile.profile_id) is None


# ── style_analyzer unit tests ─────────────────────────────────────────────────


def test_build_style_prompt_with_tone_guide(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, ToneGuide
    from app.services.style_analyzer import build_style_prompt

    store = StyleStore("t1")
    profile = store.create("t1", "A", "", "u1")
    store.update_tone_guide(
        profile.profile_id,
        ToneGuide(
            formality="합쇼체",
            density="상세하게",
            perspective="기관명칭",
            custom_rules=["수치 포함"],
            forbidden_words=["~것 같습니다"],
            preferred_words=["추진합니다"],
        ),
    )
    reloaded = store.get(profile.profile_id)
    prompt = build_style_prompt(reloaded)

    assert "합쇼체" in prompt
    assert "상세하게" in prompt
    assert "수치 포함" in prompt
    assert "추진합니다" in prompt
    assert "~것 같습니다" in prompt
    assert "=== 문체 및 스타일 지침 ===" in prompt
    assert "=== 문체 지침 끝 ===" in prompt


def test_build_style_prompt_uses_bundle_override(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, ToneGuide
    from app.services.style_analyzer import build_style_prompt

    store = StyleStore("t1")
    profile = store.create("t1", "A", "", "u1")
    # Global tone: 합쇼체
    store.update_tone_guide(profile.profile_id, ToneGuide(formality="합쇼체"))
    # Override for proposal_kr: 해요체
    store.set_bundle_override(profile.profile_id, "proposal_kr", ToneGuide(formality="해요체"))
    reloaded = store.get(profile.profile_id)

    # With bundle_id → should use override
    prompt_with_override = build_style_prompt(reloaded, bundle_id="proposal_kr")
    assert "해요체" in prompt_with_override

    # Without bundle_id → should use global
    prompt_global = build_style_prompt(reloaded, bundle_id=None)
    assert "합쇼체" in prompt_global


def test_build_style_prompt_empty_profile_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.services.style_analyzer import build_style_prompt

    assert build_style_prompt(None) == ""  # type: ignore[arg-type]


def test_build_style_prompt_no_content_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore
    from app.services.style_analyzer import build_style_prompt

    store = StyleStore("t1")
    # Fresh profile with empty ToneGuide and no examples
    profile = store.create("t1", "Empty", "", "u1")
    reloaded = store.get(profile.profile_id)
    # All ToneGuide fields are "" by default → nothing to inject
    assert build_style_prompt(reloaded) == ""


def test_build_style_prompt_includes_sample_sentences(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, ToneGuide, StyleExample
    from app.services.style_analyzer import build_style_prompt
    import uuid

    store = StyleStore("t1")
    profile = store.create("t1", "WithEx", "", "u1")
    store.update_tone_guide(profile.profile_id, ToneGuide(formality="합쇼체"))
    example = StyleExample(
        example_id=str(uuid.uuid4()),
        source_filename="doc.pdf",
        bundle_id=None,
        extracted_patterns=[],
        sample_sentences=["이를 위해 적극 추진합니다."],
        uploaded_at="2026-01-01T00:00:00Z",
        uploaded_by="u1",
    )
    store.add_example(profile.profile_id, example)
    reloaded = store.get(profile.profile_id)
    prompt = build_style_prompt(reloaded)
    assert "이를 위해 적극 추진합니다." in prompt


def test_analyze_document_style_mock_provider(tmp_path):
    """analyze_document_style returns parsed dict from provider.generate_raw."""
    from app.services.style_analyzer import analyze_document_style

    expected_json = """{
      "formality": "합쇼체",
      "density": "상세",
      "perspective": "기관명칭",
      "patterns": ["~합니다"],
      "sample_sentences": ["우리는 추진합니다."],
      "preferred_expressions": ["추진합니다"],
      "avoid_expressions": [],
      "summary": "공식적인 문체를 사용합니다."
    }"""

    class FakeProvider:
        async def generate_raw(self, prompt, max_tokens=None):
            return expected_json

    content = b"Sample document text for style analysis."
    result = run_async(analyze_document_style("report.txt", content, None, FakeProvider()))
    assert result["formality"] == "합쇼체"
    assert result["density"] == "상세"
    assert "우리는 추진합니다." in result["sample_sentences"]


def test_analyze_document_style_json_parse_failure_returns_fallback(tmp_path):
    """On JSON parse failure, analyze_document_style returns fallback dict."""
    from app.services.style_analyzer import analyze_document_style

    class BrokenProvider:
        async def generate_raw(self, prompt, max_tokens=None):
            return "This is not valid JSON at all!"

    content = b"Some text."
    result = run_async(analyze_document_style("doc.txt", content, None, BrokenProvider()))
    assert result["formality"] == "혼용"
    assert result["density"] == "보통"
    assert result["patterns"] == []


# ── API endpoint tests ─────────────────────────────────────────────────────────


def test_api_create_and_list_style_profiles(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    res = client.post("/styles", json={"name": "테스트 프로필", "description": "설명"})
    assert res.status_code == 200
    assert "profile_id" in res.json()

    list_res = client.get("/styles")
    assert list_res.status_code == 200
    profiles = list_res.json()["profiles"]
    assert len(profiles) == 1
    assert profiles[0]["name"] == "테스트 프로필"
    assert profiles[0]["is_default"] is True  # first profile auto-default


def test_api_get_style_profile_detail(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    create_res = client.post("/styles", json={"name": "Detail Test"}).json()
    profile_id = create_res["profile_id"]

    res = client.get(f"/styles/{profile_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["profile_id"] == profile_id
    assert data["name"] == "Detail Test"
    assert "tone_guide" in data
    assert "examples" in data


def test_api_get_nonexistent_profile_returns_404(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    res = client.get("/styles/does-not-exist")
    assert res.status_code == 404


def test_api_set_default_style(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    p1 = client.post("/styles", json={"name": "P1"}).json()["profile_id"]
    p2 = client.post("/styles", json={"name": "P2"}).json()["profile_id"]

    client.post(f"/styles/{p2}/set-default")
    profiles = client.get("/styles").json()["profiles"]
    defaults = [p for p in profiles if p["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["profile_id"] == p2


def test_api_update_tone_guide(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    pid = client.post("/styles", json={"name": "Tone Test"}).json()["profile_id"]

    res = client.put(f"/styles/{pid}/tone", json={
        "formality": "합쇼체",
        "density": "상세하게",
        "perspective": "기관명칭",
        "custom_rules": ["수치 포함 필수"],
        "forbidden_words": ["~것 같습니다"],
        "preferred_words": ["추진합니다"],
    })
    assert res.status_code == 200
    detail = client.get(f"/styles/{pid}").json()
    assert detail["tone_guide"]["formality"] == "합쇼체"
    assert "수치 포함 필수" in detail["tone_guide"]["custom_rules"]


def test_api_set_and_remove_bundle_override(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    pid = client.post("/styles", json={"name": "Bundle Override Test"}).json()["profile_id"]

    set_res = client.put(f"/styles/{pid}/bundles/proposal_kr", json={
        "formality": "해요체", "density": "간결하게",
        "perspective": "", "custom_rules": [], "forbidden_words": [], "preferred_words": [],
    })
    assert set_res.status_code == 200
    detail = client.get(f"/styles/{pid}").json()
    assert "proposal_kr" in detail["bundle_overrides"]
    assert detail["bundle_overrides"]["proposal_kr"]["formality"] == "해요체"

    del_res = client.delete(f"/styles/{pid}/bundles/proposal_kr")
    assert del_res.status_code == 200
    detail2 = client.get(f"/styles/{pid}").json()
    assert "proposal_kr" not in detail2["bundle_overrides"]


def test_api_delete_style_profile(tmp_path, monkeypatch):
    client = _make_client(tmp_path, monkeypatch)
    pid = client.post("/styles", json={"name": "ToDelete"}).json()["profile_id"]
    del_res = client.delete(f"/styles/{pid}")
    assert del_res.status_code == 200
    assert client.get(f"/styles/{pid}").status_code == 404


# ── Style injection integration test ─────────────────────────────────────────


def test_style_injection_in_build_bundle_prompt(tmp_path, monkeypatch):
    """When a default style profile exists, build_bundle_prompt includes the style block."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")

    from app.storage.style_store import StyleStore, ToneGuide
    from app.domain.schema import build_bundle_prompt, _current_tenant_id

    # Create a style profile with a distinct formality marker
    store = StyleStore("injection-test")
    profile = store.create("injection-test", "Test", "", "u1")
    store.update_tone_guide(
        profile.profile_id,
        ToneGuide(formality="합쇼체_UNIQUE_MARKER", density="보통"),
    )

    # Set thread-local so the schema function knows which tenant
    _current_tenant_id.value = "injection-test"
    try:
        from app.bundle_catalog.registry import get_bundle_spec
        bundle_spec = get_bundle_spec("tech_decision")
        prompt = build_bundle_prompt({"title": "테스트"}, bundle_spec)
        assert "합쇼체_UNIQUE_MARKER" in prompt
    finally:
        _current_tenant_id.value = None
