"""Tests for app.ai.structured.StructuredGenerator."""
import json
from typing import Any

import pytest
from pydantic import BaseModel

from app.ai.structured import StructuredGenerationError, StructuredGenerator
from app.providers.base import Provider, ProviderError


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeProvider(Provider):
    """Returns a fixed JSON string from generate_raw()."""

    name = "fake"

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[str] = []

    def generate_raw(self, prompt: str, *, request_id: str) -> str:
        self.calls.append(prompt)
        return self._response

    def generate_bundle(self, requirements: Any, *, schema_version: str, request_id: str, bundle_spec: Any = None, feedback_hints: str = "") -> dict:
        return {}


class _FailingProvider(Provider):
    """Always raises ProviderError from generate_raw()."""

    name = "failing"

    def generate_raw(self, prompt: str, *, request_id: str) -> str:
        raise ProviderError("network error")

    def generate_bundle(self, requirements: Any, *, schema_version: str, request_id: str, bundle_spec: Any = None, feedback_hints: str = "") -> dict:
        return {}


class _SequentialProvider(Provider):
    """Returns responses in order; cycles if exhausted."""

    name = "sequential"

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self._index = 0
        self.call_count = 0

    def generate_raw(self, prompt: str, *, request_id: str) -> str:
        resp = self._responses[self._index % len(self._responses)]
        self._index += 1
        self.call_count += 1
        return resp

    def generate_bundle(self, requirements: Any, *, schema_version: str, request_id: str, bundle_spec: Any = None, feedback_hints: str = "") -> dict:
        return {}


# ---------------------------------------------------------------------------
# Sample Pydantic models
# ---------------------------------------------------------------------------


class Point(BaseModel):
    x: float
    y: float
    label: str


class CodeReview(BaseModel):
    summary: str
    issues: list[str]
    severity: str


# ---------------------------------------------------------------------------
# Basic generation
# ---------------------------------------------------------------------------


def test_generates_valid_instance():
    provider = _FakeProvider(json.dumps({"x": 1.0, "y": 2.5, "label": "origin"}))
    gen = StructuredGenerator(Point, provider=provider)
    result = gen.generate({"input": "test"}, request_id="req-1")
    assert isinstance(result, Point)
    assert result.x == 1.0
    assert result.y == 2.5
    assert result.label == "origin"


def test_prompt_contains_schema_and_requirements():
    provider = _FakeProvider(json.dumps({"x": 0.0, "y": 0.0, "label": "t"}))
    gen = StructuredGenerator(Point, provider=provider)
    gen.generate({"my_key": "my_value"}, request_id="req-2")
    prompt = provider.calls[0]
    assert "my_key" in prompt
    assert "schema" in prompt
    # Model field names should appear in the JSON schema fragment
    assert "label" in prompt


def test_instructions_included_in_prompt():
    provider = _FakeProvider(json.dumps({"x": 0.0, "y": 0.0, "label": "t"}))
    gen = StructuredGenerator(Point, provider=provider, instructions="You are a geometry expert.")
    gen.generate({}, request_id="req-3")
    assert "geometry expert" in provider.calls[0]


def test_no_instructions_prompt_still_valid():
    provider = _FakeProvider(json.dumps({"x": 0.0, "y": 0.0, "label": "t"}))
    gen = StructuredGenerator(Point, provider=provider, instructions=None)
    result = gen.generate({}, request_id="req-4")
    assert isinstance(result, Point)


def test_complex_pydantic_model():
    review = {"summary": "Looks good", "issues": ["missing docstring", "unused import"], "severity": "low"}
    gen = StructuredGenerator(
        CodeReview,
        provider=_FakeProvider(json.dumps(review)),
        instructions="You are a senior code reviewer.",
    )
    result = gen.generate({"code": "def foo(): pass"}, request_id="req-5")
    assert isinstance(result, CodeReview)
    assert len(result.issues) == 2
    assert result.severity == "low"


# ---------------------------------------------------------------------------
# Error handling — ProviderError is not retried
# ---------------------------------------------------------------------------


def test_provider_error_propagates_immediately():
    gen = StructuredGenerator(Point, provider=_FailingProvider(), max_retries=3)
    with pytest.raises(ProviderError):
        gen.generate({}, request_id="req-6")


