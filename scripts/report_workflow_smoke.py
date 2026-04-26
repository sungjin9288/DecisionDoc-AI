#!/usr/bin/env python3
"""Smoke test for deployed Report Workflow ERP endpoints."""
from __future__ import annotations

import os
import sys
import uuid
from typing import Any

import httpx


DEFAULT_TIMEOUT_SEC = 180.0
PPTX_MAGIC = b"PK\x03\x04"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required env: {name}")
    return value


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise SystemExit(f"{response.request.method} {response.request.url.path} returned non-JSON body") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{response.request.method} {response.request.url.path} returned non-object JSON")
    return payload


def _assert_status(label: str, response: httpx.Response, expected: int) -> dict[str, Any]:
    if response.status_code != expected:
        body: dict[str, Any] | str
        try:
            body = response.json()
        except ValueError:
            body = response.text[:500]
        raise SystemExit(f"{label} expected {expected}, got {response.status_code}: {body}")
    if response.content:
        return _json(response)
    return {}


def _print_result(label: str, status_code: int, **fields: Any) -> None:
    suffix = " ".join(f"{key}={value}" for key, value in fields.items() if value not in {None, ""})
    print(f"PASS {label} -> {status_code}{(' ' + suffix) if suffix else ''}", flush=True)


def _headers(api_key: str, tenant_id: str) -> dict[str, str]:
    headers = {"X-DecisionDoc-Api-Key": api_key}
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    return headers


def _validate_planning_blueprint(planning: dict[str, Any], *, expected_slide_count: int) -> list[dict[str, Any]]:
    required_planning_fields = [
        "planning_brief",
        "audience_decision_needs",
        "narrative_arc",
        "source_strategy",
        "template_guidance",
        "quality_bar",
    ]
    missing = [field for field in required_planning_fields if not planning.get(field)]
    if missing:
        raise SystemExit(f"planning blueprint missing fields: {', '.join(missing)}")

    slide_plans = planning.get("slide_plans")
    if not isinstance(slide_plans, list) or len(slide_plans) != expected_slide_count:
        raise SystemExit(f"planning slide_plans expected {expected_slide_count}, got {len(slide_plans or [])}")

    required_slide_fields = [
        "decision_question",
        "narrative_role",
        "content_blocks",
        "data_needs",
        "design_notes",
        "acceptance_criteria",
    ]
    for idx, plan in enumerate(slide_plans, start=1):
        if not isinstance(plan, dict):
            raise SystemExit(f"slide plan {idx} is not an object")
        missing_slide = [field for field in required_slide_fields if not plan.get(field)]
        if missing_slide:
            raise SystemExit(f"slide plan {idx} missing fields: {', '.join(missing_slide)}")
    return slide_plans


