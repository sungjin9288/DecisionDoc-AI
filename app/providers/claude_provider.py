import base64
import json
import os
from typing import Any

import httpx

from app.domain.schema import build_bundle_prompt
from app.providers.base import Provider, ProviderError, UsageTokenMixin


class _ClaudeAPIError(Exception):
    def __init__(self, status_code: int, body: dict[str, Any], response: httpx.Response) -> None:
        message = (
            body.get("error", {}).get("message")
            if isinstance(body.get("error"), dict)
            else None
        ) or response.text[:500] or f"Claude API returned {status_code}"
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.response = response


class ClaudeProvider(UsageTokenMixin, Provider):
    name = "claude"

    def __init__(self) -> None:
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not self.api_key:
            raise ProviderError("Provider configuration error.")
        self.base_url = os.getenv("DECISIONDOC_CLAUDE_BASE_URL", "https://api.anthropic.com/v1").rstrip("/")
        self.model = os.getenv("DECISIONDOC_CLAUDE_MODEL", "claude-sonnet-4-20250514").strip()
        self.api_version = os.getenv("DECISIONDOC_CLAUDE_API_VERSION", "2023-06-01").strip()

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        self._set_usage_tokens(None)
        effective_max = max_output_tokens or (
            int(v) if (v := os.getenv("DECISIONDOC_MAX_OUTPUT_TOKENS")) else 8192
        )
        payload = {
            "model": self.model,
            "max_tokens": effective_max,
            "system": (
                "You are a professional document generation AI. "
                "Respond ONLY with valid JSON. "
                "No markdown fences, no commentary, just a JSON object."
            ),
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }
        body = self._post_messages(payload)
        usage = body.get("usage") or {}
        if isinstance(usage, dict):
            self._set_usage_tokens(
                {
                    "prompt_tokens": int(usage.get("input_tokens", 0) or 0),
                    "output_tokens": int(usage.get("output_tokens", 0) or 0),
                    "total_tokens": int((usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0)),
                }
            )
        raw = self._extract_text(body)
        if not raw:
            raise ProviderError("Provider returned empty response.")
        return raw

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
        mime_type = _detect_attachment_mime_type(filename)
        if mime_type == "application/pdf":
            raise ProviderError("Claude provider does not support PDF OCR fallback in this deployment.")
        payload = {
            "model": os.getenv("DECISIONDOC_CLAUDE_VISION_MODEL", self.model).strip() or self.model,
            "max_tokens": 900,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": base64.b64encode(raw).decode("ascii"),
                            },
                        },
                        {
                            "type": "text",
                            "text": (
                                "첨부 이미지에서 사람이 읽을 수 있는 텍스트와 설득 근거가 되는 시각 요소를 추출하세요. "
                                "반드시 plain text로만 답하고, 아래 세 섹션을 포함하세요.\n"
                                "[텍스트]\n[시각 요소]\n[활용 포인트]"
                            ),
                        },
                    ],
                }
            ],
        }
        body = self._post_messages(payload)
        usage = body.get("usage") or {}
        if isinstance(usage, dict):
            self._set_usage_tokens(
                {
                    "prompt_tokens": int(usage.get("input_tokens", 0) or 0),
                    "output_tokens": int(usage.get("output_tokens", 0) or 0),
                    "total_tokens": int((usage.get("input_tokens", 0) or 0) + (usage.get("output_tokens", 0) or 0)),
                }
            )
        text = self._extract_text(body)
        if not text:
            raise ProviderError("Provider returned empty response.")
        return text

    def generate_visual_asset(
        self,
        prompt: str,
        *,
        request_id: str,
        size: str = "1536x1024",
        style: str = "natural",
    ) -> dict[str, Any]:
        raise ProviderError(
            "Claude provider does not support direct visual asset generation in this deployment."
        )

    def _post_messages(self, payload: dict[str, Any]) -> dict[str, Any]:
        timeout = int(os.getenv("DECISIONDOC_PROVIDER_TIMEOUT", "120"))
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "content-type": "application/json",
        }
        beta = os.getenv("DECISIONDOC_CLAUDE_BETA", "").strip()
        if beta:
            headers["anthropic-beta"] = beta
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(f"{self.base_url}/messages", headers=headers, json=payload)
            if response.status_code >= 400:
                try:
                    body = response.json()
                except Exception:
                    body = {"error": {"message": response.text[:500]}}
                raise _ClaudeAPIError(response.status_code, body, response)
            return response.json()
        except ProviderError:
            raise
        except _ClaudeAPIError as exc:
            raise ProviderError("Provider request failed.") from exc
        except Exception as exc:
            raise ProviderError("Provider request failed.") from exc

    @staticmethod
    def _extract_text(body: dict[str, Any]) -> str:
        content = body.get("content") or []
        if not isinstance(content, list):
            return ""
        texts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text)
        return "\n".join(texts).strip()


def _detect_attachment_mime_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".pdf": "application/pdf",
    }.get(ext, "image/png")
