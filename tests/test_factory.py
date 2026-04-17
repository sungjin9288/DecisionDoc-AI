"""Tests for app/providers/factory.py — including FallbackPipeline support."""
import pytest

from app.ai.pipeline import FallbackPipeline
from app.providers.base import ProviderError
from app.providers.claude_provider import ClaudeProvider
from app.providers.factory import get_provider
from app.providers.mock_provider import MockProvider


# ---------------------------------------------------------------------------
# Single-provider cases
# ---------------------------------------------------------------------------


def test_get_provider_default_returns_mock(monkeypatch):
    monkeypatch.delenv("DECISIONDOC_PROVIDER", raising=False)
    provider = get_provider()
    assert isinstance(provider, MockProvider)


def test_get_provider_mock_returns_mock(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    provider = get_provider()
    assert isinstance(provider, MockProvider)


def test_get_provider_claude_returns_claude(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    provider = get_provider()
    assert isinstance(provider, ClaudeProvider)


def test_get_provider_unknown_raises_provider_error(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "unknown_provider")
    with pytest.raises(ProviderError):
        get_provider()


# ---------------------------------------------------------------------------
# Comma-separated FallbackPipeline cases
# ---------------------------------------------------------------------------


def test_get_provider_single_name_returns_single_provider(monkeypatch):
    """A single name must NOT be wrapped in FallbackPipeline."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    provider = get_provider()
    assert not isinstance(provider, FallbackPipeline)
    assert isinstance(provider, MockProvider)


def test_get_provider_comma_two_mocks_returns_fallback_pipeline(monkeypatch):
    """Two comma-separated names → FallbackPipeline."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock,mock")
    provider = get_provider()
    assert isinstance(provider, FallbackPipeline)


def test_get_provider_comma_pipeline_has_correct_provider_count(monkeypatch):
    """Comma-separated list must build a pipeline with the right number of providers."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock,mock,mock")
    provider = get_provider()
    assert isinstance(provider, FallbackPipeline)
    assert len(provider._providers) == 3


def test_get_provider_comma_pipeline_uses_mock(monkeypatch):
    """FallbackPipeline from mock,mock must successfully generate a bundle."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock,mock")
    provider = get_provider()
    assert isinstance(provider, FallbackPipeline)
    bundle = provider.generate_bundle({}, schema_version="v1", request_id="test")
    assert "adr" in bundle


def test_get_provider_comma_with_spaces_is_trimmed(monkeypatch):
    """Spaces around provider names must be stripped."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", " mock , mock ")
    provider = get_provider()
    assert isinstance(provider, FallbackPipeline)


def test_get_provider_name_attribute_single(monkeypatch):
    """Single mock provider must report name='mock'."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    assert get_provider().name == "mock"


def test_get_provider_name_attribute_pipeline(monkeypatch):
    """FallbackPipeline must report name='fallback'."""
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock,mock")
    assert get_provider().name == "fallback"


def test_get_provider_claude_pipeline_trims_spaces(monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", " mock , claude ")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    provider = get_provider()
    assert isinstance(provider, FallbackPipeline)
    assert [p.name for p in provider._providers] == ["mock", "claude"]
