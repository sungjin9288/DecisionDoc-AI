"""
Provider fallback pipeline.

FallbackPipeline wraps an ordered list of providers and tries each in turn,
falling back to the next one whenever a call raises an exception.  It
implements the full Provider interface, so it can replace any single provider
anywhere in the codebase — including as the provider argument for
StructuredGenerator.

Usage:

    from app.ai.pipeline import FallbackPipeline
    from app.providers.openai_provider import OpenAIProvider
    from app.providers.gemini_provider import GeminiProvider
    from app.providers.mock_provider import MockProvider

    # Try OpenAI first, fall back to Gemini, then to Mock as last resort
    pipeline = FallbackPipeline([OpenAIProvider(), GeminiProvider(), MockProvider()])

    # Drop-in replacement for any single provider:
    raw = pipeline.generate_raw(prompt, request_id="req")
    bundle = pipeline.generate_bundle(requirements, schema_version="v1", request_id="req")
"""
from typing import Any

from app.providers.base import Provider, ProviderError


class FallbackPipeline(Provider):
    """Provider that tries multiple providers in order, falling back on failure.

    Both generate_raw() and generate_bundle() implement the fallback logic
    independently, so each call always starts from the first provider.

    Usage tokens are forwarded from whichever provider succeeds, via
    consume_usage_tokens().

    Args:
        providers: Ordered list of providers to try. Must have at least one.

    Raises:
        ValueError:    If providers list is empty.
        ProviderError: If every provider in the chain fails.
    """

    name = "fallback"

    def __init__(self, providers: list[Provider]) -> None:
        if not providers:
            raise ValueError("FallbackPipeline requires at least one provider.")
        self._providers = providers
        self._active_provider: Provider | None = None

    def generate_raw(
        self,
        prompt: str,
        *,
        request_id: str,
        max_output_tokens: int | None = None,
    ) -> str:
        """Try each provider in order; return the first successful raw response.

        Raises:
            ProviderError: with a summary of all failures if every provider fails.
        """
        errors: list[str] = []
        for provider in self._providers:
            try:
                raw = provider.generate_raw(
                    prompt,
                    request_id=request_id,
                    max_output_tokens=max_output_tokens,
                )
                self._active_provider = provider
                return raw
            except Exception as exc:
                errors.append(f"[{provider.name}] {exc}")
        raise ProviderError(
            "All providers in fallback chain failed:\n" + "\n".join(errors)
        )

    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
        bundle_spec: Any = None,
        feedback_hints: str = "",
    ) -> dict[str, Any]:
        """Try each provider in order; return the first successful bundle.

        Raises:
            ProviderError: with a summary of all failures if every provider fails.
        """
        errors: list[str] = []
        for provider in self._providers:
            try:
                result = provider.generate_bundle(
                    requirements,
                    schema_version=schema_version,
                    request_id=request_id,
                    bundle_spec=bundle_spec,
                    feedback_hints=feedback_hints,
                )
                self._active_provider = provider
                return result
            except Exception as exc:
                errors.append(f"[{provider.name}] {exc}")
        raise ProviderError(
            "All providers in fallback chain failed:\n" + "\n".join(errors)
        )

    def extract_attachment_text(self, filename: str, raw: bytes, *, request_id: str) -> str:
        """Try each provider in order; return the first successful attachment extraction."""
        errors: list[str] = []
        for provider in self._providers:
            try:
                text = provider.extract_attachment_text(filename, raw, request_id=request_id)
                self._active_provider = provider
                return text
            except Exception as exc:
                errors.append(f"[{provider.name}] {exc}")
        raise ProviderError(
            "All providers in fallback chain failed:\n" + "\n".join(errors)
        )

    def consume_usage_tokens(self) -> dict[str, int] | None:
        """Forward usage tokens from the provider that last succeeded."""
        if self._active_provider is None:
            return None
        return self._active_provider.consume_usage_tokens()
