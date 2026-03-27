"""Tests for app/services/prompt_optimizer.py."""
import pytest
from app.services.prompt_optimizer import (
    analyze_feedback_patterns,
    generate_prompt_improvement,
    FeedbackPattern,
    OptimizationReport,
)


_BUNDLE_TYPE = "tech_decision"


def _make_feedback(rating: int, comment: str, bundle_type: str = _BUNDLE_TYPE) -> dict:
    return {"rating": rating, "comment": comment, "bundle_type": bundle_type}


# ── analyze_feedback_patterns ──────────────────────────────────────────────────

def test_empty_feedback_returns_empty_report():
    report = analyze_feedback_patterns([], _BUNDLE_TYPE)
    assert isinstance(report, OptimizationReport)
    assert report.total_feedback == 0
    assert report.low_rating_count == 0
    assert report.patterns == []


def test_no_low_rating_feedback():
    feedbacks = [
        _make_feedback(5, "완벽합니다!"),
        _make_feedback(4, "좋아요"),
    ]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    assert report.low_rating_count == 0
    assert report.patterns == []


def test_detects_specificity_pattern():
    feedbacks = [
        _make_feedback(2, "너무 구체적이지 않아요"),
        _make_feedback(1, "내용이 너무 추상적입니다"),
        _make_feedback(2, "구체적인 예시가 없어요"),
    ]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    types = [p.pattern_type for p in report.patterns]
    assert "specificity" in types


def test_detects_language_pattern():
    feedbacks = [
        _make_feedback(1, "영어로 나왔어요"),
        _make_feedback(2, "한국어가 아닌 내용이 많음"),
    ]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    types = [p.pattern_type for p in report.patterns]
    assert "language" in types


def test_detects_missing_section_pattern():
    feedbacks = [
        _make_feedback(1, "중요한 섹션이 누락됐어요"),
        _make_feedback(2, "필수 섹션이 빠졌습니다"),
    ]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    types = [p.pattern_type for p in report.patterns]
    assert "missing_section" in types


def test_filters_by_bundle_type():
    feedbacks = [
        _make_feedback(1, "구체적이지 않아요", bundle_type="tech_decision"),
        _make_feedback(1, "구체적이지 않아요", bundle_type="proposal_kr"),
    ]
    report = analyze_feedback_patterns(feedbacks, "tech_decision")
    assert report.total_feedback == 1


def test_priority_suggestions_non_empty_when_issues():
    feedbacks = [_make_feedback(1, "내용이 너무 구체적이지 않아요")]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    assert len(report.priority_suggestions) > 0


def test_report_has_correct_counts():
    feedbacks = [
        _make_feedback(5, "훌륭해요"),
        _make_feedback(2, "너무 구체적이지 않아요"),
        _make_feedback(1, "내용이 추상적입니다"),
    ]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    assert report.total_feedback == 3
    assert report.low_rating_count == 2  # rating < 3


# ── generate_prompt_improvement ─────────────────────────────────────────────────

def test_no_patterns_returns_original():
    original = "기존 프롬프트"
    report = OptimizationReport(
        bundle_type=_BUNDLE_TYPE,
        total_feedback=0,
        low_rating_count=0,
        patterns=[],
        priority_suggestions=[],
    )
    result = generate_prompt_improvement(original, report)
    assert result == original


def test_adds_specificity_instruction():
    feedbacks = [_make_feedback(1, "너무 구체적이지 않아요")]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    improved = generate_prompt_improvement("기존 프롬프트", report)
    assert "구체적인 수치" in improved


def test_adds_language_instruction():
    feedbacks = [_make_feedback(1, "영어로 나왔어요")]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    improved = generate_prompt_improvement("기존 프롬프트", report)
    assert "한국어" in improved


def test_improved_prompt_longer_than_original():
    feedbacks = [_make_feedback(1, "너무 추상적이에요. 구체적이지 않아요")]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    original = "기존 프롬프트"
    improved = generate_prompt_improvement(original, report)
    assert len(improved) >= len(original)


def test_patterns_sorted_by_count():
    feedbacks = [
        _make_feedback(1, "너무 구체적이지 않아요"),
        _make_feedback(2, "내용이 너무 추상적입니다"),
        _make_feedback(2, "구체적인 예시가 없어요"),
        _make_feedback(1, "영어로 나왔어요"),
    ]
    report = analyze_feedback_patterns(feedbacks, _BUNDLE_TYPE)
    if len(report.patterns) >= 2:
        assert report.patterns[0].count >= report.patterns[1].count
