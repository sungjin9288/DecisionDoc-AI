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
