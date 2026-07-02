"""app/storage/knowledge/normalizers.py — 값 정규화 및 매칭 헬퍼."""
from __future__ import annotations

from typing import Any

from app.storage.knowledge.constants import (
    _LEARNING_MODE_DEFAULT,
    _LEARNING_MODE_LABELS,
    _QUALITY_TIER_DEFAULT,
    _QUALITY_TIER_WEIGHTS,
    _REFERENCE_SUCCESS_WEIGHTS,
)


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = [item.strip() for item in values.split(",")]
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for item in values:
        text = _normalize_string(item)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_learning_mode(value: Any) -> str:
    normalized = _normalize_string(value).lower()
    return normalized if normalized in _LEARNING_MODE_LABELS else _LEARNING_MODE_DEFAULT


def _normalize_quality_tier(value: Any) -> str:
    normalized = _normalize_string(value).lower()
    return normalized if normalized in _QUALITY_TIER_WEIGHTS else _QUALITY_TIER_DEFAULT


def _normalize_success_state(value: Any) -> str:
    normalized = _normalize_string(value).lower()
    return normalized if normalized in _REFERENCE_SUCCESS_WEIGHTS else "draft"


def _normalize_reference_year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if 1900 <= parsed <= 2100:
        return parsed
    return None


def _matches_text_scope(value: Any, expected: str) -> bool:
    actual = _normalize_string(value).lower()
    needle = _normalize_string(expected).lower()
    if not actual or not needle:
        return False
    return actual in needle or needle in actual


def _matches_report_workflow_id(value: Any, report_workflow_id: str) -> bool:
    source = _normalize_string(value)
    workflow_id = _normalize_string(report_workflow_id)
    if not source or not workflow_id:
        return False
    return (
        source == workflow_id
        or source.startswith(f"report_workflow:{workflow_id}:")
        or f":{workflow_id}:" in source
    )


def _is_report_workflow_source(value: Any) -> bool:
    source = _normalize_string(value).lower()
    return source == "report_workflow"


def _extract_report_workflow_id(*values: Any) -> str:
    for value in values:
        source = _normalize_string(value)
        if not source:
            continue
        if source.startswith("report_workflow:"):
            parts = source.split(":")
            if len(parts) >= 2 and parts[1]:
                return parts[1]
    return ""
