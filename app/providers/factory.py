import os

from app.providers.base import Provider, ProviderError
from app.providers.gemini_provider import GeminiProvider
from app.providers.mock_provider import MockProvider
from app.providers.openai_provider import OpenAIProvider


def get_provider() -> Provider:
    provider_name = os.getenv("DECISIONDOC_PROVIDER", "mock").lower()
    if provider_name == "mock":
        return MockProvider()
    if provider_name == "openai":
        return OpenAIProvider()
    if provider_name == "gemini":
        return GeminiProvider()
    raise ProviderError("Provider configuration error.")
