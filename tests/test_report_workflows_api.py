from __future__ import annotations

from fastapi.testclient import TestClient


_PPTX_MAGIC = b"PK\x03\x04"


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
    final_approve = client.post(f"/report-workflows/{workflow_id}/final/approve", json={"username": "ceo", "comment": ""})
    assert final_approve.status_code == 200
    assert final_approve.json()["status"] == "final_approved"
    assert final_approve.json()["learning_artifacts"]

    pptx = client.get(f"/report-workflows/{workflow_id}/export/pptx")
    assert pptx.status_code == 200
    assert pptx.content[:4] == _PPTX_MAGIC


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
