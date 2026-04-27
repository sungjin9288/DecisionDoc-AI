"""Local-first search backend primitives for project knowledge ranking."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def tokenize_knowledge_text(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        text = _normalize_text(value)
        if text:
            tokens.update(re.findall(r"[0-9a-zA-Z가-힣]{2,}", text))
    return tokens


@dataclass(frozen=True)
class KnowledgeSearchQuery:
    title: str = ""
    goal: str = ""
    bundle_type: str = ""
    source_organization: str = ""

    def tokens(self) -> set[str]:
        return tokenize_knowledge_text(
            self.title,
            self.goal,
            self.bundle_type,
            self.source_organization,
        )


@dataclass(frozen=True)
class KnowledgeSearchMatch:
    query_terms: list[str]
    matched_terms: list[str]

    @property
    def overlap(self) -> int:
        return len(self.matched_terms)


class KnowledgeSearchBackend(Protocol):
    """Search backend contract used by KnowledgeStore ranking."""

    name: str

    def match(self, query: KnowledgeSearchQuery, document: dict[str, Any]) -> KnowledgeSearchMatch:
        """Return local keyword match details for a metadata document."""
        ...


class LocalKeywordBackend:
    """Deterministic local keyword matcher used before optional FTS/vector backends."""

    name = "local_keyword"

    def match(self, query: KnowledgeSearchQuery, document: dict[str, Any]) -> KnowledgeSearchMatch:
        query_terms = query.tokens()
        doc_terms = tokenize_knowledge_text(
            document.get("filename", ""),
            " ".join(_normalize_list(document.get("tags"))),
            " ".join(_normalize_list(document.get("applicable_bundles"))),
            document.get("source_organization", ""),
            document.get("notes", ""),
        )
        matched_terms = sorted(query_terms & doc_terms)
        return KnowledgeSearchMatch(
            query_terms=sorted(query_terms),
            matched_terms=matched_terms,
        )
