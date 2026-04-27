from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


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
        "client": "다울",
        "audience": "PM, 대표",
        "slide_count": 3,
        "learning_opt_in": True,
    }
    payload.update(overrides)
    res = client.post("/report-workflows", json=payload)
    assert res.status_code == 200
    return res.json()


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
    assert "선택 시각자료 ID: asset-rw-1" in first_outline["design_tip"]


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
        json={"name": "워크플로우 산출물", "client": "다울", "description": "승인본 저장소"},
    ).json()
    created = _create_workflow(client, slide_count=2, learning_opt_in=True)
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

    knowledge = client.get(f"/knowledge/{project['project_id']}/documents").json()
    assert knowledge["count"] == 2

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
