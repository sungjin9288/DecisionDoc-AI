import json
import os
from typing import Any

import anyio

from app.domain.schema import BUNDLE_JSON_SCHEMA_V1
from app.providers.base import Provider, ProviderError


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self) -> None:
        self.api_key = os.getenv("GEMINI_API_KEY", "")
        self._last_usage_tokens: dict[str, int] | None = None
        if not self.api_key:
            raise ProviderError("Provider configuration error.")

    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
    ) -> dict[str, Any]:
        try:
            from google import genai
            from google.genai import types
        except Exception as exc:  # pragma: no cover - env dependent
            raise ProviderError("Provider SDK unavailable.") from exc

        prompt = (
            "Return ONLY JSON matching this schema. No markdown.\n"
            "Stability checklist:\n"
            "- Return one JSON bundle object only.\n"
            "- Include top-level keys: adr, onepager, eval_plan, ops_checklist.\n"
            "- Include required fields for each doc section per schema.\n"
            "- Do not include TODO/TBD/FIXME.\n"
            "- Keep each doc section sufficiently detailed (target >= 600 chars per doc after rendering).\n"
            "- Output JSON only, no markdown.\n"
            f"schema_version={schema_version}\n"
            f"schema={json.dumps(BUNDLE_JSON_SCHEMA_V1, ensure_ascii=False)}\n"
            f"requirements={json.dumps(requirements, ensure_ascii=False)}"
        )

        try:
            client = genai.Client(api_key=self.api_key)
            async def _call_with_timeout():
                with anyio.fail_after(20):
                    return await anyio.to_thread.run_sync(
                        lambda: client.models.generate_content(
                            model=os.getenv("DECISIONDOC_GEMINI_MODEL", "gemini-1.5-flash"),
                            contents=prompt,
                            config=types.GenerateContentConfig(response_mime_type="application/json"),
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
            self._last_usage_tokens = usage_map
            return json.loads(response.text or "{}")
        except Exception as exc:  # pragma: no cover - network dependent
            raise ProviderError("Provider request failed.") from exc

    def consume_usage_tokens(self) -> dict[str, int] | None:
        usage = self._last_usage_tokens
        self._last_usage_tokens = None
        return usage
