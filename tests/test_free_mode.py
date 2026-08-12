from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.providers.base import ProviderError
from app.providers.claude_provider import ClaudeProvider
from app.providers.factory import configured_provider_names, get_provider
from app.providers.gemini_provider import GeminiProvider
from app.providers.local_provider import LocalProvider
from app.providers.openai_provider import OpenAIProvider
from app.storage.base import StorageFailedError
from app.storage.factory import get_storage
from app.storage.state_backend import StateBackendError, get_state_backend
from scripts.run_free_local import build_free_environment


REPO_ROOT = Path(__file__).resolve().parents[1]


def _enable_free_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISIONDOC_FREE_MODE", "1")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    for name in (
        "DECISIONDOC_PROVIDER_GENERATION",
        "DECISIONDOC_PROVIDER_ATTACHMENT",
        "DECISIONDOC_PROVIDER_VISUAL",
    ):
        monkeypatch.delenv(name, raising=False)


def test_free_mode_rejects_cloud_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_free_mode(monkeypatch)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")

    with pytest.raises(ProviderError, match="Free mode allows only mock or local providers"):
        configured_provider_names()


def test_free_mode_rejects_cloud_capability_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_free_mode(monkeypatch)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_PROVIDER_GENERATION", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    with pytest.raises(ProviderError, match="Free mode allows only mock or local providers"):
        configured_provider_names()


def test_free_mode_rejects_remote_local_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_free_mode(monkeypatch)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "https://paid-llm.example.com/v1")

    with pytest.raises(ProviderError, match="Free mode local LLM must use a local endpoint"):
        get_provider()


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://paid-llm.example.com/v1",
        "http://local-user:local-password@localhost:11434/v1",
        "http://localhost:11434/v1?api_key=local-query-secret",
        "http://localhost:11434/v1#local-fragment",
    ],
)
def test_free_mode_rejects_direct_local_provider_before_http_client(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    _enable_free_mode(monkeypatch)

    with (
        patch("app.providers.local_provider.httpx.Client") as sync_client,
        patch("app.providers.local_provider.httpx.AsyncClient") as async_client,
        pytest.raises(ProviderError, match="Free mode local LLM must use a local endpoint"),
    ):
        LocalProvider(base_url=endpoint)

    sync_client.assert_not_called()
    async_client.assert_not_called()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/v1",
        "http://[::1]:11434/v1",
        "http://ollama:11434/v1",
        "https://host.docker.internal:11434/v1",
    ],
)
def test_free_mode_allows_documented_local_provider_hosts(
    monkeypatch: pytest.MonkeyPatch,
    endpoint: str,
) -> None:
    _enable_free_mode(monkeypatch)

    with (
        patch("app.providers.local_provider.httpx.Client") as sync_client,
        patch("app.providers.local_provider.httpx.AsyncClient") as async_client,
    ):
        provider = LocalProvider(base_url=endpoint)

    assert provider.base_url == endpoint
    sync_client.assert_not_called()
    async_client.assert_not_called()


@pytest.mark.parametrize(
    ("provider_class", "key_name"),
    [
        (OpenAIProvider, "OPENAI_API_KEY"),
        (GeminiProvider, "GEMINI_API_KEY"),
        (ClaudeProvider, "ANTHROPIC_API_KEY"),
    ],
)
def test_free_mode_rejects_direct_cloud_provider_construction(
    monkeypatch: pytest.MonkeyPatch,
    provider_class: type,
    key_name: str,
) -> None:
    _enable_free_mode(monkeypatch)
    monkeypatch.setenv(key_name, "test-provider-key")

    with pytest.raises(ProviderError, match="Cloud providers are disabled in free mode"):
        provider_class()


def test_free_mode_allows_mock_with_local_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_free_mode(monkeypatch)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    assert get_provider().name == "mock"
    assert get_storage().__class__.__name__ == "LocalStorage"
    assert get_state_backend(data_dir=tmp_path).__class__.__name__ == "LocalStateBackend"


def test_health_reports_free_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_free_mode(monkeypatch)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")

    from app.main import create_app

    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json()["free_mode"] is True


def test_free_mode_rejects_s3_bundle_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_free_mode(monkeypatch)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "s3")
    monkeypatch.setattr("app.storage.factory.s3_from_env", lambda: object())

    with pytest.raises(StorageFailedError, match="Free mode requires local storage"):
        get_storage()


def test_free_mode_rejects_s3_state_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _enable_free_mode(monkeypatch)
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "s3")
    monkeypatch.setenv("DECISIONDOC_S3_BUCKET", "test-bucket")
    monkeypatch.setattr("app.storage.state_backend.S3StateBackend", lambda **_: object())

    with pytest.raises(StateBackendError, match="Free mode requires local state storage"):
        get_state_backend(data_dir=tmp_path)


