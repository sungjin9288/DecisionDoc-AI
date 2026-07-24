from __future__ import annotations

import base64
import hashlib
import io
import json
import zipfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.report_quality_pilot_package import (
    MAX_PACKAGE_SIZE_BYTES,
    build_pilot_review_package,
)
from app.services.report_quality_learning import (
    REQUIRED_DIMENSIONS,
    build_correction_artifact_from_snapshot,
)
from app.services.report_quality_pilot_receipt import (
    build_pilot_export_receipt,
    serialize_pilot_export_receipt,
)


_PPTX_MAGIC = b"PK\x03\x04"


def _contains_key(value, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_ATTACHMENT", "")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_VISUAL", "")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    return TestClient(create_app())


def _create_workflow(client: TestClient, **overrides):
    payload = {
        "title": "단계형 제안서",
        "goal": "PM과 대표 승인 가능한 보고서 제작",
        "client": "샘플기관",
        "audience": "PM, 대표",
        "slide_count": 3,
        "learning_opt_in": True,
    }
    payload.update(overrides)
    res = client.post("/report-workflows", json=payload)
    assert res.status_code == 200
    return res.json()


def _quality_dimension_scores(value: float = 0.86) -> dict[str, float]:
    return {
        "logic": value,
        "evidence": value,
        "audience_fit": value,
        "slide_structure": value,
        "visual_design": value,
        "public_sector_tone": value,
        "export_readiness": value,
        "learning_value": value,
    }


def _accepted_quality_correction_payload(**overrides):
    payload = {
        "username": "pm-reviewer",
        "reviewer": "pm-reviewer",
        "reviewed_at": "2026-05-15T10:00:00+09:00",
        "domain": "public_sector_ai",
        "language": "ko",
        "overall_score": 0.88,
        "dimension_scores": _quality_dimension_scores(),
        "hard_failures": [],
        "change_requests": [
            {
                "target": "slide:1",
                "issue": "문제 정의와 기대효과 연결이 약함",
                "correction": "문제-원인-해결-운영-효과 chain으로 재구성",
                "rationale": "대표/PM이 승인 근거를 빠르게 확인해야 하기 때문",
            }
        ],
        "rationale_by_dimension": {
            dimension: f"{dimension} 보강 완료"
            for dimension in _quality_dimension_scores()
        },
        "after_planning_summary": "교정 후 기획은 정책 문제, 실행 구조, 기대효과를 한 흐름으로 연결합니다.",
        "accepted_for_learning": True,
        "task_types": ["proposal_planning", "slide_message_design"],
        "skills": ["policy-planning", "evidence-gap-review"],
        "confirmed_claims": ["PM 검토 완료 구조"],
        "assumed_claims": [],
        "todo_claims": [],
        "forbidden_terms_scan": "pass",
        "privacy_security_scan": "pass",
        "human_review_status": "accepted",
    }
    payload.update(overrides)
    return payload


def _final_approve_workflow(client: TestClient, workflow_id: str) -> dict:
    planning = client.post(f"/report-workflows/{workflow_id}/planning/generate")
    assert planning.status_code == 200
    approved = client.post(
        f"/report-workflows/{workflow_id}/planning/approve",
        json={"username": "pm", "comment": ""},
    )
    assert approved.status_code == 200
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={})
    assert slides_payload.status_code == 200
    for slide in slides_payload.json()["slides"]:
        slide_approved = client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm", "comment": ""},
        )
        assert slide_approved.status_code == 200
    submitted = client.post(
        f"/report-workflows/{workflow_id}/final/submit",
        json={"username": "owner", "comment": ""},
    )
    assert submitted.status_code == 200
    pm = client.post(
        f"/report-workflows/{workflow_id}/final/pm-approve",
        json={"username": "pm", "comment": ""},
    )
    assert pm.status_code == 200
    executive = client.post(
        f"/report-workflows/{workflow_id}/final/executive-approve",
        json={"username": "ceo", "comment": ""},
    )
    assert executive.status_code == 200
    assert executive.json()["status"] == "final_approved"
    return executive.json()


def _preview_bound_quality_payload(
    client: TestClient,
    workflow_id: str,
    payload: dict,
) -> tuple[dict, dict]:
    preview = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact/preview",
        json=payload,
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    return preview_body, {
        **payload,
        "preview_fingerprint": preview_body["preview_fingerprint"],
    }


def _create_ready_quality_artifact(client: TestClient, *, title: str) -> dict:
    created = _create_workflow(
        client,
        title=title,
        slide_count=2,
        learning_opt_in=True,
    )
    workflow_id = created["report_workflow_id"]
    _final_approve_workflow(client, workflow_id)
    _, save_payload = _preview_bound_quality_payload(
        client,
        workflow_id,
        _accepted_quality_correction_payload(),
    )
    saved = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact",
        json=save_payload,
    )
    assert saved.status_code == 200
    return saved.json()


def _pilot_review_package_for_tenant(
    tenant_id: str,
    *,
    learning_ready: bool = True,
) -> bytes:
    artifacts = [
        build_correction_artifact_from_snapshot(
            {
                "tenant_id": tenant_id,
                "report_workflow_id": f"rw_external_{index}",
                "status": "final_approved",
                "export_version": 1,
                "report_type": "proposal_deck",
                "audience": "executive",
                "client": "public_sector",
                "learning": {"learning_opt_in": True},
            },
            {
                "reviewer": f"receiver-reviewer-{index}",
                "reviewed_at": "2026-07-15T09:00:00+09:00",
                "overall_score": 0.88,
                "dimension_scores": {
                    dimension: 0.86 for dimension in REQUIRED_DIMENSIONS
                },
                "change_requests": [
                    {
                        "target": "slide:1",
                        "issue": "근거와 결론의 연결이 약함",
                        "correction": "확인된 근거 다음에 결론을 배치함",
                        "rationale": "검토자가 판단 근거를 바로 확인할 수 있어야 함",
                    }
                ],
                "rationale_by_dimension": {
                    dimension: f"{dimension} 검토 완료"
                    for dimension in REQUIRED_DIMENSIONS
                },
                "before_planning_summary": f"교정 전 기획 {index}",
                "after_planning_summary": f"교정 후 기획 {index}",
                "accepted_for_learning": True,
                "confirmed_claims": ["검토된 근거"],
                "assumed_claims": [],
                "todo_claims": [],
                "forbidden_terms_scan": "pass",
                "privacy_security_scan": "pass",
                "human_review_status": "accepted",
            },
            artifact_id=f"rqa_external_{index}",
        )
        for index in range(1, 4)
    ]
    if not learning_ready:
        artifacts[1]["learning_labels"]["human_review_status"] = "pending"
    jsonl = "".join(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True) + "\n"
        for artifact in artifacts
    )
    export_sha256 = hashlib.sha256(jsonl.encode("utf-8")).hexdigest()
    preview = {
        "filename": f"report_quality_pilot_artifacts_{export_sha256[:12]}.jsonl",
        "export_sha256": export_sha256,
        "ordered_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
        "artifact_count": len(artifacts),
    }
    receipt = build_pilot_export_receipt(
        preview=preview,
        tenant_id=tenant_id,
        request_id="external-package-request-01",
    )
    package, _ = build_pilot_review_package(
        jsonl=jsonl,
        receipt_bytes=serialize_pilot_export_receipt(receipt),
        preview=preview,
        tenant_id=tenant_id,
    )
    return package


