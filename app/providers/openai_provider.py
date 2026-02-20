import json
import os
from typing import Any

import anyio

from app.domain.schema import BUNDLE_JSON_SCHEMA_V1
from app.providers.base import Provider, ProviderError


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "")
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
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover - env dependent
            raise ProviderError("Provider SDK unavailable.") from exc

        client = OpenAI(api_key=self.api_key, max_retries=0, timeout=20)
        stability_checklist = (
            "Stability checklist:\n"
            "- Return one JSON bundle object only.\n"
            "- Include top-level keys: adr, onepager, eval_plan, ops_checklist.\n"
            "- Include required fields for each doc section per schema.\n"
            "- Do not include TODO/TBD/FIXME.\n"
            "- Keep each doc section sufficiently detailed (target >= 600 chars per doc after rendering).\n"
            "- Output JSON only, no markdown."
        )
        prompt = (
            "Return ONLY JSON matching this schema. No markdown.\n"
            f"{stability_checklist}\n"
            f"schema_version={schema_version}\n"
            f"schema={json.dumps(BUNDLE_JSON_SCHEMA_V1, ensure_ascii=False)}\n"
            f"requirements={json.dumps(requirements, ensure_ascii=False)}"
        )

        try:
            async def _call_with_timeout():
                with anyio.fail_after(20):
                    return await anyio.to_thread.run_sync(
                        lambda: client.responses.create(
                            model=os.getenv("DECISIONDOC_OPENAI_MODEL", "gpt-4o-mini"),
                            input=prompt,
                            response_format={"type": "json_object"},
                        )
                    )

            response = anyio.run(_call_with_timeout)
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
            self._last_usage_tokens = usage_map
            text = response.output_text
            return json.loads(text)
        except Exception as exc:  # pragma: no cover - network dependent
            raise ProviderError("Provider request failed.") from exc

    def consume_usage_tokens(self) -> dict[str, int] | None:
        usage = self._last_usage_tokens
        self._last_usage_tokens = None
        return usage