def run_report_workflow_smoke(
    *,
    base_url: str,
    api_key: str,
    tenant_id: str = "",
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    base_url = base_url.rstrip("/")
    run_id = uuid.uuid4().hex[:8]
    slide_count = 2
    owns_client = client is None
    http = client or httpx.Client(timeout=timeout_sec)
    auth_headers = _headers(api_key, tenant_id)

    try:
        health = http.get(f"{base_url}/health")
        _assert_status("GET /health", health, 200)
        _print_result("GET /health", health.status_code)

        no_auth = http.post(f"{base_url}/report-workflows", json={"title": "[SMOKE] unauthorized"})
        no_auth_body = _assert_status("POST /report-workflows (no key)", no_auth, 401)
        if no_auth_body.get("code") not in {"UNAUTHORIZED", None}:
            raise SystemExit("POST /report-workflows (no key) did not return UNAUTHORIZED")
        _print_result("POST /report-workflows (no key)", no_auth.status_code)

        create_payload = {
            "title": f"[SMOKE] Report Workflow Blueprint {run_id}",
            "goal": "운영 배포 후 기획 설계서, 장표 승인, 최종 승인, PPTX export 흐름을 검증합니다.",
            "client": "DecisionDoc Smoke",
            "audience": "PM, 대표",
            "owner": "smoke-runner",
            "slide_count": slide_count,
            "attachments_context": "스모크 테스트용 컨텍스트입니다. 실제 고객 원문은 포함하지 않습니다.",
            "source_refs": ["smoke_context"],
            "learning_opt_in": False,
        }
        created = http.post(f"{base_url}/report-workflows", headers=auth_headers, json=create_payload)
        created_body = _assert_status("POST /report-workflows (auth)", created, 200)
        workflow_id = str(created_body.get("report_workflow_id") or "")
        if not workflow_id:
            raise SystemExit("POST /report-workflows (auth) missing report_workflow_id")
        _print_result("POST /report-workflows (auth)", created.status_code, workflow_id=workflow_id)

        blocked_slides = http.post(f"{base_url}/report-workflows/{workflow_id}/slides/generate", headers=auth_headers, json={})
        _assert_status("POST /slides/generate before planning approval", blocked_slides, 400)
        _print_result("POST /slides/generate before planning approval", blocked_slides.status_code)

        planning = http.post(f"{base_url}/report-workflows/{workflow_id}/planning/generate", headers=auth_headers)
        planning_body = _assert_status("POST /planning/generate", planning, 200)
        if planning_body.get("status") != "planning_draft":
            raise SystemExit(f"planning/generate expected planning_draft, got {planning_body.get('status')}")
        slide_plans = _validate_planning_blueprint(dict(planning_body.get("planning") or {}), expected_slide_count=slide_count)
        _print_result("POST /planning/generate", planning.status_code, slide_plans=len(slide_plans))

        planning_approve = http.post(
            f"{base_url}/report-workflows/{workflow_id}/planning/approve",
            headers=auth_headers,
            json={"username": "smoke-pm", "comment": "planning smoke approved"},
        )
        planning_approve_body = _assert_status("POST /planning/approve", planning_approve, 200)
        if planning_approve_body.get("status") != "planning_approved":
            raise SystemExit(f"planning/approve expected planning_approved, got {planning_approve_body.get('status')}")
        _print_result("POST /planning/approve", planning_approve.status_code)

        slides = http.post(f"{base_url}/report-workflows/{workflow_id}/slides/generate", headers=auth_headers, json={})
        slides_body = _assert_status("POST /slides/generate", slides, 200)
        slide_drafts = slides_body.get("slides")
        if not isinstance(slide_drafts, list) or len(slide_drafts) != slide_count:
            raise SystemExit(f"slides/generate expected {slide_count} slides, got {len(slide_drafts or [])}")
        _print_result("POST /slides/generate", slides.status_code, slides=len(slide_drafts))

        early_final = http.post(
            f"{base_url}/report-workflows/{workflow_id}/final/submit",
            headers=auth_headers,
            json={"username": "smoke-pm", "comment": "early final smoke"},
        )
        _assert_status("POST /final/submit before slide approvals", early_final, 400)
        _print_result("POST /final/submit before slide approvals", early_final.status_code)

        for slide in slide_drafts:
            slide_id = str(slide.get("slide_id") or "")
            if not slide_id:
                raise SystemExit("slides/generate returned a slide without slide_id")
            approved = http.post(
                f"{base_url}/report-workflows/{workflow_id}/slides/{slide_id}/approve",
                headers=auth_headers,
                json={"username": "smoke-pm", "comment": "slide smoke approved"},
            )
            _assert_status(f"POST /slides/{slide_id}/approve", approved, 200)
        _print_result("POST /slides/{slide_id}/approve", 200, approved=len(slide_drafts))

        final_submit = http.post(
            f"{base_url}/report-workflows/{workflow_id}/final/submit",
            headers=auth_headers,
            json={"username": "smoke-pm", "comment": "final smoke submit"},
        )
        final_submit_body = _assert_status("POST /final/submit", final_submit, 200)
        if final_submit_body.get("status") != "final_review":
            raise SystemExit(f"final/submit expected final_review, got {final_submit_body.get('status')}")
        approval_id = str(final_submit_body.get("final_approval_id") or "")
        if not approval_id:
            raise SystemExit("final/submit missing linked final_approval_id")
        if final_submit_body.get("final_approval_status") != "in_review":
            raise SystemExit(
                f"final/submit expected linked approval in_review, got {final_submit_body.get('final_approval_status')}"
            )
        _print_result("POST /final/submit", final_submit.status_code, approval_id=approval_id)

        blocked_executive = http.post(
            f"{base_url}/report-workflows/{workflow_id}/final/executive-approve",
            headers=auth_headers,
            json={"username": "smoke-exec", "comment": "executive smoke should wait for PM"},
        )
        _assert_status("POST /final/executive-approve before PM", blocked_executive, 400)
        _print_result("POST /final/executive-approve before PM", blocked_executive.status_code)

        pm_approve = http.post(
            f"{base_url}/report-workflows/{workflow_id}/final/pm-approve",
            headers=auth_headers,
            json={"username": "smoke-pm", "comment": "final PM smoke approved"},
        )
        pm_approve_body = _assert_status("POST /final/pm-approve", pm_approve, 200)
        if pm_approve_body.get("status") != "final_review":
            raise SystemExit(f"final/pm-approve expected final_review, got {pm_approve_body.get('status')}")
        if pm_approve_body.get("final_approval_status") != "in_review":
            raise SystemExit(
                f"final/pm-approve expected linked approval in_review, got {pm_approve_body.get('final_approval_status')}"
            )
        _print_result("POST /final/pm-approve", pm_approve.status_code)

        final_approve = http.post(
            f"{base_url}/report-workflows/{workflow_id}/final/executive-approve",
            headers=auth_headers,
            json={"username": "smoke-exec", "comment": "final executive smoke approved"},
        )
        final_approve_body = _assert_status("POST /final/executive-approve", final_approve, 200)
        if final_approve_body.get("status") != "final_approved":
            raise SystemExit(f"final/executive-approve expected final_approved, got {final_approve_body.get('status')}")
        if final_approve_body.get("final_approval_status") != "approved":
            raise SystemExit(
                "final/executive-approve expected linked approval approved, "
                f"got {final_approve_body.get('final_approval_status')}"
            )
        _print_result("POST /final/executive-approve", final_approve.status_code)

        pptx = http.get(f"{base_url}/report-workflows/{workflow_id}/export/pptx", headers=auth_headers)
        if pptx.status_code != 200:
            raise SystemExit(f"GET /export/pptx expected 200, got {pptx.status_code}: {pptx.text[:500]}")
        if not pptx.content.startswith(PPTX_MAGIC):
            raise SystemExit("GET /export/pptx did not return PPTX magic bytes")
        _print_result("GET /export/pptx", pptx.status_code, bytes=len(pptx.content))

        return {
            "workflow_id": workflow_id,
            "slide_count": slide_count,
            "pptx_bytes": len(pptx.content),
            "status": "passed",
        }
    finally:
        if owns_client:
            http.close()


def main() -> int:
    base_url = _required_env("SMOKE_BASE_URL")
    api_key = _required_env("SMOKE_API_KEY")
    tenant_id = os.getenv("SMOKE_TENANT_ID", "").strip()
    timeout_sec = float(os.getenv("SMOKE_TIMEOUT_SEC", str(DEFAULT_TIMEOUT_SEC)))

    result = run_report_workflow_smoke(
        base_url=base_url,
        api_key=api_key,
        tenant_id=tenant_id,
        timeout_sec=timeout_sec,
    )
    print(
        "Report workflow smoke completed "
        f"workflow_id={result['workflow_id']} slide_count={result['slide_count']} pptx_bytes={result['pptx_bytes']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
