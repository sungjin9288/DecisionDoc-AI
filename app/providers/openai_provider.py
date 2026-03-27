import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any  # noqa: F401 — used in _create_kwargs type annotation

import anyio

from app.domain.schema import build_bundle_prompt
from app.providers.base import Provider, ProviderError, UsageTokenMixin


class OpenAIProvider(UsageTokenMixin, Provider):
    name = "openai"

    def __init__(self, model_override: str | None = None) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ProviderError("Provider configuration error.")
        self._model_override = model_override

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        """Call OpenAI and return the raw text response.

        Token usage is captured via _set_usage_tokens() before returning.

        Raises:
            ProviderError: on SDK import failure, API error, or timeout.
        """
        # Reset stale token state from any previous call before making a new one.
        self._set_usage_tokens(None)

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ProviderError("Provider SDK unavailable.") from exc

        _timeout = int(os.getenv("DECISIONDOC_PROVIDER_TIMEOUT", "120"))
        client = OpenAI(api_key=self.api_key, max_retries=0, timeout=_timeout)

        try:
            # Priority: explicit kwarg > env var
            effective_max = max_output_tokens or (
                int(v) if (v := os.getenv("DECISIONDOC_MAX_OUTPUT_TOKENS")) else None
            )
            _create_kwargs: dict[str, Any] = dict(
                model=self._model_override or os.getenv("DECISIONDOC_OPENAI_MODEL", "gpt-4o-mini"),
                input=prompt,
                text={"format": {"type": "json_object"}},
            )
            if effective_max:
                _create_kwargs["max_output_tokens"] = effective_max

            async def _call_with_timeout():
                with anyio.fail_after(_timeout):
                    return await anyio.to_thread.run_sync(
                        lambda: client.responses.create(**_create_kwargs)
                    )

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                response = anyio.run(_call_with_timeout)
            else:
                # Keep the sync provider API usable even when called under an active event loop.
                with ThreadPoolExecutor(max_workers=1) as executor:
                    response = executor.submit(anyio.run, _call_with_timeout).result()
            usage = getattr(response, "usage", None)
            usage_map: dict[str, int] | None = None
            if usage is not None:
                prompt_tokens = getattr(usage, "input_tokens", None)
                output_tokens = getattr(usage, "output_tokens", None)
                total_tokens = getattr(usage, "total_tokens", None)
                if isinstance(prompt_tokens, int) or isinstance(output_tokens, int) or isinstance(total_tokens, int):
                    usage_map = {
                        "prompt_tokens": int(prompt_tokens or 0),
                        "output_tokens": int(output_tokens or 0),
                        "total_tokens": int(total_tokens or 0),
                    }
            self._set_usage_tokens(usage_map)
            return response.output_text
        except Exception as exc:  # pragma: no cover - network dependent
            raise ProviderError("Provider request failed.") from exc

    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
        bundle_spec: Any = None,
        feedback_hints: str = "",
    ) -> dict[str, Any]:
        prompt = build_bundle_prompt(requirements, schema_version, bundle_spec, feedback_hints=feedback_hints)
        _max = getattr(bundle_spec, "max_output_tokens", None) if bundle_spec else None
        try:
            raw = self.generate_raw(prompt, request_id=request_id, max_output_tokens=_max)
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderError("Provider request failed.") from exc