def test_free_local_runner_prints_cost_safe_environment(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_free_local.py",
            "--provider",
            "mock",
            "--data-dir",
            str(tmp_path),
            "--print-env",
        ],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "OPENAI_API_KEY": "must-not-be-printed",
            "LOCAL_LLM_BASE_URL": (
                "http://local-user:local-password@localhost:11434/v1"
                "?api_key=local-query-secret"
            ),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "DECISIONDOC_FREE_MODE=1" in result.stdout
    assert "DECISIONDOC_PROVIDER=mock" in result.stdout
    assert "DECISIONDOC_STORAGE=local" in result.stdout
    assert "DECISIONDOC_STATE_STORAGE=local" in result.stdout
    assert "must-not-be-printed" not in result.stdout
    assert "local-password" not in result.stdout
    assert "local-query-secret" not in result.stdout
    assert "LOCAL_LLM_BASE_URL=http://localhost:11434/v1" in result.stdout


def test_free_local_runner_defaults_local_provider_to_loopback_ollama(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_free_local.py",
            "--provider",
            "local",
            "--data-dir",
            str(tmp_path),
            "--print-env",
        ],
        cwd=REPO_ROOT,
        env={key: value for key, value in os.environ.items() if key != "LOCAL_LLM_BASE_URL"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "DECISIONDOC_PROVIDER_GENERATION=local" in result.stdout
    assert "DECISIONDOC_PROVIDER_ATTACHMENT=mock" in result.stdout
    assert "DECISIONDOC_PROVIDER_VISUAL=mock" in result.stdout
    assert "LOCAL_LLM_BASE_URL=http://localhost:11434/v1" in result.stdout


def test_free_local_environment_disables_inherited_external_actions(
    tmp_path: Path,
) -> None:
    env = build_free_environment(
        {
            "AWS_PROFILE": "paid-profile",
            "AWS_CONTAINER_CREDENTIALS_FULL_URI": "http://169.254.170.2/credentials",
            "DECISIONDOC_OPS_KEY": "ops-key",
            "DECISIONDOC_SEARCH_ENABLED": "1",
            "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED": "1",
            "G2B_API_KEY": "g2b-key",
            "SLACK_WEBHOOK_URL": "https://hooks.slack.example/test",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PASSWORD": "smtp-password",
            "STRIPE_SECRET_KEY": "stripe-key",
            "VOICE_BRIEF_API_BASE_URL": "https://voice.example.com",
        },
        provider="mock",
        data_dir=tmp_path,
    )

    assert env["DECISIONDOC_OPS_KEY"] == ""
    assert env["DECISIONDOC_SEARCH_ENABLED"] == "0"
    assert env["DECISIONDOC_PROCUREMENT_COPILOT_ENABLED"] == "0"
    assert env["G2B_API_KEY"] == ""
    assert env["SLACK_WEBHOOK_URL"] == ""
    assert env["SMTP_HOST"] == ""
    assert env["SMTP_PASSWORD"] == ""
    assert env["STRIPE_SECRET_KEY"] == ""
    assert env["VOICE_BRIEF_API_BASE_URL"] == ""
    assert env["AWS_EC2_METADATA_DISABLED"] == "true"
    assert env["AWS_SHARED_CREDENTIALS_FILE"] == os.devnull
    assert env["AWS_CONFIG_FILE"] == os.devnull
    assert "AWS_PROFILE" not in env
    assert "AWS_CONTAINER_CREDENTIALS_FULL_URI" not in env


def test_free_local_environment_replaces_blank_local_llm_defaults(
    tmp_path: Path,
) -> None:
    env = build_free_environment(
        {
            "LOCAL_LLM_BASE_URL": "",
            "LOCAL_LLM_MODEL": "",
            "LOCAL_LLM_API_KEY": "",
        },
        provider="local",
        data_dir=tmp_path,
    )

    assert env["LOCAL_LLM_BASE_URL"] == "http://localhost:11434/v1"
    assert env["LOCAL_LLM_MODEL"] == "llama3.1:8b"
    assert env["LOCAL_LLM_API_KEY"] == "local"


def test_free_local_environment_replaces_inherited_remote_local_llm_url(
    tmp_path: Path,
) -> None:
    env = build_free_environment(
        {
            "LOCAL_LLM_BASE_URL": "https://paid-llm.example.com/v1",
            "LOCAL_LLM_MODEL": "local-model",
        },
        provider="local",
        data_dir=tmp_path,
    )

    assert env["LOCAL_LLM_BASE_URL"] == "http://localhost:11434/v1"
    assert "paid-llm.example.com" not in env["LOCAL_LLM_BASE_URL"]


def test_development_compose_defaults_to_free_mode() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "DECISIONDOC_FREE_MODE=${DECISIONDOC_FREE_MODE:-1}" in compose
    assert "DECISIONDOC_PROVIDER=${DECISIONDOC_PROVIDER:-mock}" in compose
    assert "DECISIONDOC_STORAGE=${DECISIONDOC_STORAGE:-local}" in compose
    assert "DECISIONDOC_STATE_STORAGE=${DECISIONDOC_STATE_STORAGE:-local}" in compose
