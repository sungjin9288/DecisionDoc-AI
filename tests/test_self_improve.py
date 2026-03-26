"""tests/test_self_improve.py — 자기개선 루프 통합 테스트.

PromptOverrideStore, feedback trigger, prompt injection, few-shot quality를 검증합니다.
"""
import json
import os
from pathlib import Path

import pytest


# ── PromptOverrideStore 단위 테스트 ──────────────────────────────────────


def test_override_store_save_and_get(tmp_path):
    from app.storage.prompt_override_store import PromptOverrideStore
    store = PromptOverrideStore(tmp_path)
    store.save_override(
        bundle_id="tech_decision",
        override_hint="반드시 구체적인 수치를 포함하세요.",
        trigger_reason="low_rating_pattern",
        avg_score_before=0.65,
    )
    record = store.get_override("tech_decision")
    assert record is not None
    assert record["override_hint"] == "반드시 구체적인 수치를 포함하세요."
    assert record["trigger_reason"] == "low_rating_pattern"
    assert record["avg_score_before"] == 0.65
    assert record["applied_count"] == 0


def test_override_store_increment_applied(tmp_path):
    from app.storage.prompt_override_store import PromptOverrideStore
    store = PromptOverrideStore(tmp_path)
    store.save_override("prd_kr", "섹션을 빠짐없이 작성하세요.", "low_rating_pattern")
    store.increment_applied("prd_kr")
    store.increment_applied("prd_kr")
    assert store.get_override("prd_kr")["applied_count"] == 2


def test_override_store_delete(tmp_path):
    from app.storage.prompt_override_store import PromptOverrideStore
    store = PromptOverrideStore(tmp_path)
    store.save_override("okr_plan_kr", "힌트", "low_rating_pattern")
    store.delete_override("okr_plan_kr")
    assert store.get_override("okr_plan_kr") is None


def test_override_store_list_overrides(tmp_path):
    from app.storage.prompt_override_store import PromptOverrideStore
    store = PromptOverrideStore(tmp_path)
    store.save_override("a", "hint_a", "low_rating_pattern")
    store.save_override("b", "hint_b", "llm_judge_feedback")
    overrides = store.list_overrides()
    assert len(overrides) == 2


def test_override_store_missing_bundle_returns_none(tmp_path):
    from app.storage.prompt_override_store import PromptOverrideStore
    store = PromptOverrideStore(tmp_path)
    assert store.get_override("nonexistent") is None


# ── FeedbackStore.get_low_rated 단위 테스트 ──────────────────────────────


def test_feedback_store_get_low_rated(tmp_path):
    from app.storage.feedback_store import FeedbackStore
    store = FeedbackStore(tmp_path)
    store.save({"bundle_type": "prd_kr", "rating": 1, "comment": "너무 추상적"})
    store.save({"bundle_type": "prd_kr", "rating": 2, "comment": "섹션 누락"})
    store.save({"bundle_type": "prd_kr", "rating": 5, "comment": "훌륭해요"})
    store.save({"bundle_type": "tech_decision", "rating": 1, "comment": "다른 번들"})

    low = store.get_low_rated("prd_kr", max_rating=2)
    assert len(low) == 2
    assert all(r["rating"] <= 2 for r in low)
    assert all(r["bundle_type"] == "prd_kr" for r in low)


# ── EvalRecord llm_feedbacks 필드 테스트 ─────────────────────────────────


def test_eval_record_llm_feedbacks_field(tmp_path):
    from app.eval.eval_store import EvalRecord, EvalStore
    store = EvalStore(tmp_path)
    record = EvalRecord(
        request_id="req-1",
        bundle_id="tech_decision",
        timestamp="2026-03-01T00:00:00+00:00",
        heuristic_score=0.85,
        llm_score=4.2,
        issues=[],
        doc_scores={},
        llm_feedbacks=["구체적인 수치가 필요합니다.", "논리적 흐름이 좋습니다."],
    )
    store.append(record)
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].llm_feedbacks == ["구체적인 수치가 필요합니다.", "논리적 좋습니다." if False else "논리적 흐름이 좋습니다."]


def test_eval_record_default_llm_feedbacks(tmp_path):
    """기존 포맷(llm_feedbacks 없음) 레코드도 로드 가능한지 확인."""
    from app.eval.eval_store import EvalStore
    # 구 형식 레코드 수동 작성 (llm_feedbacks 필드 없음)
    old_line = json.dumps({
        "request_id": "old-req",
        "bundle_id": "tech_decision",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "heuristic_score": 0.75,
        "llm_score": None,
        "issues": [],
        "doc_scores": {},
        # llm_feedbacks 없음 — 구 버전 호환
    })
    tenant_dir = tmp_path / "tenants" / "system"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    path = tenant_dir / "eval_results.jsonl"
    path.write_text(old_line + "\n")
    store = EvalStore(tmp_path)
    records = store.load_all()
    assert len(records) == 1
    assert records[0].llm_feedbacks == []  # default_factory 적용


# ── /feedback 엔드포인트 → auto-improve 트리거 테스트 ─────────────────────


def test_feedback_triggers_override_after_threshold(tmp_path, monkeypatch):
    """저평점 3건 제출 후 PromptOverrideStore에 오버라이드가 저장되는지 확인."""
    from fastapi.testclient import TestClient
    from app.storage.prompt_override_store import PromptOverrideStore
    import app.main as main_module

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOW_RATING_THRESHOLD", "3")
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")

    app = main_module.create_app()
    client = TestClient(app)
    override_store = PromptOverrideStore(tmp_path)

    payload = {
        "bundle_id": "tech_decision",
        "bundle_type": "tech_decision",
        "rating": 1,
        "comment": "너무 추상적이고 일반적입니다",
    }
    for _ in range(3):
        resp = client.post("/feedback", json=payload)
        assert resp.status_code == 200

    # 3건 제출 후 override가 저장되어야 함
    record = override_store.get_override("tech_decision")
    assert record is not None
    assert record["trigger_reason"] == "low_rating_pattern"


