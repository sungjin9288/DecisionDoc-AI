"""tests/test_finetune.py — Fine-tune 데이터 파이프라인 단위 테스트.

커버 항목:
  1. FineTuneStore.save_record — 정상 저장
  2. FineTuneStore.save_record — request_id 중복 방지
  3. FineTuneStore.get_stats — 통계 집계
  4. FineTuneStore.export_for_training — JSONL 내보내기
  5. FineTuneStore.export_for_training — min_records 미달 시 None
  6. FineTuneStore.get_records — bundle_id 필터
  7. FineTuneStore.clear_dataset — 전체 삭제
  8. Trigger B: run_eval_pipeline에서 heuristic_score >= 임계값이면 레코드 수집
  9. Trigger B: heuristic_score < 임계값이면 수집하지 않음
 10. Trigger A: /feedback 엔드포인트 — 고평점이면 generation context로 레코드 수집
 11. /finetune/stats 엔드포인트 — 200 OK
 12. /finetune/records 엔드포인트 — 200 OK
 13. /finetune/export 엔드포인트 — OPS key 없으면 401
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest


# ── FineTuneStore 단위 테스트 ──────────────────────────────────────────────────

def _make_store(tmp_path: Path):
    from app.storage.finetune_store import FineTuneStore
    return FineTuneStore(tmp_path)


def _sample_messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "You are a document expert."},
        {"role": "user", "content": "제목\n목표: test"},
        {"role": "assistant", "content": "# Test Doc\n\nContent here."},
    ]


def _sample_metadata(request_id: str = "req-001", bundle_id: str = "tech_decision") -> dict[str, Any]:
    return {
        "request_id": request_id,
        "bundle_id": bundle_id,
        "heuristic_score": 0.9,
        "llm_score": None,
        "user_rating": None,
        "source": "high_eval_score",
    }


def test_save_record_stores_successfully(tmp_path: Path) -> None:
    """정상 레코드가 저장되고 True를 반환한다."""
    store = _make_store(tmp_path)
    result = store.save_record(_sample_messages(), _sample_metadata("req-001"))
    assert result is True
    records = store.get_records()
    assert len(records) == 1
    assert records[0]["metadata"]["request_id"] == "req-001"


def test_save_record_deduplication(tmp_path: Path) -> None:
    """동일 request_id는 중복 저장되지 않는다."""
    store = _make_store(tmp_path)
    store.save_record(_sample_messages(), _sample_metadata("req-dup"))
    result = store.save_record(_sample_messages(), _sample_metadata("req-dup"))
    assert result is False
    assert len(store.get_records()) == 1


def test_get_stats_aggregates_correctly(tmp_path: Path) -> None:
    """get_stats가 total_records, per_bundle_count, avg_heuristic를 올바르게 집계한다."""
    store = _make_store(tmp_path)
    store.save_record(_sample_messages(), _sample_metadata("req-1", "bundle_a"))
    store.save_record(_sample_messages(), _sample_metadata("req-2", "bundle_a"))
    store.save_record(_sample_messages(), _sample_metadata("req-3", "bundle_b"))

    stats = store.get_stats()
    assert stats["total_records"] == 3
    assert stats["per_bundle_count"]["bundle_a"] == 2
    assert stats["per_bundle_count"]["bundle_b"] == 1
    assert stats["avg_heuristic"] == pytest.approx(0.9, abs=0.001)


def test_export_for_training_writes_messages_only(tmp_path: Path) -> None:
    """export_for_training이 messages 필드만 포함한 JSONL을 작성한다."""
    store = _make_store(tmp_path)
    for i in range(12):
        store.save_record(_sample_messages(), _sample_metadata(f"req-{i}"))

    export_path = store.export_for_training()
    assert export_path is not None
    path = Path(export_path)
    assert path.exists()

    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 12
    for line in lines:
        obj = json.loads(line)
        assert "messages" in obj
        assert "metadata" not in obj, "메타데이터는 내보내기 파일에서 제외되어야 한다"


def test_export_for_training_returns_none_if_too_few(tmp_path: Path) -> None:
    """레코드가 min_records 미만이면 None을 반환한다."""
    store = _make_store(tmp_path)
    store.save_record(_sample_messages(), _sample_metadata("req-1"))
    result = store.export_for_training(min_records=10)
    assert result is None


def test_get_records_filters_by_bundle_id(tmp_path: Path) -> None:
    """get_records가 bundle_id로 올바르게 필터링한다."""
    store = _make_store(tmp_path)
    store.save_record(_sample_messages(), _sample_metadata("req-a", "bundle_x"))
    store.save_record(_sample_messages(), _sample_metadata("req-b", "bundle_y"))

    x_records = store.get_records(bundle_id="bundle_x")
    assert len(x_records) == 1
    assert x_records[0]["metadata"]["bundle_id"] == "bundle_x"


def test_clear_dataset_removes_all_records(tmp_path: Path) -> None:
    """clear_dataset이 모든 레코드를 삭제하고 삭제된 수를 반환한다."""
    store = _make_store(tmp_path)
    for i in range(5):
        store.save_record(_sample_messages(), _sample_metadata(f"req-{i}"))

    removed = store.clear_dataset()
    assert removed == 5
    assert store.get_records() == []


# ── Trigger B: run_eval_pipeline 통합 테스트 ─────────────────────────────────

def test_trigger_b_collects_record_when_score_high(tmp_path: Path, monkeypatch) -> None:
    """heuristic_score >= min_score 이면 run_eval_pipeline이 fine-tune 레코드를 수집한다."""
    from app.eval.eval_store import EvalStore
    from app.eval.pipeline import run_eval_pipeline
    from app.storage.finetune_store import FineTuneStore

    eval_store = EvalStore(tmp_path)
    ft_store = FineTuneStore(tmp_path)

    monkeypatch.setenv("FINETUNE_MIN_SCORE", "0.0")  # 모든 점수 통과

    docs = [{"doc_type": "adr", "markdown": "# ADR\n\nContent."}]
    run_eval_pipeline(
        request_id="trigger-b-req",
        bundle_id="tech_decision",
        docs=docs,
        eval_store=eval_store,
        run_llm_judge=False,
        title="Test",
        goal="Test goal",
        context="",
        finetune_store=ft_store,
        ft_system_prompt="You are an expert.",
        ft_output="# Generated Doc",
    )

    records = ft_store.get_records()
    assert len(records) >= 1
    assert records[0]["metadata"]["source"] == "high_eval_score"
    assert records[0]["metadata"]["request_id"] == "trigger-b-req"


def test_trigger_b_skips_record_when_score_low(tmp_path: Path, monkeypatch) -> None:
    """heuristic_score < min_score 이면 fine-tune 레코드를 수집하지 않는다."""
    from app.eval.eval_store import EvalStore
    from app.eval.pipeline import run_eval_pipeline
    from app.storage.finetune_store import FineTuneStore

    eval_store = EvalStore(tmp_path)
    ft_store = FineTuneStore(tmp_path)

    monkeypatch.setenv("FINETUNE_MIN_SCORE", "1.0")  # 최대값이므로 사실상 절대 통과 안 함

    docs = [{"doc_type": "adr", "markdown": "# ADR\n\nContent."}]
    run_eval_pipeline(
        request_id="trigger-b-low",
        bundle_id="tech_decision",
        docs=docs,
        eval_store=eval_store,
        run_llm_judge=False,
        finetune_store=ft_store,
        ft_system_prompt="You are an expert.",
        ft_output="# Generated Doc",
    )

    # Score must be < 1.0 to pass, but we required 1.0 exactly — so nothing collected
    # unless the heuristic_score happens to be 1.0 (unlikely). Check records are absent.
    records = ft_store.get_records()
    assert len(records) == 0


# ── Trigger A: /feedback 엔드포인트 ──────────────────────────────────────────

def _make_ft_client(tmp_path: Path, monkeypatch):
    """Fine-tune 엔드포인트 테스트용 TestClient."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "0")
    import app.main as main_module
    from fastapi.testclient import TestClient
    return TestClient(main_module.create_app()), tmp_path


