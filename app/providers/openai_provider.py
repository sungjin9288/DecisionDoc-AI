import asyncio
import base64
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

    def extract_attachment_text(self, filename: str, raw: bytes, *, request_id: str) -> str:
        self._set_usage_tokens(None)

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ProviderError("Provider SDK unavailable.") from exc

        mime_type = _detect_attachment_mime_type(filename)
        encoded_data = base64.b64encode(raw).decode("ascii")
        _timeout = int(os.getenv("DECISIONDOC_PROVIDER_TIMEOUT", "120"))
        client = OpenAI(api_key=self.api_key, max_retries=0, timeout=_timeout)
        model = os.getenv("DECISIONDOC_OPENAI_VISION_MODEL") or self._model_override or os.getenv(
            "DECISIONDOC_OPENAI_MODEL", "gpt-4o-mini"
        )
        is_pdf = mime_type == "application/pdf"
        prompt = (
            "첨부된 파일에서 사람이 읽을 수 있는 텍스트와 설득 근거가 되는 시각 요소를 추출하세요. "
            "파일이 스캔 PDF라면 OCR 결과를 우선 정리하고, 이미지/도표/표지 구성도 함께 설명하세요. "
            "아래 형식의 plain text만 반환하세요.\n"
            "[텍스트]\n"
            "- 실제로 읽히는 문구\n"
            "[시각 요소]\n"
            "- 도표/표/사진/아이콘/레이아웃의 핵심\n"
            "[활용 포인트]\n"
            "- 문서/PPT에서 어떻게 쓰면 설득력이 높아지는지 2~4개 bullet"
        )

        async def _call_with_timeout():
            with anyio.fail_after(_timeout):
                return await anyio.to_thread.run_sync(
                    lambda: client.responses.create(
                        model=model,
                        input=[{
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": prompt},
                                (
                                    {
                                        "type": "input_file",
                                        "filename": filename,
                                        "file_data": encoded_data,
                                    }
                                    if is_pdf
                                    else {
                                        "type": "input_image",
                                        "image_url": f"data:{mime_type};base64,{encoded_data}",
                                    }
                                ),
                            ],
                        }],
                        max_output_tokens=900,
                    )
                )

        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                response = anyio.run(_call_with_timeout)
            else:
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
            text = (response.output_text or "").strip()
            if not text:
                raise ProviderError("Provider returned empty response.")
            return text
        except ProviderError:
            raise
        except Exception as exc:  # pragma: no cover - network dependent
            raise ProviderError("Provider request failed.") from exc


def _detect_attachment_mime_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".heic": "image/heic",
        ".svg": "image/svg+xml",
        ".pdf": "application/pdf",
    }.get(ext, "image/png")
