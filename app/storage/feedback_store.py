"""FeedbackStore — append-only JSONL store for user ratings.

Each line is a JSON object with at least:
  feedback_id, bundle_type, rating (1-5), comment, timestamp

High-rated entries (rating >= 4) can be retrieved as few-shot examples
for future prompt injection.
"""
from __future__ import annotations

import functools
import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger("decisiondoc.storage.feedback")


class FeedbackStore:
    """Thread-safe, append-only JSONL feedback store."""

    def __init__(self, data_dir: Path, tenant_id: str = "system") -> None:
        self._tenant_id = tenant_id
        tenant_dir = Path(data_dir) / "tenants" / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        self._path = tenant_dir / "feedback.jsonl"
        self._lock = threading.Lock()

    def save(self, feedback: dict[str, Any]) -> str:
        """Append one feedback record. Returns the generated feedback_id."""
        feedback_id = str(uuid.uuid4())
        record = {
            "feedback_id": feedback_id,
            "timestamp": time.time(),
            **feedback,
        }
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        return feedback_id

    def save_feedback(self, feedback: dict[str, Any]) -> str:
        """Save a feedback record, ensuring the `docs` field is always present.

        If ``feedback`` does not contain a ``docs`` key, an empty list is stored.
        Returns the generated feedback_id.
        """
        enriched = dict(feedback)
        if "docs" not in enriched:
            enriched["docs"] = []
        return self.save(enriched)

    def get_all(self) -> list[dict[str, Any]]:
        """Return all feedback records (all bundles, all ratings)."""
        if not self._path.exists():
            return []
        results: list[dict[str, Any]] = []
        with self._lock:
            try:
                lines = self._path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                results.append(json.loads(line))
            except json.JSONDecodeError as exc:
                _log.warning("Skipping malformed feedback line: %s", exc)
                continue
        return results

    def get_low_rated(
        self, bundle_type: str, max_rating: int = 2
    ) -> list[dict[str, Any]]:
        """Return all low-rated feedback records for a bundle type.

        Used by prompt_optimizer to detect quality degradation patterns.
        """
        if not self._path.exists():
            return []
        results: list[dict[str, Any]] = []
        with self._lock:
            try:
                lines = self._path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                record.get("bundle_type") == bundle_type
                and record.get("rating", 5) <= max_rating
            ):
                results.append(record)
        return results

    def get_high_rated_examples(
        self,
        bundle_type: str,
        min_rating: int = 4,
        limit: int = 2,
        doc_content_limit: int = 800,
    ) -> list[dict[str, Any]]:
        """Return up to `limit` high-rated feedback records for a bundle type.

        Returns structured records with docs keyed by doc_type, each truncated
        to ``doc_content_limit`` chars. Used for few-shot injection into LLM prompts.

        Shape per record:
          {
            "rating":    int,
            "comment":   str,
            "title":     str,
            "bundle_id": str,
            "timestamp": str | float,
            "docs": {
              "<doc_type>": {
                "heading": str,   # first heading found (## ...) or doc_type
                "content": str,   # first doc_content_limit chars of markdown
              },
              ...
            },
          }
        """
        if not self._path.exists():
            return []
        raw: list[dict[str, Any]] = []
        with self._lock:
            try:
                lines = self._path.read_text(encoding="utf-8").splitlines()
            except OSError:
                return []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                record.get("bundle_type") == bundle_type
                and record.get("rating", 0) >= min_rating
            ):
                raw.append(record)
                if len(raw) >= limit:
                    break

        results: list[dict[str, Any]] = []
        for record in raw:
            docs_structured: dict[str, Any] = {}
            raw_docs = record.get("docs", [])
            if isinstance(raw_docs, list):
                for doc in raw_docs:
                    if not isinstance(doc, dict):
                        continue
                    doc_type = doc.get("doc_type", "unknown")
                    markdown = doc.get("markdown", "")
                    # Extract first ## heading as section heading
                    heading = doc_type
                    for line_md in markdown.splitlines():
                        stripped = line_md.strip()
                        if stripped.startswith("## ") or stripped.startswith("# "):
                            heading = stripped.lstrip("#").strip()
                            break
                    docs_structured[doc_type] = {
                        "heading": heading,
                        "content": markdown[:doc_content_limit].strip(),
                    }
            results.append({
                "rating":    record.get("rating", 0),
                "comment":   record.get("comment", ""),
                "title":     record.get("title", ""),
                "bundle_id": record.get("bundle_type", bundle_type),
                "timestamp": record.get("timestamp", ""),
                "docs":      docs_structured,
            })
        return results


@functools.lru_cache(maxsize=50)
def get_feedback_store(tenant_id: str = "system") -> "FeedbackStore":
    """Return a cached FeedbackStore for the given tenant."""
    from pathlib import Path
    data_dir = Path(os.getenv("DATA_DIR", "./data"))
    return FeedbackStore(data_dir, tenant_id=tenant_id)


def clear_feedback_store_cache() -> None:
    """Invalidate the store factory cache (call after tenant update)."""
    get_feedback_store.cache_clear()
