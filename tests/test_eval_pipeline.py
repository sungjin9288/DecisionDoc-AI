"""tests/test_eval_pipeline.py — 평가 파이프라인 단위 테스트."""
from dataclasses import asdict
from pathlib import Path

import pytest

from app.eval.eval_store import EvalRecord, EvalStore
from app.eval.pipeline import run_eval_pipeline
from app.eval.report import _grade, generate_report


def _make_store(tmp_path: Path) -> EvalStore:
    return EvalStore(tmp_path)


def _sample_docs() -> list[dict]:
    return [
        {
            "doc_type": "adr",
            "markdown": (
                "# ADR: 테스트 결정\n\n"
                "## Goal\n목표 내용입니다.\n\n"
                "## Decision\n**결정 사항**: 옵션 A를 채택한다.\n\n"
                "## Options\n- Option A: 설명\n- Option B: 설명\n\n"
                "## Risks\n- 리스크 1\n- 리스크 2\n\n"
                "## Assumptions\n- 가정 1\n\n"
                "## Checks\n- 체크 1\n\n"
                "## Next actions\n- 액션 1\n"
            ),
        }
    ]


def test_eval_store_append_and_load(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    record = EvalRecord(
        request_id="req-001",
        bundle_id="tech_decision",
        timestamp="2026-01-01T00:00:00+00:00",
        heuristic_score=0.85,
        llm_score=None,
        issues=[],
        doc_scores={"adr": 0.85},
    )
    store.append(record)
    loaded = store.load_all()
    assert len(loaded) == 1
    assert loaded[0].request_id == "req-001"
    assert loaded[0].heuristic_score == 0.85


def test_eval_store_summary_empty(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    s = store.summary()
    assert s["total"] == 0
    assert s["avg_heuristic"] is None


def test_eval_store_summary_aggregation(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    for i, score in enumerate([0.8, 0.9, 0.7]):
        store.append(EvalRecord(
            request_id=f"req-{i}",
            bundle_id="tech_decision",
            timestamp="2026-01-01T00:00:00+00:00",
            heuristic_score=score,
            llm_score=None,
            issues=[],
            doc_scores={},
        ))
    s = store.summary()
    assert s["total"] == 3
    assert abs(s["avg_heuristic"] - 0.8) < 0.01


def test_run_eval_pipeline_returns_record(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    record = run_eval_pipeline(
        request_id="req-test",
        bundle_id="tech_decision",
        docs=_sample_docs(),
        eval_store=store,
    )
    assert record.request_id == "req-test"
    assert 0.0 <= record.heuristic_score <= 1.0
    assert len(store.load_all()) == 1


def test_run_eval_pipeline_saves_multiple(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    run_eval_pipeline("r1", "tech_decision", _sample_docs(), store)
    run_eval_pipeline("r2", "tech_decision", _sample_docs(), store)
    assert len(store.load_all()) == 2


def test_generate_report_empty(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    report = generate_report(store)
    assert report["total_evaluated"] == 0
    assert "데이터 없음" in report["status"]


def test_generate_report_with_data(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    store.append(EvalRecord(
        request_id="r1", bundle_id="tech_decision",
        timestamp="2026-01-01T00:00:00+00:00",
        heuristic_score=0.85, llm_score=None, issues=[], doc_scores={},
    ))
    report = generate_report(store)
    assert report["total_evaluated"] == 1
    assert "tech_decision" in report["by_bundle"]


def test_grade_function() -> None:
    assert "A" in _grade(0.95)
    assert "B" in _grade(0.82)
    assert "C" in _grade(0.75)
    assert "D" in _grade(0.65)
    assert "F" in _grade(0.5)
    assert "N/A" in _grade(None)


def test_eval_store_multiple_bundles(tmp_path: Path) -> None:
    store = _make_store(tmp_path)
    for bid in ["tech_decision", "proposal_kr", "prd_kr"]:
        store.append(EvalRecord(
            request_id=f"r-{bid}", bundle_id=bid,
            timestamp="2026-01-01T00:00:00+00:00",
            heuristic_score=0.75, llm_score=None, issues=[], doc_scores={},
        ))
    s = store.summary()
    assert len(s["by_bundle"]) == 3


def test_eval_report_endpoint(tmp_path, monkeypatch) -> None:
    """GET /eval/report 엔드포인트 통합 테스트."""
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    client = TestClient(create_app())
    res = client.get("/eval/report", headers={"X-DecisionDoc-Ops-Key": "test-ops-key"})
    assert res.status_code == 200
    data = res.json()
    # Response is {"report": {...}, "generated_at": "..."}
    report = data.get("report", data)  # handle both wrapped and direct format
    assert "total_evaluated" in report


def test_eval_run_endpoint(tmp_path, monkeypatch) -> None:
    """POST /eval/run 엔드포인트 통합 테스트."""
    from fastapi.testclient import TestClient
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app
    client = TestClient(create_app())
    res = client.post("/eval/run", json={
        "request_id": "test-001",
        "bundle_id": "tech_decision",
        "docs": [{"doc_type": "adr", "markdown": "# ADR: 테스트\n\n## Goal\n목표\n\n## Decision\n결정\n\n## Options\n- A\n"}],
    }, headers={"X-DecisionDoc-Ops-Key": "test-ops-key"})
    assert res.status_code == 200
    data = res.json()
    assert data["request_id"] == "test-001"
    assert "heuristic_score" in data