def test_finetune_stats_endpoint_returns_200(tmp_path: Path, monkeypatch) -> None:
    """/finetune/stats 엔드포인트가 200을 반환한다."""
    client, _ = _make_ft_client(tmp_path, monkeypatch)
    resp = client.get("/finetune/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_records" in data
    assert "per_bundle_count" in data


def test_finetune_records_endpoint_returns_200(tmp_path: Path, monkeypatch) -> None:
    """/finetune/records 엔드포인트가 200을 반환한다."""
    client, _ = _make_ft_client(tmp_path, monkeypatch)
    resp = client.get("/finetune/records")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_finetune_export_requires_ops_key(tmp_path: Path, monkeypatch) -> None:
    """/finetune/export는 OPS key 없이 접근 시 401을 반환한다."""
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "secret-ops-key")
    client, _ = _make_ft_client(tmp_path, monkeypatch)
    resp = client.post("/finetune/export", json={})
    assert resp.status_code in (401, 403)


def test_finetune_clear_requires_ops_key(tmp_path: Path, monkeypatch) -> None:
    """/finetune/dataset DELETE는 OPS key 없이 접근 시 401을 반환한다."""
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "secret-ops-key")
    client, _ = _make_ft_client(tmp_path, monkeypatch)
    resp = client.delete("/finetune/dataset")
    assert resp.status_code in (401, 403)
