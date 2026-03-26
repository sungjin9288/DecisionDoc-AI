"""tests/test_dashboard.py — AI 성능 대시보드 API 엔드포인트 테스트.

Coverage:
  - EvalStore: get_all_stats, get_per_bundle_stats, get_bundle_history
  - FeedbackStore: get_all (신규 메서드)
  - GET /dashboard/overview
  - GET /dashboard/bundle-performance
  - GET /dashboard/improvement-history
  - GET /dashboard/score-history/{bundle_id}
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pytest


# ── EvalStore 신규 메서드 단위 테스트 ────────────────────────────────────────


def _ts(offset_seconds: int = 0) -> str:
    """ISO UTC timestamp with optional second offset."""
    from datetime import timedelta
    return (datetime.now(timezone.utc).replace(microsecond=0)
            + timedelta(seconds=offset_seconds)).isoformat()


def _make_record(bundle_id, h_score, llm_score=None, ts_offset=0):
    from app.eval.eval_store import EvalRecord
    return EvalRecord(
        request_id=f"req-{bundle_id}-{ts_offset}",
        bundle_id=bundle_id,
        timestamp=_ts(ts_offset),
        heuristic_score=h_score,
        llm_score=llm_score,
        issues=[],
        doc_scores={},
    )


def test_eval_store_get_all_stats_empty(tmp_path):
    """데이터 없을 때 get_all_stats가 0값 반환하는지 확인."""
    from app.eval.eval_store import EvalStore
    store = EvalStore(tmp_path)
    stats = store.get_all_stats()
    assert stats["total_count"] == 0
    assert stats["avg_heuristic"] is None
    assert stats["avg_llm"] is None
    assert stats["low_quality_count"] == 0


def test_eval_store_get_all_stats_with_data(tmp_path):
    """heuristic, llm, low_quality 집계가 올바른지 확인."""
    from app.eval.eval_store import EvalStore
    store = EvalStore(tmp_path)
    store.append(_make_record("tech_decision", 0.9, llm_score=4.0))
    store.append(_make_record("tech_decision", 0.5, llm_score=2.0))  # low quality
    store.append(_make_record("prd_kr", 0.75))

    stats = store.get_all_stats()
    assert stats["total_count"] == 3
    assert abs(stats["avg_heuristic"] - round((0.9 + 0.5 + 0.75) / 3, 3)) < 0.001
    assert stats["low_quality_count"] == 1  # only 0.5 < 0.6
    # avg_llm only from 2 records with llm_score
    assert abs(stats["avg_llm"] - round((4.0 + 2.0) / 2, 3)) < 0.001


def test_eval_store_get_per_bundle_stats(tmp_path):
    """번들별 집계 (count, avg_heuristic, last_timestamp, recent_scores) 확인."""
    from app.eval.eval_store import EvalStore
    store = EvalStore(tmp_path)
    for i in range(5):
        store.append(_make_record("tech_decision", 0.7 + i * 0.04, ts_offset=i))
    store.append(_make_record("prd_kr", 0.8))

    per_bundle = store.get_per_bundle_stats()
    assert "tech_decision" in per_bundle
    assert "prd_kr" in per_bundle

    td = per_bundle["tech_decision"]
    assert td["count"] == 5
    assert len(td["recent_scores"]) == 5
    assert td["avg_llm"] is None  # no llm scores


def test_eval_store_get_bundle_history(tmp_path):
    """get_bundle_history가 해당 번들 레코드만, 최신 순으로 반환하는지 확인."""
    from app.eval.eval_store import EvalStore
    store = EvalStore(tmp_path)
    for i in range(8):
        store.append(_make_record("tech_decision", 0.7 + i * 0.02, ts_offset=i))
    store.append(_make_record("prd_kr", 0.9))  # 다른 번들

    history = store.get_bundle_history("tech_decision", limit=5)
    assert len(history) == 5
    assert all(r.bundle_id == "tech_decision" for r in history)
    # Most recent first
    assert history[0].timestamp >= history[1].timestamp


def test_feedback_store_get_all(tmp_path):
    """FeedbackStore.get_all이 모든 레코드를 반환하는지 확인."""
    from app.storage.feedback_store import FeedbackStore
    store = FeedbackStore(tmp_path)
    store.save({"bundle_type": "tech_decision", "rating": 5, "comment": "좋아요"})
    store.save({"bundle_type": "prd_kr", "rating": 2, "comment": "아쉬워요"})

    all_records = store.get_all()
    assert len(all_records) == 2
    assert any(r["bundle_type"] == "tech_decision" for r in all_records)


# ── Dashboard API 통합 테스트 ────────────────────────────────────────────────


@pytest.fixture()
def _dash_client(tmp_path, monkeypatch):
    """Dashboard API 테스트용 TestClient."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    return TestClient(main_module.create_app()), tmp_path