# ── build_bundle_prompt override 주입 테스트 ─────────────────────────────


def test_build_bundle_prompt_injects_override(tmp_path, monkeypatch):
    """PromptOverrideStore에 오버라이드가 있을 때 프롬프트에 주입되는지 확인."""
    from app.storage.prompt_override_store import PromptOverrideStore, clear_override_store_cache
    from app.storage.ab_test_store import clear_ab_test_store_cache
    from app.bundle_catalog.registry import get_bundle_spec
    from app.domain.schema import build_bundle_prompt

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Clear LRU caches so stores point to tmp_path, not a previous test's directory
    clear_ab_test_store_cache()
    clear_override_store_cache()
    store = PromptOverrideStore(tmp_path)
    store.save_override(
        bundle_id="tech_decision",
        override_hint="반드시 구체적인 수치를 포함하세요.",
        trigger_reason="low_rating_pattern",
    )

    bundle_spec = get_bundle_spec("tech_decision")
    prompt = build_bundle_prompt(
        {"title": "테스트", "goal": "목표"},
        "v1",
        bundle_spec=bundle_spec,
    )
    assert "품질 개선 지시" in prompt
    assert "반드시 구체적인 수치를 포함하세요." in prompt

    # increment_applied 확인
    assert store.get_override("tech_decision")["applied_count"] == 1


# ── get_high_rated_examples 구조화된 포맷 테스트 ─────────────────────────


def test_get_high_rated_examples_structured_docs(tmp_path):
    """고평점 예시가 구조화된 docs dict(doc_type 키)로 반환되는지 확인."""
    from app.storage.feedback_store import FeedbackStore

    store = FeedbackStore(tmp_path)
    store.save({
        "bundle_type": "tech_decision",
        "rating": 5,
        "comment": "훌륭한 문서",
        "title": "MSA 전환 결정",
        "docs": [
            {
                "doc_type": "adr",
                "markdown": "## 결정 배경\n MSA 전환을 위한 상세 분석 내용 " + "x" * 1000,
            },
            {
                "doc_type": "onepager",
                "markdown": "# 요약\n핵심 요약 내용 " + "y" * 500,
            },
        ],
    })

    examples = store.get_high_rated_examples("tech_decision", min_rating=4)
    assert len(examples) == 1
    ex = examples[0]

    # 구조화된 docs dict 확인
    docs = ex["docs"]
    assert isinstance(docs, dict)
    assert "adr" in docs
    assert "onepager" in docs

    # heading 추출 확인
    assert "결정 배경" in docs["adr"]["heading"]

    # content 800자 제한 확인
    assert len(docs["adr"]["content"]) <= 800
    assert len(docs["onepager"]["content"]) <= 800

    # 필수 필드 확인
    assert ex["rating"] == 5
    assert ex["comment"] == "훌륭한 문서"
    assert ex["title"] == "MSA 전환 결정"


def test_get_high_rated_examples_no_docs(tmp_path):
    """docs 없는 고평점 피드백도 빈 docs dict으로 반환되는지 확인."""
    from app.storage.feedback_store import FeedbackStore

    store = FeedbackStore(tmp_path)
    store.save({
        "bundle_type": "prd_kr",
        "rating": 4,
        "comment": "좋아요",
        "docs": [],
    })

    examples = store.get_high_rated_examples("prd_kr")
    assert len(examples) == 1
    assert examples[0]["docs"] == {}


def test_build_feedback_hints_uses_all_docs(tmp_path, monkeypatch):
    """_build_feedback_hints가 모든 doc_type의 내용을 포함하는지 확인."""
    from app.storage.feedback_store import FeedbackStore, clear_feedback_store_cache
    from app.services.generation_service import GenerationService
    from unittest.mock import MagicMock

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Clear LRU cache so get_feedback_store picks up tmp_path
    clear_feedback_store_cache()
    store = FeedbackStore(tmp_path)
    store.save({
        "bundle_type": "tech_decision",
        "rating": 5,
        "comment": "최고의 문서",
        "title": "API 게이트웨이 선택",
        "docs": [
            {"doc_type": "adr",      "markdown": "## ADR 내용\n상세 결정 근거 텍스트"},
            {"doc_type": "onepager", "markdown": "## 요약\n핵심 요약 텍스트"},
        ],
    })

    svc = GenerationService(
        provider_factory=MagicMock(),
        template_dir=tmp_path,
        data_dir=tmp_path,
        feedback_store=store,
    )
    hints = svc._build_feedback_hints("tech_decision")

    # 모든 doc_type 포함 확인
    assert "adr" in hints
    assert "onepager" in hints
    # 구조화된 예시 제목 포함
    assert "예시 1" in hints
    assert "API 게이트웨이 선택" in hints
    # 사용자 피드백 코멘트 포함
    assert "최고의 문서" in hints


def test_build_feedback_hints_empty_when_no_feedback(tmp_path, monkeypatch):
    """고평점 피드백이 없으면 빈 문자열 반환."""
    from app.storage.feedback_store import FeedbackStore, clear_feedback_store_cache
    from app.services.generation_service import GenerationService
    from unittest.mock import MagicMock

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    # Clear LRU cache so get_feedback_store picks up tmp_path (empty store)
    clear_feedback_store_cache()
    store = FeedbackStore(tmp_path)
    svc = GenerationService(
        provider_factory=MagicMock(),
        template_dir=tmp_path,
        data_dir=tmp_path,
        feedback_store=store,
    )
    assert svc._build_feedback_hints("tech_decision") == ""