def test_report_workflow_crud_and_tenant_boundary(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client)

    listed = client.get("/report-workflows")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    detail = client.get(f"/report-workflows/{created['report_workflow_id']}")
    assert detail.status_code == 200
    assert detail.json()["title"] == "단계형 제안서"

    other_tenant = client.get(
        f"/report-workflows/{created['report_workflow_id']}",
        headers={"X-Tenant-ID": "other"},
    )
    assert other_tenant.status_code == 403


def test_report_workflow_create_persists_approval_assignees(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(
        client,
        owner="owner",
        pm_reviewer="pm-user",
        executive_approver="ceo-user",
        slide_count=2,
    )
    workflow_id = created["report_workflow_id"]

    assert created["owner"] == "owner"
    assert created["pm_reviewer"] == "pm-user"
    assert created["executive_approver"] == "ceo-user"

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm-user", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()
    for slide in slides_payload["slides"]:
        client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm-user", "comment": ""},
        )
    submitted = client.post(
        f"/report-workflows/{workflow_id}/final/submit",
        json={"username": "owner", "comment": ""},
    )

    assert submitted.status_code == 200
    body = submitted.json()
    assert body["approval_steps"][0]["assignee"] == "pm-user"
    assert body["approval_steps"][1]["assignee"] == "ceo-user"
    linked_approval = client.get(f"/approvals/{body['final_approval_id']}").json()
    assert linked_approval["reviewer"] == "pm-user"
    assert linked_approval["approver"] == "ceo-user"
    assert linked_approval["gov_options"]["pm_reviewer"] == "pm-user"
    assert linked_approval["gov_options"]["executive_approver"] == "ceo-user"


def test_planning_and_slides_generation_with_mock_provider(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=4)
    workflow_id = created["report_workflow_id"]

    blocked = client.post(f"/report-workflows/{workflow_id}/slides/generate")
    assert blocked.status_code == 400

    planning = client.post(f"/report-workflows/{workflow_id}/planning/generate")
    assert planning.status_code == 200
    assert planning.json()["status"] == "planning_draft"
    planning_payload = planning.json()["planning"]
    assert len(planning_payload["slide_plans"]) == 4
    assert planning_payload["planning_brief"]
    assert planning_payload["audience_decision_needs"]
    assert planning_payload["narrative_arc"]
    assert planning_payload["source_strategy"]
    assert planning_payload["template_guidance"]
    assert planning_payload["quality_bar"]
    assert planning_payload["slide_plans"][0]["decision_question"]
    assert planning_payload["slide_plans"][0]["content_blocks"]
    assert planning_payload["slide_plans"][0]["acceptance_criteria"]

    approved = client.post(
        f"/report-workflows/{workflow_id}/planning/approve",
        json={"username": "pm", "comment": "승인"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "planning_approved"

    slides = client.post(f"/report-workflows/{workflow_id}/slides/generate")
    assert slides.status_code == 200
    assert slides.json()["status"] == "slides_draft"
    assert len(slides.json()["slides"]) == 4


def test_slide_approval_final_approval_and_pptx_export(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()

    early_final = client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "pm", "comment": ""})
    assert early_final.status_code == 400

    for slide in slides_payload["slides"]:
        res = client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm", "comment": ""},
        )
        assert res.status_code == 200

    final_submit = client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "pm", "comment": ""})
    assert final_submit.status_code == 200
    assert [step["stage"] for step in final_submit.json()["approval_steps"]] == ["pm_review", "executive_review"]
    assert final_submit.json()["final_approval_id"]
    assert final_submit.json()["final_approval_status"] == "in_review"
    approval = client.get(f"/approvals/{final_submit.json()['final_approval_id']}")
    assert approval.status_code == 200
    assert approval.json()["bundle_id"] == "report_workflow"
    assert approval.json()["status"] == "in_review"
    final_approve = client.post(f"/report-workflows/{workflow_id}/final/approve", json={"username": "ceo", "comment": ""})
    assert final_approve.status_code == 200
    assert final_approve.json()["status"] == "final_approved"
    assert final_approve.json()["final_approval_status"] == "approved"
    assert final_approve.json()["learning_artifacts"]

    pptx = client.get(f"/report-workflows/{workflow_id}/export/pptx")
    assert pptx.status_code == 200
    assert pptx.content[:4] == _PPTX_MAGIC

    snapshot = client.get(f"/report-workflows/{workflow_id}/export/snapshot")
    assert snapshot.status_code == 200
    assert snapshot.headers["content-type"].startswith("application/json")
    assert "report_workflow_snapshot" in snapshot.headers.get("content-disposition", "")
    snapshot_payload = snapshot.json()
    assert snapshot_payload["export_version"] == "decisiondoc_report_workflow_snapshot.v1"
    assert snapshot_payload["report_workflow_id"] == workflow_id
    assert snapshot_payload["approval"]["final_approval_status"] == "approved"
    assert snapshot_payload["slide_outline"][0]["decision_question"]
    assert snapshot_payload["slide_outline"][0]["acceptance_criteria"]
    assert snapshot_payload["promotion"]["project_document_id"] is None


