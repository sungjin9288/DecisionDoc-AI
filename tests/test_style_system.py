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

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.async_helper import run_async


# ── Client factory ─────────────────────────────────────────────────────────────


def _make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_FREE_MODE", "0")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setattr("app.main.load_dotenv", lambda *args, **kwargs: None)
    from app.main import create_app

    return TestClient(create_app())


# ── StyleStore unit tests ──────────────────────────────────────────────────────


def test_style_store_create(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    profile = store.create("표준체", "우리 회사 표준 문체", "user-1")
    assert profile.profile_id
    assert profile.name == "표준체"
    assert profile.description == "우리 회사 표준 문체"
    assert profile.created_by == "user-1"
    assert profile.is_default is True  # first profile auto-set as default


def test_style_store_get(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    created = store.create("A", "", "u1")
    found = store.get(created.profile_id)
    assert found is not None
    assert found.profile_id == created.profile_id
    assert store.get("nonexistent-id") is None


def test_style_store_get_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    p1 = store.create("First", "", "u1")
    store.create("Second", "", "u1")
    # First is auto-default; second should not be
    default = store.get_default()
    assert default is not None
    assert default.profile_id == p1.profile_id


def test_style_store_lists_only_its_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    tenant_a = StyleStore("tenant_a")
    tenant_b = StyleStore("tenant_b")
    tenant_a.create("A1", "", "u1")
    tenant_a.create("A2", "", "u1")
    tenant_b.create("B1", "", "u2")
    assert len(tenant_a.list_profiles()) == 2
    assert len(tenant_b.list_profiles()) == 1


def test_style_store_set_default(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore

    store = StyleStore("t1")
    p1 = store.create("First", "", "u1")
    p2 = store.create("Second", "", "u1")

    store.set_default(p2.profile_id)
    assert store.get(p2.profile_id).is_default is True
    assert store.get(p1.profile_id).is_default is False
    assert store.get_default().profile_id == p2.profile_id


def test_style_store_update_tone_guide(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, ToneGuide

    store = StyleStore("t1")
    profile = store.create("A", "", "u1")
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
    profile = store.create("A", "", "u1")
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
    profile = store.create("A", "", "u1")
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
    profile = store.create("ToDelete", "", "u1")
    assert store.get(profile.profile_id) is not None
    store.delete(profile.profile_id)
    assert store.get(profile.profile_id) is None


# ── style_analyzer unit tests ─────────────────────────────────────────────────


def test_build_style_prompt_with_tone_guide(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, ToneGuide
    from app.services.style_analyzer import build_style_prompt

    store = StyleStore("t1")
    profile = store.create("A", "", "u1")
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
    profile = store.create("A", "", "u1")
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
    profile = store.create("Empty", "", "u1")
    reloaded = store.get(profile.profile_id)
    # All ToneGuide fields are "" by default → nothing to inject
    assert build_style_prompt(reloaded) == ""


def test_build_style_prompt_includes_sample_sentences(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.storage.style_store import StyleStore, ToneGuide, StyleExample
    from app.services.style_analyzer import build_style_prompt
    import uuid

    store = StyleStore("t1")
    profile = store.create("WithEx", "", "u1")
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


def test_build_style_prompt_uses_two_most_recent_valid_relevant_examples(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.services.style_analyzer import build_style_prompt
    from app.storage.style_store import StyleExample, StyleStore, ToneGuide

    store = StyleStore("t1")
    profile = store.create("Recent", "", "u1")
    store.update_tone_guide(profile.profile_id, ToneGuide(formality="합쇼체"))

    def add_example(example_id, bundle_id, sentences, uploaded_at):
        store.add_example(
            profile.profile_id,
            StyleExample(
                example_id=example_id,
                source_filename=f"{example_id}.txt",
                bundle_id=bundle_id,
                extracted_patterns=[],
                sample_sentences=sentences,
                uploaded_at=uploaded_at,
                uploaded_by="u1",
            ),
        )

    add_example(
        "00000000-0000-4000-8000-00000000000a",
        "proposal_kr",
        ["A 문장입니다."],
        "2026-01-01T00:00:00+00:00",
    )
    add_example(
        "00000000-0000-4000-8000-00000000000b",
        "proposal_kr",
        ["", "B 첫 문장입니다.", "   ", "B 둘째 문장입니다."],
        "2026-01-02T00:00:00+00:00",
    )
    add_example(
        "00000000-0000-4000-8000-00000000000c",
        None,
        ["C 문장입니다."],
        "2026-01-03T00:00:00+00:00",
    )
    add_example(
        "00000000-0000-4000-8000-00000000000d",
        "tech_decision",
        ["다른 번들 문장입니다."],
        "2026-01-04T00:00:00+00:00",
    )
    add_example(
        "00000000-0000-4000-8000-00000000000e",
        "proposal_kr",
        ["", "   "],
        "2026-01-05T00:00:00+00:00",
    )

    prompt = build_style_prompt(store.get(profile.profile_id), bundle_id="proposal_kr")

    assert "A 문장입니다." not in prompt
    assert "B 첫 문장입니다." in prompt
    assert "B 둘째 문장입니다." in prompt
    assert "C 문장입니다." in prompt
    assert "다른 번들 문장입니다." not in prompt
    assert prompt.index("B 첫 문장입니다.") < prompt.index("C 문장입니다.")


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
        async def generate_raw(self, prompt, *, request_id, max_output_tokens=None):
            return expected_json

    content = b"Sample document text for style analysis."
    result = run_async(analyze_document_style("report.txt", content, None, FakeProvider()))
    assert result["formality"] == "합쇼체"
    assert result["density"] == "상세"
    assert "우리는 추진합니다." in result["sample_sentences"]


@pytest.mark.parametrize(
    "provider_result",
    [
        "This is not valid JSON at all!",
        "[]",
        '{"formality": [], "density": "보통", "perspective": "혼용", '
        '"patterns": [], "sample_sentences": ["문장"], '
        '"preferred_expressions": [], "avoid_expressions": [], "summary": "요약"}',
        '{"formality": "혼용", "density": "보통", "perspective": "혼용", '
        '"patterns": [], "sample_sentences": ["", "   "], '
        '"preferred_expressions": [], "avoid_expressions": [], "summary": "요약"}',
        RuntimeError("provider unavailable"),
        TypeError("provider body failed"),
    ],
)
def test_analyze_document_style_invalid_result_fails_once(provider_result):
    from app.services.style_analyzer import analyze_document_style

    class StubProvider:
        calls = 0

        async def generate_raw(self, prompt, *, request_id, max_output_tokens=None):
            self.calls += 1
            if isinstance(provider_result, Exception):
                raise provider_result
            return provider_result

    provider = StubProvider()
    usage_totals = {}
    content = b"Some text."
    with pytest.raises(ValueError, match="문체 분석에 실패했습니다"):
        run_async(
            analyze_document_style(
                "doc.txt",
                content,
                None,
                provider,
                usage_totals=usage_totals,
            )
        )
    assert provider.calls == 1
    assert usage_totals == {"provider_calls": 1}


def test_analyze_document_style_sync_type_error_is_not_retried():
    from app.services.style_analyzer import analyze_document_style

    class TypeErrorProvider:
        calls = 0

        def generate_raw(self, prompt, *, request_id, max_output_tokens=None):
            self.calls += 1
            raise TypeError("provider body failed")

    provider = TypeErrorProvider()
    usage_totals = {}
    with pytest.raises(ValueError, match="문체 분석에 실패했습니다"):
        run_async(
            analyze_document_style(
                "doc.txt",
                b"Some text.",
                None,
                provider,
                usage_totals=usage_totals,
            )
        )
    assert provider.calls == 1
    assert usage_totals == {"provider_calls": 1}


def test_analyze_document_style_image_uses_attachment_fallback(tmp_path):
    from app.services.style_analyzer import analyze_document_style

    expected_json = """{
      "formality": "혼용",
      "density": "보통",
      "perspective": "기관명칭",
      "patterns": ["캡션 중심"],
      "sample_sentences": ["이미지에 표 제목이 반복됩니다."],
      "preferred_expressions": ["현황", "근거"],
      "avoid_expressions": [],
      "summary": "이미지형 자료에서도 핵심 레이블과 캡션을 우선 정리합니다."
    }"""

    class SyncImageProvider:
        def extract_attachment_text(self, filename, raw, *, request_id):
            return "[텍스트]\n- 파주시 경영평가 착수보고\n[시각 요소]\n- 표지형 슬라이드\n[활용 포인트]\n- 제목과 핵심 수치를 요약"

        def generate_raw(self, prompt, *, request_id, max_output_tokens=None):
            return expected_json

    result = run_async(
        analyze_document_style("capture.png", b"\x89PNG\r\n\x1a\nfake", None, SyncImageProvider())
    )
    assert result["formality"] == "혼용"
    assert "이미지에 표 제목이 반복됩니다." in result["sample_sentences"]


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
    client.post("/styles", json={"name": "P1"})
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


def test_api_adds_reads_and_deletes_manual_style_example_without_provider(
    tmp_path, monkeypatch
):
    client = _make_client(tmp_path, monkeypatch)
    profile_id = client.post("/styles", json={"name": "Manual"}).json()["profile_id"]
    monkeypatch.setattr(
        "app.providers.factory.get_provider_for_bundle",
        lambda *args, **kwargs: pytest.fail("manual style example must not call provider"),
    )

    response = client.post(
        f"/styles/{profile_id}/examples",
        json={
            "label": "대표 제안 문장",
            "sample_sentences": [
                "사업 목표에 따라 단계별 실행계획을 수립합니다.",
                "성과지표는 측정 가능한 기준으로 관리합니다.",
            ],
            "bundle_id": "proposal_kr",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_filename"] == "수동 예시: 대표 제안 문장"
    example_id = payload["example_id"]
    detail = client.get(f"/styles/{profile_id}").json()
    assert detail["tone_guide"] == {
        "formality": "",
        "density": "",
        "perspective": "",
        "custom_rules": [],
        "forbidden_words": [],
        "preferred_words": [],
    }
    assert detail["examples"] == [
        {
            "example_id": example_id,
            "source_filename": "수동 예시: 대표 제안 문장",
            "bundle_id": "proposal_kr",
            "extracted_patterns": [],
            "sample_sentences": [
                "사업 목표에 따라 단계별 실행계획을 수립합니다.",
                "성과지표는 측정 가능한 기준으로 관리합니다.",
            ],
            "uploaded_at": detail["examples"][0]["uploaded_at"],
            "uploaded_by": "anonymous",
        }
    ]

    delete_response = client.delete(f"/styles/{profile_id}/examples/{example_id}")
    assert delete_response.status_code == 200
    assert client.get(f"/styles/{profile_id}").json()["examples"] == []


@pytest.mark.parametrize(
    "payload",
    [
        {"label": " ", "sample_sentences": ["유효한 문장입니다."]},
        {"label": "예시", "sample_sentences": []},
        {"label": "예시", "sample_sentences": ["문장"] * 9},
        {"label": "예시", "sample_sentences": ["   "]},
        {"label": "가" * 121, "sample_sentences": ["유효한 문장입니다."]},
        {"label": "예시", "sample_sentences": ["가" * 1001]},
        {
            "label": "예시",
            "sample_sentences": ["유효한 문장입니다."],
            "unexpected": True,
        },
    ],
)
def test_api_rejects_invalid_manual_style_example_without_saving(
    tmp_path, monkeypatch, payload
):
    client = _make_client(tmp_path, monkeypatch)
    profile_id = client.post("/styles", json={"name": "Bounds"}).json()["profile_id"]

    response = client.post(f"/styles/{profile_id}/examples", json=payload)

    assert response.status_code == 422
    assert client.get(f"/styles/{profile_id}").json()["examples"] == []


def test_api_manual_style_example_cannot_cross_tenant(tmp_path, monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "manual-style-test-secret-key-32chars")
    client = _make_client(tmp_path, monkeypatch)
    from app.services.auth_service import create_access_token
    from app.storage.style_store import StyleStore

    tenant_a_store = StyleStore(
        "tenant-a",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    )
    profile = tenant_a_store.create("Tenant A", "", "owner-a")
    tenant_b_token = create_access_token("user-b", "tenant-b", "member", "user-b")

    response = client.post(
        f"/styles/{profile.profile_id}/examples",
        headers={
            "Authorization": f"Bearer {tenant_b_token}",
            "X-Tenant-ID": "tenant-b",
        },
        json={"label": "Foreign", "sample_sentences": ["저장되면 안 됩니다."]},
    )

    assert response.status_code == 403
    assert tenant_a_store.get(profile.profile_id).examples == []


def test_manual_style_examples_feed_recent_example_prompt_without_provider(
    tmp_path, monkeypatch
):
    client = _make_client(tmp_path, monkeypatch)
    profile_id = client.post("/styles", json={"name": "Prompt"}).json()["profile_id"]
    monkeypatch.setattr(
        "app.providers.factory.get_provider_for_bundle",
        lambda *args, **kwargs: pytest.fail("manual style example must not call provider"),
    )
    for label in ("A", "B", "C"):
        response = client.post(
            f"/styles/{profile_id}/examples",
            json={
                "label": label,
                "sample_sentences": [f"수동 {label} 문장입니다."],
                "bundle_id": "proposal_kr",
            },
        )
        assert response.status_code == 200

    from app.services.style_analyzer import build_style_prompt
    from app.storage.style_store import get_style_store

    profile = get_style_store(
        "system",
        data_dir=tmp_path,
        backend=client.app.state.state_backend,
    ).get(profile_id)
    prompt = build_style_prompt(profile, bundle_id="proposal_kr")
    assert "수동 A 문장입니다." not in prompt
    assert "수동 B 문장입니다." in prompt
    assert "수동 C 문장입니다." in prompt


def test_manual_style_example_ui_contract_and_escaping() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    render_start = html.index("function renderStyleDetail")
    render_end = html.index("function wireStyleDetailActions", render_start)
    render_source = html[render_start:render_end]
    add_start = html.index("async function addManualStyleExample")
    add_end = html.index("async function analyzeStyleDocuments", add_start)
    add_source = html[add_start:add_end]

    for element_id in (
        "style-example-name",
        "style-example-sentences",
        "style-example-bundle",
        "style-example-save",
    ):
        assert f'id="{element_id}"' in render_source
    assert "escapeHtml(ex.source_filename || '')" in render_source
    assert (
        "escapeHtml(ex.bundle_id ? (_bundleNameMap[ex.bundle_id] || ex.bundle_id)"
        in render_source
    )
    assert "escapeHtml(s || '')" in render_source
    assert "if (saveButton.disabled) return;" in add_source
    assert "saveButton.disabled = true;" in add_source
    assert "sample_sentences: sampleSentences" in add_source
    assert "styleDetailProfileId" in add_source
    assert "loadStyleDetail(profileId, { isCurrent: isCurrentProfile })" in add_source


def test_api_style_analysis_retains_successes_and_reports_failures(
    tmp_path, monkeypatch
):
    client = _make_client(tmp_path, monkeypatch)
    profile_id = client.post("/styles", json={"name": "Batch"}).json()["profile_id"]
    valid_result = """{
      "formality": "합쇼체",
      "density": "상세",
      "perspective": "기관명칭",
      "patterns": ["~합니다"],
      "sample_sentences": ["유효한 예시 문장입니다."],
      "preferred_expressions": ["추진합니다"],
      "avoid_expressions": [],
      "summary": "공식 문체입니다."
    }"""

    class BatchProvider:
        name = "style-test-stub"

        def __init__(self):
            self.results = iter((valid_result, "not-json"))

        def generate_raw(self, prompt, *, request_id, max_output_tokens=None):
            return next(self.results)

    monkeypatch.setattr(
        "app.providers.factory.get_provider_for_bundle",
        lambda bundle_id, tenant_id: BatchProvider(),
    )

    response = client.post(
        f"/styles/{profile_id}/analyze",
        files=[
            ("files", ("valid.txt", b"valid source", "text/plain")),
            ("files", ("invalid.txt", b"invalid source", "text/plain")),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["filename"] for item in payload["analyzed"]] == ["valid.txt"]
    assert payload["failed"] == [
        {"filename": "invalid.txt", "error": "invalid.txt: 문체 분석에 실패했습니다."}
    ]
    assert payload["message"] == "1개 파일 분석 성공, 1개 실패"
    detail = client.get(f"/styles/{profile_id}").json()
    assert [item["source_filename"] for item in detail["examples"]] == ["valid.txt"]


def test_api_mock_style_analysis_reports_failure_without_saving(
    tmp_path, monkeypatch
):
    client = _make_client(tmp_path, monkeypatch)
    profile_id = client.post("/styles", json={"name": "Mock"}).json()["profile_id"]

    response = client.post(
        f"/styles/{profile_id}/analyze",
        files=[("files", ("sample.txt", b"sample source", "text/plain"))],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analyzed"] == []
    assert payload["failed"] == [
        {"filename": "sample.txt", "error": "sample.txt: 문체 분석에 실패했습니다."}
    ]
    assert payload["message"] == "0개 파일 분석 성공, 1개 실패"
    assert client.get(f"/styles/{profile_id}").json()["examples"] == []


def test_style_upload_ui_reports_success_and_failure_counts_honestly() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    start = html.index("async function analyzeStyleDocuments")
    end = html.index("async function removeStyleExample", start)
    source = html[start:end]

    assert "3개 이상 업로드할수록 정확도가 높아집니다." not in html
    assert "모델 자체를 학습시키지는 않습니다." in html
    assert "const analyzed = Array.isArray(data.analyzed) ? data.analyzed : [];" in source
    assert "const failed = Array.isArray(data.failed) ? data.failed : [];" in source
    assert "analyzed.length" in source
    assert "failed.length" in source
    assert "분석 성공" in source
    assert "분석 실패" in source


# ── Style injection integration test ─────────────────────────────────────────


def test_style_injection_in_build_bundle_prompt(tmp_path, monkeypatch):
    """When a default style profile exists, build_bundle_prompt includes the style block."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")

    from app.storage.style_store import StyleStore, ToneGuide
    from app.domain.schema import build_bundle_prompt, _current_tenant_id

    # Create a style profile with a distinct formality marker
    store = StyleStore("injection-test")
    profile = store.create("Test", "", "u1")
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


def test_recent_valid_style_examples_reach_bundle_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")

    from app.domain.schema import _current_tenant_id, build_bundle_prompt
    from app.storage.style_store import StyleExample, StyleStore, ToneGuide

    store = StyleStore("style-example-integration")
    profile = store.create("Test", "", "u1")
    store.update_tone_guide(profile.profile_id, ToneGuide(formality="합쇼체"))
    for suffix, sentence, uploaded_at in (
        ("a", "통합 A 문장입니다.", "2026-01-01T00:00:00+00:00"),
        ("b", "통합 B 문장입니다.", "2026-01-02T00:00:00+00:00"),
        ("c", "통합 C 문장입니다.", "2026-01-03T00:00:00+00:00"),
    ):
        store.add_example(
            profile.profile_id,
            StyleExample(
                example_id=f"00000000-0000-4000-8000-00000000000{suffix}",
                source_filename=f"{suffix}.txt",
                bundle_id="tech_decision",
                extracted_patterns=[],
                sample_sentences=[sentence],
                uploaded_at=uploaded_at,
                uploaded_by="u1",
            ),
        )

    _current_tenant_id.value = "style-example-integration"
    try:
        from app.bundle_catalog.registry import get_bundle_spec

        prompt = build_bundle_prompt(
            {"title": "테스트"},
            "v1",
            bundle_spec=get_bundle_spec("tech_decision"),
        )
        assert "통합 A 문장입니다." not in prompt
        assert "통합 B 문장입니다." in prompt
        assert "통합 C 문장입니다." in prompt
        assert prompt.index("통합 B 문장입니다.") < prompt.index("통합 C 문장입니다.")
    finally:
        _current_tenant_id.value = None


def test_style_ui_copy_describes_prompt_reference_not_model_training():
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    # Style examples and analysis feed the prompt; no model weights are trained.
    for phrase in ("맞춤 스타일 학습", "스타일 학습됨", "문체·어투를 학습"):
        assert phrase not in html
    assert "맞춤 문체 반영" in html
    assert "문체 분석됨" in html
    assert "모델 학습 아님" in html
