from __future__ import annotations

import json

import pytest

from app.providers.base import ProviderError
from app.providers.claude_provider import ClaudeProvider


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)
        self.headers = {}

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *args, **kwargs):
        self.response = kwargs.pop("response", None)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):  # noqa: ANN001
        return self.response


def test_claude_provider_generate_raw_parses_text_and_usage(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DECISIONDOC_CLAUDE_MODEL", "claude-sonnet-4-20250514")
    payload = {
        "content": [{"type": "text", "text": "{\"ok\": true}"}],
        "usage": {"input_tokens": 12, "output_tokens": 8},
    }
    fake_response = _FakeResponse(200, payload)
    monkeypatch.setattr(
        "app.providers.claude_provider.httpx.Client",
        lambda *args, **kwargs: _FakeClient(response=fake_response),
    )

    provider = ClaudeProvider()
    raw = provider.generate_raw("return json", request_id="req-1", max_output_tokens=64)

    assert raw == "{\"ok\": true}"
    assert provider.consume_usage_tokens() == {
        "prompt_tokens": 12,
        "output_tokens": 8,
        "total_tokens": 20,
    }


def test_claude_provider_generate_bundle_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    payload = {
        "error": {
            "message": "quota exhausted",
            "type": "error",
            "code": "insufficient_quota",
        }
    }
    fake_response = _FakeResponse(429, payload)
    monkeypatch.setattr(
        "app.providers.claude_provider.httpx.Client",
        lambda *args, **kwargs: _FakeClient(response=fake_response),
    )

    provider = ClaudeProvider()
    with pytest.raises(ProviderError):
        provider.generate_bundle({"title": "x", "goal": "y"}, schema_version="v1", request_id="req-2")


def test_claude_provider_extract_attachment_text_rejects_pdf(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    provider = ClaudeProvider()

    with pytest.raises(ProviderError, match="does not support PDF OCR fallback"):
        provider.extract_attachment_text("scan.pdf", b"%PDF-1.4", request_id="req-3")