def test_report_quality_correction_artifact_preview_and_save(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2, learning_opt_in=True)
    workflow_id = created["report_workflow_id"]
    _final_approve_workflow(client, workflow_id)

    payload = _accepted_quality_correction_payload()
    preview = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact/preview",
        json=payload,
    )

    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["persisted"] is False
    assert preview_body["validation"]["ok"] is True
    assert preview_body["validation"]["ready_for_learning"] is True
    artifact = preview_body["artifact"]
    assert artifact["workflow_reference"]["workflow_status"] == "final_approved"
    assert artifact["workflow_reference"]["learning_opt_in"] is True
    assert artifact["workflow_reference"]["source_material_policy"] == "metadata_only"
    assert artifact["training_boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert _contains_key(artifact, "content_base64") is False
    assert _contains_key(artifact, "api_key") is False
    assert len(preview_body["preview_fingerprint"]) == 64

    payload["preview_fingerprint"] = preview_body["preview_fingerprint"]

    saved = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact",
        json=payload,
    )

    assert saved.status_code == 200
    saved_body = saved.json()
    assert saved_body["persisted"] is True
    assert saved_body["validation"]["ready_for_learning"] is True
    assert saved_body["artifact"] == preview_body["artifact"]
    assert saved_body["preview_fingerprint"] == preview_body["preview_fingerprint"]
    stored_artifact = saved_body["report_workflow"]["learning_artifacts"][-1]
    assert stored_artifact["kind"] == "report_quality_correction_accepted"
    assert stored_artifact["payload"]["validation"]["artifact_id"] == saved_body["artifact"]["artifact_id"]
    assert stored_artifact["payload"]["preview_fingerprint"] == preview_body["preview_fingerprint"]
    assert _contains_key(stored_artifact, "content_base64") is False

    duplicate = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact",
        json=payload,
    )
    assert duplicate.status_code == 400
    assert "already been saved" in duplicate.json()["detail"]


def test_report_quality_correction_save_requires_current_preview(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2, learning_opt_in=True)
    workflow_id = created["report_workflow_id"]
    _final_approve_workflow(client, workflow_id)
    payload = _accepted_quality_correction_payload()

    missing_preview = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact",
        json=payload,
    )
    assert missing_preview.status_code == 400
    assert "preview_fingerprint is required" in missing_preview.json()["detail"]

    preview_body, preview_bound_payload = _preview_bound_quality_payload(
        client,
        workflow_id,
        payload,
    )
    preview_bound_payload["after_planning_summary"] = "preview 이후 변경된 교정 결과"
    stale_preview = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact",
        json=preview_bound_payload,
    )

    assert stale_preview.status_code == 400
    assert "preview again" in stale_preview.json()["detail"]
    refreshed_preview, _ = _preview_bound_quality_payload(
        client,
        workflow_id,
        preview_bound_payload,
    )
    assert refreshed_preview["preview_fingerprint"] != preview_body["preview_fingerprint"]
    assert refreshed_preview["artifact"]["artifact_id"] != preview_body["artifact"]["artifact_id"]


def test_report_quality_correction_preview_rejects_empty_dimension_rationale(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2, learning_opt_in=True)
    workflow_id = created["report_workflow_id"]
    _final_approve_workflow(client, workflow_id)
    payload = _accepted_quality_correction_payload()
    payload["rationale_by_dimension"]["visual_design"] = ""

    response = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact/preview",
        json=payload,
    )

    assert response.status_code == 200
    validation = response.json()["validation"]
    assert validation["ok"] is False
    assert validation["ready_for_learning"] is False
    assert "rationale_by_dimension.visual_design must be non-empty" in "\n".join(validation["errors"])


def test_report_workflow_develop_quality_preview_runs_document_ops_agent(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2, source_refs=["source-report"])
    workflow_id = created["report_workflow_id"]
    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={})
    assert slides.status_code == 200

    preview = client.post(
        f"/report-workflows/{workflow_id}/develop-quality/preview",
        json={
            "username": "pm-reviewer",
            "focus": "대표 승인 전 보고서 품질 개선",
            "additional_notes": "논리와 근거 구분을 먼저 확인",
            "capture_trajectory": False,
        },
    )

    assert preview.status_code == 200
    body = preview.json()
    assert body["report_type"] == "report_workflow_develop_quality_preview"
    assert body["persisted"] is False
    assert body["report_workflow"]["report_workflow_id"] == workflow_id
    assert body["document_ops_request"]["task_type"] == "develop_quality_improvement"
    assert body["document_ops_request"]["skill_name"] == "develop-document-improver"
    assert body["document_ops_request"]["source_reference_count"] >= 3
    result = body["develop_result"]
    assert result["skill_name"] == "develop-document-improver"
    assert result["task_type"] == "develop_quality_improvement"
    assert result["critique"]
    assert result["revision_tasks"]
    assert result["qa"]["hard_gate_pass"] is True
    assert result["trajectory_saved"] is False
    assert body["training_boundary"]["provider_fine_tune_api_call_authorized"] is False


