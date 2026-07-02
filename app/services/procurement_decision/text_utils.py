"""Pure text/date/number parsing helpers used across procurement decision evaluation.

Extracted from ``app.services.procurement_decision_service`` (pure code
move, no behavior changes).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from app.services.procurement_decision.constants import NEGATIVE_SIGNAL_TERMS, REGION_TERMS


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    normalized = _normalize_text(text)
    return any(term.lower() in normalized for term in terms)


def _matched_groups(text: str, groups: dict[str, tuple[str, ...]]) -> set[str]:
    normalized = _normalize_text(text)
    matched: set[str] = set()
    for key, terms in groups.items():
        if any(term.lower() in normalized for term in terms):
            matched.add(key)
    return matched


def _detect_region(text: str) -> str | None:
    normalized = _normalize_text(text)
    for region in REGION_TERMS:
        if region.lower() in normalized:
            return region
    return None


def _extract_budget_amount(value: str) -> int | None:
    if not value:
        return None
    normalized = value.replace(",", "").replace(" ", "")
    match = re.search(r"(\d+(?:\.\d+)?)억원", normalized)
    if match:
        return int(float(match.group(1)) * 100_000_000)
    match = re.search(r"(\d+)만원", normalized)
    if match:
        return int(match.group(1)) * 10_000
    digits = re.sub(r"\D", "", normalized)
    if digits:
        return int(digits)
    return None


def _parse_deadline(value: str) -> datetime | None:
    if not value:
        return None
    normalized = value.strip().replace(".", "-").replace("/", "-")
    normalized = normalized.replace("년", "-").replace("월", "-").replace("일", "")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", normalized)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    hour = 23
    minute = 59
    time_match = re.search(r"(\d{1,2}):(\d{2})", normalized)
    if time_match:
        hour, minute = map(int, time_match.groups())
    try:
        return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None


def _score_from_overlap(overlap_count: int) -> float:
    if overlap_count >= 3:
        return 90.0
    if overlap_count == 2:
        return 78.0
    if overlap_count == 1:
        return 64.0
    return 28.0


def _has_negative_signal(text: str) -> bool:
    return _contains_any(text, NEGATIVE_SIGNAL_TERMS)
