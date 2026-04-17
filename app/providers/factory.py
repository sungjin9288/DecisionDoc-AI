import os

from app.ai.pipeline import FallbackPipeline
from app.providers.base import Provider, ProviderError
from app.providers.claude_provider import ClaudeProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.local_provider import LocalProvider
from app.providers.mock_provider import MockProvider
from app.providers.openai_provider import OpenAIProvider

CAPABILITY_PROVIDER_ENV = {
    "generation": "DECISIONDOC_PROVIDER_GENERATION",
    "attachment": "DECISIONDOC_PROVIDER_ATTACHMENT",
    "visual": "DECISIONDOC_PROVIDER_VISUAL",
}


def _get_int(name: str, default: int) -> int:
    """Read an integer env var with a safe fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_provider_names(raw: str) -> list[str]:
    return [n.strip() for n in str(raw or "").lower().split(",") if n.strip()]


def _resolve_provider_names(capability: str | None = None) -> list[str]:
    if capability:
        env_name = CAPABILITY_PROVIDER_ENV.get(capability)
        if env_name:
            override = os.getenv(env_name, "")
            if override.strip():
                names = _parse_provider_names(override)
                if names:
                    return names
    names = _parse_provider_names(os.getenv("DECISIONDOC_PROVIDER", "mock"))
    if not names:
        raise ProviderError("Provider configuration error.")
    return names


def _build_provider_chain(names: list[str], *, model_override: str | None = None) -> Provider:
    providers = [_make_single_provider(n, model_override=model_override) for n in names]
    if len(providers) == 1:
        return providers[0]
    return FallbackPipeline(providers)


def configured_provider_names() -> set[str]:
    names: set[str] = set(_resolve_provider_names())
    for capability in CAPABILITY_PROVIDER_ENV:
        names.update(_resolve_provider_names(capability))
    return names


def _make_single_provider(name: str, model_override: str | None = None) -> Provider:
    """Instantiate a single named provider.

    Args:
        name: Provider name ("mock" | "openai" | "gemini" | "claude" | "local").
        model_override: If set, override the model name for OpenAI (fine-tuned models).

    Raises:
        ProviderError: If the name is not recognised.
    """
    if name == "mock":
        return MockProvider()
    if name == "openai":
        return OpenAIProvider(model_override=model_override)
    if name == "gemini":
        return GeminiProvider()
    if name == "claude":
        return ClaudeProvider()
    if name == "local":
        from app.config import (
            get_local_llm_api_key,
            get_local_llm_base_url,
            get_local_llm_model,
            get_local_llm_timeout,
        )
        return LocalProvider(
            base_url=get_local_llm_base_url(),
            model=model_override or get_local_llm_model(),
            api_key=get_local_llm_api_key(),
            timeout=get_local_llm_timeout(),
        )
    raise ProviderError("Provider configuration error.")


def get_provider(model_override: str | None = None) -> Provider:
    """Return the configured provider, or a FallbackPipeline for comma-separated names.

    DECISIONDOC_PROVIDER accepts:
      - A single name:              "mock" | "openai" | "gemini" | "claude"
      - A comma-separated fallback: "openai,gemini,claude"

    Args:
        model_override: If set, passes the model name to the OpenAI provider
                        (used when serving fine-tuned models).

    Returns:
        A single Provider when only one name is given, or a FallbackPipeline
        that tries each provider in order on failure.

    Raises:
        ProviderError: If any provider name is unrecognised or required credentials
                       are missing (raised by the provider's __init__).
    """
    return _build_provider_chain(_resolve_provider_names(), model_override=model_override)


def get_provider_for_capability(capability: str, model_override: str | None = None) -> Provider:
    """Return a provider using a capability-specific chain when configured."""
    return _build_provider_chain(_resolve_provider_names(capability), model_override=model_override)


def get_provider_for_bundle(bundle_id: str | None, tenant_id: str) -> Provider:
    """Return a fine-tuned model provider if one is active for this bundle+tenant.

    Falls back to the default configured provider when no active fine-tuned model exists.

    Args:
        bundle_id: The bundle being generated (e.g. "business_plan_kr").
        tenant_id: The tenant ID (e.g. "system").

    Returns:
        An OpenAI provider using the fine-tuned model_id, or the default provider.
    """
    try:
        from app.storage.model_registry import ModelRegistry
        registry = ModelRegistry()
        active_model = registry.get_active_model(bundle_id, tenant_id)
        if active_model and active_model.get("status") == "ready":
            model_id = active_model.get("model_id", "")
            if model_id and not model_id.startswith("pending:"):
                return get_provider_for_capability("generation", model_override=model_id)
    except Exception:
        pass  # Silently fall back to default provider
    return get_provider_for_capability("generation")
