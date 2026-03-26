"""Tests for app.ai.pipeline.FallbackPipeline."""
from typing import Any

import pytest

from app.ai.pipeline import FallbackPipeline
from app.providers.base import Provider, ProviderError, UsageTokenMixin


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _OkProvider(Provider):
    def __init__(self, name: str, raw_response: str = '{"ok": true}') -> None:
        self.name = name
        self._raw_response = raw_response
        self.raw_calls = 0
        self.bundle_calls = 0

    def generate_raw(self, prompt: str, *, request_id: str) -> str:
        self.raw_calls += 1
        return self._raw_response

    def generate_bundle(self, requirements: Any, *, schema_version: str, request_id: str, bundle_spec: Any = None, feedback_hints: str = "") -> dict:
        self.bundle_calls += 1
        return {"ok": True, "provider": self.name}


class _FailProvider(Provider):
    def __init__(self, name: str) -> None:
        self.name = name
        self.raw_calls = 0
        self.bundle_calls = 0

    def generate_raw(self, prompt: str, *, request_id: str) -> str:
        self.raw_calls += 1
        raise ProviderError(f"{self.name} failed")

    def generate_bundle(self, requirements: Any, *, schema_version: str, request_id: str, bundle_spec: Any = None, feedback_hints: str = "") -> dict:
        self.bundle_calls += 1
        raise ProviderError(f"{self.name} failed")


class _TokenProvider(UsageTokenMixin, Provider):
    """Provider that reports fixed usage tokens."""

    def __init__(self, name: str, tokens: dict[str, int]) -> None:
        self.name = name
        self._tokens = tokens

    def generate_raw(self, prompt: str, *, request_id: str) -> str:
        self._set_usage_tokens(self._tokens)
        return '{"ok": true}'

    def generate_bundle(self, requirements: Any, *, schema_version: str, request_id: str, bundle_spec: Any = None, feedback_hints: str = "") -> dict:
        self._set_usage_tokens(self._tokens)
        return {"ok": True}


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_empty_providers_raises():
    with pytest.raises(ValueError, match="at least one"):
        FallbackPipeline([])


def test_pipeline_name():
    assert FallbackPipeline([_OkProvider("p")]).name == "fallback"


# ---------------------------------------------------------------------------
# generate_raw — success and fallback
# ---------------------------------------------------------------------------


def test_uses_first_provider_when_it_succeeds():
    p1 = _OkProvider("primary", '{"first": true}')
    p2 = _OkProvider("secondary", '{"second": true}')
    pipeline = FallbackPipeline([p1, p2])
    result = pipeline.generate_raw("prompt", request_id="req")
    assert result == '{"first": true}'
    assert p1.raw_calls == 1
    assert p2.raw_calls == 0


def test_falls_back_to_second_on_first_raw_failure():
    p1 = _FailProvider("primary")
    p2 = _OkProvider("secondary", '{"fallback": true}')
    pipeline = FallbackPipeline([p1, p2])
    result = pipeline.generate_raw("prompt", request_id="req")
    assert result == '{"fallback": true}'
    assert p1.raw_calls == 1
    assert p2.raw_calls == 1


def test_all_providers_tried_before_raising():
    p1 = _FailProvider("p1")
    p2 = _FailProvider("p2")
    p3 = _FailProvider("p3")
    pipeline = FallbackPipeline([p1, p2, p3])
    with pytest.raises(ProviderError):
        pipeline.generate_raw("prompt", request_id="req")
    assert p1.raw_calls == p2.raw_calls == p3.raw_calls == 1


def test_error_message_names_all_failed_providers():
    p1 = _FailProvider("openai")
    p2 = _FailProvider("gemini")
    pipeline = FallbackPipeline([p1, p2])
    with pytest.raises(ProviderError) as exc_info:
        pipeline.generate_raw("prompt", request_id="req")
    msg = str(exc_info.value)
    assert "openai" in msg
    assert "gemini" in msg


# ---------------------------------------------------------------------------
# generate_bundle — success and fallback
# ---------------------------------------------------------------------------


def test_generate_bundle_uses_first_provider():
    p1 = _OkProvider("primary")
    p2 = _OkProvider("secondary")
    pipeline = FallbackPipeline([p1, p2])
    result = pipeline.generate_bundle({}, schema_version="v1", request_id="req")
    assert result["provider"] == "primary"
    assert p1.bundle_calls == 1
    assert p2.bundle_calls == 0


def test_generate_bundle_falls_back():
    p1 = _FailProvider("primary")
    p2 = _OkProvider("secondary")
    pipeline = FallbackPipeline([p1, p2])
    result = pipeline.generate_bundle({}, schema_version="v1", request_id="req")
    assert result["provider"] == "secondary"
    assert p1.bundle_calls == 1
    assert p2.bundle_calls == 1


def test_generate_bundle_raises_if_all_fail():
    pipeline = FallbackPipeline([_FailProvider("a"), _FailProvider("b")])
    with pytest.raises(ProviderError, match="All providers"):
        pipeline.generate_bundle({}, schema_version="v1", request_id="req")


# ---------------------------------------------------------------------------
# Usage token forwarding
# ---------------------------------------------------------------------------


def test_consume_usage_tokens_from_successful_provider():
    tokens = {"prompt_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    pipeline = FallbackPipeline([_TokenProvider("tok", tokens)])
    pipeline.generate_raw("prompt", request_id="req")
    assert pipeline.consume_usage_tokens() == tokens


def test_consume_usage_tokens_returns_none_before_any_call():
    pipeline = FallbackPipeline([_OkProvider("p")])
    assert pipeline.consume_usage_tokens() is None


def test_consume_usage_tokens_forwarded_from_fallback_provider():
    tokens = {"prompt_tokens": 20, "output_tokens": 10, "total_tokens": 30}
    p1 = _FailProvider("primary")
    p2 = _TokenProvider("secondary", tokens)
    pipeline = FallbackPipeline([p1, p2])
    pipeline.generate_raw("prompt", request_id="req")
    assert pipeline.consume_usage_tokens() == tokens


def test_consume_usage_tokens_cleared_after_read():
    tokens = {"prompt_tokens": 5, "output_tokens": 5, "total_tokens": 10}
    pipeline = FallbackPipeline([_TokenProvider("tok", tokens)])
    pipeline.generate_raw("prompt", request_id="req")
    first = pipeline.consume_usage_tokens()
    second = pipeline.consume_usage_tokens()
    assert first == tokens
    assert second is None  # cleared after first read


# ---------------------------------------------------------------------------
# Single-provider edge case
# ---------------------------------------------------------------------------


def test_single_provider_success():
    p = _OkProvider("solo", '{"solo": true}')
    pipeline = FallbackPipeline([p])
    assert pipeline.generate_raw("prompt", request_id="req") == '{"solo": true}'


def test_single_provider_failure_raises():
    pipeline = FallbackPipeline([_FailProvider("solo")])
    with pytest.raises(ProviderError):
        pipeline.generate_raw("prompt", request_id="req")
