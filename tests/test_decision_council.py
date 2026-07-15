from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

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
    record = _build_procurement_record(
        tmp_path,
        project_id="proj-council-2",
        recommendation_value="NO_GO",
    )

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


def test_decision_council_store_rejects_unsafe_tenant_before_creating_paths(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))

    for tenant_id in ("", " tenant-a", "tenant-a ", ".", "..", "a/b", "a\\b", "a\x00b"):
        with pytest.raises(ValueError, match="Invalid tenant_id"):
            store.get_latest(tenant_id=tenant_id, project_id="proj-unsafe")

    assert not (tmp_path / "tenants").exists()


def test_decision_council_store_rejects_mismatched_scope_before_writing(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_store = DecisionCouncilStore(base_dir=str(source_dir))
    source_service = DecisionCouncilService(decision_council_store=source_store)
    record = _build_procurement_record(source_dir, project_id="proj-scope")
    session = source_service.run_procurement_council(
        tenant_id="default",
        project_id="proj-scope",
        goal="scope 검증용 council을 만든다.",
        procurement_record=record,
    )
    target_store = DecisionCouncilStore(base_dir=str(target_dir))

    with pytest.raises(ValueError, match="tenant does not match"):
        target_store.upsert_latest(
            session.model_copy(update={"tenant_id": "foreign"}),
            tenant_id="default",
        )
    with pytest.raises(ValueError, match="key does not match"):
        target_store.upsert_latest(
            session.model_copy(update={"session_key": "forged:key"}),
            tenant_id="default",
        )

    assert not (target_dir / "tenants").exists()


def test_decision_council_service_rejects_foreign_procurement_record(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(tmp_path, project_id="proj-owned")

    with pytest.raises(ValueError, match="does not match Decision Council scope"):
        service.run_procurement_council(
            tenant_id="other-tenant",
            project_id="proj-owned",
            goal="다른 tenant record를 사용하지 않는다.",
            procurement_record=record,
        )
    with pytest.raises(ValueError, match="does not match Decision Council scope"):
        service.run_procurement_council(
            tenant_id="default",
            project_id="proj-other",
            goal="다른 project record를 사용하지 않는다.",
            procurement_record=record,
        )

    assert not (tmp_path / "tenants" / "other-tenant").exists()


def test_decision_council_store_preserves_drift_and_updates_owned_record(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(tmp_path, project_id="proj-drift")
    first = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-drift",
        goal="현재 tenant의 council을 만든다.",
        procurement_record=record,
    )
    path = tmp_path / "tenants" / "default" / "decision_council_sessions.json"
    owned = json.loads(path.read_text(encoding="utf-8"))[0]
    foreign = {**owned, "tenant_id": "foreign", "session_id": "session-foreign"}
    malformed = {**owned, "session_id": "session-malformed"}
    malformed.pop("goal")
    path.write_text(
        json.dumps([foreign, malformed, owned], ensure_ascii=False),
        encoding="utf-8",
    )

    latest = store.get_latest(tenant_id="default", project_id="proj-drift")
    assert latest is not None
    assert latest.session_id == first.session_id

    updated = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-drift",
        goal="현재 tenant의 council만 갱신한다.",
        procurement_record=record,
    )
    persisted = json.loads(path.read_text(encoding="utf-8"))

    assert persisted[:2] == [foreign, malformed]
    assert persisted[2]["session_id"] == first.session_id
    assert persisted[2]["session_revision"] == 2
    assert updated.session_revision == 2


def test_decision_council_store_rejects_duplicate_owned_session(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(tmp_path, project_id="proj-duplicate")
    session = service.run_procurement_council(
        tenant_id="default",
        project_id="proj-duplicate",
        goal="중복 감지 기준을 만든다.",
        procurement_record=record,
    )
    path = tmp_path / "tenants" / "default" / "decision_council_sessions.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    duplicate = {**records[0], "session_id": "session-duplicate"}
    records.append(duplicate)
    path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    original = path.read_bytes()

    with pytest.raises(ValueError, match="Duplicate Decision Council"):
        store.get_latest(tenant_id="default", project_id="proj-duplicate")
    with pytest.raises(ValueError, match="Duplicate Decision Council"):
        store.upsert_latest(session, tenant_id="default")

    assert path.read_bytes() == original


def test_decision_council_store_preserves_invalid_state_document(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_store = DecisionCouncilStore(base_dir=str(source_dir))
    source_service = DecisionCouncilService(decision_council_store=source_store)
    record = _build_procurement_record(source_dir, project_id="proj-invalid-state")
    session = source_service.run_procurement_council(
        tenant_id="default",
        project_id="proj-invalid-state",
        goal="invalid state 보존을 검증한다.",
        procurement_record=record,
    )
    path = target_dir / "tenants" / "default" / "decision_council_sessions.json"
    path.parent.mkdir(parents=True)
    path.write_text('{"not": "a session list"}', encoding="utf-8")
    original = path.read_bytes()
    store = DecisionCouncilStore(base_dir=str(target_dir))

    with pytest.raises(ValueError, match="Invalid Decision Council state document"):
        store.get_latest(tenant_id="default", project_id="proj-invalid-state")
    with pytest.raises(ValueError, match="Invalid Decision Council state document"):
        store.upsert_latest(session, tenant_id="default")

    assert path.read_bytes() == original


def test_decision_council_concurrent_instances_preserve_every_session(tmp_path):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_store = DecisionCouncilStore(base_dir=str(source_dir))
    source_service = DecisionCouncilService(decision_council_store=source_store)
    record = _build_procurement_record(source_dir, project_id="proj-template")
    template = source_service.run_procurement_council(
        tenant_id="default",
        project_id="proj-template",
        goal="동시 저장 template을 만든다.",
        procurement_record=record,
    )
    stores = [DecisionCouncilStore(base_dir=str(target_dir)) for _ in range(20)]

    def save_session(index: int) -> None:
        project_id = f"proj-concurrent-{index}"
        session = template.model_copy(
            update={
                "session_id": f"session-concurrent-{index}",
                "session_key": DecisionCouncilStore.build_session_key(
                    project_id=project_id,
                    use_case="public_procurement",
                    target_bundle_type="bid_decision_kr",
                ),
                "project_id": project_id,
                "goal": f"동시 저장 {index}",
                "operation": None,
            }
        )
        stores[index].upsert_latest(session, tenant_id="default")

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(save_session, range(20)))

    path = target_dir / "tenants" / "default" / "decision_council_sessions.json"
    records = json.loads(path.read_text(encoding="utf-8"))
    assert {record["project_id"] for record in records} == {
        f"proj-concurrent-{index}" for index in range(20)
    }


def test_decision_council_generation_context_includes_consensus_and_handoff(tmp_path):
    store = DecisionCouncilStore(base_dir=str(tmp_path))
    service = DecisionCouncilService(decision_council_store=store)
    record = _build_procurement_record(
        tmp_path,
        project_id="proj-council-3",
        recommendation_value="GO",
    )

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
