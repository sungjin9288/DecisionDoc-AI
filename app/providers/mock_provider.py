"""Mock provider — returns realistic sample content without calling any LLM.

The implementation now lives in the ``app.providers.mock`` package, split into
focused modules (provider, shared, registry, fixtures_proposal,
fixtures_bid_decision, fixtures_rfp_performance, fixtures_business,
fixtures_edu, fixtures_presentation). This module is kept as a
backward-compatible facade that re-exports ``MockProvider`` so existing
``from app.providers.mock_provider import MockProvider`` imports keep working
unchanged.
"""
from app.providers.mock.provider import MockProvider

__all__ = ["MockProvider"]
