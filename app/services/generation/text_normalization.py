"""Finished-document text normalization and sanitization helpers.

Shared string/row cleanup utilities used by the proposal, attachment, and
performance quality guards to strip reference-context noise and normalize
LLM output before it is embedded into rendered documents.
"""
from __future__ import annotations

import re
from typing import Any


def _has_meaningful_text(value: Any, *, min_chars: int = 80) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_chars


def _normalized_row_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    rows: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized:
            rows.append(normalized)
    return rows


def _ensure_text(value: Any, fallback: str, *, min_chars: int = 80) -> str:
    if _has_meaningful_text(value, min_chars=min_chars):
        return _normalize_finished_doc_text(value)
    return _normalize_finished_doc_text(fallback)


def _ensure_rows(value: Any, fallback_rows: list[str], *, min_items: int = 3) -> list[str]:
    rows = _normalized_row_list(value)
    if len(rows) >= min_items:
        return rows
    merged = list(rows)
    for row in fallback_rows:
        if row not in merged:
            merged.append(row)
        if len(merged) >= max(min_items, len(fallback_rows)):
            break
    return merged


def _project_subject(title: str) -> str:
    subject = str(title or "").strip()
    for suffix in (
        " 사업 제안서",
        " 제안서",
        " 사업수행계획서",
        " 수행계획서",
        " 발표자료",
        " 보고서",
    ):
        if subject.endswith(suffix):
            subject = subject[: -len(suffix)].strip()
    return subject or str(title or "").strip()


def _strip_reference_noise(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = re.sub(
        r"(?im)^\s*(?:\*\*)?(?:참고 맥락|범위 참고 맥락|제안서 인풋 참고 맥락|수행계획 인풋 참고 맥락)(?:\*\*)?\s*:\s*.*$",
        "",
        text,
    )
    cleaned = re.sub(r"\s*\([^)]*(?:발주처는|계약 기간은|산출물은)[^)]*\)", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_finished_doc_text(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    cleaned = _strip_reference_noise(text)
    replacements = (
        ("제안한다.을 달성하기 위해", "제안하며, 이를 달성하기 위해"),
        ("제안한다.를", "제안 내용을"),
        ("제안한다.은", "제안은"),
        ("제안한다.는", "제안은"),
        ("사업 제안서 사업", "사업"),
        ("달성을 통한", "달성을 위한"),
        ("은(는)", "는"),
    )
    for source, target in replacements:
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _normalize_finished_doc_value(value: Any) -> Any:
    if isinstance(value, str):
        return _normalize_finished_doc_text(value)
    if isinstance(value, list):
        normalized_items: list[Any] = []
        for item in value:
            normalized = _normalize_finished_doc_value(item)
            if isinstance(normalized, str):
                if normalized:
                    normalized_items.append(normalized)
            else:
                normalized_items.append(normalized)
        return normalized_items
    if isinstance(value, dict):
        return {key: _normalize_finished_doc_value(item) for key, item in value.items()}
    return value


def _sanitize_rows(
    value: Any,
    fallback_rows: list[str],
    *,
    min_items: int = 3,
    banned_terms: tuple[str, ...] = ("참고 맥락", "인풋 참고 맥락"),
) -> list[str]:
    rows: list[str] = []
    for row in _normalized_row_list(value):
        if any(term in row for term in banned_terms):
            continue
        cleaned_row = _normalize_finished_doc_text(row)
        if cleaned_row:
            rows.append(cleaned_row)
    if len(rows) >= min_items:
        return rows
    return _ensure_rows(rows, fallback_rows, min_items=min_items)
