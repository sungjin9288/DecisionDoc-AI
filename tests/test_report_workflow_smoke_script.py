from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest


def _load_smoke_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "report_workflow_smoke.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_report_workflow_smoke", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_report_workflow_smoke_runs_full_flow_with_mock_transport(capsys):
    smoke = _load_smoke_module()
    state = {
        "workflow_id": "wf-smoke",
        "slides_approved": set(),
    }
    slides = [
        {"slide_id": "slide-001", "page": 1, "title": "기획", "body": "본문"},
        {"slide_id": "slide-002", "page": 2, "title": "승인", "body": "본문"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/report-workflows" and request.method == "POST":
            if request.headers.get("X-DecisionDoc-Api-Key") != "smoke-key":
                return httpx.Response(401, json={"code": "UNAUTHORIZED"})
            return httpx.Response(
                200,
                json={
                    "report_workflow_id": state["workflow_id"],
                    "status": "planning_required",
                },
            )
        if path.endswith("/slides/generate") and not state.get("planning_approved"):
            return httpx.Response(400, json={"detail": "기획안 승인 후 장표를 생성할 수 있습니다."})
        if path.endswith("/planning/generate"):
            return httpx.Response(
                200,
                json={
                    "status": "planning_draft",
                    "planning": {
                        "planning_brief": "기획 브리프",
                        "audience_decision_needs": ["승인 기준"],
                        "narrative_arc": ["문제", "해결"],
                        "source_strategy": ["근거 매핑"],
                        "template_guidance": ["템플릿"],
                        "quality_bar": ["완성 기준"],
                        "slide_plans": [
                            {
                                "slide_id": "slide-001",
                                "decision_question": "질문",
                                "narrative_role": "역할",
                                "content_blocks": ["블록"],
                                "data_needs": ["데이터"],
                                "design_notes": ["디자인"],
                                "acceptance_criteria": ["승인 기준"],
                            },
                            {
                                "slide_id": "slide-002",
                                "decision_question": "질문",
                                "narrative_role": "역할",
                                "content_blocks": ["블록"],
                                "data_needs": ["데이터"],
                                "design_notes": ["디자인"],
                                "acceptance_criteria": ["승인 기준"],
                            },
                        ],
                    },
                },
            )
        if path.endswith("/planning/approve"):
            state["planning_approved"] = True
            return httpx.Response(200, json={"status": "planning_approved"})
        if path.endswith("/slides/generate"):
            return httpx.Response(200, json={"status": "slides_draft", "slides": slides})
        if path.endswith("/final/submit") and len(state["slides_approved"]) < len(slides):
            return httpx.Response(400, json={"detail": "모든 장표 승인 필요"})
        if "/slides/" in path and path.endswith("/approve"):
            state["slides_approved"].add(path.split("/")[-2])
            return httpx.Response(200, json={"status": "slides_approved"})
        if path.endswith("/final/submit"):
            return httpx.Response(
                200,
                json={
                    "status": "final_review",
                    "final_approval_id": "approval-smoke",
                    "final_approval_status": "in_review",
                },
            )
        if path.endswith("/final/executive-approve") and not state.get("pm_final_approved"):
            return httpx.Response(400, json={"detail": "PM 검토 승인 후 대표 최종 승인을 진행할 수 있습니다."})
        if path.endswith("/final/pm-approve"):
            state["pm_final_approved"] = True
            return httpx.Response(200, json={"status": "final_review", "final_approval_status": "in_review"})
        if path.endswith("/final/executive-approve"):
            return httpx.Response(200, json={"status": "final_approved", "final_approval_status": "approved"})
        if path.endswith("/export/pptx"):
            return httpx.Response(200, content=smoke.PPTX_MAGIC + b"payload")
        return httpx.Response(404, json={"detail": path})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test")
    result = smoke.run_report_workflow_smoke(
        base_url="https://example.test",
        api_key="smoke-key",
        tenant_id="tenant-smoke",
        client=client,
    )

    assert result == {
        "workflow_id": "wf-smoke",
        "slide_count": 2,
        "pptx_bytes": len(smoke.PPTX_MAGIC + b"payload"),
        "status": "passed",
    }
    assert "PASS POST /planning/generate -> 200 slide_plans=2" in capsys.readouterr().out


def test_report_workflow_smoke_does_not_send_tenant_header_by_default():
    smoke = _load_smoke_module()

    assert smoke._headers("key", "") == {"X-DecisionDoc-Api-Key": "key"}


def test_report_workflow_smoke_fails_when_blueprint_fields_are_missing():
    smoke = _load_smoke_module()

    with pytest.raises(SystemExit, match="planning blueprint missing fields"):
        smoke._validate_planning_blueprint({"slide_plans": []}, expected_slide_count=2)
