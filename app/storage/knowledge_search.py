"""Local-first search backend primitives for project knowledge ranking."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import get_knowledge_search_backend_name


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
            tokens.update(re.findall(r"[0-9a-zA-Z가-힣_]{2,}", text))
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


class SQLiteFtsBackend:
    """SQLite FTS5-backed metadata matcher with local keyword fallback.

    The backend intentionally remains stateless and per-document because the
    current KnowledgeStore ranking contract calls `match()` one document at a
    time. This makes the first FTS step opt-in without changing persistence.
    """

    name = "sqlite_fts"

    def __init__(self) -> None:
        self._local = LocalKeywordBackend()
        self._available = self._check_fts5_available()

    def match(self, query: KnowledgeSearchQuery, document: dict[str, Any]) -> KnowledgeSearchMatch:
        local_match = self._local.match(query, document)
        if not self._available:
            return KnowledgeSearchMatch(
                query_terms=local_match.query_terms,
                matched_terms=local_match.matched_terms,
            )

        query_terms = sorted(query.tokens())
        if not query_terms:
            return KnowledgeSearchMatch(query_terms=[], matched_terms=[])

        doc_text = _document_search_text(document)
        matched_terms = set(local_match.matched_terms)
        matched_terms.update(term for term in query_terms if self._matches_term(term, doc_text))
        return KnowledgeSearchMatch(
            query_terms=query_terms,
            matched_terms=sorted(matched_terms),
        )

    @staticmethod
    def _check_fts5_available() -> bool:
        try:
            with sqlite3.connect(":memory:") as conn:
                conn.execute("CREATE VIRTUAL TABLE docs USING fts5(body)")
        except sqlite3.Error:
            return False
        return True

    @staticmethod
    def _matches_term(term: str, doc_text: str) -> bool:
        if not term or not doc_text:
            return False
        try:
            with sqlite3.connect(":memory:") as conn:
                conn.execute("CREATE VIRTUAL TABLE docs USING fts5(body)")
                conn.execute("INSERT INTO docs(rowid, body) VALUES (1, ?)", (doc_text,))
                cursor = conn.execute(
                    "SELECT rowid FROM docs WHERE docs MATCH ? LIMIT 1",
                    (_quote_fts_term(term),),
                )
                return cursor.fetchone() is not None
        except sqlite3.Error:
            return False


def _document_search_text(document: dict[str, Any]) -> str:
    return " ".join(
        [
            _normalize_text(document.get("filename", "")),
            " ".join(_normalize_list(document.get("tags"))),
            " ".join(_normalize_list(document.get("applicable_bundles"))),
            _normalize_text(document.get("source_organization", "")),
            _normalize_text(document.get("notes", "")),
        ]
    ).strip()


def _quote_fts_term(term: str) -> str:
    escaped = str(term or "").replace('"', '""')
    return f'"{escaped}"'


def get_knowledge_search_backend() -> KnowledgeSearchBackend:
    """Build the configured Knowledge search backend."""
    name = get_knowledge_search_backend_name()
    if name in {"sqlite_fts", "fts5", "sqlite"}:
        return SQLiteFtsBackend()
    return LocalKeywordBackend()
