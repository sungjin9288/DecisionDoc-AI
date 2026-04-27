from __future__ import annotations

import pytest

from app.storage.report_workflow_store import (
    PlanningVersion,
    ReportWorkflowStatus,
    ReportWorkflowStore,
    SlideDraft,
    SlidePlan,
    SlideStatus,
)


def _store(tmp_path):
    return ReportWorkflowStore(base_dir=str(tmp_path))


def _planning() -> PlanningVersion:
    return PlanningVersion(
        plan_id="plan-1",
        version=0,
        status="draft",
        objective="목적",
        audience="PM",
        executive_message="핵심 메시지",
        table_of_contents=["1장", "2장"],
        slide_plans=[
            SlidePlan(
                slide_id="slide-001",
                page=1,
                title="1장",
                key_message="A",
                decision_question="A를 승인할 것인가?",
                content_blocks=["메시지", "근거"],
                acceptance_criteria=["판단 기준이 명확함"],
            ),
            SlidePlan(slide_id="slide-002", page=2, title="2장", key_message="B"),
        ],
        open_questions=[],
        risk_notes=[],
        created_by="ai",
        created_at="2026-04-25T00:00:00+00:00",
        planning_brief="목적과 승인 기준을 먼저 확정한다.",
        audience_decision_needs=["승인 범위 확인"],
        narrative_arc=["문제", "해결", "승인"],
        template_guidance=["headline/evidence/decision 구조"],
        source_strategy=["첨부자료를 장표별 근거로 매핑"],
        quality_bar=["장표별 승인 기준 명확화"],
    )


def _slides() -> list[SlideDraft]:
    return [
        SlideDraft(
            slide_id="slide-001",
            page=1,
            title="1장",
            body="본문 1",
            visual_spec="도식 1",
            speaker_note="노트 1",
            source_refs=[],
        ),
        SlideDraft(
            slide_id="slide-002",
            page=2,
            title="2장",
            body="본문 2",
            visual_spec="도식 2",
            speaker_note="노트 2",
            source_refs=[],
        ),
    ]


def test_create_report_workflow_defaults_to_planning_required(tmp_path):
    rec = _store(tmp_path).create(tenant_id="t1", title="보고서")

    assert rec.status == ReportWorkflowStatus.PLANNING_REQUIRED.value
    assert rec.learning_opt_in is False


def test_tenant_isolation(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="alpha", title="보고서")

    assert store.get(rec.report_workflow_id, tenant_id="alpha") is not None
    assert store.get(rec.report_workflow_id, tenant_id="beta") is None