def test_dashboard_overview_empty(tmp_path, monkeypatch):
    """GET /dashboard/overview — 빈 데이터에서 0/null 반환하는지 확인."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    client = TestClient(main_module.create_app())

    resp = client.get("/dashboard/overview")
    assert resp.status_code == 200
    d = resp.json()
    assert d["total_generations"] == 0
    assert d["avg_heuristic_score"] is None
    assert d["active_ab_tests"] == 0
    assert d["total_feedback_count"] == 0


def test_dashboard_overview_with_data(tmp_path, monkeypatch):
    """GET /dashboard/overview — 실제 데이터가 있을 때 집계 반환 확인."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    from app.eval.eval_store import EvalStore
    from app.storage.feedback_store import FeedbackStore

    # Seed data
    eval_store = EvalStore(tmp_path)
    eval_store.append(_make_record("tech_decision", 0.85))
    eval_store.append(_make_record("tech_decision", 0.75))
    fb_store = FeedbackStore(tmp_path)
    fb_store.save({"bundle_type": "tech_decision", "rating": 4, "comment": ""})

    client = TestClient(main_module.create_app())
    resp = client.get("/dashboard/overview")
    assert resp.status_code == 200
    d = resp.json()
    assert d["total_generations"] == 2
    assert d["avg_heuristic_score"] is not None
    assert d["total_feedback_count"] == 1
    assert d["avg_rating"] == 4.0


def test_dashboard_bundle_performance_empty(tmp_path, monkeypatch):
    """GET /dashboard/bundle-performance — 빈 데이터에서 빈 배열 반환."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    client = TestClient(main_module.create_app())

    resp = client.get("/dashboard/bundle-performance")
    assert resp.status_code == 200
    assert resp.json() == []


def test_dashboard_bundle_performance_with_data(tmp_path, monkeypatch):
    """GET /dashboard/bundle-performance — 번들별 통계가 올바른지 확인."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    from app.eval.eval_store import EvalStore

    eval_store = EvalStore(tmp_path)
    for i in range(6):
        eval_store.append(_make_record("tech_decision", 0.7 + i * 0.03, ts_offset=i))
    eval_store.append(_make_record("prd_kr", 0.85))

    client = TestClient(main_module.create_app())
    resp = client.get("/dashboard/bundle-performance")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    bundle_ids = [d["bundle_id"] for d in data]
    assert "tech_decision" in bundle_ids
    assert "prd_kr" in bundle_ids

    td = next(d for d in data if d["bundle_id"] == "tech_decision")
    assert td["generation_count"] == 6
    assert td["avg_heuristic_score"] is not None
    assert td["score_trend"] in ("improving", "declining", "stable")


def test_dashboard_improvement_history_empty(tmp_path, monkeypatch):
    """GET /dashboard/improvement-history — 빈 데이터에서 빈 배열 반환."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    client = TestClient(main_module.create_app())

    resp = client.get("/dashboard/improvement-history")
    assert resp.status_code == 200
    assert resp.json() == []


def test_dashboard_improvement_history_with_override(tmp_path, monkeypatch):
    """GET /dashboard/improvement-history — 오버라이드 이벤트가 포함되는지 확인."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    from app.storage.prompt_override_store import PromptOverrideStore

    override_store = PromptOverrideStore(tmp_path)
    override_store.save_override(
        bundle_id="tech_decision",
        override_hint="더 구체적인 예시를 포함할 것",
        trigger_reason="low_rating_pattern",
        avg_score_before=0.65,
    )

    client = TestClient(main_module.create_app())
    resp = client.get("/dashboard/improvement-history")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 1
    override_events = [e for e in events if e["event_type"] == "override_saved"]
    assert len(override_events) == 1
    assert override_events[0]["bundle_id"] == "tech_decision"


def test_dashboard_score_history_empty_bundle(tmp_path, monkeypatch):
    """GET /dashboard/score-history/{bundle_id} — 존재하지 않는 번들은 빈 배열."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    client = TestClient(main_module.create_app())

    resp = client.get("/dashboard/score-history/nonexistent_bundle")
    assert resp.status_code == 200
    assert resp.json() == []


def test_dashboard_score_history_with_data(tmp_path, monkeypatch):
    """GET /dashboard/score-history/{bundle_id} — 점수 시계열이 반환되는지 확인."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    from app.eval.eval_store import EvalStore

    eval_store = EvalStore(tmp_path)
    for i in range(5):
        eval_store.append(_make_record("tech_decision", 0.7 + i * 0.04, llm_score=3.0, ts_offset=i))

    client = TestClient(main_module.create_app())
    resp = client.get("/dashboard/score-history/tech_decision")
    assert resp.status_code == 200
    records = resp.json()
    assert len(records) == 5
    assert all("heuristic_score" in r for r in records)
    assert all("timestamp" in r for r in records)
    # Chronological order (ascending)
    assert records[0]["timestamp"] <= records[-1]["timestamp"]


def test_dashboard_score_history_limit_50(tmp_path, monkeypatch):
    """GET /dashboard/score-history/{bundle_id} — 최대 50건 제한 확인."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    import app.main as main_module
    from fastapi.testclient import TestClient
    from app.eval.eval_store import EvalStore

    eval_store = EvalStore(tmp_path)
    for i in range(70):
        eval_store.append(_make_record("tech_decision", 0.75, ts_offset=i))

    client = TestClient(main_module.create_app())
    resp = client.get("/dashboard/score-history/tech_decision")
    assert resp.status_code == 200
    assert len(resp.json()) == 50
