"""Tests for POST /generate/stream (SSE streaming endpoint)."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def _parse_events(text: str) -> list[dict]:
    """Parse SSE text into a list of {event, data} dicts."""
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        ev: dict = {}
        for line in block.splitlines():
            if line.startswith("event: "):
                ev["event"] = line[7:]
            elif line.startswith("data: "):
                try:
                    ev["data"] = json.loads(line[6:])
                except json.JSONDecodeError:
                    ev["data"] = line[6:]
        if ev:
            events.append(ev)
    return events


def test_stream_returns_event_stream_content_type(tmp_path, monkeypatch):
    """Content-Type must be text/event-stream."""
    client = _create_client(tmp_path, monkeypatch)
    with client.stream(
        "POST",
        "/generate/stream",
        json={"title": "스트림 테스트", "goal": "SSE 확인"},
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]


def test_stream_contains_complete_event(tmp_path, monkeypatch):
    """Response must include an 'event: complete' block."""
    client = _create_client(tmp_path, monkeypatch)
    with client.stream("POST", "/generate/stream", json={"title": "t", "goal": "g"}) as r:
        body = r.read().decode()
    events = _parse_events(body)
    event_types = [e["event"] for e in events]
    assert "complete" in event_types


def test_stream_only_valid_event_types(tmp_path, monkeypatch):
    """All emitted events must be one of: progress, complete, error."""
    client = _create_client(tmp_path, monkeypatch)
    with client.stream("POST", "/generate/stream", json={"title": "t", "goal": "g"}) as r:
        body = r.read().decode()
    events = _parse_events(body)
    valid_types = {"progress", "complete", "error"}
    for ev in events:
        assert ev["event"] in valid_types, f"Unexpected event type: {ev['event']}"


def test_stream_complete_event_has_docs(tmp_path, monkeypatch):
    """The 'complete' event data must contain a non-empty docs list."""
    client = _create_client(tmp_path, monkeypatch)
    with client.stream("POST", "/generate/stream", json={"title": "t", "goal": "g"}) as r:
        body = r.read().decode()
    events = _parse_events(body)
    complete = next(e for e in events if e["event"] == "complete")
    assert isinstance(complete["data"]["docs"], list)
    assert len(complete["data"]["docs"]) > 0


def test_stream_invalid_payload_returns_422(tmp_path, monkeypatch):
    """Missing 'goal' field must return 422 before any streaming starts."""
    client = _create_client(tmp_path, monkeypatch)
    r = client.post("/generate/stream", json={"title": "only-title"})
    assert r.status_code == 422
