"""Tests for deterministic procurement hard filters and soft-fit scoring."""
from __future__ import annotations

from datetime import datetime, timezone

from app.schemas import NormalizedProcurementOpportunity, ProcurementDecisionUpsert
from app.services.procurement_decision_service import ProcurementDecisionService
from app.storage.knowledge_store import KnowledgeStore
from app.storage.procurement_store import ProcurementDecisionStore


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


def _attach_snapshot(
    tmp_path,
    *,
    project_id: str,
    title: str,
    issuer: str,
    budget: str,
    deadline: str,
    raw_text: str,
    key_requirements: list[str],
    evaluation_criteria: list[str] | None = None,
) -> None:
    store = _store(tmp_path)
    snapshot = store.save_source_snapshot(
        tenant_id="tenant-a",
        project_id=project_id,
        source_kind="g2b_import",
        source_label=title,
        external_id=f"{project_id}-bid",
        payload={
            "announcement": {
                "bid_number": f"{project_id}-bid",
                "title": title,
                "issuer": issuer,
                "budget": budget,
                "deadline": deadline,
                "bid_type": "일반경쟁",
                "category": "용역",
                "detail_url": "https://www.g2b.go.kr/example",
                "raw_text": raw_text,
                "source": "scrape",
            },
            "extracted_fields": {
                "project_title": title,
                "issuer": issuer,
                "budget": budget,
                "deadline": deadline,
                "objective": "공공 서비스 고도화 사업",
                "key_requirements": key_requirements,
                "evaluation_criteria": ["기술점수(80)", "가격점수(20)"] if evaluation_criteria is None else evaluation_criteria,
                "confidence": 0.92,
            },
            "structured_context": raw_text,
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
                title=title,
                issuer=issuer,
                budget=budget,
                deadline=deadline,
                bid_type="일반경쟁",
                category="용역",
                region="전국",
                raw_text_preview=raw_text[:1000],
            ),
            source_snapshots=[snapshot],
            notes="attached opportunity",
        )
    )


