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
    ) -> dict[str, Any]:
        raise NotImplementedError

    def consume_usage_tokens(self) -> dict[str, int] | None:
        return None
