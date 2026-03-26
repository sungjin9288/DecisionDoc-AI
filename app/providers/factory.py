import os

from app.ai.pipeline import FallbackPipeline
from app.providers.base import Provider, ProviderError
from app.providers.gemini_provider import GeminiProvider
from app.providers.local_provider import LocalProvider
from app.providers.mock_provider import MockProvider
from app.providers.openai_provider import OpenAIProvider


def _get_int(name: str, default: int) -> int:
    """Read an integer env var with a safe fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _make_single_provider(name: str, model_override: str | None = None) -> Provider:
    """Instantiate a single named provider.

    Args:
        name: Provider name ("mock" | "openai" | "gemini" | "local").
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
      - A single name:              "mock" | "openai" | "gemini"
      - A comma-separated fallback: "openai,gemini" (tries openai first, falls back to gemini)

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
    raw = os.getenv("DECISIONDOC_PROVIDER", "mock").lower()
    names = [n.strip() for n in raw.split(",") if n.strip()]
    if not names:
        raise ProviderError("Provider configuration error.")
    providers = [_make_single_provider(n, model_override=model_override) for n in names]
    if len(providers) == 1:
        return providers[0]
    return FallbackPipeline(providers)


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
                return get_provider(model_override=model_id)
    except Exception:
        pass  # Silently fall back to default provider
    return get_provider()
