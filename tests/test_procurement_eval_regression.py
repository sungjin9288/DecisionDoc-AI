"""Fixture-based regression guard for procurement recommendation drift."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.schemas import NormalizedProcurementOpportunity, ProcurementDecisionUpsert
from app.services.procurement_decision_service import ProcurementDecisionService
from app.storage.knowledge_store import KnowledgeStore
from app.storage.procurement_store import ProcurementDecisionStore


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "procurement"
    / "procurement_eval_regression_cases.json"
)


def _fixed_now() -> datetime:
    return datetime(2026, 3, 25, 0, 0, tzinfo=timezone.utc)


def _store(tmp_path) -> ProcurementDecisionStore:
    return ProcurementDecisionStore(base_dir=str(tmp_path))


def _service(tmp_path) -> ProcurementDecisionService:
    return ProcurementDecisionService(
        procurement_store=_store(tmp_path),
        data_dir=str(tmp_path),
        now_provider=_fixed_now,
    )


def _load_cases() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _seed_case(tmp_path, case: dict) -> str:
    project_id = case["case_id"]
    store = _store(tmp_path)
    snapshot = store.save_source_snapshot(
        tenant_id="tenant-a",
        project_id=project_id,
        source_kind="g2b_import",
        source_label=case["title"],
        external_id=f"{project_id}-bid",
        payload={
            "announcement": {
                "bid_number": f"{project_id}-bid",
                "title": case["title"],
                "issuer": case["issuer"],
                "budget": case["budget"],
                "deadline": case["deadline"],
                "bid_type": "일반경쟁",
                "category": "용역",
                "detail_url": "https://www.g2b.go.kr/example",
                "raw_text": case["raw_text"],
                "source": "fixture",
            },
            "extracted_fields": {
                "project_title": case["title"],
                "issuer": case["issuer"],
                "budget": case["budget"],
                "deadline": case["deadline"],
                "objective": "공공 서비스 고도화 사업",
                "key_requirements": case["key_requirements"],
                "evaluation_criteria": ["기술점수(80)", "가격점수(20)"] if case["key_requirements"] else [],
                "confidence": 0.92 if case["key_requirements"] else 0.5,
            },
            "structured_context": case["raw_text"],
        },
    )
    store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="tenant-a",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id=f"{project_id}-bid",
                source_url="https://www.g2b.go.kr/example",
                title=case["title"],
                issuer=case["issuer"],
                budget=case["budget"],
                deadline=case["deadline"],
                bid_type="일반경쟁",
                category="용역",
                region="전국",
                raw_text_preview=case["raw_text"][:1000],
            ),
            source_snapshots=[snapshot],
            notes="fixture-seeded procurement case",
        )
    )
    capability_text = str(case.get("capability_text", "")).strip()
    if capability_text:
        KnowledgeStore(project_id, data_dir=str(tmp_path)).add_document(
            f"{project_id}.txt",
            capability_text,
        )
    return project_id


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["case_id"])
def test_procurement_eval_regression_cases_match_expected_labels(tmp_path, case):
    project_id = _seed_case(tmp_path, case)
    record = _service(tmp_path).recommend_project(project_id=project_id, tenant_id="tenant-a")

    assert record.recommendation is not None
    assert record.recommendation.value == case["expected_recommendation"]
    assert record.soft_fit_status == case["expected_score_status"]

    expected_score_min = case.get("expected_score_min")
    expected_score_max = case.get("expected_score_max")
    if expected_score_min is not None:
        assert record.soft_fit_score is not None
        assert record.soft_fit_score >= float(expected_score_min)
    if expected_score_max is not None:
        assert record.soft_fit_score is not None
        assert record.soft_fit_score <= float(expected_score_max)

    expected_hard_failure = case.get("expected_hard_failure")
    if expected_hard_failure:
        blocking_codes = [
            item.code
            for item in record.hard_filters
            if item.blocking and item.status == "fail"
        ]
        assert expected_hard_failure in blocking_codes

    for expected_missing in case.get("expected_missing", []):
        assert expected_missing in record.missing_data
