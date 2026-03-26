"""tests/test_local_provider.py — Unit tests for the local LLM provider.

Coverage:
  A. LocalProvider._parse_json_response — code-fence stripping
  B. LocalProvider._chat_completion — successful response
  C. LocalProvider._chat_completion — HTTP 4xx error → ProviderError
  D. LocalProvider._chat_completion — ConnectError with retry
  E. LocalProvider._chat_completion — usage token tracking
  F. LocalProvider.generate_raw — full call including JSON clean-up
  G. LocalProvider.generate_bundle — full round-trip
  H. LocalProvider.health_check — OpenAI-compatible server
  I. LocalProvider.health_check — Ollama server
  J. LocalProvider.health_check — server unreachable
  K. factory.get_provider — DECISIONDOC_PROVIDER=local
  L. /local-llm/health endpoint — not configured
  M. /local-llm/health endpoint — configured but server down
  N. /local-llm/models endpoint
  O. config — local LLM getters default values
  P. .env.example — all expected vars present
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.providers.base import ProviderError
from app.providers.local_provider import LocalProvider
from tests.async_helper import run_async


# ────────────────────────────────────────────────────────────────────────────
# Shared fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def provider() -> LocalProvider:
    return LocalProvider(
        base_url="http://localhost:11434/v1",
        model="llama3.1:8b",
        api_key="local",
        timeout=10,
        max_retries=2,
    )


def _make_openai_response(content: str, prompt_tokens: int = 10, completion_tokens: int = 20) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


# ────────────────────────────────────────────────────────────────────────────
# A. _parse_json_response
# ────────────────────────────────────────────────────────────────────────────

class TestParseJsonResponse:
    def test_plain_json_unchanged(self, provider):
        raw = '{"key": "value"}'
        assert provider._parse_json_response(raw) == '{"key": "value"}'

    def test_strips_json_code_fence(self, provider):
        raw = "```json\n{\"key\": \"value\"}\n```"
        assert provider._parse_json_response(raw) == '{"key": "value"}'

    def test_strips_bare_code_fence(self, provider):
        raw = "```\n{\"key\": \"value\"}\n```"
        assert provider._parse_json_response(raw) == '{"key": "value"}'

    def test_strips_and_trims_whitespace(self, provider):
        raw = "  ```json\n  {\"x\": 1}  \n```  "
        result = provider._parse_json_response(raw)
        assert result.strip() == '{"x": 1}'

    def test_empty_string(self, provider):
        assert provider._parse_json_response("") == ""


# ────────────────────────────────────────────────────────────────────────────
# B. _chat_completion — successful response
# ────────────────────────────────────────────────────────────────────────────

class TestChatCompletionSuccess:
    def test_returns_content_string(self, provider):
        resp_data = _make_openai_response('{"result": "ok"}')
        mock_response = MagicMock()
        mock_response.json.return_value = resp_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = provider._chat_completion(
                [{"role": "user", "content": "hello"}]
            )

        assert result == '{"result": "ok"}'

    def test_records_usage_tokens(self, provider):
        resp_data = _make_openai_response('{"x": 1}', prompt_tokens=5, completion_tokens=15)
        mock_response = MagicMock()
        mock_response.json.return_value = resp_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            provider._chat_completion([{"role": "user", "content": "test"}])

        usage = provider.consume_usage_tokens()
        assert usage is not None
        assert usage["prompt_tokens"] == 5
        assert usage["output_tokens"] == 15
        assert usage["total_tokens"] == 20

    def test_no_usage_key_does_not_crash(self, provider):
        resp_data = {"choices": [{"message": {"content": "hi"}}]}
        mock_response = MagicMock()
        mock_response.json.return_value = resp_data
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.return_value = mock_response

            result = provider._chat_completion([{"role": "user", "content": "x"}])

        assert result == "hi"


# ────────────────────────────────────────────────────────────────────────────
# C. _chat_completion — HTTP error → ProviderError
# ────────────────────────────────────────────────────────────────────────────

class TestChatCompletionHttpError:
    def test_http_4xx_raises_provider_error(self, provider):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        http_err = httpx.HTTPStatusError(
            "401 Unauthorized", request=MagicMock(), response=mock_response
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = http_err

            with pytest.raises(ProviderError, match="401"):
                provider._chat_completion([{"role": "user", "content": "x"}])

    def test_http_error_message_contains_response_text(self, provider):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        http_err = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=mock_response
        )

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = http_err

            with pytest.raises(ProviderError) as exc_info:
                provider._chat_completion([{"role": "user", "content": "x"}])

        assert "500" in str(exc_info.value)
        assert "Internal Server Error" in str(exc_info.value)


# ────────────────────────────────────────────────────────────────────────────
# D. _chat_completion — ConnectError with retry
# ────────────────────────────────────────────────────────────────────────────

class TestChatCompletionRetry:
    def test_connect_error_raises_after_max_retries(self, provider):
        """ConnectError should trigger retries and eventually raise ProviderError."""
        p = LocalProvider(
            base_url="http://localhost:11434/v1",
            model="llama3.1:8b",
            max_retries=2,
            timeout=5,
        )
        connect_err = httpx.ConnectError("Connection refused")

        with patch("httpx.Client") as mock_client_cls, \
             patch("time.sleep"):  # skip actual sleep
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = connect_err

            with pytest.raises(ProviderError, match="unreachable"):
                p._chat_completion([{"role": "user", "content": "x"}])

        assert mock_client.post.call_count == 2  # max_retries attempts

    def test_connect_error_succeeds_on_retry(self):
        """If the second attempt succeeds, no error is raised."""
        p = LocalProvider(max_retries=2, timeout=5)
        connect_err = httpx.ConnectError("Connection refused")
        success_response = MagicMock()
        success_response.json.return_value = _make_openai_response('{"ok":true}')
        success_response.raise_for_status = MagicMock()

        with patch("httpx.Client") as mock_client_cls, \
             patch("time.sleep"):
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.post.side_effect = [connect_err, success_response]

            result = p._chat_completion([{"role": "user", "content": "x"}])

        assert result == '{"ok":true}'


# ────────────────────────────────────────────────────────────────────────────
# E. generate_raw
# ────────────────────────────────────────────────────────────────────────────

class TestGenerateRaw:
    def test_strips_code_fence_from_response(self, provider):
        raw_with_fence = "```json\n{\"sections\": []}\n```"
        with patch.object(provider, "_chat_completion", return_value=raw_with_fence):
            result = provider.generate_raw("prompt", request_id="req-1")
        assert result == '{"sections": []}'

    def test_resets_usage_tokens_before_call(self, provider):
        provider._set_usage_tokens({"prompt_tokens": 999})
        with patch.object(provider, "_chat_completion", return_value='{"x":1}'):
            provider.generate_raw("p", request_id="r")
        # usage was reset inside generate_raw before _chat_completion ran
        # (the mock returns no usage, so now it should be None)
        assert provider.consume_usage_tokens() is None


# ────────────────────────────────────────────────────────────────────────────
# F. generate_bundle
# ────────────────────────────────────────────────────────────────────────────

class TestGenerateBundle:
    def test_returns_parsed_dict(self, provider):
        bundle_json = '{"title": "Test", "sections": []}'
        with patch.object(provider, "generate_raw", return_value=bundle_json):
            result = provider.generate_bundle(
                {"title": "Test"},
                schema_version="v1",
                request_id="req-1",
            )
        assert isinstance(result, dict)
        assert result["title"] == "Test"

    def test_invalid_json_raises_provider_error(self, provider):
        with patch.object(provider, "generate_raw", return_value="NOT JSON"):
            with pytest.raises(ProviderError):
                provider.generate_bundle(
                    {"title": "Test"},
                    schema_version="v1",
                    request_id="req-2",
                )


# ────────────────────────────────────────────────────────────────────────────
# G. health_check — OpenAI-compatible server
# ────────────────────────────────────────────────────────────────────────────

class TestHealthCheck:
    def test_openai_endpoint_ok(self, provider):
        models_response = {"data": [{"id": "llama3.1:8b"}, {"id": "qwen2.5:14b"}]}
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = models_response

        async def mock_get(*args, **kwargs):
            return mock_resp

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = run_async(provider.health_check())

        assert result["status"] == "ok"
        assert "llama3.1:8b" in result["available_models"]

    def test_ollama_fallback_ok(self, provider):
        """If /models returns non-200, falls back to Ollama /api/tags."""
        ollama_response = {"models": [{"name": "llama3.1:8b"}, {"name": "qwen2.5:14b"}]}

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            if "/models" in url:
                resp.status_code = 404
            else:
                resp.status_code = 200
                resp.json.return_value = ollama_response
            return resp

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = run_async(provider.health_check())

        assert result["status"] == "ok"
        assert result.get("type") == "ollama"
        assert "llama3.1:8b" in result["available_models"]

    def test_server_unreachable_returns_error(self):
        p = LocalProvider(base_url="http://localhost:19999/v1")

        async def mock_get(*args, **kwargs):
            raise httpx.ConnectError("Connection refused")

        mock_client = AsyncMock()
        mock_client.get = mock_get
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = run_async(p.health_check())

        assert result["status"] == "error"
        assert "hint" in result


# ────────────────────────────────────────────────────────────────────────────
# H. factory.get_provider — DECISIONDOC_PROVIDER=local
# ────────────────────────────────────────────────────────────────────────────

class TestFactory:
    def test_returns_local_provider_when_env_set(self, monkeypatch):
        monkeypatch.setenv("DECISIONDOC_PROVIDER", "local")
        monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
        monkeypatch.setenv("LOCAL_LLM_MODEL", "llama3.1:8b")

        from app.providers.factory import get_provider

        provider = get_provider()
        assert isinstance(provider, LocalProvider)

    def test_local_provider_uses_env_url(self, monkeypatch):
        monkeypatch.setenv("DECISIONDOC_PROVIDER", "local")
        monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://custom-host:8000/v1")
        monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:14b")

        from app.providers.factory import get_provider

        provider = get_provider()
        assert isinstance(provider, LocalProvider)
        assert provider.base_url == "http://custom-host:8000/v1"
        assert provider.model == "qwen2.5:14b"


# ────────────────────────────────────────────────────────────────────────────
# I. /local-llm/health endpoint
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client_mock(tmp_path_factory):
    """TestClient with DECISIONDOC_PROVIDER=mock (local LLM not configured)."""
    import os
    from starlette.testclient import TestClient
    from app.main import create_app

    old_env = os.environ.copy()
    os.environ["DECISIONDOC_PROVIDER"] = "mock"
    os.environ["DECISIONDOC_ENV"] = "dev"
    os.environ["DECISIONDOC_MAINTENANCE"] = "0"
    os.environ["DATA_DIR"] = str(tmp_path_factory.mktemp("local-llm-mock"))
    os.environ.pop("DECISIONDOC_API_KEY", None)
    os.environ.pop("DECISIONDOC_API_KEYS", None)

    client = TestClient(create_app())
    yield client

    os.environ.clear()
    os.environ.update(old_env)


@pytest.fixture(scope="module")
def client_local(tmp_path_factory):
    """TestClient with DECISIONDOC_PROVIDER=local."""
    import os
    from starlette.testclient import TestClient

    old_env = os.environ.copy()
    os.environ["DECISIONDOC_PROVIDER"] = "local"
    os.environ["LOCAL_LLM_BASE_URL"] = "http://localhost:19999/v1"  # nothing listening
    os.environ["LOCAL_LLM_MODEL"] = "llama3.1:8b"

    from app.main import create_app
    c = TestClient(create_app())

    # Restore env after yield
    yield c

    os.environ.clear()
    os.environ.update(old_env)


class TestLocalLLMHealthEndpoint:
    def test_not_configured_returns_200(self, client_mock):
        res = client_mock.get("/local-llm/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "not_configured"

    def test_not_configured_message_present(self, client_mock):
        res = client_mock.get("/local-llm/health")
        assert "message" in res.json()

    def test_configured_unreachable_returns_503(self, client_local):
        # The local server at port 19999 is not running
        res = client_local.get("/local-llm/health")
        assert res.status_code == 503
        assert res.json()["status"] == "error"


# ────────────────────────────────────────────────────────────────────────────
# J. /local-llm/models endpoint
# ────────────────────────────────────────────────────────────────────────────

class TestLocalLLMModelsEndpoint:
    def test_models_endpoint_returns_dict(self, client_mock):
        res = client_mock.get("/local-llm/models")
        assert res.status_code == 200
        data = res.json()
        assert "models" in data
        assert "current" in data

    def test_models_current_uses_env(self, client_mock, monkeypatch):
        monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen2.5:14b")
        # Re-request; current model is read from env at request time
        res = client_mock.get("/local-llm/models")
        assert res.status_code == 200

    def test_models_list_is_list(self, client_mock):
        res = client_mock.get("/local-llm/models")
        assert isinstance(res.json()["models"], list)


# ────────────────────────────────────────────────────────────────────────────
# K. config — local LLM getters default values
# ────────────────────────────────────────────────────────────────────────────

class TestConfigLocalLLM:
    def test_base_url_default(self, monkeypatch):
        monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
        from app.config import get_local_llm_base_url
        assert get_local_llm_base_url() == "http://localhost:11434/v1"

    def test_model_default(self, monkeypatch):
        monkeypatch.delenv("LOCAL_LLM_MODEL", raising=False)
        from app.config import get_local_llm_model
        assert get_local_llm_model() == "llama3.1:8b"

    def test_timeout_default(self, monkeypatch):
        monkeypatch.delenv("LOCAL_LLM_TIMEOUT", raising=False)
        from app.config import get_local_llm_timeout
        assert get_local_llm_timeout() == 300

    def test_api_key_default(self, monkeypatch):
        monkeypatch.delenv("LOCAL_LLM_API_KEY", raising=False)
        from app.config import get_local_llm_api_key
        assert get_local_llm_api_key() == "local"

    def test_base_url_from_env(self, monkeypatch):
        monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://myserver:8000/v1")
        from app.config import get_local_llm_base_url
        assert get_local_llm_base_url() == "http://myserver:8000/v1"

    def test_model_from_env(self, monkeypatch):
        monkeypatch.setenv("LOCAL_LLM_MODEL", "mistral:7b")
        from app.config import get_local_llm_model
        assert get_local_llm_model() == "mistral:7b"

    def test_timeout_from_env(self, monkeypatch):
        monkeypatch.setenv("LOCAL_LLM_TIMEOUT", "600")
        from app.config import get_local_llm_timeout
        assert get_local_llm_timeout() == 600


# ────────────────────────────────────────────────────────────────────────────
# L. .env.example — required vars present
# ────────────────────────────────────────────────────────────────────────────

class TestEnvExample:
    @pytest.fixture(scope="class")
    def env_content(self):
        import pathlib
        p = pathlib.Path(__file__).parent.parent / ".env.example"
        return p.read_text(encoding="utf-8")

    REQUIRED_VARS = [
        "LOCAL_LLM_BASE_URL",
        "LOCAL_LLM_MODEL",
        "LOCAL_LLM_API_KEY",
        "LOCAL_LLM_TIMEOUT",
        "DECISIONDOC_PROVIDER",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "DECISIONDOC_SEARCH_ENABLED",
        "SERPER_API_KEY",
        "BRAVE_API_KEY",
        "TAVILY_API_KEY",
        "DECISIONDOC_LLM_JUDGE_MODEL",
        "FINETUNE_MIN_RATING",
        "AUTO_EXPAND_THRESHOLD",
    ]

    @pytest.mark.parametrize("var", REQUIRED_VARS)
    def test_var_present(self, env_content, var):
        assert var in env_content, f"Missing env var in .env.example: {var}"
