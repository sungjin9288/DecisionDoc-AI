"""Module-level text/JSON helpers shared across report workflow mixins."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


def _clean_json_text(raw: str) -> str:
    text = str(raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    first = min([idx for idx in [text.find("{"), text.find("[")] if idx >= 0] or [0])
    if first > 0:
        text = text[first:]
    return text


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    return [value]


def _string_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _safe_slide_id(value: Any, page: int) -> str:
    raw = str(value or "").strip()
    if raw:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", raw)[:48].strip("-") or f"slide-{page:03d}"
    return f"slide-{page:03d}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedupe_strings(values: list[Any], *, limit: int = 8) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped
