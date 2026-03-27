"""Tests for SearchService — unit tests without real HTTP calls."""
import os
from unittest.mock import MagicMock, patch

import pytest


def test_search_service_not_available_by_default():
    """SearchService is disabled when DECISIONDOC_SEARCH_ENABLED is not set."""
    from app.services.search_service import SearchService
    # Ensure no keys are set
    env = {k: v for k, v in os.environ.items()
           if k not in ("SERPER_API_KEY", "BRAVE_API_KEY", "TAVILY_API_KEY",
                        "DECISIONDOC_SEARCH_ENABLED")}
    with patch.dict(os.environ, env, clear=True):
        svc = SearchService()
        assert not svc.is_available()


def test_search_service_not_available_without_key(monkeypatch):
    """SearchService is unavailable even when enabled if no API key is set."""
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "1")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from app.services.search_service import SearchService
    svc = SearchService()
    assert not svc.is_available()


def test_search_returns_empty_when_disabled():
    """search() returns [] when service is not available."""
    from app.services.search_service import SearchService
    svc = SearchService()
    svc._enabled = False
    results = svc.search("test query")
    assert results == []


def test_search_service_detects_serper_key(monkeypatch):
    """SearchService detects SERPER_API_KEY and sets provider to serper."""
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "1")
    monkeypatch.setenv("SERPER_API_KEY", "test-key-123")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    from app.services.search_service import SearchService
    svc = SearchService()
    assert svc.is_available()
    assert svc._provider == "serper"


def test_search_gracefully_handles_http_error(monkeypatch):
    """search() returns [] on HTTP error (graceful degradation)."""
    monkeypatch.setenv("DECISIONDOC_SEARCH_ENABLED", "1")
    monkeypatch.setenv("SERPER_API_KEY", "test-key-123")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    import httpx
    from app.services.search_service import SearchService

    svc = SearchService()
    with patch.object(httpx, "post", side_effect=httpx.ConnectError("connection refused")):
        results = svc.search("test query")
    assert results == []
