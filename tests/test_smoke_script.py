from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import httpx


def _load_smoke_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "smoke.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_smoke_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _decision_council_response(
    *,
    session_id: str = "council-123",
    session_revision: int = 1,
    direction: str = "proceed",
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "session_key": "public_procurement:project-123:bid_decision_kr",
        "session_revision": session_revision,
        "tenant_id": "system",
        "project_id": "project-123",
        "use_case": "public_procurement",
        "target_bundle_type": "bid_decision_kr",
        "supported_bundle_types": ["bid_decision_kr", "proposal_kr"],
        "goal": "입찰 참여 여부 판단과 bid_decision_kr drafting 방향을 정리한다.",
        "context": "provider=mock; recommendation=GO",
        "constraints": "기존 approval/share/export 흐름은 그대로 유지한다.",
        "source_procurement_decision_id": "decision-123",
        "source_snapshot_ids": [],
        "created_at": "2026-04-03T00:00:00+00:00",
        "updated_at": "2026-04-03T00:00:00+00:00",
        "operation": "created",
        "role_opinions": [
            {
                "role": "Requirement Analyst",
                "stance": "support",
                "summary": "필수 요구사항은 대체로 충족된다.",
                "evidence_refs": [],
                "risks": [],
                "disagreements": [],
                "recommended_actions": [],
            }
        ],
        "disagreements": [],
        "risks": ["최신 인증 증빙 재확인 필요"],
        "consensus": {
            "alignment": "aligned",
            "recommended_direction": direction,
            "summary": "기존 recommendation을 bid_decision_kr drafting brief로 전달한다.",
            "strategy_options": ["현재 recommendation 기준으로 의사결정 문서를 작성한다."],
            "disagreements": [],
            "top_risks": ["최신 인증 증빙 재확인 필요"],
            "conditions": [],
            "open_questions": [],
        },
        "handoff": {
            "target_bundle_type": "bid_decision_kr",
            "recommended_direction": direction,
            "drafting_brief": "기존 procurement recommendation을 근거 중심으로 정리한다.",
            "must_include": ["recommendation 근거"],
            "must_address": ["리스크와 조건"],
            "must_not_claim": [],
            "open_questions": [],
            "source_procurement_decision_id": "decision-123",
        },
    }


