"""app/providers/local_provider.py — Local LLM provider.

Supports any OpenAI-compatible local LLM server:
- Ollama  (http://localhost:11434/v1)
- vLLM    (OpenAI-compatible API)
- LM Studio (OpenAI-compatible API)
- LocalAI  (OpenAI-compatible API)

Environment variables:
    LOCAL_LLM_BASE_URL   — API base URL (default: http://localhost:11434/v1)
    LOCAL_LLM_MODEL      — Model name  (default: llama3.1:8b)
    LOCAL_LLM_API_KEY    — API key     (default: "local"; most servers ignore it)
    LOCAL_LLM_TIMEOUT    — Request timeout seconds (default: 300)
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.domain.schema import build_bundle_prompt
from app.providers.base import Provider, ProviderError, UsageTokenMixin

_log = logging.getLogger("decisiondoc.provider.local")


class LocalProvider(UsageTokenMixin, Provider):
    """OpenAI-compatible local LLM provider.

    Works with Ollama, vLLM, LM Studio, and any server that speaks the
    OpenAI chat-completions protocol.  All public methods are synchronous
    (matching the rest of the provider layer); ``health_check`` is async
    so it can be awaited from FastAPI route handlers.
    """

    name = "local"

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3.1:8b",
        api_key: str = "local",
        timeout: int = 300,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    # ── Public provider interface ────────────────────────────────────

    def generate_raw(
        self,
        prompt: str,
        *,
        request_id: str,
        max_output_tokens: int | None = None,
    ) -> str:
        """Call the local LLM and return the cleaned text response.

        Code fences (```json ... ```) are stripped so downstream callers
        can ``json.loads()`` the result directly.

        Raises:
            ProviderError: on connection failure, HTTP error, or after
                           exhausting ``max_retries`` attempts.
        """
        self._set_usage_tokens(None)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional document generation AI. "
                    "Respond ONLY with valid JSON. "
                    "No explanations, no markdown code blocks, just pure JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        raw = self._chat_completion(messages, max_tokens=max_output_tokens or 4096)
        return self._parse_json_response(raw)

    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
        bundle_spec: Any = None,
        feedback_hints: str = "",
    ) -> dict[str, Any]:
        """Build a prompt and generate a structured bundle via the local LLM.

        Raises:
            ProviderError: on LLM failure or unparseable JSON response.
        """
        prompt = build_bundle_prompt(
            requirements, schema_version, bundle_spec, feedback_hints=feedback_hints
        )
        _max = getattr(bundle_spec, "max_output_tokens", None) if bundle_spec else None
        try:
            raw = self.generate_raw(prompt, request_id=request_id, max_output_tokens=_max)
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError("Provider request failed.") from exc

    # ── Internal helpers ─────────────────────────────────────────────

    def _chat_completion(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> str:
        """POST to /chat/completions with exponential-backoff retry on ConnectError.

        Returns the raw ``content`` string from the first choice.

        Raises:
            ProviderError: on HTTP error, unexpected exception, or after all
                           retries are exhausted.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    res = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    res.raise_for_status()
                    data = res.json()

                    # Track token usage when the server reports it
                    if "usage" in data:
                        u = data["usage"]
                        self._set_usage_tokens(
                            {
                                "prompt_tokens": u.get("prompt_tokens", 0),
                                "output_tokens": u.get("completion_tokens", 0),
                                "total_tokens": u.get("total_tokens", 0),
                            }
                        )

                    return data["choices"][0]["message"]["content"]

            except httpx.ConnectError as exc:
                last_exc = exc
                _log.error(
                    "[LocalProvider] Connection failed (attempt %d/%d) to %s: %s",
                    attempt + 1,
                    self.max_retries,
                    self.base_url,
                    exc,
                )
                if attempt < self.max_retries - 1:
                    time.sleep(2**attempt)

            except httpx.HTTPStatusError as exc:
                raise ProviderError(
                    f"Local LLM returned {exc.response.status_code}: "
                    f"{exc.response.text[:200]}"
                ) from exc

            except ProviderError:
                raise

            except Exception as exc:  # pragma: no cover
                raise ProviderError(f"Local LLM error: {exc}") from exc

        raise ProviderError(
            f"Local LLM unreachable after {self.max_retries} attempts. "
            f"Is the server running at {self.base_url}?"
        ) from last_exc

    @staticmethod
    def _parse_json_response(text: str) -> str:
        """Strip markdown code fences from LLM output and return trimmed text."""
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```\s*$", "", text)
        return text.strip()

    # ── Health check (async, for FastAPI route handlers) ─────────────

    async def health_check(self) -> dict:
        """Check if the local LLM server is reachable and enumerate models.

        Tries the standard OpenAI ``/models`` endpoint first; falls back to
        the Ollama ``/api/tags`` endpoint.

        Returns a dict with ``status`` ("ok" | "error") and related info.
        """
        # 1. Try OpenAI-compatible /models endpoint
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                if res.status_code == 200:
                    models = res.json().get("data", [])
                    return {
                        "status": "ok",
                        "endpoint": self.base_url,
                        "model": self.model,
                        "available_models": [m.get("id") for m in models],
                    }
        except Exception:
            pass

        # 2. Try Ollama /api/tags endpoint
        try:
            ollama_base = self.base_url.replace("/v1", "").rstrip("/")
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(f"{ollama_base}/api/tags")
                if res.status_code == 200:
                    models = res.json().get("models", [])
                    return {
                        "status": "ok",
                        "type": "ollama",
                        "endpoint": self.base_url,
                        "model": self.model,
                        "available_models": [m.get("name") for m in models],
                    }
        except Exception as exc:
            return {
                "status": "error",
                "endpoint": self.base_url,
                "error": str(exc),
                "hint": "Is Ollama/vLLM/LM Studio running?",
            }

        return {
            "status": "error",
            "endpoint": self.base_url,
            "error": "Could not connect to local LLM server",
            "hint": "Is Ollama/vLLM/LM Studio running?",
        }
