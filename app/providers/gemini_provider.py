import json
import os
from typing import Any

import anyio

from app.domain.schema import build_bundle_prompt
from app.providers.base import Provider, ProviderError, UsageTokenMixin


class GeminiProvider(UsageTokenMixin, Provider):
    name = "gemini"

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ProviderError("Provider configuration error.")

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        """Call Gemini and return the raw text response.

        Token usage is captured via _set_usage_tokens() before returning.

        Raises:
            ProviderError: on SDK import failure, empty response, API error, or timeout.
        """
        # Reset stale token state from any previous call before making a new one.
        self._set_usage_tokens(None)

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ProviderError("Provider SDK unavailable.") from exc

        try:
            client = genai.Client(api_key=self.api_key)

            _timeout = int(os.getenv("DECISIONDOC_PROVIDER_TIMEOUT", "120"))
            # Priority: explicit kwarg > env var
            effective_max = max_output_tokens or (
                int(v) if (v := os.getenv("DECISIONDOC_MAX_OUTPUT_TOKENS")) else None
            )
            _gen_config = types.GenerateContentConfig(
                response_mime_type="application/json",
                **({"max_output_tokens": effective_max} if effective_max else {}),
            )

            async def _call_with_timeout():
                with anyio.fail_after(_timeout):
                    return await anyio.to_thread.run_sync(
                        lambda: client.models.generate_content(
                            model=os.getenv("DECISIONDOC_GEMINI_MODEL", "gemini-2.0-flash"),
                            contents=prompt,
                            config=_gen_config,
                        )
                    )

            response = anyio.run(_call_with_timeout)
            usage = getattr(response, "usage_metadata", None)
            usage_map: dict[str, int] | None = None
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_token_count", None)
                output_tokens = getattr(usage, "candidates_token_count", None)
                total_tokens = getattr(usage, "total_token_count", None)
                if isinstance(prompt_tokens, int) or isinstance(output_tokens, int) or isinstance(total_tokens, int):
                    usage_map = {
                        "prompt_tokens": int(prompt_tokens or 0),
                        "output_tokens": int(output_tokens or 0),
                        "total_tokens": int(total_tokens or 0),
                    }
            self._set_usage_tokens(usage_map)
            raw = response.text
            if not raw:
                raise ProviderError("Provider returned empty response.")
            return raw
        except ProviderError:
            raise
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
