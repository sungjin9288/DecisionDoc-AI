from __future__ import annotations

from pathlib import Path

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementChecklistSeverity,
    ProcurementChecklistStatus,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementRecommendationValue,
)
from app.services.decision_council_service import DecisionCouncilService
from app.storage.decision_council_store import DecisionCouncilStore
from app.storage.procurement_store import ProcurementDecisionStore


def _build_procurement_record(
    tmp_path: Path,
    *,
    project_id: str = "proj-council-1",
    recommendation_value: str = "CONDITIONAL_GO",
) -> object:
    procurement_store = ProcurementDecisionStore(base_dir=str(tmp_path))
    return procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="default",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="G2B-COUNCIL-001",
                source_url="https://www.g2b.go.kr/notice/G2B-COUNCIL-001",
                title="AI 민원 분석 고도화 사업",
                issuer="행정안전부",
                budget="5억원",
                deadline="2026-05-30 18:00",
                bid_type="일반경쟁",
                category="용역",
                raw_text_preview="소프트웨어사업자 등록, ISMS 인증, 공공 AI 레퍼런스 필요",
            ),
            hard_filters=[
                ProcurementHardFilterResult(
                    code="mandatory_certification_or_license",
                    label="필수 인증",
                    status="pass",
                    blocking=True,
                    reason="소프트웨어사업자 등록 보유",
                    evidence=["소프트웨어사업자 등록 확인"],
                )
            ],
            checklist_items=[
                ProcurementChecklistItem(
                    category="eligibility_and_compliance",
                    title="ISMS 인증 증빙 확인",
                    status=ProcurementChecklistStatus.ACTION_NEEDED,
                    severity=ProcurementChecklistSeverity.HIGH,
                    remediation_note="최신 인증서 사본 확보 필요",
                    owner="compliance",
                )
            ],
            soft_fit_score=72.5,
            soft_fit_status="scored",
            missing_data=["핵심 레퍼런스 제출 가능 여부"],
            recommendation=ProcurementRecommendation(
                value=ProcurementRecommendationValue(recommendation_value),
                summary="조건 해소 시 진행 가능한 기회",
                evidence=["공공 AI 경험 존재", "필수 인증 증빙은 보완 필요"],
            ),
        )
    )


def test_decision_council_service_builds_structured_procurement_session(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(tmp_path)

    session = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-council-1",
        goal="입찰 참여 여부를 경영진이 빠르게 판단할 수 있게 정리한다.",
        context="공공 AI 구축 레퍼런스는 있으나 최신 인증 증빙은 재확인이 필요하다.",
        constraints="외부 제안서 작성으로 바로 확장하지 않는다.",
        procurement_record=record,
    )

    assert session.operation == "created"
    assert session.project_id == "proj-council-1"
    assert session.target_bundle_type == "bid_decision_kr"
    assert session.supported_bundle_types == ["bid_decision_kr", "proposal_kr"]
    assert [opinion.role for opinion in session.role_opinions] == [
        "Requirement Analyst",
        "Risk Reviewer",
        "Domain Strategist",
        "Compliance Reviewer",
        "Drafting Lead",
    ]
    assert session.consensus.recommended_direction == "proceed_with_conditions"
    assert session.consensus.strategy_options
    assert session.risks
    assert session.handoff.target_bundle_type == "bid_decision_kr"
    assert session.handoff.source_procurement_decision_id == record.decision_id
    assert session.source_procurement_updated_at == record.updated_at
    assert session.source_procurement_recommendation_value == "CONDITIONAL_GO"
    assert session.source_procurement_missing_data_count == 1
    assert session.source_procurement_action_needed_count == 1
    assert session.source_procurement_blocking_hard_filter_count == 0
    assert any("ISMS" in item for item in session.handoff.must_address)


def test_decision_council_store_upsert_latest_reuses_session_id_and_bumps_revision(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(tmp_path, recommendation_value="NO_GO")

    first = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-council-2",
        goal="입찰 미진행 근거를 정리한다.",
        procurement_record=record,
    )
    second = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-council-2",
        goal="입찰 미진행 근거를 더 명확히 정리한다.",
        procurement_record=record,
    )

    latest = store.get_latest(tenant_id="default", project_id="proj-council-2")
    assert latest is not None
    assert first.operation == "created"
    assert second.operation == "updated"
    assert first.session_id == second.session_id
    assert second.session_revision == first.session_revision + 1
    assert latest.session_id == second.session_id
    assert latest.session_revision == second.session_revision
    assert latest.goal == "입찰 미진행 근거를 더 명확히 정리한다."


def test_decision_council_generation_context_includes_consensus_and_handoff(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(tmp_path, recommendation_value="GO")

    session = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-council-3",
        goal="즉시 Go 판단 근거를 정리한다.",
        procurement_record=record,
    )
    context = service.build_generation_context(session)
    proposal_context = service.build_generation_context(session, bundle_type="proposal_kr")

    assert session.operation == "created"
    assert session.consensus.recommended_direction == "proceed"
    assert f"council_session_id: {session.session_id}" in context
    assert "Drafting handoff:" in context
    assert "must_include" in context
    assert "applied_bundle_type: bid_decision_kr" in context
    assert "proposal_kr 작성 시" in proposal_context
    assert "Proposal drafting handoff:" in proposal_context
    assert "applied_bundle_type: proposal_kr" in proposal_context


def test_decision_council_binding_marks_session_stale_after_procurement_update(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    procurement_store = ProcurementDecisionStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(tmp_path, project_id="proj-council-4", recommendation_value="GO")

    session = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-council-4",
        goal="현재 recommendation 기준의 council handoff를 만든다.",
        procurement_record=record,
    )

    updated_record = procurement_store.upsert(
        ProcurementDecisionUpsert(
            project_id="proj-council-4",
            tenant_id="default",
            opportunity=record.opportunity,
            recommendation=ProcurementRecommendation(
                value=ProcurementRecommendationValue.NO_GO,
                summary="업데이트 이후 recommendation",
            ),
            missing_data=["최신 증빙 재확인"],
        )
    )
    assert updated_record.updated_at != record.updated_at

    refreshed = service.attach_procurement_binding(
        session=session,
        procurement_record=updated_record,
    )

    assert refreshed.current_procurement_binding_status == "stale"
    assert refreshed.current_procurement_binding_reason_code == "procurement_updated"
    assert refreshed.current_procurement_updated_at == updated_record.updated_at
    assert refreshed.source_procurement_recommendation_value == "GO"
    assert refreshed.current_procurement_recommendation_value == "NO_GO"
    assert refreshed.current_procurement_missing_data_count == 1
    assert refreshed.current_procurement_action_needed_count == 0
    assert "다시 실행해야" in refreshed.current_procurement_binding_summary


def test_decision_council_binding_stays_current_for_notes_only_override_update(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    procurement_store = ProcurementDecisionStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(tmp_path, project_id="proj-council-5", recommendation_value="NO_GO")

    session = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-council-5",
        goal="override reason 이후에도 같은 procurement 판단 기준을 유지한다.",
        procurement_record=record,
    )

    updated_record = procurement_store.update_notes(
        project_id="proj-council-5",
        tenant_id="default",
        notes="notes-only override reason",
    )

    refreshed = service.attach_procurement_binding(
        session=session,
        procurement_record=updated_record,
    )

    assert updated_record.updated_at == record.updated_at
    assert refreshed.current_procurement_binding_status == "current"
    assert refreshed.current_procurement_binding_reason_code == ""
    assert refreshed.current_procurement_updated_at == updated_record.updated_at
    assert refreshed.current_procurement_recommendation_value == "NO_GO"