def test_report_quality_correction_artifact_summary_and_jsonl_export(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2, learning_opt_in=True)
    workflow_id = created["report_workflow_id"]
    _final_approve_workflow(client, workflow_id)

    _, save_payload = _preview_bound_quality_payload(
        client,
        workflow_id,
        _accepted_quality_correction_payload(),
    )
    saved = client.post(
        f"/report-workflows/{workflow_id}/learning/correction-artifact",
        json=save_payload,
    )
    assert saved.status_code == 200

    summary = client.get("/report-workflows/learning/correction-artifacts")
    assert summary.status_code == 200
    body = summary.json()
    assert body["report_type"] == "report_quality_correction_artifact_summary"
    assert body["total_artifacts"] == 1
    assert body["ready_artifacts"] == 1
    assert body["not_ready_artifacts"] == 0
    assert body["returned"] == 1
    assert body["training_boundary"]["provider_fine_tune_api_call_authorized"] is False
    item = body["artifacts"][0]
    assert item["report_workflow_id"] == workflow_id
    assert item["workflow_title"] == "단계형 제안서"
    assert item["client"] == "샘플기관"
    assert item["ready_for_learning"] is True
    assert item["validation_ok"] is True
    assert item["overall_score"] == 0.88
    assert item["task_types"] == ["proposal_planning", "slide_message_design"]
    assert "artifact" not in item

    detail = client.get(
        f"/report-workflows/learning/correction-artifacts/{item['artifact_id']}"
    )
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["report_type"] == "report_quality_correction_artifact_detail"
    assert detail_body["artifact_id"] == item["artifact_id"]
    assert detail_body["store_artifact_id"] == item["store_artifact_id"]
    assert detail_body["report_workflow_id"] == workflow_id
    assert detail_body["artifact"]["workflow_reference"]["source_material_policy"] == "metadata_only"
    assert detail_body["validation"]["ready_for_learning"] is True
    assert len(detail_body["preview_fingerprint"]) == 64
    assert detail_body["training_boundary"]["external_dataset_upload_authorized"] is False
    assert detail_body["training_boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert detail_body["training_boundary"]["training_execution_authorized"] is False
    assert _contains_key(detail_body, "content_base64") is False
    assert _contains_key(detail_body, "api_key") is False

    detail_by_store_id = client.get(
        f"/report-workflows/learning/correction-artifacts/{item['store_artifact_id']}"
    )
    assert detail_by_store_id.status_code == 200
    assert detail_by_store_id.json()["artifact_id"] == item["artifact_id"]

    with pytest.raises(KeyError, match="quality correction artifact not found"):
        client.app.state.report_workflow_service.get_quality_correction_artifact(
            item["artifact_id"],
            tenant_id="other",
        )

    missing_detail = client.get(
        "/report-workflows/learning/correction-artifacts/rqc_missing"
    )
    assert missing_detail.status_code == 404
    assert "quality correction artifact not found" in missing_detail.json()["detail"]

    other_tenant = client.get(
        "/report-workflows/learning/correction-artifacts",
        headers={"X-Tenant-ID": "other"},
    )
    assert other_tenant.status_code == 403

    exported = client.get("/report-workflows/learning/correction-artifacts/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in exported.text.splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["schema_version"] == "decisiondoc_report_quality_correction_artifact.v1"
    assert lines[0]["workflow_reference"]["report_workflow_id"] == workflow_id
    assert lines[0]["workflow_reference"]["source_material_policy"] == "metadata_only"
    assert lines[0]["training_boundary"]["training_execution_authorized"] is False


def test_report_quality_correction_artifact_summary_paginates_ready_pool(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    saved_artifacts = [
        _create_ready_quality_artifact(client, title=f"파일럿 탐색 {index}")
        for index in range(1, 5)
    ]
    saved_ids = {item["artifact"]["artifact_id"] for item in saved_artifacts}

    first_page = client.get(
        "/report-workflows/learning/correction-artifacts?ready_only=true&offset=0&limit=2"
    )
    second_page = client.get(
        "/report-workflows/learning/correction-artifacts?ready_only=true&offset=2&limit=2"
    )
    past_end = client.get(
        "/report-workflows/learning/correction-artifacts?ready_only=true&offset=4&limit=2"
    )

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert past_end.status_code == 200
    first_body = first_page.json()
    second_body = second_page.json()
    past_end_body = past_end.json()
    assert first_body["offset"] == 0
    assert first_body["limit"] == 2
    assert first_body["filtered_total"] == 4
    assert first_body["returned"] == 2
    assert first_body["has_more"] is True
    assert second_body["offset"] == 2
    assert second_body["filtered_total"] == 4
    assert second_body["returned"] == 2
    assert second_body["has_more"] is False
    page_ids = {
        item["artifact_id"]
        for item in [*first_body["artifacts"], *second_body["artifacts"]]
    }
    assert page_ids == saved_ids
    assert past_end_body["offset"] == 4
    assert past_end_body["returned"] == 0
    assert past_end_body["has_more"] is False
    assert client.get(
        "/report-workflows/learning/correction-artifacts?offset=-1"
    ).status_code == 422


def test_report_quality_pilot_export_requires_three_to_five_unique_ready_artifacts(
    tmp_path,
    monkeypatch,
):
    client = _create_client(tmp_path, monkeypatch)
    saved_artifacts = [
        _create_ready_quality_artifact(client, title=f"파일럿 품질 검토 {index}")
        for index in range(1, 4)
    ]
    artifact_ids = [item["artifact"]["artifact_id"] for item in saved_artifacts]

    too_small = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export",
        json={"artifact_ids": artifact_ids[:2]},
    )
    assert too_small.status_code == 422

    duplicate = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export",
        json={"artifact_ids": [artifact_ids[0], artifact_ids[0], artifact_ids[1]]},
    )
    assert duplicate.status_code == 422

    requested_order = list(reversed(artifact_ids))
    preview = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export/preview",
        json={"artifact_ids": requested_order},
    )
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["report_type"] == "report_quality_correction_pilot_export_preview"
    assert preview_body["artifact_count"] == 3
    assert preview_body["ordered_artifact_ids"] == requested_order
    assert preview_body["validation"] == {
        "ok": True,
        "resolved_artifact_count": 3,
        "ready_artifact_count": 3,
    }
    assert [item["position"] for item in preview_body["artifacts"]] == [1, 2, 3]
    assert [item["artifact_id"] for item in preview_body["artifacts"]] == requested_order
    assert all(item["ready_for_learning"] is True for item in preview_body["artifacts"])
    assert all(item["source_material_policy"] == "metadata_only" for item in preview_body["artifacts"])
    assert preview_body["training_boundary"]["external_dataset_upload_authorized"] is False
    assert preview_body["training_boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert preview_body["training_boundary"]["training_execution_authorized"] is False
    assert preview_body["training_boundary"]["model_promotion_authorized"] is False
    assert _contains_key(preview_body, "content_base64") is False

    unconfirmed = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export",
        json={"artifact_ids": requested_order},
    )
    assert unconfirmed.status_code == 422
    assert "preview_sha256" in unconfirmed.text

    stale_preview = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export",
        json={"artifact_ids": requested_order, "preview_sha256": "0" * 64},
    )
    assert stale_preview.status_code == 400
    assert "preview_sha256 does not match" in stale_preview.json()["detail"]

    exported = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export",
        json={
            "artifact_ids": requested_order,
            "preview_sha256": preview_body["export_sha256"],
        },
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/x-ndjson")
    assert exported.headers["x-decisiondoc-pilot-artifact-count"] == "3"
    assert exported.headers["x-decisiondoc-pilot-preview-verified"] == "true"
    assert exported.headers["x-decisiondoc-training-authorized"] == "false"
    body_sha256 = hashlib.sha256(exported.content).hexdigest()
    assert exported.headers["x-decisiondoc-pilot-sha256"] == body_sha256
    assert preview_body["export_sha256"] == body_sha256
    encoded_receipt = exported.headers["x-decisiondoc-pilot-receipt"]
    encoded_receipt += "=" * (-len(encoded_receipt) % 4)
    receipt_bytes = base64.urlsafe_b64decode(encoded_receipt)
    receipt = json.loads(receipt_bytes)
    assert exported.headers["x-decisiondoc-pilot-receipt-sha256"] == hashlib.sha256(
        receipt_bytes
    ).hexdigest()
    assert receipt["schema_version"] == "decisiondoc_report_quality_pilot_export_receipt.v1"
    assert receipt["request_id"] == exported.headers["x-request-id"]
    assert receipt["tenant_id"] == "system"
    assert receipt["export"]["sha256"] == body_sha256
    assert receipt["export"]["ordered_artifact_ids"] == requested_order
    assert receipt["preview"] == {"sha256": body_sha256, "verified": True}
    assert all(value is False for value in receipt["external_action_boundary"].values())
    assert preview_body["filename"] == f"report_quality_pilot_artifacts_{body_sha256[:12]}.jsonl"
    assert (
        f'report_quality_pilot_artifacts_{body_sha256[:12]}.jsonl'
        in exported.headers["content-disposition"]
    )
    lines = [json.loads(line) for line in exported.text.splitlines() if line.strip()]
    assert [item["artifact_id"] for item in lines] == requested_order
    assert all(item["training_boundary"]["training_execution_authorized"] is False for item in lines)
    assert all(_contains_key(item, "content_base64") is False for item in lines)

    packaged = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export/package",
        json={
            "artifact_ids": requested_order,
            "preview_sha256": preview_body["export_sha256"],
        },
    )
    assert packaged.status_code == 200
    assert packaged.headers["content-type"] == "application/zip"
    assert packaged.headers["x-decisiondoc-pilot-sha256"] == body_sha256
    assert packaged.headers["x-decisiondoc-pilot-preview-verified"] == "true"
    assert packaged.headers["x-decisiondoc-training-authorized"] == "false"
    assert packaged.headers["x-decisiondoc-pilot-package-sha256"] == hashlib.sha256(
        packaged.content
    ).hexdigest()
    with zipfile.ZipFile(io.BytesIO(packaged.content)) as archive:
        manifest = json.loads(archive.read("pilot_package_manifest.json"))
        assert manifest["ordered_artifact_ids"] == requested_order
        assert manifest["export_sha256"] == body_sha256
        assert manifest["request_id"] == packaged.headers["x-request-id"]
        assert all(
            value is False
            for value in manifest["external_action_boundary"].values()
        )
        assert preview_body["filename"] in archive.namelist()
        assert f"report_quality_pilot_receipt_{body_sha256[:12]}.json" in archive.namelist()

    workflow_state_before_verification = client.get("/report-workflows").json()
    verified = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-package/verify",
        files={"file": ("received-pilot-package.zip", packaged.content, "application/zip")},
    )
    assert verified.status_code == 200
    verification = verified.json()
    assert verification["report_type"] == "report_quality_pilot_review_package_verification"
    assert verification["status"] == "verified"
    assert verification["package_sha256"] == hashlib.sha256(packaged.content).hexdigest()
    assert verification["package_size_bytes"] == len(packaged.content)
    assert verification["tenant_id"] == "system"
    assert verification["artifact_count"] == 3
    assert verification["ordered_artifact_ids"] == requested_order
    assert verification["export_sha256"] == body_sha256
    assert len(verification["entries"]) == 2
    assert verification["review_readiness"] == {
        "all_ready": True,
        "ready_artifact_count": 3,
        "blocked_artifact_count": 0,
    }
    assert [item["artifact_id"] for item in verification["artifacts"]] == requested_order
    assert all(item["ready_for_learning"] is True for item in verification["artifacts"])
    assert all(item["validation_ok"] is True for item in verification["artifacts"])
    assert all(item["reviewer"] == "pm-reviewer" for item in verification["artifacts"])
    assert "외부 실행 승인이 아닙니다" in verification["operator_summary"]
    assert "사람 검토 결정" in verification["next_review_action"]
    assert all(verification["validation"].values())
    assert all(
        value is False
        for value in verification["external_action_boundary"].values()
    )
    assert verification["persisted"] is False
    assert client.get("/report-workflows").json() == workflow_state_before_verification

    from app.storage.audit_store import AuditStore

    preview_audits = AuditStore("system").query(
        filters={"action": "report_quality.pilot_preview", "result": "success"},
    )
    assert preview_audits
    assert preview_audits[0]["detail"]["pilot_sha256"] == preview_body["export_sha256"]
    assert preview_audits[0]["detail"]["pilot_artifact_count"] == 3
    assert preview_audits[0]["detail"]["pilot_preview_verified"] is False

    export_audits = AuditStore("system").query(
        filters={"action": "report_quality.pilot_export", "result": "success"},
    )
    assert export_audits
    assert export_audits[0]["detail"]["pilot_sha256"] == body_sha256
    assert export_audits[0]["detail"]["request_id"] == receipt["request_id"]
    assert export_audits[0]["detail"]["pilot_artifact_count"] == 3
    assert export_audits[0]["detail"]["pilot_preview_verified"] is True

    package_audits = AuditStore("system").query(
        filters={"action": "report_quality.pilot_package", "result": "success"},
    )
    assert package_audits
    assert package_audits[0]["detail"]["pilot_sha256"] == body_sha256
    assert package_audits[0]["detail"]["pilot_artifact_count"] == 3
    assert package_audits[0]["detail"]["pilot_preview_verified"] is True

    package_verification_audits = AuditStore("system").query(
        filters={"action": "report_quality.pilot_package_verify", "result": "success"},
    )
    assert package_verification_audits
    assert package_verification_audits[0]["detail"]["pilot_sha256"] == body_sha256
    assert (
        package_verification_audits[0]["detail"]["pilot_package_sha256"]
        == verification["package_sha256"]
    )
    assert package_verification_audits[0]["detail"]["pilot_artifact_count"] == 3
    assert package_verification_audits[0]["detail"]["pilot_preview_verified"] is True
    assert (
        package_verification_audits[0]["detail"]["pilot_artifact_semantics_verified"]
        is True
    )

    first_wrapper_id = saved_artifacts[0]["report_workflow"]["learning_artifacts"][-1]["artifact_id"]
    alias_duplicate = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export/preview",
        json={"artifact_ids": [artifact_ids[0], first_wrapper_id, artifact_ids[1]]},
    )
    assert alias_duplicate.status_code == 400
    assert "resolve to unique artifacts" in alias_duplicate.json()["detail"]

    missing = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-export/preview",
        json={"artifact_ids": [artifact_ids[0], artifact_ids[1], "rqa_missing"]},
    )
    assert missing.status_code == 404
    assert "quality correction artifact not found" in missing.json()["detail"]


