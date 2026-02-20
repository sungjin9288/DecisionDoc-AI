import os
from importlib.util import find_spec

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.live


def _resolve_live_api_key() -> str:
    raw_keys = os.getenv("DECISIONDOC_API_KEYS")
    if raw_keys is not None:
        keys = [item.strip() for item in raw_keys.split(",") if item.strip()]
        if keys:
            return keys[0]
    return os.getenv("DECISIONDOC_API_KEY", "")


def _live_client(monkeypatch, provider: str):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    from app.main import create_app

    return TestClient(create_app())


def test_live_openai_generate_ok(monkeypatch):
    if os.getenv("DECISIONDOC_PROVIDER") != "openai" or not os.getenv("OPENAI_API_KEY"):
        pytest.skip("Set DECISIONDOC_PROVIDER=openai and OPENAI_API_KEY to run live OpenAI test.")
    if find_spec("openai") is None:
        pytest.skip("openai SDK is not installed.")

    client = _live_client(monkeypatch, "openai")
    headers = {}
    api_key = _resolve_live_api_key()
    if api_key:
        headers["X-DecisionDoc-Api-Key"] = api_key
    response = client.post("/generate", json={"title": "Live OpenAI", "goal": "live smoke"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai"
    assert len(body["docs"]) == 4


def test_live_gemini_generate_ok(monkeypatch):
    if os.getenv("DECISIONDOC_PROVIDER") != "gemini" or not os.getenv("GEMINI_API_KEY"):
        pytest.skip("Set DECISIONDOC_PROVIDER=gemini and GEMINI_API_KEY to run live Gemini test.")
    if find_spec("google.genai") is None:
        pytest.skip("google-genai SDK is not installed.")

    client = _live_client(monkeypatch, "gemini")
    headers = {}
    api_key = _resolve_live_api_key()
    if api_key:
        headers["X-DecisionDoc-Api-Key"] = api_key
    response = client.post("/generate", json={"title": "Live Gemini", "goal": "live smoke"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "gemini"
    assert len(body["docs"]) == 4
