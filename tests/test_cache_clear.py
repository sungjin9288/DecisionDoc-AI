"""Tests for GenerationService.clear_cache() and POST /ops/cache/clear."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.providers.factory import get_provider
from app.schemas import GenerateRequest
from app.services.generation_service import GenerationService


def _make_service(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_CACHE_ENABLED", "1")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    template_dir = Path("app/templates/v1")
    return GenerationService(
        provider_factory=get_provider,
        template_dir=template_dir,
        data_dir=tmp_path,
    )


def test_clear_cache_removes_json_files(tmp_path, monkeypatch):
    """clear_cache() removes all *.json files in the cache directory."""
    service = _make_service(tmp_path, monkeypatch)
    payload = GenerateRequest(title="cache clear test", goal="verify clear_cache")
    service.generate_documents(payload, request_id="cc-req-1")

    cache_files = list(service.cache_dir.glob("*.json"))
    assert len(cache_files) >= 1

    removed = service.clear_cache()
    assert removed >= 1
    assert list(service.cache_dir.glob("*.json")) == []


def test_clear_cache_returns_correct_count(tmp_path, monkeypatch):
    """clear_cache() returns the count of files removed."""
    service = _make_service(tmp_path, monkeypatch)
    service.generate_documents(
        GenerateRequest(title="t1", goal="g1"), request_id="cc-1"
    )
    service.generate_documents(
        GenerateRequest(title="t2", goal="g2"), request_id="cc-2"
    )
    count_before = len(list(service.cache_dir.glob("*.json")))
    removed = service.clear_cache()
    assert removed == count_before


def test_clear_cache_on_empty_returns_zero(tmp_path, monkeypatch):
    """clear_cache() returns 0 when cache is already empty."""
    service = _make_service(tmp_path, monkeypatch)
    assert service.clear_cache() == 0


# ── Integration tests: POST /ops/cache/clear ─────────────────────


def _create_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "test-ops-key")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    from app.main import create_app

    return TestClient(create_app())


def test_cache_clear_endpoint_requires_ops_key(tmp_path, monkeypatch):
    """POST /ops/cache/clear without ops key returns 401."""
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/ops/cache/clear")
    assert response.status_code == 401


def test_cache_clear_endpoint_returns_cleared_count(tmp_path, monkeypatch):
    """POST /ops/cache/clear with valid ops key returns success."""
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/ops/cache/clear",
        headers={"X-DecisionDoc-Ops-Key": "test-ops-key"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cleared"] is True
    assert isinstance(body["files_removed"], int)
