"""Tests for Milestone 5 procurement decision bundle and downstream handoff."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.bundle_catalog.registry import BUNDLE_REGISTRY
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


HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    return TestClient(create_app())


@pytest.fixture
def disabled_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    return TestClient(create_app())


def _create_project(client: TestClient) -> str:
    response = client.post("/projects", json={"name": "조달 의사결정 프로젝트"}, headers=HEADERS)
    assert response.status_code == 200
    return response.json()["project_id"]


def _seed_procurement_decision(client: TestClient, project_id: str) -> None:
    store = client.app.state.procurement_store
    snapshot = store.save_source_snapshot(
        tenant_id="system",
        project_id=project_id,
        source_kind="g2b_import",
        source_label="나라장터 상세조회",
        external_id="20260325077-00",
        payload={
            "announcement": {
                "bid_number": "20260325077-00",
                "issuer": "행정안전부",
                "title": "AI 기반 민원 서비스 고도화 사업",
            },
            "extracted_fields": {
                "mandatory_certifications": ["ISMS", "소프트웨어사업자 신고"],
                "required_references": "공공 AI 서비스 구축 레퍼런스 2건 이상",
            },
            "structured_context": (
                "발주기관은 행정안전부이며, 공공 민원 서비스의 상담·처리 자동화를 목표로 한다. "
                "예산은 5억원 수준이고, 제안 마감 전 파트너 구성과 인증 증빙 정리가 필요하다."
            ),
        },
    )
    store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="20260325077-00",
                source_url="https://www.g2b.go.kr/notice/20260325077-00",
                title="AI 기반 민원 서비스 고도화 사업",
                issuer="행정안전부",
                budget="5억원",
                deadline="2026-04-30 18:00",
                bid_type="일반경쟁",
                category="용역",
                region="전국",
                raw_text_preview="행정안전부 민원 AI 고도화 공고 미리보기",
            ),
            capability_profile=CapabilityProfileReference(
                source_kind="knowledge_document",
                source_ref="project-knowledge",
                title="공공 민원 서비스 수행 역량",
                summary="공공 AI 상담 시스템 구축 경험과 ISMS 보안 대응 경험을 보유",
                document_ids=["cap-1"],
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="mandatory_certification_or_license",
                    label="필수 자격 및 인증",
                    status=ProcurementHardFilterStatus.PASS,
                    blocking=False,
                    reason="ISMS와 소프트웨어사업자 신고 기준 충족",
                    evidence=["ISMS 인증", "소프트웨어사업자 신고 완료"],
                ),
                ProcurementHardFilterResult(
                    code="partner_readiness",
                    label="파트너 구성 준비도",
                    status=ProcurementHardFilterStatus.UNKNOWN,
                    blocking=False,
                    reason="전문 파트너 확약서 최신본 미확인",
                    evidence=["후보 파트너 1개사 협의 중"],
                ),
            ],
            score_breakdown=[
                ProcurementScoreBreakdownItem(
                    key="domain_fit",
                    label="도메인 적합도",
                    score=82.0,
                    weight=0.35,
                    weighted_score=28.7,
                    status=ProcurementScoreStatus.SCORED,
                    summary="공공 민원 서비스 수행 경험이 충분함",
                    evidence=["공공 민원 AI 구축 2건"],
                ),
                ProcurementScoreBreakdownItem(
                    key="delivery_readiness",
                    label="수행 준비도",
                    score=66.0,
                    weight=0.25,
                    weighted_score=16.5,
                    status=ProcurementScoreStatus.SCORED,
                    summary="핵심 인력은 확보되었으나 파트너 확약서 갱신 필요",
                    evidence=["PM/컨설턴트 확보", "파트너 확약서 갱신 필요"],
                ),
            ],
            soft_fit_score=72.4,
            soft_fit_status=ProcurementScoreStatus.SCORED,
            missing_data=["최신 파트너 확약서"],
            checklist_items=[
                ProcurementChecklistItem(
                    category="partner_and_staffing",
                    title="전문 파트너 확약서 갱신",
                    status=ProcurementChecklistStatus.ACTION_NEEDED,
                    severity=ProcurementChecklistSeverity.HIGH,
                    evidence="확약서가 지난 분기 기준 문서임",
                    remediation_note="최신 확약서 수령 후 첨부",
                    owner="BD Lead",
                    due_date="2026-04-05",
                ),
                ProcurementChecklistItem(
                    category="eligibility_and_compliance",
                    title="입찰 자격 및 인증 확인",
                    status=ProcurementChecklistStatus.READY,
                    severity=ProcurementChecklistSeverity.MEDIUM,
                    evidence="필수 자격 충족",
                    remediation_note="",
                    owner="Delivery Lead",
                    due_date="2026-04-02",
                ),
            ],
            recommendation=ProcurementRecommendation(
                value=ProcurementRecommendationValue.CONDITIONAL_GO,
                summary="핵심 적합도는 충분하나 파트너 준비도를 닫은 뒤 입찰하는 것이 안전함",
                evidence=["도메인 적합도 양호", "필수 인증 충족"],
                missing_data=["최신 파트너 확약서"],
                remediation_notes=["파트너 확약서 갱신 후 제안 착수"],
            ),
            source_snapshots=[snapshot],
            notes="Milestone 5 handoff seed",
        )
    )


def test_bid_decision_bundle_is_registered():
    assert "bid_decision_kr" in BUNDLE_REGISTRY
    assert BUNDLE_REGISTRY["bid_decision_kr"].doc_keys == [
        "opportunity_brief",
        "go_no_go_memo",
        "bid_readiness_checklist",
        "proposal_kickoff_summary",
    ]


def test_generate_bid_decision_bundle_uses_project_procurement_state(client):
    project_id = _create_project(client)
    _seed_procurement_decision(client, project_id)

    response = client.post(
        "/generate",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 참여 여부를 판단하고 downstream handoff를 준비한다",
            "bundle_type": "bid_decision_kr",
            "project_id": project_id,
        },
        headers=HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["docs"]) == 4
    assert {doc["doc_type"] for doc in body["docs"]} == {
        "opportunity_brief",
        "go_no_go_memo",
        "bid_readiness_checklist",
        "proposal_kickoff_summary",
    }
    combined = "\n".join(doc["markdown"] for doc in body["docs"])
    assert "행정안전부" in combined
    assert "CONDITIONAL_GO" in combined
    assert "최신 파트너 확약서" in combined


def test_generate_export_bid_decision_bundle_writes_existing_markdown_exports(client):
    project_id = _create_project(client)
    _seed_procurement_decision(client, project_id)

    response = client.post(
        "/generate/export",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 의사결정 결과를 문서로 저장한다",
            "bundle_type": "bid_decision_kr",
            "project_id": project_id,
        },
        headers=HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["files"]) == 4
    export_dir = Path(body["export_dir"])
    assert export_dir.exists()

    for item in body["files"]:
        path = Path(item["path"])
        assert path.exists()
        assert path.read_text(encoding="utf-8").strip()

    kickoff = next(item for item in body["files"] if item["doc_type"] == "proposal_kickoff_summary")
    kickoff_text = Path(kickoff["path"]).read_text(encoding="utf-8")
    assert "RFP 분석 인풋" in kickoff_text
    assert "제안서 인풋" in kickoff_text


def test_bid_decision_bundle_is_blocked_when_feature_flag_is_off(disabled_client):
    project_id = _create_project(disabled_client)
    _seed_procurement_decision(disabled_client, project_id)

    response = disabled_client.post(
        "/generate",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 참여 여부를 판단한다",
            "bundle_type": "bid_decision_kr",
            "project_id": project_id,
        },
        headers=HEADERS,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FEATURE_DISABLED"


def test_bid_decision_stream_is_blocked_when_feature_flag_is_off(disabled_client):
    project_id = _create_project(disabled_client)
    _seed_procurement_decision(disabled_client, project_id)

    response = disabled_client.post(
        "/generate/stream",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 참여 여부를 판단한다",
            "bundle_type": "bid_decision_kr",
            "project_id": project_id,
        },
        headers=HEADERS,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FEATURE_DISABLED"


def test_bid_decision_export_is_blocked_when_feature_flag_is_off(disabled_client):
    project_id = _create_project(disabled_client)
    _seed_procurement_decision(disabled_client, project_id)

    response = disabled_client.post(
        "/generate/export",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 참여 여부를 판단한다",
            "bundle_type": "bid_decision_kr",
            "project_id": project_id,
        },
        headers=HEADERS,
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "FEATURE_DISABLED"


@pytest.mark.parametrize("bundle_type", ["rfp_analysis_kr", "proposal_kr", "performance_plan_kr"])
def test_downstream_bundles_receive_procurement_handoff_context(client, bundle_type):
    project_id = _create_project(client)
    _seed_procurement_decision(client, project_id)

    response = client.post(
        "/generate",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 후속 문서 작성을 준비한다",
            "bundle_type": bundle_type,
            "project_id": project_id,
        },
        headers=HEADERS,
    )

    assert response.status_code == 200
    combined = "\n".join(doc["markdown"] for doc in response.json()["docs"])
    assert "행정안전부" in combined
    assert "CONDITIONAL_GO" in combined


@pytest.mark.parametrize("bundle_type", ["rfp_analysis_kr", "proposal_kr", "performance_plan_kr"])
def test_downstream_bundles_still_generate_without_procurement_handoff_when_flag_is_off(disabled_client, bundle_type):
    project_id = _create_project(disabled_client)
    _seed_procurement_decision(disabled_client, project_id)

    response = disabled_client.post(
        "/generate",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 후속 문서를 생성한다",
            "bundle_type": bundle_type,
            "project_id": project_id,
        },
        headers=HEADERS,
    )

    assert response.status_code == 200
    combined = "\n".join(doc["markdown"] for doc in response.json()["docs"])
    assert "CONDITIONAL_GO" not in combined
    assert "최신 파트너 확약서" not in combined