def test_discover_recent_g2b_bid_number_returns_first_available_result():
    smoke = _load_smoke_module()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("getBidPblancListInfoServc"):
            return httpx.Response(200, json={"response": {"body": {"items": []}}})
        return httpx.Response(
            200,
            json={
                "response": {
                    "body": {
                        "items": [
                            {"bidNtceNo": "R26BK01499999", "bidNtceNm": "Smoke Fixture"},
                        ]
                    }
                }
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    discovered = smoke._discover_recent_g2b_bid_number(
        "fake-key",
        timeout_sec=30,
        now=datetime(2026, 3, 28, 9, 0, 0),
        client=client,
    )

    assert discovered == "R26BK01499999"
    assert any("getBidPblancListInfoServc" in call for call in calls)
    assert any("getBidPblancListInfoThng" in call for call in calls)


def test_discover_recent_g2b_bid_number_returns_none_when_no_items_exist():
    smoke = _load_smoke_module()

    def handler(request: httpx.Request) -> httpx.Response:
        _ = request
        return httpx.Response(200, json={"response": {"body": {"items": []}}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    discovered = smoke._discover_recent_g2b_bid_number(
        "fake-key",
        timeout_sec=30,
        now=datetime(2026, 3, 28, 9, 0, 0),
        client=client,
    )

    assert discovered is None


def test_run_document_upload_smoke_validates_auth_and_success_paths(capsys):
    smoke = _load_smoke_module()
    seen_api_key_headers: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/generate/from-documents":
            raise AssertionError(f"Unhandled request: {request.method} {request.url}")
        seen_api_key_headers.append(request.headers.get("x-decisiondoc-api-key", ""))
        if request.headers.get("x-decisiondoc-api-key") != "api-key":
            return httpx.Response(401, json={"code": "UNAUTHORIZED", "request_id": "req-no-auth"})
        return httpx.Response(
            200,
            json={
                "request_id": "req-upload",
                "bundle_id": "bundle-upload",
                "docs": [
                    {"doc_type": "adr", "markdown": "# ADR"},
                    {"doc_type": "onepager", "markdown": "# One-pager"},
                ],
            },
        )

    client = httpx.Client(base_url="https://example.com", transport=httpx.MockTransport(handler))
    smoke._run_document_upload_smoke(
        client,
        base_url="https://example.com",
        api_key="api-key",
    )

    out = capsys.readouterr().out
    assert "POST /generate/from-documents (no key) -> 401" in out
    assert "POST /generate/from-documents (auth) -> 200" in out
    assert seen_api_key_headers == ["", "api-key"]


def test_run_procurement_smoke_retries_import_with_detail_url_before_discovery(monkeypatch):
    smoke = _load_smoke_module()
    requested_targets: list[str] = []
    council_payloads: list[dict[str, str]] = []
    generated_bundles: list[str] = []
    council_response = _decision_council_response(direction="proceed")
    state = {"proposal_generated": False}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return httpx.Response(200, json={"features": {"procurement_copilot": True}})
        if path == "/auth/register":
            return httpx.Response(200, json={"access_token": "token-123"})
        if path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        if path.endswith("/imports/g2b-opportunity"):
            payload = smoke._json_body(httpx.Response(200, content=request.content))
            requested_targets.append(payload["url_or_number"])
            if len(requested_targets) == 1:
                return httpx.Response(404, json={"code": "not_found"})
            return httpx.Response(
                200,
                json={
                    "opportunity": {
                        "title": "Recovered announcement",
                    }
                },
            )
        if path.endswith("/procurement/evaluate"):
            return httpx.Response(200, json={"decision": {"soft_fit_score": 54.0}})
        if path.endswith("/procurement/recommend"):
            return httpx.Response(200, json={"recommendation": {"value": "GO"}})
        if path.endswith("/decision-council/run"):
            council_payloads.append(smoke._json_body(httpx.Response(200, content=request.content)))
            return httpx.Response(200, json=council_response)
        if path == "/generate/stream":
            payload = smoke._json_body(httpx.Response(200, content=request.content))
            generated_bundles.append(payload["bundle_type"])
            if payload["bundle_type"] == "proposal_kr":
                state["proposal_generated"] = True
            body = 'event: complete\ndata: {"request_id":"req-1","bundle_id":"bundle-1"}\n\n'
            return httpx.Response(200, text=body)
        if path == "/projects/project-123":
            documents = [
                {
                    "request_id": "req-1",
                    "bundle_id": "bid_decision_kr",
                    "title": "Recovered announcement",
                    "doc_snapshot": "[]",
                    "source_decision_council_session_id": council_response["session_id"],
                    "source_decision_council_session_revision": council_response["session_revision"],
                    "source_decision_council_direction": "proceed",
                }
            ]
            if state["proposal_generated"]:
                documents.append(
                    {
                        "request_id": "req-2",
                        "bundle_id": "proposal_kr",
                        "title": "Recovered announcement proposal",
                        "doc_snapshot": "[]",
                        "source_decision_council_session_id": council_response["session_id"],
                        "source_decision_council_session_revision": council_response["session_revision"],
                        "source_decision_council_direction": "proceed",
                    }
                )
            return httpx.Response(200, json={"documents": documents})
        if path == "/approvals":
            return httpx.Response(200, json={"approval_id": "approval-1"})
        if path == "/share":
            return httpx.Response(200, json={"share_id": "share-1", "share_url": "/shared/share-1"})
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    monkeypatch.setattr(smoke, "_discover_recent_g2b_bid_number", lambda *args, **kwargs: None)
    client = httpx.Client(base_url="https://example.com", transport=httpx.MockTransport(handler))
    smoke._run_procurement_smoke(
        client,
        base_url="https://example.com",
        api_key="api-key",
        provider="mock",
        url_or_number="R26BK01398367",
    )

    assert requested_targets == [
        "R26BK01398367",
        "https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=R26BK01398367",
    ]
    assert council_payloads == [
        {
            "goal": "입찰 참여 여부 판단과 bid_decision_kr drafting 방향을 정리한다.",
            "context": "provider=mock; recommendation=GO",
            "constraints": "기존 approval/share/export 흐름은 그대로 유지한다.",
        }
    ]
    assert generated_bundles == ["bid_decision_kr", "proposal_kr"]


def test_run_procurement_smoke_discovers_recent_target_when_not_configured(monkeypatch):
    smoke = _load_smoke_module()
    requested_targets: list[str] = []
    generated_bundles: list[str] = []
    council_response = _decision_council_response(direction="proceed")
    state = {"proposal_generated": False}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return httpx.Response(200, json={"features": {"procurement_copilot": True}})
        if path == "/auth/register":
            return httpx.Response(200, json={"access_token": "token-123"})
        if path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        if path.endswith("/imports/g2b-opportunity"):
            payload = smoke._json_body(httpx.Response(200, content=request.content))
            requested_targets.append(payload["url_or_number"])
            return httpx.Response(200, json={"opportunity": {"title": "Discovered announcement"}})
        if path.endswith("/procurement/evaluate"):
            return httpx.Response(200, json={"decision": {"soft_fit_score": 61.0}})
        if path.endswith("/procurement/recommend"):
            return httpx.Response(200, json={"recommendation": {"value": "GO"}})
        if path.endswith("/decision-council/run"):
            return httpx.Response(200, json=council_response)
        if path == "/generate/stream":
            payload = smoke._json_body(httpx.Response(200, content=request.content))
            generated_bundles.append(payload["bundle_type"])
            if payload["bundle_type"] == "proposal_kr":
                state["proposal_generated"] = True
            bundle_id = payload["bundle_type"]
            request_id = "req-1" if bundle_id == "bid_decision_kr" else "req-2"
            body = f'event: complete\ndata: {{"request_id":"{request_id}","bundle_id":"{bundle_id}"}}\n\n'
            return httpx.Response(200, text=body)
        if path == "/projects/project-123":
            documents = [
                {
                    "request_id": "req-1",
                    "bundle_id": "bid_decision_kr",
                    "title": "Discovered announcement",
                    "doc_snapshot": "[]",
                    "source_decision_council_session_id": council_response["session_id"],
                    "source_decision_council_session_revision": council_response["session_revision"],
                    "source_decision_council_direction": "proceed",
                }
            ]
            if state["proposal_generated"]:
                documents.append(
                    {
                        "request_id": "req-2",
                        "bundle_id": "proposal_kr",
                        "title": "Discovered announcement proposal",
                        "doc_snapshot": "[]",
                        "source_decision_council_session_id": council_response["session_id"],
                        "source_decision_council_session_revision": council_response["session_revision"],
                        "source_decision_council_direction": "proceed",
                    }
                )
            return httpx.Response(200, json={"documents": documents})
        if path == "/approvals":
            return httpx.Response(200, json={"approval_id": "approval-1"})
        if path == "/share":
            return httpx.Response(200, json={"share_id": "share-1", "share_url": "/shared/share-1"})
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    monkeypatch.setattr(smoke, "_discover_recent_g2b_bid_number", lambda *args, **kwargs: "R26BK01455555")
    client = httpx.Client(base_url="https://example.com", transport=httpx.MockTransport(handler))
    smoke._run_procurement_smoke(
        client,
        base_url="https://example.com",
        api_key="api-key",
        provider="mock",
        url_or_number="",
    )

    assert requested_targets == ["R26BK01455555"]
    assert generated_bundles == ["bid_decision_kr", "proposal_kr"]


def test_run_procurement_smoke_skips_when_no_target_is_configured_and_discovery_finds_nothing(monkeypatch, capsys):
    smoke = _load_smoke_module()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return httpx.Response(200, json={"features": {"procurement_copilot": True}})
        if path == "/auth/register":
            return httpx.Response(200, json={"access_token": "token-123"})
        if path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    monkeypatch.setattr(smoke, "_discover_recent_g2b_bid_number", lambda *args, **kwargs: None)
    client = httpx.Client(base_url="https://example.com", transport=httpx.MockTransport(handler))

    smoke._run_procurement_smoke(
        client,
        base_url="https://example.com",
        api_key="api-key",
        provider="mock",
        url_or_number="",
    )

    assert "SKIP procurement smoke could not discover a recent live G2B opportunity" in capsys.readouterr().out


def test_run_procurement_smoke_skips_when_all_import_fallback_targets_404(monkeypatch, capsys):
    smoke = _load_smoke_module()
    requested_targets: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return httpx.Response(200, json={"features": {"procurement_copilot": True}})
        if path == "/auth/register":
            return httpx.Response(200, json={"access_token": "token-123"})
        if path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        if path.endswith("/imports/g2b-opportunity"):
            payload = smoke._json_body(httpx.Response(200, content=request.content))
            requested_targets.append(payload["url_or_number"])
            return httpx.Response(404, json={"code": "not_found"})
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    monkeypatch.setattr(smoke, "_discover_recent_g2b_bid_number", lambda *args, **kwargs: None)
    client = httpx.Client(base_url="https://example.com", transport=httpx.MockTransport(handler))

    smoke._run_procurement_smoke(
        client,
        base_url="https://example.com",
        api_key="api-key",
        provider="mock",
        url_or_number="R26BK01398367",
    )

    assert requested_targets == [
        "R26BK01398367",
        "https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=R26BK01398367",
    ]
    assert "SKIP procurement smoke import could not resolve a live G2B opportunity" in capsys.readouterr().out


def test_run_procurement_smoke_validates_remediation_handoff_queue_for_no_go(monkeypatch):
    smoke = _load_smoke_module()
    summary_statuses: list[str] = []
    copy_payloads: list[dict[str, str]] = []
    open_payloads: list[dict[str, str]] = []
    council_payloads: list[dict[str, str]] = []
    council_response = _decision_council_response(direction="do_not_proceed")
    state = {
        "opened": False,
        "override_saved": False,
        "proposal_generated": False,
    }

    def _request_json(request: httpx.Request) -> dict[str, str]:
        return smoke._json_body(httpx.Response(200, content=request.content))

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return httpx.Response(200, json={"features": {"procurement_copilot": True}})
        if path == "/auth/register":
            return httpx.Response(200, json={"access_token": "token-123"})
        if path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        if path.endswith("/imports/g2b-opportunity"):
            return httpx.Response(200, json={"opportunity": {"title": "Recovered announcement"}})
        if path.endswith("/procurement/evaluate"):
            return httpx.Response(200, json={"decision": {"soft_fit_score": 54.0}})
        if path.endswith("/procurement/recommend"):
            return httpx.Response(200, json={"recommendation": {"value": "NO_GO"}})
        if path.endswith("/decision-council/run"):
            council_payloads.append(_request_json(request))
            return httpx.Response(200, json=council_response)
        if path == "/generate/stream":
            payload = _request_json(request)
            bundle_type = payload.get("bundle_type")
            if bundle_type == "bid_decision_kr":
                body = 'event: complete\ndata: {"request_id":"req-1","bundle_id":"bid_decision_kr"}\n\n'
                return httpx.Response(200, text=body)
            if bundle_type == "proposal_kr":
                if not state["override_saved"]:
                    return httpx.Response(
                        409,
                        json={"detail": {"code": "procurement_override_reason_required"}},
                    )
                state["proposal_generated"] = True
                body = 'event: complete\ndata: {"request_id":"req-2","bundle_id":"proposal_kr"}\n\n'
                return httpx.Response(200, text=body)
        if path == "/projects/project-123":
            documents = [
                {
                    "request_id": "req-1",
                    "bundle_id": "bid_decision_kr",
                    "title": "Recovered announcement",
                    "doc_snapshot": "[]",
                    "source_decision_council_session_id": council_response["session_id"],
                    "source_decision_council_session_revision": council_response["session_revision"],
                    "source_decision_council_direction": "do_not_proceed",
                }
            ]
            if state["proposal_generated"]:
                documents.append(
                    {
                        "request_id": "req-2",
                        "bundle_id": "proposal_kr",
                        "title": "Recovered announcement proposal",
                        "doc_snapshot": "[]",
                        "source_decision_council_session_id": council_response["session_id"],
                        "source_decision_council_session_revision": council_response["session_revision"],
                        "source_decision_council_direction": "do_not_proceed",
                    }
                )
            return httpx.Response(200, json={"documents": documents})
        if path == "/approvals":
            return httpx.Response(200, json={"approval_id": "approval-1"})
        if path == "/share":
            return httpx.Response(200, json={"share_id": "share-1", "share_url": "/shared/share-1"})
        if path.endswith("/procurement/remediation-link-copy"):
            payload = _request_json(request)
            copy_payloads.append(payload)
            return httpx.Response(200, json={"logged": True})
        if path.endswith("/procurement/remediation-link-open"):
            payload = _request_json(request)
            open_payloads.append(payload)
            state["opened"] = True
            return httpx.Response(200, json={"logged": True})
        if path.endswith("/procurement/override-reason"):
            state["override_saved"] = True
            return httpx.Response(200, json={"override_reason_saved": True})
        if path == "/admin/locations/system/procurement-quality-summary":
            if state["opened"] and state["override_saved"]:
                handoff_status = "opened_resolved"
            elif state["opened"]:
                handoff_status = "opened_unresolved"
            else:
                handoff_status = "shared_not_opened"
            summary_statuses.append(handoff_status)
            return httpx.Response(
                200,
                json={
                    "procurement": {
                        "handoff": {
                            "remediation_queue": [
                                {
                                    "project_id": "project-123",
                                    "handoff_status": handoff_status,
                                }
                            ]
                        }
                    }
                },
            )
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    monkeypatch.setattr(smoke, "_discover_recent_g2b_bid_number", lambda *args, **kwargs: None)
    client = httpx.Client(base_url="https://example.com", transport=httpx.MockTransport(handler))
    smoke._run_procurement_smoke(
        client,
        base_url="https://example.com",
        api_key="api-key",
        provider="mock",
        url_or_number="R26BK01398367",
    )

    assert summary_statuses == [
        "shared_not_opened",
        "opened_unresolved",
        "opened_resolved",
    ]
    assert council_payloads == [
        {
            "goal": "입찰 참여 여부 판단과 bid_decision_kr drafting 방향을 정리한다.",
            "context": "provider=mock; recommendation=NO_GO",
            "constraints": "기존 approval/share/export 흐름은 그대로 유지한다.",
        }
    ]
    assert copy_payloads == [
        {
            "source": "location_summary",
            "context_kind": "blocked_event",
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
        }
    ]
    assert open_payloads == [
        {
            "source": "url_restore",
            "context_kind": "blocked_event",
            "bundle_type": "proposal_kr",
            "error_code": "procurement_override_reason_required",
            "recommendation": "NO_GO",
        }
    ]


def test_run_procurement_smoke_prefers_ops_summary_route_for_handoff_validation(monkeypatch):
    smoke = _load_smoke_module()
    summary_paths: list[str] = []
    council_response = _decision_council_response(direction="do_not_proceed")
    state = {
        "opened": False,
        "override_saved": False,
        "proposal_generated": False,
    }

    def _request_json(request: httpx.Request) -> dict[str, str]:
        return smoke._json_body(httpx.Response(200, content=request.content))

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return httpx.Response(200, json={"features": {"procurement_copilot": True}})
        if path == "/auth/register":
            return httpx.Response(200, json={"access_token": "token-123"})
        if path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        if path.endswith("/imports/g2b-opportunity"):
            return httpx.Response(200, json={"opportunity": {"title": "Recovered announcement"}})
        if path.endswith("/procurement/evaluate"):
            return httpx.Response(200, json={"decision": {"soft_fit_score": 54.0}})
        if path.endswith("/procurement/recommend"):
            return httpx.Response(200, json={"recommendation": {"value": "NO_GO"}})
        if path.endswith("/decision-council/run"):
            return httpx.Response(200, json=council_response)
        if path == "/generate/stream":
            payload = _request_json(request)
            bundle_type = payload.get("bundle_type")
            if bundle_type == "bid_decision_kr":
                body = 'event: complete\ndata: {"request_id":"req-1","bundle_id":"bid_decision_kr"}\n\n'
                return httpx.Response(200, text=body)
            if bundle_type == "proposal_kr":
                if not state["override_saved"]:
                    return httpx.Response(409, json={"detail": {"code": "procurement_override_reason_required"}})
                state["proposal_generated"] = True
                body = 'event: complete\ndata: {"request_id":"req-2","bundle_id":"proposal_kr"}\n\n'
                return httpx.Response(200, text=body)
        if path == "/projects/project-123":
            documents = [
                {
                    "request_id": "req-1",
                    "bundle_id": "bid_decision_kr",
                    "title": "Recovered announcement",
                    "doc_snapshot": "[]",
                    "source_decision_council_session_id": council_response["session_id"],
                    "source_decision_council_session_revision": council_response["session_revision"],
                    "source_decision_council_direction": "do_not_proceed",
                }
            ]
            if state["proposal_generated"]:
                documents.append(
                    {
                        "request_id": "req-2",
                        "bundle_id": "proposal_kr",
                        "title": "Recovered announcement proposal",
                        "doc_snapshot": "[]",
                        "source_decision_council_session_id": council_response["session_id"],
                        "source_decision_council_session_revision": council_response["session_revision"],
                        "source_decision_council_direction": "do_not_proceed",
                    }
                )
            return httpx.Response(200, json={"documents": documents})
        if path == "/approvals":
            return httpx.Response(200, json={"approval_id": "approval-1"})
        if path == "/share":
            return httpx.Response(200, json={"share_id": "share-1", "share_url": "/shared/share-1"})
        if path.endswith("/procurement/remediation-link-copy"):
            return httpx.Response(200, json={"logged": True})
        if path.endswith("/procurement/remediation-link-open"):
            state["opened"] = True
            return httpx.Response(200, json={"logged": True})
        if path.endswith("/procurement/override-reason"):
            state["override_saved"] = True
            return httpx.Response(200, json={"override_reason_saved": True})
        if path == "/admin/tenants/system/procurement-quality-summary":
            assert request.headers.get("X-DecisionDoc-Ops-Key") == "ops-key"
            if state["opened"] and state["override_saved"]:
                handoff_status = "opened_resolved"
            elif state["opened"]:
                handoff_status = "opened_unresolved"
            else:
                handoff_status = "shared_not_opened"
            summary_paths.append(path)
            return httpx.Response(
                200,
                json={
                    "procurement": {
                        "handoff": {
                            "remediation_queue": [
                                {
                                    "project_id": "project-123",
                                    "handoff_status": handoff_status,
                                }
                            ]
                        }
                    }
                },
            )
        if path == "/admin/locations/system/procurement-quality-summary":
            raise AssertionError("Location summary route should not be used when SMOKE_OPS_KEY is set")
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    monkeypatch.setattr(smoke, "_discover_recent_g2b_bid_number", lambda *args, **kwargs: None)
    monkeypatch.setenv("SMOKE_OPS_KEY", "ops-key")
    client = httpx.Client(base_url="https://example.com", transport=httpx.MockTransport(handler))
    smoke._run_procurement_smoke(
        client,
        base_url="https://example.com",
        api_key="api-key",
        provider="mock",
        url_or_number="R26BK01398367",
    )

    assert summary_paths == [
        "/admin/tenants/system/procurement-quality-summary",
        "/admin/tenants/system/procurement-quality-summary",
        "/admin/tenants/system/procurement-quality-summary",
    ]


def test_run_procurement_smoke_skips_handoff_validation_when_recommendation_is_not_no_go(monkeypatch, capsys):
    smoke = _load_smoke_module()
    remediation_calls: list[str] = []
    generated_bundles: list[str] = []
    council_response = _decision_council_response(direction="proceed")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/version":
            return httpx.Response(200, json={"features": {"procurement_copilot": True}})
        if path == "/auth/register":
            return httpx.Response(200, json={"access_token": "token-123"})
        if path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        if path.endswith("/imports/g2b-opportunity"):
            return httpx.Response(200, json={"opportunity": {"title": "Recovered announcement"}})
        if path.endswith("/procurement/evaluate"):
            return httpx.Response(200, json={"decision": {"soft_fit_score": 72.0}})
        if path.endswith("/procurement/recommend"):
            return httpx.Response(200, json={"recommendation": {"value": "GO"}})
        if path.endswith("/decision-council/run"):
            return httpx.Response(200, json=council_response)
        if path == "/generate/stream":
            payload = smoke._json_body(httpx.Response(200, content=request.content))
            generated_bundles.append(payload["bundle_type"])
            bundle_id = payload["bundle_type"]
            request_id = "req-1" if bundle_id == "bid_decision_kr" else "req-2"
            body = f'event: complete\ndata: {{"request_id":"{request_id}","bundle_id":"{bundle_id}"}}\n\n'
            return httpx.Response(200, text=body)
        if path == "/projects/project-123":
            return httpx.Response(
                200,
                json={
                    "documents": [
                        {
                            "request_id": "req-1",
                            "bundle_id": "bid_decision_kr",
                            "title": "Recovered announcement",
                            "doc_snapshot": "[]",
                            "source_decision_council_session_id": council_response["session_id"],
                            "source_decision_council_session_revision": council_response["session_revision"],
                            "source_decision_council_direction": "proceed",
                        },
                        {
                            "request_id": "req-2",
                            "bundle_id": "proposal_kr",
                            "title": "Recovered announcement proposal",
                            "doc_snapshot": "[]",
                            "source_decision_council_session_id": council_response["session_id"],
                            "source_decision_council_session_revision": council_response["session_revision"],
                            "source_decision_council_direction": "proceed",
                        },
                    ]
                },
            )
        if path == "/approvals":
            return httpx.Response(200, json={"approval_id": "approval-1"})
        if path == "/share":
            return httpx.Response(200, json={"share_id": "share-1", "share_url": "/shared/share-1"})
        if "remediation-link" in path or "procurement-quality-summary" in path or "override-reason" in path:
            remediation_calls.append(path)
            raise AssertionError(f"Unexpected remediation handoff request: {request.method} {request.url}")
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    monkeypatch.setattr(smoke, "_discover_recent_g2b_bid_number", lambda *args, **kwargs: None)
    client = httpx.Client(base_url="https://example.com", transport=httpx.MockTransport(handler))
    smoke._run_procurement_smoke(
        client,
        base_url="https://example.com",
        api_key="api-key",
        provider="mock",
        url_or_number="R26BK01398367",
    )

    assert remediation_calls == []
    assert generated_bundles == ["bid_decision_kr", "proposal_kr"]
    assert (
        "SKIP procurement handoff smoke requires a NO_GO recommendation (got GO)"
        in capsys.readouterr().out
    )
