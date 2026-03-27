"""bundle_eval.py — BundleSpec 기반 동적 문서 평가.

BundleSpec의 validator_headings/critical_non_empty_headings를 활용하여
번들별 맞춤 평가를 수행합니다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.bundle_catalog.spec import BundleSpec, DocumentSpec


@dataclass
class DocEvalResult:
    doc_key: str
    score: float  # 0.0 ~ 1.0
    issues: list[str]
    passed_checks: list[str]


@dataclass
class BundleEvalResult:
    bundle_id: str
    overall_score: float  # 0.0 ~ 1.0
    doc_results: list[DocEvalResult]
    summary: str


def _check_headings_present(markdown: str, headings: list[str]) -> tuple[list[str], list[str]]:
    """Return (found, missing) heading lists."""
    found, missing = [], []
    for h in headings:
        if h in markdown:
            found.append(h)
        else:
            missing.append(h)
    return found, missing


def _check_non_empty_headings(markdown: str, headings: list[str]) -> tuple[list[str], list[str]]:
    """Return (non_empty, empty) for critical headings."""
    non_empty, empty = [], []
    lines = markdown.splitlines()
    for h in headings:
        found_heading = False
        has_content = False
        for i, line in enumerate(lines):
            if line.strip() == h.strip():
                found_heading = True
                # Check next non-empty lines for content
                for j in range(i + 1, min(i + 10, len(lines))):
                    nxt = lines[j].strip()
                    if nxt.startswith("#"):
                        break
                    if nxt:
                        has_content = True
                        break
                break
        if found_heading and has_content:
            non_empty.append(h)
        elif found_heading:
            empty.append(h)
        else:
            empty.append(h)  # Missing heading is also "empty"
    return non_empty, empty


def _check_minimum_length(markdown: str, min_words: int = 50) -> tuple[bool, int]:
    """Check if markdown has minimum word count."""
    words = len(markdown.split())
    return words >= min_words, words


def _check_no_placeholder(markdown: str) -> tuple[bool, list[str]]:
    """Detect placeholder patterns like [TODO], {{...}}, <...>."""
    patterns = [
        r"\[TODO[^\]]*\]",
        r"\{\{[^}]+\}\}",  # Unfilled Jinja2 vars
        r"<[A-Z_]+>",      # <PLACEHOLDER>
        r"TBD",
        r"작성 예정",
        r"내용 없음",
    ]
    found = []
    for p in patterns:
        matches = re.findall(p, markdown, re.IGNORECASE)
        found.extend(matches)
    return len(found) == 0, found


def evaluate_document(doc_spec: DocumentSpec, markdown: str) -> DocEvalResult:
    """Evaluate a single document against its DocumentSpec."""
    issues: list[str] = []
    passed: list[str] = []
    scores: list[float] = []

    # 1. Validator headings check (weight: 0.35)
    found_h, missing_h = _check_headings_present(markdown, doc_spec.validator_headings)
    heading_score = len(found_h) / max(len(doc_spec.validator_headings), 1)
    scores.append(heading_score * 0.35)
    if missing_h:
        issues.append(f"누락된 헤딩: {', '.join(missing_h)}")
    else:
        passed.append("모든 필수 헤딩 존재")

    # 2. Critical non-empty headings check (weight: 0.35)
    non_empty, empty = _check_non_empty_headings(markdown, doc_spec.critical_non_empty_headings)
    critical_score = len(non_empty) / max(len(doc_spec.critical_non_empty_headings), 1)
    scores.append(critical_score * 0.35)
    if empty:
        issues.append(f"내용 없는 필수 섹션: {', '.join(empty)}")
    else:
        passed.append("모든 핵심 섹션에 내용 있음")

    # 3. Minimum length check (weight: 0.15)
    ok_len, word_count = _check_minimum_length(markdown)
    scores.append(0.15 if ok_len else word_count / 50 * 0.15)
    if not ok_len:
        issues.append(f"내용 부족 ({word_count} 단어, 최소 50 단어 권장)")
    else:
        passed.append(f"충분한 내용 ({word_count} 단어)")

    # 4. No placeholder check (weight: 0.15)
    no_ph, placeholders = _check_no_placeholder(markdown)
    scores.append(0.15 if no_ph else 0.0)
    if not no_ph:
        issues.append(f"미완성 플레이스홀더 발견: {placeholders[:3]}")
    else:
        passed.append("플레이스홀더 없음")

    total_score = sum(scores)
    return DocEvalResult(
        doc_key=doc_spec.key,
        score=round(total_score, 3),
        issues=issues,
        passed_checks=passed,
    )


def evaluate_bundle_docs(
    bundle_spec: BundleSpec,
    docs: list[dict[str, Any]],
) -> BundleEvalResult:
    """Evaluate all documents in a bundle response.

    Args:
        bundle_spec: The BundleSpec for this bundle
        docs: List of {"doc_type": str, "markdown": str} dicts from GenerateResponse

    Returns:
        BundleEvalResult with per-doc scores and overall summary
    """
    doc_map = {d["doc_type"]: d.get("markdown", "") for d in docs}
    doc_results: list[DocEvalResult] = []

    for doc_spec in bundle_spec.docs:
        markdown = doc_map.get(doc_spec.key, "")
        result = evaluate_document(doc_spec, markdown)
        doc_results.append(result)

    if not doc_results:
        return BundleEvalResult(
            bundle_id=bundle_spec.id,
            overall_score=0.0,
            doc_results=[],
            summary="평가할 문서가 없습니다.",
        )

    overall = sum(r.score for r in doc_results) / len(doc_results)
    all_issues = [issue for r in doc_results for issue in r.issues]

    if overall >= 0.85:
        summary = f"✅ 우수 ({overall:.0%}) — 모든 문서가 기준을 충족합니다."
    elif overall >= 0.65:
        summary = f"⚠️ 보통 ({overall:.0%}) — 일부 개선이 필요합니다."
    else:
        summary = f"❌ 미흡 ({overall:.0%}) — 주요 문제: {'; '.join(all_issues[:2])}"

    return BundleEvalResult(
        bundle_id=bundle_spec.id,
        overall_score=round(overall, 3),
        doc_results=doc_results,
        summary=summary,
    )


def compute_bundle_heuristic_score(
    bundle_spec: BundleSpec,
    docs: list[dict[str, Any]],
) -> float:
    """Convenience function: returns 0.0~1.0 heuristic score."""
    result = evaluate_bundle_docs(bundle_spec, docs)
    return result.overall_score
