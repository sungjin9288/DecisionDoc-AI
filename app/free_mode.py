"""Fail-closed configuration helpers for the no-cost local runtime."""

from __future__ import annotations

import os
from urllib.parse import urlsplit


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FREE_PROVIDERS = frozenset({"mock", "local"})
_LOCAL_LLM_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "ollama", "host.docker.internal"})


class FreeModeConfigurationError(ValueError):
    """Raised when free mode could reach a billable cloud dependency."""


def is_free_mode() -> bool:
    return os.getenv("DECISIONDOC_FREE_MODE", "0").strip().lower() in _TRUE_VALUES


def validate_free_provider_names(names: list[str]) -> None:
    if is_free_mode() and not set(names).issubset(_FREE_PROVIDERS):
        raise FreeModeConfigurationError(
            "Free mode allows only mock or local providers."
        )


def validate_cloud_provider_disabled() -> None:
    if is_free_mode():
        raise FreeModeConfigurationError(
            "Cloud providers are disabled in free mode."
        )


def validate_free_storage_kind(kind: str, *, state: bool = False) -> None:
    if is_free_mode() and kind.lower() != "local":
        label = "state storage" if state else "storage"
        raise FreeModeConfigurationError(f"Free mode requires local {label}.")


def is_free_local_llm_url(base_url: str) -> bool:
    try:
        parsed = urlsplit(base_url)
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower()
    return (
        parsed.scheme in {"http", "https"}
        and hostname in _LOCAL_LLM_HOSTS
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def validate_free_local_llm_url(base_url: str) -> None:
    if not is_free_mode():
        return
    if not is_free_local_llm_url(base_url):
        raise FreeModeConfigurationError(
            "Free mode local LLM must use a local endpoint."
        )
