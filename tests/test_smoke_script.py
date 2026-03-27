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


def test_run_procurement_smoke_retries_import_with_detail_url_before_discovery(monkeypatch):
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
            return httpx.Response(200, json={"recommendation": {"value": "NO_GO"}})
        if path == "/generate/stream":
            body = 'event: complete\ndata: {"request_id":"req-1","bundle_id":"bundle-1"}\n\n'
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
                        }
                    ]
                },
            )
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
