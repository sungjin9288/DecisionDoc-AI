"""Tests for project-scoped procurement decision models and persistence."""
from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from app.main import create_app
from app.schemas import (
    CapabilityProfileReference,
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementChecklistSeverity,
    ProcurementChecklistStatus,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementHardFilterStatus,
    ProcurementRecommendation,
    ProcurementRecommendationValue,
    ProcurementScoreBreakdownItem,
    ProcurementScoreStatus,
)
from app.storage.procurement_store import ProcurementDecisionStore


def _sample_upsert(project_id: str = "proj-001", tenant_id: str = "tenant-a") -> ProcurementDecisionUpsert:
    return ProcurementDecisionUpsert(
        project_id=project_id,
        tenant_id=tenant_id,
        opportunity=NormalizedProcurementOpportunity(
            source_kind="g2b",
            source_id="20260325001-00",
            source_url="https://www.g2b.go.kr/example",
            title="AI 기반 민원 서비스 고도화 사업",
            issuer="행정안전부",
            budget="5억원",
            deadline="2026-04-30 17:00",
            bid_type="일반경쟁",
            category="용역",
            region="전국",
            raw_text_preview="공고 미리보기",
        ),
        capability_profile=CapabilityProfileReference(
            source_kind="knowledge_document",
            source_ref="project-knowledge",
            title="공공사업 수행역량",
            summary="행정기관 DX 구축 경험과 보안 컨설팅 역량",
            document_ids=["doc-cap-1", "doc-cap-2"],
        ),
        hard_filters=[
            ProcurementHardFilterResult(
                code="mandatory_domain_experience",
                label="필수 도메인 경험",
                status=ProcurementHardFilterStatus.PASS,
                blocking=False,
                reason="유사 공공 민원 시스템 구축 사례 보유",
                evidence=["유사 사업 수행 3건"],
            )
        ],
        score_breakdown=[
            ProcurementScoreBreakdownItem(
                key="domain_fit",
                label="도메인 적합도",
                score=84.0,
                weight=0.25,
                weighted_score=21.0,
                status=ProcurementScoreStatus.SCORED,
                summary="행정기관 서비스 구축 경험이 충분함",
                evidence=["공공 DX 레퍼런스 3건"],
            )
        ],
        checklist_items=[
            ProcurementChecklistItem(
                category="eligibility_and_compliance",
                title="입찰참가자격 확인",
                status=ProcurementChecklistStatus.ACTION_NEEDED,
                severity=ProcurementChecklistSeverity.HIGH,
                evidence="최신 증빙 미첨부",
                remediation_note="증빙서류 업데이트 필요",
                owner="BD Lead",
                due_date="2026-03-31",
            )
        ],
        recommendation=ProcurementRecommendation(
            value=ProcurementRecommendationValue.CONDITIONAL_GO,
            summary="핵심 역량은 적합하나 입찰 준비 항목 보완이 필요함",
            evidence=["레퍼런스 적합", "기술역량 충분"],
            missing_data=["최신 자격 증빙"],
            remediation_notes=["증빙 확보 후 진행"],
        ),
        notes="Milestone 1 persistence baseline",
    )


class TestProcurementModels:
    def test_upsert_model_serializes_nested_state(self):
        payload = _sample_upsert()
        dumped = payload.model_dump(mode="json")
        assert dumped["project_id"] == "proj-001"
        assert dumped["opportunity"]["source_kind"] == "g2b"
        assert dumped["recommendation"]["value"] == "CONDITIONAL_GO"
        assert dumped["checklist_items"][0]["status"] == "action_needed"

    def test_upsert_model_rejects_unknown_fields(self):
        with pytest.raises(ValidationError):
            ProcurementDecisionUpsert.model_validate(
                {
                    "project_id": "proj-001",
                    "tenant_id": "tenant-a",
                    "unexpected": True,
                }
            )


class TestProcurementDecisionStore:
    def test_upsert_persists_and_reads_record(self, tmp_path):
        store = ProcurementDecisionStore(base_dir=str(tmp_path))
        saved = store.upsert(_sample_upsert())

        assert saved.decision_id
        assert saved.created_at
        assert saved.updated_at
        assert saved.project_id == "proj-001"
        assert saved.opportunity is not None
        assert saved.opportunity.title == "AI 기반 민원 서비스 고도화 사업"

        reloaded = ProcurementDecisionStore(base_dir=str(tmp_path)).get("proj-001", tenant_id="tenant-a")
        assert reloaded is not None
        assert reloaded.decision_id == saved.decision_id
        assert reloaded.recommendation is not None
        assert reloaded.recommendation.value == ProcurementRecommendationValue.CONDITIONAL_GO

    def test_upsert_updates_existing_project_record(self, tmp_path):
        store = ProcurementDecisionStore(base_dir=str(tmp_path))
        first = store.upsert(_sample_upsert())
        time.sleep(0.01)

        updated_payload = _sample_upsert()
        updated_payload.recommendation = ProcurementRecommendation(
            value=ProcurementRecommendationValue.GO,
            summary="보완항목 해결 후 바로 진행 가능",
            evidence=["적격성 확보"],
        )
        updated = store.upsert(updated_payload)

        assert updated.decision_id == first.decision_id
        assert updated.created_at == first.created_at
        assert updated.updated_at > first.updated_at
        assert updated.recommendation is not None
        assert updated.recommendation.value == ProcurementRecommendationValue.GO

    def test_store_is_tenant_scoped(self, tmp_path):
        store = ProcurementDecisionStore(base_dir=str(tmp_path))
        store.upsert(_sample_upsert(project_id="shared-proj", tenant_id="tenant-a"))

        other = _sample_upsert(project_id="shared-proj", tenant_id="tenant-b")
        other.opportunity = NormalizedProcurementOpportunity(
            source_kind="g2b",
            source_id="20260325002-00",
            title="클라우드 전환 컨설팅",
            issuer="조달청",
        )
        store.upsert(other)

        tenant_a = store.get("shared-proj", tenant_id="tenant-a")
        tenant_b = store.get("shared-proj", tenant_id="tenant-b")
        assert tenant_a is not None and tenant_b is not None
        assert tenant_a.tenant_id == "tenant-a"
        assert tenant_b.tenant_id == "tenant-b"
        assert tenant_a.opportunity is not None
        assert tenant_b.opportunity is not None
        assert tenant_a.opportunity.title != tenant_b.opportunity.title

    def test_save_source_snapshot_round_trip(self, tmp_path):
        store = ProcurementDecisionStore(base_dir=str(tmp_path))
        metadata = store.save_source_snapshot(
            tenant_id="tenant-a",
            project_id="proj-001",
            source_kind="g2b_fetch",
            source_label="나라장터 상세조회",
            external_id="20260325001-00",
            payload={"bid_number": "20260325001-00", "issuer": "행정안전부"},
        )

        assert metadata.snapshot_id
        assert metadata.storage_path.endswith(f"{metadata.snapshot_id}.json")

        loaded = store.load_source_snapshot(
            tenant_id="tenant-a",
            project_id="proj-001",
            snapshot_id=metadata.snapshot_id,
        )
        assert loaded == {"bid_number": "20260325001-00", "issuer": "행정안전부"}


class TestProcurementStoreAppWiring:
    def test_create_app_exposes_procurement_store(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
        monkeypatch.setenv("DECISIONDOC_ENV", "dev")
        monkeypatch.setenv("DATA_DIR", str(tmp_path))
        monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
        monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

        app = create_app()
        assert hasattr(app.state, "procurement_store")
        assert isinstance(app.state.procurement_store, ProcurementDecisionStore)