def test_report_quality_pilot_package_verification_rejects_tamper_cross_tenant_and_oversize(
    tmp_path,
    monkeypatch,
):
    client = _create_client(tmp_path, monkeypatch)
    package = _pilot_review_package_for_tenant("system")

    tampered = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(package)) as source, zipfile.ZipFile(tampered, "w") as target:
        for name in source.namelist():
            content = source.read(name)
            if name.endswith(".jsonl"):
                content += b"{}\n"
            target.writestr(name, content)
    tampered_result = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-package/verify",
        files={"file": ("tampered.zip", tampered.getvalue(), "application/zip")},
    )
    assert tampered_result.status_code == 400
    assert "SHA-256 mismatch" in tampered_result.json()["detail"]

    not_ready_package = _pilot_review_package_for_tenant(
        "system",
        learning_ready=False,
    )
    not_ready_result = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-package/verify",
        files={"file": ("not-ready.zip", not_ready_package, "application/zip")},
    )
    assert not_ready_result.status_code == 400
    assert "artifact is not learning-ready" in not_ready_result.json()["detail"]

    cross_tenant_package = _pilot_review_package_for_tenant("other-tenant")
    cross_tenant_result = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-package/verify",
        files={
            "file": (
                "other-tenant.zip",
                cross_tenant_package,
                "application/zip",
            )
        },
    )
    assert cross_tenant_result.status_code == 403
    assert "tenant does not match" in cross_tenant_result.json()["detail"]

    oversized_result = client.post(
        "/report-workflows/learning/correction-artifacts/pilot-package/verify",
        files={
            "file": (
                "oversized.zip",
                b"x" * (MAX_PACKAGE_SIZE_BYTES + 1),
                "application/zip",
            )
        },
    )
    assert oversized_result.status_code == 413
    assert oversized_result.json()["detail"] == "pilot review package is too large"

    from app.storage.audit_store import AuditStore

    failed_audits = AuditStore("system").query(
        filters={"action": "report_quality.pilot_package_verify", "result": "failure"},
    )
    blocked_audits = AuditStore("system").query(
        filters={"action": "access.blocked", "result": "blocked"},
    )
    assert len(failed_audits) == 3
    assert all(
        item["detail"]["pilot_artifact_semantics_verified"] is False
        for item in failed_audits
    )
    assert len(blocked_audits) == 1
    assert blocked_audits[0]["detail"]["status_code"] == 403
    assert blocked_audits[0]["detail"]["path"].endswith("/pilot-package/verify")
    assert blocked_audits[0]["detail"]["pilot_package_sha256"] == hashlib.sha256(
        cross_tenant_package
    ).hexdigest()
    assert blocked_audits[0]["detail"]["pilot_artifact_count"] == 3
    assert blocked_audits[0]["detail"]["pilot_artifact_semantics_verified"] is True


