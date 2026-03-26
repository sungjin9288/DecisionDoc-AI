"""search_service — optional web search augmentation for document generation.

Supports (in priority order): Serper, Brave, Tavily search APIs.
Gracefully returns [] when no API key is configured.

Environment variables:
    DECISIONDOC_SEARCH_ENABLED   — "1" to enable (default: "0")
    SERPER_API_KEY               — Google Search via serper.dev
    BRAVE_API_KEY                — Brave Search API
    TAVILY_API_KEY               — Tavily AI Search
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("decisiondoc.search")


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class SearchService:
    """Web search abstraction with graceful degradation."""

    def __init__(self) -> None:
        self._enabled = os.getenv("DECISIONDOC_SEARCH_ENABLED", "0") == "1"
        self._provider, self._api_key = self._detect_provider()

    def _detect_provider(self) -> tuple[str | None, str | None]:
        if serper := os.getenv("SERPER_API_KEY"):
            return "serper", serper
        if brave := os.getenv("BRAVE_API_KEY"):
            return "brave", brave
        if tavily := os.getenv("TAVILY_API_KEY"):
            return "tavily", tavily
        return None, None

    def is_available(self) -> bool:
        return self._enabled and self._provider is not None

    def search(self, query: str, num: int = 5) -> list[SearchResult]:
        if not self.is_available():
            return []
        try:
            if self._provider == "serper":
                return self._search_serper(query, num)
            if self._provider == "brave":
                return self._search_brave(query, num)
            if self._provider == "tavily":
                return self._search_tavily(query, num)
        except Exception as exc:
            logger.warning("search failed provider=%s error=%s", self._provider, exc)
        return []

    def _search_serper(self, query: str, num: int) -> list[SearchResult]:
        import httpx
        resp = httpx.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self._api_key, "Content-Type": "application/json"},
            json={"q": query, "num": num, "gl": "kr", "hl": "ko"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("link", ""),
                snippet=item.get("snippet", ""),
            )
            for item in resp.json().get("organic", [])[:num]
        ]

    def _search_brave(self, query: str, num: int) -> list[SearchResult]:
        import httpx
        resp = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self._api_key, "Accept": "application/json"},
            params={"q": query, "count": num},
            timeout=10.0,
        )
        resp.raise_for_status()
        results = resp.json().get("web", {}).get("results", [])
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("description", ""),
            )
            for r in results[:num]
        ]

    def _search_tavily(self, query: str, num: int) -> list[SearchResult]:
        import httpx
        resp = httpx.post(
            "https://api.tavily.com/search",
            json={"api_key": self._api_key, "query": query, "max_results": num},
            timeout=10.0,
        )
        resp.raise_for_status()
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
            )
            for r in resp.json().get("results", [])[:num]
        ]