def test_slides_blocked_before_planning_approval(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서")

    with pytest.raises(ValueError):
        store.save_slides(rec.report_workflow_id, _slides(), tenant_id="t1")


def test_planning_change_request_then_reapproval(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서")
    store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    store.request_planning_changes(rec.report_workflow_id, author="pm", comment="수정", tenant_id="t1")
    updated = store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    approved = store.approve_planning(rec.report_workflow_id, author="pm", tenant_id="t1")

    assert updated.status == ReportWorkflowStatus.PLANNING_DRAFT.value
    assert approved.status == ReportWorkflowStatus.PLANNING_APPROVED.value
    assert approved.planning is not None
    assert approved.planning.planning_brief == "목적과 승인 기준을 먼저 확정한다."
    assert approved.planning.slide_plans[0].decision_question == "A를 승인할 것인가?"
    assert approved.planning.slide_plans[0].acceptance_criteria == ["판단 기준이 명확함"]


def test_final_submit_blocked_until_all_slides_approved(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서")
    store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    store.approve_planning(rec.report_workflow_id, author="pm", tenant_id="t1")
    store.save_slides(rec.report_workflow_id, _slides(), tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-001", author="pm", tenant_id="t1")

    with pytest.raises(ValueError):
        store.submit_final(rec.report_workflow_id, author="pm", tenant_id="t1")


def test_full_approval_flow_and_immutability(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서")
    store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    store.approve_planning(rec.report_workflow_id, author="pm", tenant_id="t1")
    store.save_slides(rec.report_workflow_id, _slides(), tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-001", author="pm", tenant_id="t1")
    slides_approved = store.approve_slide(rec.report_workflow_id, "slide-002", author="pm", tenant_id="t1")
    final_review = store.submit_final(rec.report_workflow_id, author="pm", tenant_id="t1")
    final = store.approve_final(rec.report_workflow_id, author="ceo", tenant_id="t1")

    assert slides_approved.status == ReportWorkflowStatus.SLIDES_APPROVED.value
    assert final_review.status == ReportWorkflowStatus.FINAL_REVIEW.value
    assert [step.stage for step in final_review.approval_steps] == ["pm_review", "executive_review"]
    assert final.status == ReportWorkflowStatus.FINAL_APPROVED.value
    assert all(step.status == "approved" for step in final.approval_steps)
    with pytest.raises(ValueError):
        store.request_slide_changes(rec.report_workflow_id, "slide-001", author="pm", comment="수정", tenant_id="t1")


def test_final_approval_chain_requires_pm_before_executive(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서")
    store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    store.approve_planning(rec.report_workflow_id, author="pm", tenant_id="t1")
    store.save_slides(rec.report_workflow_id, _slides(), tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-001", author="pm", tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-002", author="pm", tenant_id="t1")
    submitted = store.submit_final(rec.report_workflow_id, author="owner", tenant_id="t1")

    with pytest.raises(ValueError, match="PM 검토 승인 후"):
        store.approve_final_step(
            rec.report_workflow_id,
            stage="executive_review",
            author="ceo",
            tenant_id="t1",
        )

    pm_approved = store.approve_final_step(
        rec.report_workflow_id,
        stage="pm_review",
        author="pm",
        comment="실무 승인",
        tenant_id="t1",
    )
    final = store.approve_final_step(
        rec.report_workflow_id,
        stage="executive_review",
        author="ceo",
        comment="최종 승인",
        tenant_id="t1",
    )

    assert submitted.status == ReportWorkflowStatus.FINAL_REVIEW.value
    assert pm_approved.status == ReportWorkflowStatus.FINAL_REVIEW.value
    assert pm_approved.approval_steps[0].status == "approved"
    assert final.status == ReportWorkflowStatus.FINAL_APPROVED.value
    assert final.final_approved_by == "ceo"
    assert final.approval_steps[1].status == "approved"


def test_final_change_request_blocks_until_resubmitted(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서")
    store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    store.approve_planning(rec.report_workflow_id, author="pm", tenant_id="t1")
    store.save_slides(rec.report_workflow_id, _slides(), tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-001", author="pm", tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-002", author="pm", tenant_id="t1")
    store.submit_final(rec.report_workflow_id, author="owner", tenant_id="t1")

    changes = store.request_final_changes(
        rec.report_workflow_id,
        author="pm",
        comment="근거 보완",
        tenant_id="t1",
    )

    assert changes.status == ReportWorkflowStatus.FINAL_CHANGES_REQUESTED.value
    assert changes.approval_steps[0].status == "changes_requested"
    with pytest.raises(ValueError):
        store.approve_final_step(
            rec.report_workflow_id,
            stage="pm_review",
            author="pm",
            tenant_id="t1",
        )


def test_learning_artifacts_only_when_opted_in(tmp_path):
    store = _store(tmp_path)
    off = store.create(tenant_id="t1", title="off", learning_opt_in=False)
    on = store.create(tenant_id="t1", title="on", learning_opt_in=True)

    store.save_planning(off.report_workflow_id, _planning(), tenant_id="t1")
    off = store.approve_planning(off.report_workflow_id, author="pm", tenant_id="t1")
    store.save_planning(on.report_workflow_id, _planning(), tenant_id="t1")
    on = store.approve_planning(on.report_workflow_id, author="pm", tenant_id="t1")

    assert off.learning_artifacts == []
    assert on.learning_artifacts


def test_slide_change_request_updates_slide_status(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서")
    store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    store.approve_planning(rec.report_workflow_id, author="pm", tenant_id="t1")
    store.save_slides(rec.report_workflow_id, _slides(), tenant_id="t1")
    updated = store.request_slide_changes(
        rec.report_workflow_id,
        "slide-001",
        author="pm",
        comment="근거 추가",
        tenant_id="t1",
    )

    assert updated.status == ReportWorkflowStatus.SLIDES_CHANGES_REQUESTED.value
    assert updated.slides[0].status == SlideStatus.CHANGES_REQUESTED.value


def test_slide_visual_asset_metadata_updates_without_changing_approval_status(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서", learning_opt_in=True)
    store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    store.approve_planning(rec.report_workflow_id, author="pm", tenant_id="t1")
    store.save_slides(rec.report_workflow_id, _slides(), tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-001", author="pm", tenant_id="t1")

    updated = store.update_slide_visual_assets(
        rec.report_workflow_id,
        "slide-001",
        visual_prompt="스마트 교차로 관제 흐름도",
        reference_refs=["concept-board-1"],
        generated_asset_ids=["asset-1", "asset-2"],
        selected_asset_id="asset-2",
        selected_asset={"asset_id": "asset-2", "slide_title": "1장"},
        author="designer",
        tenant_id="t1",
    )

    slide = updated.slides[0]
    assert slide.status == SlideStatus.APPROVED.value
    assert slide.visual_prompt == "스마트 교차로 관제 흐름도"
    assert slide.reference_refs == ["concept-board-1"]
    assert slide.generated_asset_ids == ["asset-1", "asset-2"]
    assert slide.selected_asset_id == "asset-2"
    assert slide.selected_asset["slide_title"] == "1장"
    assert updated.learning_artifacts[-1]["kind"] == "slide_visual_asset_updated"


def test_final_approved_workflow_locks_slide_visual_asset_metadata(tmp_path):
    store = _store(tmp_path)
    rec = store.create(tenant_id="t1", title="보고서")
    store.save_planning(rec.report_workflow_id, _planning(), tenant_id="t1")
    store.approve_planning(rec.report_workflow_id, author="pm", tenant_id="t1")
    store.save_slides(rec.report_workflow_id, _slides(), tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-001", author="pm", tenant_id="t1")
    store.approve_slide(rec.report_workflow_id, "slide-002", author="pm", tenant_id="t1")
    store.submit_final(rec.report_workflow_id, author="owner", tenant_id="t1")
    store.approve_final(rec.report_workflow_id, author="ceo", tenant_id="t1")

    with pytest.raises(ValueError, match="최종 승인된"):
        store.update_slide_visual_assets(
            rec.report_workflow_id,
            "slide-001",
            visual_prompt="승인 후 변경",
            tenant_id="t1",
        )