def test_report_quality_correction_artifact_requires_final_approved_opt_in(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    not_final = _create_workflow(client, slide_count=2, learning_opt_in=True)
    not_final_id = not_final["report_workflow_id"]
    client.post(f"/report-workflows/{not_final_id}/planning/generate")
    client.post(f"/report-workflows/{not_final_id}/planning/approve", json={"username": "pm", "comment": ""})
    client.post(f"/report-workflows/{not_final_id}/slides/generate", json={})

    _, status_payload = _preview_bound_quality_payload(
        client,
        not_final_id,
        _accepted_quality_correction_payload(),
    )
    blocked_by_status = client.post(
        f"/report-workflows/{not_final_id}/learning/correction-artifact",
        json=status_payload,
    )

    assert blocked_by_status.status_code == 400
    assert "workflow_status=final_approved" in blocked_by_status.json()["detail"]

    no_opt_in = _create_workflow(client, slide_count=2, learning_opt_in=False)
    no_opt_in_id = no_opt_in["report_workflow_id"]
    _final_approve_workflow(client, no_opt_in_id)
    _, opt_in_payload = _preview_bound_quality_payload(
        client,
        no_opt_in_id,
        _accepted_quality_correction_payload(),
    )
    blocked_by_opt_in = client.post(
        f"/report-workflows/{no_opt_in_id}/learning/correction-artifact",
        json=opt_in_payload,
    )

    assert blocked_by_opt_in.status_code == 400
    assert "learning_opt_in=true" in blocked_by_opt_in.json()["detail"]


def test_slide_visual_asset_metadata_api_and_pptx_export_adapter(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()
    slide = slides_payload["slides"][0]

    selected_asset = {
        "asset_id": "asset-rw-1",
        "doc_type": "report_workflow",
        "slide_title": slide["title"],
        "visual_type": "concept diagram",
        "visual_brief": "교통 안전 AI 관제 흐름도",
        "layout_hint": "right visual panel",
        "source_kind": "provider_image",
        "source_model": "test-model",
        "prompt": "스마트 교차로 관제 흐름도",
        "media_type": "image/png",
        "encoding": "base64",
        "content_base64": "iVBORw0KGgo=",
    }
    updated = client.put(
        f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/visual-assets",
        json={
            "username": "designer",
            "visual_prompt": "스마트 교차로 관제 흐름도",
            "reference_refs": ["uploaded-concept.png"],
            "generated_asset_ids": ["asset-rw-1"],
            "selected_asset_id": "asset-rw-1",
            "selected_asset": selected_asset,
        },
    )

    assert updated.status_code == 200
    updated_slide = updated.json()["slides"][0]
    assert updated_slide["visual_prompt"] == "스마트 교차로 관제 흐름도"
    assert updated_slide["reference_refs"] == ["uploaded-concept.png"]
    assert updated_slide["generated_asset_ids"] == ["asset-rw-1"]
    assert updated_slide["selected_asset_id"] == "asset-rw-1"
    assert updated_slide["selected_asset"]["asset_id"] == "asset-rw-1"
    assert updated_slide["status"] == slide["status"]

    captured = {}

    def _fake_build_pptx(slide_data, title, *, include_outline_overview=False, visual_assets=None):
        captured["slide_data"] = slide_data
        captured["title"] = title
        captured["include_outline_overview"] = include_outline_overview
        captured["visual_assets"] = visual_assets
        return _PPTX_MAGIC + b"fake"

    with patch("app.services.report_workflow_service.build_pptx", side_effect=_fake_build_pptx):
        pptx = client.get(f"/report-workflows/{workflow_id}/export/pptx")

    assert pptx.status_code == 200
    assert pptx.content[:4] == _PPTX_MAGIC
    assert captured["visual_assets"][0]["asset_id"] == "asset-rw-1"
    first_outline = captured["slide_data"]["slide_outline"][0]
    assert first_outline["visual"] == "스마트 교차로 관제 흐름도"
    assert first_outline["core_message"]
    assert first_outline["decision_question"]
    assert first_outline["acceptance_criteria"]
    assert "content_blocks" in first_outline
    assert "data_needs" in first_outline
    assert first_outline["narrative_role"]
    assert first_outline["layout_hint"]
    assert first_outline["evidence_points"]
    assert "Editable PPTX" in first_outline["design_tip"]
    assert "선택 시각자료 ID: asset-rw-1" in first_outline["design_tip"]

    snapshot = client.get(f"/report-workflows/{workflow_id}/export/snapshot")
    assert snapshot.status_code == 200
    snapshot_payload = snapshot.json()
    assert snapshot_payload["visual_assets"][0]["asset_id"] == "asset-rw-1"
    assert snapshot_payload["visual_assets"][0]["has_content_base64"] is True
    assert snapshot_payload["visual_assets"][0]["content_base64_len"] > 0
    assert "content_base64" not in snapshot_payload["visual_assets"][0]
    assert snapshot_payload["slides"][0]["selected_asset"]["has_content_base64"] is True
    assert _contains_key(snapshot_payload, "content_base64") is False


def test_report_workflow_generates_visual_assets_and_attaches_first_candidates(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()

    generated = client.post(
        f"/report-workflows/{workflow_id}/visual-assets/generate",
        json={"username": "designer", "max_assets": 2, "select_first": False},
    )

    assert generated.status_code == 200
    body = generated.json()
    assert body["count"] == 2
    assert len(body["assets"]) == 2
    assert len(body["report_workflow"]["visual_assets"]) == 2
    updated_slides = body["report_workflow"]["slides"]
    assert updated_slides[0]["generated_asset_ids"]
    assert updated_slides[0]["selected_asset_id"] == ""
    assert updated_slides[0]["status"] == slides_payload["slides"][0]["status"]

    selected = client.post(
        f"/report-workflows/{workflow_id}/slides/{updated_slides[0]['slide_id']}/visual-assets/select",
        json={"username": "designer", "asset_id": updated_slides[0]["generated_asset_ids"][0]},
    )
    assert selected.status_code == 200
    selected_slide = selected.json()["slides"][0]
    assert selected_slide["selected_asset_id"] == updated_slides[0]["generated_asset_ids"][0]
    assert selected_slide["selected_asset"]["asset_id"] == selected_slide["selected_asset_id"]


def test_report_workflow_list_redacts_visual_asset_payloads(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    client.post(f"/report-workflows/{workflow_id}/slides/generate", json={})
    generated = client.post(
        f"/report-workflows/{workflow_id}/visual-assets/generate",
        json={"username": "designer", "max_assets": 2, "select_first": True},
    )
    assert generated.status_code == 200

    detail = client.get(f"/report-workflows/{workflow_id}")
    assert detail.status_code == 200
    assert _contains_key(detail.json(), "content_base64") is True

    listed = client.get("/report-workflows")
    assert listed.status_code == 200
    item = listed.json()["report_workflows"][0]
    assert item["visual_asset_count"] == 2
    assert _contains_key(item, "content_base64") is False
    assert _contains_key(item, "content_base64_len") is True
    assert _contains_key(item, "has_content_base64") is True


def test_slide_visual_asset_metadata_api_respects_final_approval_lock(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()
    for slide in slides_payload["slides"]:
        client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm", "comment": ""},
        )
    client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "owner", "comment": ""})
    client.post(f"/report-workflows/{workflow_id}/final/approve", json={"username": "ceo", "comment": ""})

    blocked = client.put(
        f"/report-workflows/{workflow_id}/slides/{slides_payload['slides'][0]['slide_id']}/visual-assets",
        json={"visual_prompt": "승인 후 변경"},
    )

    assert blocked.status_code == 400
    assert "최종 승인된" in blocked.json()["detail"]


def test_report_workflow_visual_asset_generation_respects_final_approval_lock(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()
    for slide in slides_payload["slides"]:
        client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm", "comment": ""},
        )
    client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "owner", "comment": ""})
    client.post(f"/report-workflows/{workflow_id}/final/approve", json={"username": "ceo", "comment": ""})

    blocked = client.post(
        f"/report-workflows/{workflow_id}/visual-assets/generate",
        json={"max_assets": 2},
    )

    assert blocked.status_code == 400
    assert "최종 승인된" in blocked.json()["detail"]


