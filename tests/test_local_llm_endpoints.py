"""Zero-network regression tests for the local LLM read-only endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.providers.local_provider import LocalProvider
from app.routers.local_llm import router


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_local_llm_endpoints_are_stably_not_configured_without_clients(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.delenv("DECISIONDOC_PROVIDER_GENERATION", raising=False)
    expected = {
        "status": "not_configured",
        "message": (
            "Set DECISIONDOC_PROVIDER_GENERATION=local or "
            "DECISIONDOC_PROVIDER=local to enable local LLM."
        ),
    }

    with (
        patch("app.routers.local_llm.LocalProvider") as local_provider,
        patch("app.providers.local_provider.httpx.AsyncClient") as http_client,
    ):
        health = client.get("/local-llm/health")
        models = client.get("/local-llm/models")

    assert health.status_code == 200
    assert health.json() == expected
    assert models.status_code == 200
    assert models.json() == expected
    local_provider.assert_not_called()
    http_client.assert_not_called()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://paid-llm.example.com/v1",
        "http://local-user:local-password@localhost:11434/v1",
        "http://localhost:11434/v1?api_key=local-query-secret",
        "http://localhost:11434/v1#local-fragment",
    ],
)
def test_local_llm_endpoints_reject_unsafe_free_mode_configuration_without_network(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    monkeypatch.setenv("DECISIONDOC_FREE_MODE", "1")
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", endpoint)
    expected = {
        "status": "configuration_error",
        "message": "Local LLM configuration is invalid.",
    }

    with (
        patch("app.providers.local_provider.httpx.Client") as sync_client,
        patch("app.providers.local_provider.httpx.AsyncClient") as async_client,
    ):
        health = client.get("/local-llm/health")
        models = client.get("/local-llm/models")

    assert health.status_code == 503
    assert health.json() == expected
    assert models.status_code == 503
    assert models.json() == expected
    sync_client.assert_not_called()
    async_client.assert_not_called()


@pytest.mark.parametrize(
    "generation_chain",
    ["local", "local,mock", "mock,local"],
)
def test_capability_local_provider_health_and_models_use_shared_health_path(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    generation_chain: str,
) -> None:
    monkeypatch.setenv("DECISIONDOC_FREE_MODE", "1")
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", generation_chain)
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:14b")
    health_result = {
        "status": "ok",
        "endpoint": "http://127.0.0.1:11434/v1",
        "model": "qwen2.5:14b",
        "available_models": ["qwen2.5:14b", "llama3.1:8b"],
    }

    with (
        patch.object(
            LocalProvider,
            "health_check",
            new=AsyncMock(return_value=health_result),
        ) as health_check,
        patch("app.providers.local_provider.httpx.AsyncClient") as http_client,
    ):
        health = client.get("/local-llm/health")
        models = client.get("/local-llm/models")

    assert health.status_code == 200
    assert health.json() == health_result
    assert models.status_code == 200
    assert models.json() == {
        "models": ["qwen2.5:14b", "llama3.1:8b"],
        "current": "qwen2.5:14b",
    }
    assert health_check.await_count == 2
    http_client.assert_not_called()
