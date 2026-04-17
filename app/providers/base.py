from abc import ABC, abstractmethod
from typing import Any


class ProviderError(Exception):
    pass


class UsageTokenMixin:
    """Mixin that standardizes usage-token tracking for LLM providers."""

    _last_usage_tokens: dict[str, int] | None = None

    def _set_usage_tokens(self, usage_map: dict[str, int] | None) -> None:
        self._last_usage_tokens = usage_map

    def consume_usage_tokens(self) -> dict[str, int] | None:
        usage = self._last_usage_tokens
        self._last_usage_tokens = None
        return usage


class Provider(ABC):
    name: str

    @abstractmethod
    def generate_bundle(
        self,
        requirements: dict[str, Any],
        *,
        schema_version: str,
        request_id: str,
        bundle_spec: Any = None,
        feedback_hints: str = "",
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate_raw(self, prompt: str, *, request_id: str, max_output_tokens: int | None = None) -> str:
        """Generate raw LLM text output for the given prompt string.

        Override in subclasses to enable StructuredGenerator and FallbackPipeline.
        Token usage should be stored via _set_usage_tokens() before returning.

        Raises:
            NotImplementedError: if the subclass has not implemented this method.
            ProviderError:       on API / SDK / network failure.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement generate_raw(). "
            "Override this method to use StructuredGenerator or FallbackPipeline."
        )

    def extract_attachment_text(self, filename: str, raw: bytes, *, request_id: str) -> str:
        """Extract readable text from image-like attachments via provider OCR/vision.

        Override in providers that support multimodal file reading. The default
        implementation intentionally fails so callers can decide whether to
        surface a guidance message or try another provider.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement extract_attachment_text()."
        )

    def generate_visual_asset(
        self,
        prompt: str,
        *,
        request_id: str,
        size: str = "1536x1024",
        style: str = "natural",
    ) -> dict[str, Any]:
        """Generate a visual asset (typically raster image bytes) from a prompt.

        Implementations should return a dict with at least:
        - ``media_type``: MIME type such as ``image/png``
        - ``data``: raw bytes
        Optional fields such as ``revised_prompt`` or ``model`` may also be returned.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not implement generate_visual_asset()."
        )

    def consume_usage_tokens(self) -> dict[str, int] | None:
        return None