def test_pm_and_executive_final_approval_chain_api(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()
    for slide in slides_payload["slides"]:
        client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm", "comment": ""},
        )
    client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "owner", "comment": ""})

    blocked = client.post(
        f"/report-workflows/{workflow_id}/final/executive-approve",
        json={"username": "ceo", "comment": ""},
    )
    assert blocked.status_code == 400

    pm = client.post(
        f"/report-workflows/{workflow_id}/final/pm-approve",
        json={"username": "pm", "comment": "실무 승인"},
    )
    assert pm.status_code == 200
    assert pm.json()["status"] == "final_review"
    assert pm.json()["approval_steps"][0]["status"] == "approved"
    linked_approval = client.get(f"/approvals/{pm.json()['final_approval_id']}").json()
    assert linked_approval["reviewer_approved"] is True
    assert linked_approval["status"] == "in_review"

    executive = client.post(
        f"/report-workflows/{workflow_id}/final/executive-approve",
        json={"username": "ceo", "comment": "대표 승인"},
    )
    assert executive.status_code == 200
    assert executive.json()["status"] == "final_approved"
    assert executive.json()["approval_steps"][1]["status"] == "approved"
    assert executive.json()["final_approval_status"] == "approved"
    linked_approval = client.get(f"/approvals/{executive.json()['final_approval_id']}").json()
    assert linked_approval["status"] == "approved"


