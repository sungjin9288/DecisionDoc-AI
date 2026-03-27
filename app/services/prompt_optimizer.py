"""prompt_optimizer.py — 피드백 패턴 분석 및 프롬프트 개선 제안.

저평점(1-2) 피드백 코멘트에서 패턴을 분석하고,
번들별 prompt_hint 개선 방향을 제안합니다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class FeedbackPattern:
    pattern_type: str        # "specificity", "missing_section", "language", "irrelevant", "other"
    count: int
    examples: list[str]      # Sample comments showing this pattern
    suggestion: str          # Actionable prompt improvement suggestion


@dataclass
class OptimizationReport:
    bundle_type: str
    total_feedback: int
    low_rating_count: int
    patterns: list[FeedbackPattern]
    priority_suggestions: list[str]  # Top 3 actionable suggestions


# Pattern definitions: (name, regex_list, suggestion)
_PATTERNS: list[tuple[str, list[str], str]] = [
    (
        "specificity",
        [r"구체적", r"너무 일반적", r"추상적", r"generic", r"vague", r"모호"],
        "prompt_hint에 '수치, 예시, 고유 데이터를 반드시 포함하세요' 지시 추가",
    ),
    (
        "missing_section",
        [r"섹션.*없", r"없.*섹션", r"누락", r"빠졌", r"missing"],
        "prompt_hint에 각 필수 섹션의 최소 내용 요건 명시",
    ),
    (
        "language",
        [r"영어", r"한국어.*아니", r"번역", r"language", r"english"],
        "prompt_hint에 '반드시 한국어로만 작성' 강조 및 영문 사용 금지 명시",
    ),
    (
        "irrelevant",
        [r"관련.*없", r"엉뚱", r"다른.*내용", r"맥락.*모름", r"irrelevant", r"off.topic"],
        "prompt_hint에 사용자 제공 컨텍스트를 최우선으로 반영하도록 지시 추가",
    ),
    (
        "too_short",
        [r"짧", r"부족", r"적", r"thin", r"short", r"too brief"],
        "prompt_hint에 각 섹션별 최소 문단 수 또는 bullet point 수 명시",
    ),
]


def _detect_pattern(comment: str) -> str | None:
    """Return pattern type if comment matches, else None."""
    comment_lower = comment.lower()
    for pattern_name, regexes, _ in _PATTERNS:
        for rx in regexes:
            if re.search(rx, comment_lower):
                return pattern_name
    return None


def analyze_feedback_patterns(
    feedbacks: list[dict[str, Any]],
    bundle_type: str,
    low_rating_threshold: int = 3,
) -> OptimizationReport:
    """Analyze feedback records to find patterns in low-rated responses.

    Args:
        feedbacks: List of feedback dicts with keys: rating (int), comment (str),
                   bundle_type (str)
        bundle_type: Bundle identifier to filter feedbacks
        low_rating_threshold: Ratings below this are considered "low"

    Returns:
        OptimizationReport with identified patterns and suggestions
    """
    relevant = [f for f in feedbacks if f.get("bundle_type") == bundle_type]
    low_rated = [f for f in relevant if f.get("rating", 5) < low_rating_threshold]

    pattern_counts: dict[str, list[str]] = {p[0]: [] for p in _PATTERNS}
    pattern_counts["other"] = []

    for fb in low_rated:
        comment = fb.get("comment", "")
        if not comment:
            continue
        detected = _detect_pattern(comment)
        if detected and detected in pattern_counts:
            pattern_counts[detected].append(comment)
        else:
            pattern_counts["other"].append(comment)

    patterns: list[FeedbackPattern] = []
    for p_name, regexes, suggestion in _PATTERNS:
        examples = pattern_counts.get(p_name, [])
        if examples:
            patterns.append(FeedbackPattern(
                pattern_type=p_name,
                count=len(examples),
                examples=examples[:3],
                suggestion=suggestion,
            ))

    # Sort by count descending
    patterns.sort(key=lambda p: p.count, reverse=True)

    # Top 3 priority suggestions
    priority = [p.suggestion for p in patterns[:3]]
    if not priority and low_rated:
        priority = ["전반적인 품질 개선을 위해 더 많은 피드백 수집이 필요합니다."]

    return OptimizationReport(
        bundle_type=bundle_type,
        total_feedback=len(relevant),
        low_rating_count=len(low_rated),
        patterns=patterns,
        priority_suggestions=priority,
    )


def generate_prompt_improvement(
    current_prompt: str,
    report: OptimizationReport,
) -> str:
    """Generate an improved prompt_hint based on optimization report.

    Returns the improved prompt string. Does NOT call any LLM —
    applies rule-based improvements from detected patterns.
    """
    if not report.patterns:
        return current_prompt

    additions: list[str] = []
    for pattern in report.patterns:
        if pattern.pattern_type == "specificity":
            additions.append("- 반드시 구체적인 수치, 실제 사례, 고유한 세부사항을 포함하세요.")
        elif pattern.pattern_type == "missing_section":
            additions.append("- 모든 섹션을 빠짐없이 작성하고, 각 섹션에 최소 3개 이상의 내용을 포함하세요.")
        elif pattern.pattern_type == "language":
            additions.append("- 모든 내용을 반드시 한국어로만 작성하세요. 영문 사용 금지.")
        elif pattern.pattern_type == "irrelevant":
            additions.append("- 사용자가 제공한 제목, 목표, 컨텍스트를 최우선으로 반영하세요.")
        elif pattern.pattern_type == "too_short":
            additions.append("- 각 섹션에 충분한 내용(최소 100자 이상)을 작성하세요.")

    if not additions:
        return current_prompt

    improved = current_prompt.rstrip()
    improved += "\n" + "\n".join(additions)
    return improved
