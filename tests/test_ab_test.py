"""tests/test_ab_test.py — ABTestStore 단위 테스트 + A/B 통합 테스트."""
import json
import os
from pathlib import Path

import pytest


# ── ABTestStore 단위 테스트 ────────────────────────────────────────────────


def test_ab_store_create_and_get_active(tmp_path):
    """create_test 후 get_active_test가 올바른 레코드를 반환하는지 확인."""
    from app.storage.ab_test_store import ABTestStore

    store = ABTestStore(tmp_path)
    store.create_test(
        bundle_id="tech_decision",
        variant_a_hint="수치를 포함하세요.",
        variant_b_hint="섹션을 상세히 작성하세요.",
        min_samples=5,
    )

    test = store.get_active_test("tech_decision")
    assert test is not None
    assert test["bundle_id"] == "tech_decision"
    assert test["status"] == "active"
    assert test["variant_a_hint"] == "수치를 포함하세요."
    assert test["variant_b_hint"] == "섹션을 상세히 작성하세요."
    assert test["min_samples"] == 5
    assert test["generation_count"] == 0
    assert test["winner"] is None
    assert "variant_a" in test["results"]
    assert "variant_b" in test["results"]


def test_ab_store_get_next_variant_alternates(tmp_path):
    """get_next_variant가 A→B→A→B 순으로 교대 반환하는지 확인."""
    from app.storage.ab_test_store import ABTestStore

    store = ABTestStore(tmp_path)
    store.create_test("prd_kr", "hint_a", "hint_b")

    assert store.get_next_variant("prd_kr") == "variant_a"   # count 0 → A
    assert store.get_next_variant("prd_kr") == "variant_b"   # count 1 → B
    assert store.get_next_variant("prd_kr") == "variant_a"   # count 2 → A
    assert store.get_next_variant("prd_kr") == "variant_b"   # count 3 → B

    # generation_count는 4여야 함
    test = store.get_active_test("prd_kr")
    assert test["generation_count"] == 4


def test_ab_store_no_active_test_returns_none(tmp_path):
    """활성 테스트가 없으면 get_active_test / get_next_variant 모두 None 반환."""
    from app.storage.ab_test_store import ABTestStore

    store = ABTestStore(tmp_path)
    assert store.get_active_test("nonexistent") is None
    assert store.get_next_variant("nonexistent") is None


def test_ab_store_record_and_conclude(tmp_path):
    """양쪽 variant에 min_samples 건 채운 후 evaluate_and_conclude가 winner를 반환."""
    from app.storage.ab_test_store import ABTestStore

    store = ABTestStore(tmp_path)
    store.create_test("tech_decision", "hint_a", "hint_b", min_samples=3)

    # variant_a 점수가 높음 → variant_a 우승이어야 함
    for _ in range(3):
        store.record_result("tech_decision", "variant_a", heuristic_score=0.9)
    for _ in range(2):
        store.record_result("tech_decision", "variant_b", heuristic_score=0.6)

    # 아직 B가 min_samples(3) 미달 → 결론 안 남
    assert store.evaluate_and_conclude("tech_decision") is None

    # B 1건 추가 → min_samples 충족
    store.record_result("tech_decision", "variant_b", heuristic_score=0.7)
    winner = store.evaluate_and_conclude("tech_decision")
    assert winner == "variant_a"

    # 상태가 concluded로 변경되었는지 확인
    with store._lock:
        data = store._load()
    test = data["tech_decision"]
    assert test["status"] == "concluded"
    assert test["winner"] == "variant_a"
    assert test["winner_avg_score"] == pytest.approx(0.9)


def test_ab_store_conclude_winner_saved_to_override(tmp_path, monkeypatch):
    """conclude 시 우승자 hint가 PromptOverrideStore에 저장되는지 확인."""
    from app.storage.ab_test_store import ABTestStore
    from app.storage.prompt_override_store import PromptOverrideStore

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store = ABTestStore(tmp_path)
    store.create_test("prd_kr", "hint_a_wins", "hint_b_loses", min_samples=2)

    # variant_a 점수 우세
    for _ in range(2):
        store.record_result("prd_kr", "variant_a", heuristic_score=0.8)
        store.record_result("prd_kr", "variant_b", heuristic_score=0.5)

    winner = store.evaluate_and_conclude("prd_kr")
    assert winner == "variant_a"

    # PromptOverrideStore에 winner hint 저장 확인
    override_store = PromptOverrideStore(tmp_path)
    record = override_store.get_override("prd_kr")
    assert record is not None
    assert record["override_hint"] == "hint_a_wins"
    assert record["trigger_reason"] == "ab_test_winner"