def test_final_approved_workflow_promotes_to_project_and_knowledge(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    project = client.post(
        "/projects",
        json={"name": "워크플로우 산출물", "client": "샘플기관", "description": "승인본 저장소"},
    ).json()
    created = _create_workflow(client, slide_count=2, learning_opt_in=True)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()
    requirement_ref = "requirement:decision-1:hard_filter:registration"
    first_slide = slides_payload["slides"][0]
    client.put(
        f"/report-workflows/{workflow_id}/slides/{first_slide['slide_id']}/visual-assets",
        json={
            "username": "designer",
            "reference_refs": [requirement_ref],
        },
    )
    for slide in slides_payload["slides"]:
        client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm", "comment": ""},
        )
    client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "owner", "comment": ""})
    client.post(f"/report-workflows/{workflow_id}/final/pm-approve", json={"username": "pm", "comment": ""})
    client.post(f"/report-workflows/{workflow_id}/final/executive-approve", json={"username": "ceo", "comment": ""})

    promoted = client.post(
        f"/report-workflows/{workflow_id}/promote",
        json={
            "project_id": project["project_id"],
            "promote_to_knowledge": True,
            "tags": ["승인본"],
            "quality_tier": "gold",
            "success_state": "approved",
        },
    )

    assert promoted.status_code == 200
    body = promoted.json()
    assert body["project_id"] == project["project_id"]
    assert body["project_document_id"]
    assert body["knowledge_project_id"] == project["project_id"]
    assert body["knowledge_document_count"] == 2
    assert {doc["doc_type"] for doc in body["knowledge_documents"]} == {
        "report_workflow_planning",
        "report_workflow_slides",
    }

    project_detail = client.get(f"/projects/{project['project_id']}").json()
    assert len(project_detail["documents"]) == 1
    assert project_detail["documents"][0]["source_kind"] == "report_workflow"
    assert project_detail["documents"][0]["source_evidence_refs"] == [
        requirement_ref
    ]

    knowledge = client.get(f"/knowledge/{project['project_id']}/documents").json()
    assert knowledge["count"] == 2
    assert {
        doc["knowledge_scope"]["report_workflow_id"]
        for doc in knowledge["documents"]
    } == {workflow_id}
    assert {
        doc["knowledge_scope"]["project_id"]
        for doc in knowledge["documents"]
    } == {project["project_id"]}

    duplicate = client.post(
        f"/report-workflows/{workflow_id}/promote",
        json={"project_id": project["project_id"], "promote_to_knowledge": True},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["project_document_id"] == body["project_document_id"]
    assert duplicate.json()["knowledge_document_count"] == 2


def test_promote_to_knowledge_requires_learning_opt_in(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    project = client.post("/projects", json={"name": "학습 비동의"}).json()
    created = _create_workflow(client, slide_count=2, learning_opt_in=False)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()
    for slide in slides_payload["slides"]:
        client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm", "comment": ""},
        )
    client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "owner", "comment": ""})
    client.post(f"/report-workflows/{workflow_id}/final/pm-approve", json={"username": "pm", "comment": ""})
    client.post(f"/report-workflows/{workflow_id}/final/executive-approve", json={"username": "ceo", "comment": ""})

    blocked = client.post(
        f"/report-workflows/{workflow_id}/promote",
        json={"project_id": project["project_id"], "promote_to_knowledge": True},
    )
    assert blocked.status_code == 400
    assert "learning_opt_in=true" in blocked.json()["detail"]

    project_only = client.post(
        f"/report-workflows/{workflow_id}/promote",
        json={"project_id": project["project_id"], "promote_to_knowledge": False},
    )
    assert project_only.status_code == 200
    assert project_only.json()["project_document_id"]
    assert project_only.json()["knowledge_document_count"] == 0


def test_final_change_request_api(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    slides_payload = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}).json()
    for slide in slides_payload["slides"]:
        client.post(
            f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
            json={"username": "pm", "comment": ""},
        )
    client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "owner", "comment": ""})
    changes = client.post(
        f"/report-workflows/{workflow_id}/final/request-changes",
        json={"username": "pm", "comment": "근거 보완"},
    )

    assert changes.status_code == 200
    assert changes.json()["status"] == "final_changes_requested"
    assert changes.json()["approval_steps"][0]["status"] == "changes_requested"
    assert changes.json()["final_approval_status"] == "changes_requested"


def test_invalid_provider_json_uses_quality_warning_fallback(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)

    class BadProvider:
        name = "bad"

        def generate_raw(self, prompt, *, request_id, max_output_tokens=None):
            return "not json"

    client.app.state.report_workflow_service._provider_factory = lambda: BadProvider()
    created = _create_workflow(client, slide_count=2)
    workflow_id = created["report_workflow_id"]

    planning = client.post(f"/report-workflows/{workflow_id}/planning/generate")
    assert planning.status_code == 200
    assert planning.json()["quality_warnings"]
    planning_payload = planning.json()["planning"]
    assert len(planning_payload["slide_plans"]) == 2
    assert planning_payload["planning_brief"]
    assert planning_payload["quality_bar"]
    assert planning_payload["slide_plans"][0]["decision_question"]


def test_missing_workflow_and_missing_slide_return_404(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch)
    assert client.get("/report-workflows/nope").status_code == 404

    created = _create_workflow(client)
    workflow_id = created["report_workflow_id"]
    client.post(f"/report-workflows/{workflow_id}/planning/generate")
    client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
    client.post(f"/report-workflows/{workflow_id}/slides/generate", json={})
    missing_slide = client.post(
        f"/report-workflows/{workflow_id}/slides/nope/approve",
        json={"username": "pm", "comment": ""},
    )
    assert missing_slide.status_code == 404
