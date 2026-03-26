"""
app.ai — Reusable AI toolkit for structured LLM generation.

Key exports:
    StructuredGenerator   — Generic typed LLM output generator (Pydantic-first).
    FallbackPipeline      — Multi-provider fallback chain.
    StructuredGenerationError — Raised when generation fails after all retries.

Quick start:

    from pydantic import BaseModel
    from app.ai import StructuredGenerator, FallbackPipeline
    from app.providers.openai_provider import OpenAIProvider
    from app.providers.mock_provider import MockProvider

    class PRD(BaseModel):
        problem: str
        personas: list[str]
        requirements: list[str]

    provider = FallbackPipeline([OpenAIProvider(), MockProvider()])
    gen = StructuredGenerator(PRD, provider=provider, max_retries=1)
    prd = gen.generate({"project": "my-app"}, request_id="req-1")
"""
from app.ai.pipeline import FallbackPipeline
from app.ai.structured import StructuredGenerationError, StructuredGenerator

__all__ = ["StructuredGenerator", "StructuredGenerationError", "FallbackPipeline"]