def test_ab_store_list_active_and_concluded(tmp_path):
    """list_active_tests / list_concluded_tests 필터링 동작 확인."""
    from app.storage.ab_test_store import ABTestStore

    store = ABTestStore(tmp_path)
    store.create_test("bundle_a", "a_hint", "b_hint", min_samples=1)
    store.create_test("bundle_b", "a_hint", "b_hint", min_samples=1)

    assert len(store.list_active_tests()) == 2
    assert len(store.list_concluded_tests()) == 0

    # bundle_a 결론 처리
    store.record_result("bundle_a", "variant_a", 0.9)
    store.record_result("bundle_a", "variant_b", 0.7)
    store.evaluate_and_conclude("bundle_a")

    active = store.list_active_tests()
    concluded = store.list_concluded_tests()
    assert len(active) == 1
    assert active[0]["bundle_id"] == "bundle_b"
    assert len(concluded) == 1
    assert concluded[0]["bundle_id"] == "bundle_a"


def test_ab_store_delete_test(tmp_path):
    """delete_test 후 get_active_test가 None을 반환하는지 확인."""
    from app.storage.ab_test_store import ABTestStore

    store = ABTestStore(tmp_path)
    store.create_test("tech_decision", "h_a", "h_b")
    assert store.get_active_test("tech_decision") is not None

    store.delete_test("tech_decision")
    assert store.get_active_test("tech_decision") is None
    assert store.list_active_tests() == []


# ── 통합 테스트: schema.py A/B 주입 ──────────────────────────────────────


def test_build_bundle_prompt_uses_ab_variant(tmp_path, monkeypatch):
    """활성 A/B 테스트가 있을 때 build_bundle_prompt가 해당 variant의 hint를 주입하는지 확인."""
    from app.storage.ab_test_store import ABTestStore
    from app.bundle_catalog.registry import get_bundle_spec
    from app.domain.schema import build_bundle_prompt, _ab_selected

    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    # A/B 테스트 생성
    ab_store = ABTestStore(tmp_path)
    ab_store.create_test(
        bundle_id="tech_decision",
        variant_a_hint="A 변형: 반드시 수치를 포함하세요.",
        variant_b_hint="B 변형: 섹션을 빠짐없이 작성하세요.",
        min_samples=5,
    )

    bundle_spec = get_bundle_spec("tech_decision")
    prompt = build_bundle_prompt(
        {"title": "테스트", "goal": "목표"},
        "v1",
        bundle_spec=bundle_spec,
    )

    # variant_a (첫 번째 호출, count=0 → A)가 주입되어야 함
    assert "품질 개선 지시" in prompt
    assert "A 변형: 반드시 수치를 포함하세요." in prompt

    # _ab_selected thread-local에 variant_a가 기록되었는지 확인
    assert getattr(_ab_selected, "bundle_id", None) == "tech_decision"
    assert getattr(_ab_selected, "variant", None) == "variant_a"

    # 두 번째 호출 → variant_b
    prompt2 = build_bundle_prompt(
        {"title": "테스트2", "goal": "목표2"},
        "v1",
        bundle_spec=bundle_spec,
    )
    assert "B 변형: 섹션을 빠짐없이 작성하세요." in prompt2
    assert getattr(_ab_selected, "variant", None) == "variant_b"


# ── REST API 엔드포인트 통합 테스트 ──────────────────────────────────────


def test_ab_test_api_endpoints(tmp_path, monkeypatch):
    """GET /ab-tests/active, /concluded, POST /ab-tests/{bundle_id}/reset 동작 확인."""
    from fastapi.testclient import TestClient
    from app.storage.ab_test_store import ABTestStore
    import app.main as main_module

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-api-key")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")

    application = main_module.create_app()
    client = TestClient(application)
    auth_headers = {
        "X-DecisionDoc-Api-Key": "test-api-key",
        "X-DecisionDoc-Ops-Key": "test-ops-key",
    }

    def _tests(resp):
        """Extract test list from either bare list or wrapped {"tests": [...]} format."""
        data = resp.json()
        return data["tests"] if isinstance(data, dict) and "tests" in data else data

    # 초기 상태: 빈 목록
    resp = client.get("/ab-tests/active", headers=auth_headers)
    assert resp.status_code == 200
    assert _tests(resp) == []

    resp = client.get("/ab-tests/concluded", headers=auth_headers)
    assert resp.status_code == 200
    assert _tests(resp) == []

    # ABTestStore에 직접 테스트 생성
    ab_store = ABTestStore(tmp_path)
    ab_store.create_test("tech_decision", "hint_a", "hint_b", min_samples=5)

    resp = client.get("/ab-tests/active", headers=auth_headers)
    assert resp.status_code == 200
    active = _tests(resp)
    assert len(active) == 1
    assert active[0]["bundle_id"] == "tech_decision"
    assert active[0]["status"] == "active"

    # Reset (delete) 테스트
    resp = client.post("/ab-tests/tech_decision/reset", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] is True
    assert body["bundle_id"] == "tech_decision"

    # 삭제 후 active 목록이 비었는지 확인
    resp = client.get("/ab-tests/active", headers=auth_headers)
    assert resp.status_code == 200
    assert _tests(resp) == []