class TestProcurementDecisionService:
    def test_clear_go_case_scores_high_without_hard_fail(self, tmp_path):
        _attach_snapshot(
            tmp_path,
            project_id="proj-go",
            title="AI 기반 공공 민원 플랫폼 구축",
            issuer="행정안전부",
            budget="5억원",
            deadline="2026-05-30 17:00",
            raw_text="입찰참가자격: 소프트웨어사업자, ISMS 보유. 유사사업 수행실적 필요.",
            key_requirements=["AI 민원 서비스", "클라우드 전환", "정보보호 체계"],
        )
        ks = KnowledgeStore("proj-go", data_dir=str(tmp_path))
        ks.add_document(
            "capability.txt",
            (
                "공공 행정 AI 플랫폼 구축 레퍼런스 3건. "
                "클라우드 전환과 정보보호 컨설팅 수행 경험 보유. "
                "소프트웨어사업자 등록 및 ISMS 인증 보유. "
                "PM, PMO, 컨설턴트, 개발자, 아키텍트 인력 확보."
            ),
        )

        record = _service(tmp_path).evaluate_project(project_id="proj-go", tenant_id="tenant-a")

        assert record.capability_profile is not None
        assert not any(item.blocking and item.status == "fail" for item in record.hard_filters)
        assert record.soft_fit_status == "scored"
        assert record.soft_fit_score is not None
        assert record.soft_fit_score >= 75.0
        assert any(item.key == "domain_fit" and item.score >= 75.0 for item in record.score_breakdown)
        assert record.missing_data == []

    def test_conditional_case_scores_midrange_without_blocking_fail(self, tmp_path):
        _attach_snapshot(
            tmp_path,
            project_id="proj-conditional",
            title="데이터 기반 정책 지원 시스템",
            issuer="서울특별시",
            budget="15억원",
            deadline="2026-04-18 17:00",
            raw_text="지역제한 없음. 데이터 분석 및 보고체계 구축.",
            key_requirements=["데이터 분석", "정책 지원", "보고 체계"],
        )
        ks = KnowledgeStore("proj-conditional", data_dir=str(tmp_path))
        ks.add_document(
            "capability.txt",
            (
                "공공 데이터 분석 컨설팅 수행 경험 보유. "
                "PM과 컨설턴트 중심 수행 가능. "
                "레퍼런스는 제한적이며 클라우드 경험은 적음."
            ),
        )

        record = _service(tmp_path).evaluate_project(project_id="proj-conditional", tenant_id="tenant-a")

        assert not any(item.blocking and item.status == "fail" for item in record.hard_filters)
        assert record.soft_fit_status == "scored"
        assert record.soft_fit_score is not None
        assert 55.0 <= record.soft_fit_score < 75.0
        assert any(item.key == "reference_project_fit" for item in record.score_breakdown)

    def test_hard_fail_case_marks_blocking_filter(self, tmp_path):
        _attach_snapshot(
            tmp_path,
            project_id="proj-no-go",
            title="보안 인증 기반 통합 관제 고도화",
            issuer="조달청",
            budget="8억원",
            deadline="2026-03-30 18:00",
            raw_text="필수 요건: ISMS 보유, 공동수급 가능. 유사사업 수행실적 필요.",
            key_requirements=["보안 관제", "클라우드", "통합 플랫폼"],
        )
        ks = KnowledgeStore("proj-no-go", data_dir=str(tmp_path))
        ks.add_document(
            "capability.txt",
            "공공 컨설팅 수행 경험은 있으나 보안 인증과 협력사 체계는 아직 확보되지 않음.",
        )

        record = _service(tmp_path).evaluate_project(project_id="proj-no-go", tenant_id="tenant-a")

        blocking_failures = [item.code for item in record.hard_filters if item.blocking and item.status == "fail"]
        assert "mandatory_certification_or_license" in blocking_failures or "impossible_deadline" in blocking_failures
        assert record.soft_fit_score is not None
        assert record.soft_fit_score < 55.0 or "deadline" in record.missing_data

    def test_insufficient_data_case_is_explicit(self, tmp_path):
        _attach_snapshot(
            tmp_path,
            project_id="proj-insufficient",
            title="신규 행정 서비스 개선 사업",
            issuer="행정안전부",
            budget="",
            deadline="",
            raw_text="사업 개요만 존재.",
            key_requirements=[],
            evaluation_criteria=[],
        )

        record = _service(tmp_path).evaluate_project(project_id="proj-insufficient", tenant_id="tenant-a")

        assert record.soft_fit_status == "insufficient_data"
        assert "capability profile knowledge context" in record.missing_data
        assert "structured RFP requirement signals" in record.missing_data
        assert "deadline" in record.missing_data
        assert any(item.status == "insufficient_data" for item in record.score_breakdown)

    def test_recommendation_go_case_builds_ready_checklist(self, tmp_path):
        _attach_snapshot(
            tmp_path,
            project_id="proj-go-rec",
            title="AI 기반 공공 민원 플랫폼 구축",
            issuer="행정안전부",
            budget="5억원",
            deadline="2026-05-30 17:00",
            raw_text="입찰참가자격: 소프트웨어사업자, ISMS 보유. 유사사업 수행실적 필요.",
            key_requirements=["AI 민원 서비스", "클라우드 전환", "정보보호 체계"],
        )
        ks = KnowledgeStore("proj-go-rec", data_dir=str(tmp_path))
        ks.add_document(
            "capability.txt",
            (
                "공공 행정 AI 플랫폼 구축 레퍼런스 3건. "
                "클라우드 전환과 정보보호 컨설팅 수행 경험 보유. "
                "소프트웨어사업자 등록 및 ISMS 인증 보유. "
                "PM, PMO, 컨설턴트, 개발자, 아키텍트 인력 확보."
            ),
        )

        record = _service(tmp_path).recommend_project(project_id="proj-go-rec", tenant_id="tenant-a")

        assert record.recommendation is not None
        assert record.recommendation.value == "GO"
        assert record.recommendation.remediation_notes == []
        assert len(record.checklist_items) == 10
        assert any(item.category == "eligibility_and_compliance" for item in record.checklist_items)
        assert all(item.status in {"ready", "action_needed"} for item in record.checklist_items)

    def test_recommendation_conditional_case_has_action_items(self, tmp_path):
        _attach_snapshot(
            tmp_path,
            project_id="proj-conditional-rec",
            title="데이터 기반 정책 지원 시스템",
            issuer="서울특별시",
            budget="15억원",
            deadline="2026-04-18 17:00",
            raw_text="지역제한 없음. 데이터 분석 및 보고체계 구축.",
            key_requirements=["데이터 분석", "정책 지원", "보고 체계"],
        )
        ks = KnowledgeStore("proj-conditional-rec", data_dir=str(tmp_path))
        ks.add_document(
            "capability.txt",
            (
                "공공 데이터 분석 컨설팅 수행 경험 보유. "
                "PM과 컨설턴트 중심 수행 가능. "
                "레퍼런스는 제한적이며 클라우드 경험은 적음."
            ),
        )

        record = _service(tmp_path).recommend_project(project_id="proj-conditional-rec", tenant_id="tenant-a")

        assert record.recommendation is not None
        assert record.recommendation.value == "CONDITIONAL_GO"
        assert record.recommendation.remediation_notes
        assert any(item.status == "action_needed" for item in record.checklist_items)

    def test_recommendation_no_go_case_has_blocked_checklist(self, tmp_path):
        _attach_snapshot(
            tmp_path,
            project_id="proj-no-go-rec",
            title="보안 인증 기반 통합 관제 고도화",
            issuer="조달청",
            budget="8억원",
            deadline="2026-03-30 18:00",
            raw_text="필수 요건: ISMS 보유, 공동수급 가능. 유사사업 수행실적 필요.",
            key_requirements=["보안 관제", "클라우드", "통합 플랫폼"],
        )
        ks = KnowledgeStore("proj-no-go-rec", data_dir=str(tmp_path))
        ks.add_document(
            "capability.txt",
            "공공 컨설팅 수행 경험은 있으나 보안 인증과 협력사 체계는 아직 확보되지 않음.",
        )

        record = _service(tmp_path).recommend_project(project_id="proj-no-go-rec", tenant_id="tenant-a")

        assert record.recommendation is not None
        assert record.recommendation.value == "NO_GO"
        assert any(item.status == "blocked" for item in record.checklist_items)
        assert any(item.severity == "critical" for item in record.checklist_items if item.status == "blocked")

    def test_recommendation_insufficient_data_case_surfaces_missing_inputs(self, tmp_path):
        _attach_snapshot(
            tmp_path,
            project_id="proj-insufficient-rec",
            title="신규 행정 서비스 개선 사업",
            issuer="행정안전부",
            budget="",
            deadline="",
            raw_text="사업 개요만 존재.",
            key_requirements=[],
            evaluation_criteria=[],
        )

        record = _service(tmp_path).recommend_project(project_id="proj-insufficient-rec", tenant_id="tenant-a")

        assert record.recommendation is not None
        assert record.recommendation.value == "CONDITIONAL_GO"
        assert "structured RFP requirement signals" in record.recommendation.missing_data
        assert any(item.status == "action_needed" for item in record.checklist_items)