def test_provider_error_no_retry_calls():
    """ProviderError must not trigger retries — only one call should be made."""
    call_count = 0

    class _CountingFailProvider(Provider):
        name = "counting-fail"

        def generate_raw(self, prompt, *, request_id):
            nonlocal call_count
            call_count += 1
            raise ProviderError("fail")

        def generate_bundle(self, *a, **kw):
            return {}

    gen = StructuredGenerator(Point, provider=_CountingFailProvider(), max_retries=5)
    with pytest.raises(ProviderError):
        gen.generate({}, request_id="req-7")
    assert call_count == 1  # no retries


# ---------------------------------------------------------------------------
# Retry on JSON parse error
# ---------------------------------------------------------------------------


def test_json_parse_error_retries_and_succeeds():
    good = json.dumps({"x": 3.0, "y": 4.0, "label": "retry-win"})
    provider = _SequentialProvider(["not-json {{", good])
    gen = StructuredGenerator(Point, provider=provider, max_retries=2)
    result = gen.generate({}, request_id="req-8")
    assert result.label == "retry-win"
    assert provider.call_count == 2


def test_raises_after_all_retries_exhausted_json_error():
    provider = _FakeProvider("not-json-at-all")
    gen = StructuredGenerator(Point, provider=provider, max_retries=1)
    with pytest.raises(StructuredGenerationError) as exc_info:
        gen.generate({}, request_id="req-9")
    err = exc_info.value
    assert err.attempts == 2  # initial + 1 retry
    assert err.last_raw == "not-json-at-all"
    assert len(provider.calls) == 2


# ---------------------------------------------------------------------------
# Retry on Pydantic validation error
# ---------------------------------------------------------------------------


def test_validation_error_retries_with_self_correction():
    bad = json.dumps({"x": 1.0, "y": 2.0})          # missing "label"
    good = json.dumps({"x": 1.0, "y": 2.0, "label": "fixed"})
    provider = _SequentialProvider([bad, good])
    gen = StructuredGenerator(Point, provider=provider, max_retries=2)
    result = gen.generate({}, request_id="req-10")
    assert result.label == "fixed"
    assert provider.call_count == 2


def test_raises_after_all_retries_exhausted_validation_error():
    bad = json.dumps({"x": 1.0, "y": 2.0})  # missing "label" — always fails
    provider = _FakeProvider(bad)
    gen = StructuredGenerator(Point, provider=provider, max_retries=1)
    with pytest.raises(StructuredGenerationError) as exc_info:
        gen.generate({}, request_id="req-11")
    assert exc_info.value.attempts == 2


# ---------------------------------------------------------------------------
# Error hint injection
# ---------------------------------------------------------------------------


def test_error_hint_injected_into_retry_prompt_for_json_error():
    bad_json = "{{{{ definitely not json"
    provider = _FakeProvider(bad_json)
    gen = StructuredGenerator(Point, provider=provider, max_retries=1)

    with pytest.raises(StructuredGenerationError):
        gen.generate({}, request_id="req-12")

    assert len(provider.calls) == 2
    first_prompt, second_prompt = provider.calls
    assert len(second_prompt) > len(first_prompt)
    assert "valid JSON" in second_prompt


def test_error_hint_injected_into_retry_prompt_for_validation_error():
    bad = json.dumps({"x": 1.0})  # missing y and label
    provider = _FakeProvider(bad)
    gen = StructuredGenerator(Point, provider=provider, max_retries=1)

    with pytest.raises(StructuredGenerationError):
        gen.generate({}, request_id="req-13")

    assert len(provider.calls) == 2
    _, second_prompt = provider.calls
    assert "validation" in second_prompt.lower()


# ---------------------------------------------------------------------------
# max_retries=0 (single attempt only)
# ---------------------------------------------------------------------------


def test_max_retries_zero_means_single_attempt():
    provider = _FakeProvider("bad-json")
    gen = StructuredGenerator(Point, provider=provider, max_retries=0)
    with pytest.raises(StructuredGenerationError) as exc_info:
        gen.generate({}, request_id="req-14")
    assert exc_info.value.attempts == 1
    assert len(provider.calls) == 1
