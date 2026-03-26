"""Tests for app/eval/bundle_eval.py — BundleSpec-based evaluation."""
import pytest
from app.eval.bundle_eval import (
    evaluate_document,
    evaluate_bundle_docs,
    compute_bundle_heuristic_score,
    DocEvalResult,
    BundleEvalResult,
)
from app.bundle_catalog.registry import get_bundle_spec, BUNDLE_REGISTRY


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_good_doc(headings: list[str], extra: str = "") -> str:
    """Generate markdown that passes all standard checks."""
    lines = []
    for h in headings:
        lines.append(h)
        lines.append("이 섹션에는 충분한 내용이 포함되어 있습니다. " * 3)
        lines.append("")
    lines.append(extra)
    return "\n".join(lines)


def _make_docs(bundle_spec, content_fn=None):
    """Build mock docs list from bundle spec."""
    docs = []
    for doc_spec in bundle_spec.docs:
        md = content_fn(doc_spec) if content_fn else _make_good_doc(
            doc_spec.validator_headings,
        )
        docs.append({"doc_type": doc_spec.key, "markdown": md})
    return docs


# ── unit: evaluate_document ────────────────────────────────────────────────────

def test_evaluate_document_perfect_score():
    bundle = get_bundle_spec("tech_decision")
    doc_spec = bundle.docs[0]
    md = _make_good_doc(doc_spec.validator_headings)
    result = evaluate_document(doc_spec, md)
    assert isinstance(result, DocEvalResult)
    assert result.score >= 0.85, f"Expected high score, got {result.score}"


def test_evaluate_document_empty_markdown():
    bundle = get_bundle_spec("tech_decision")
    doc_spec = bundle.docs[0]
    result = evaluate_document(doc_spec, "")
    assert result.score < 0.5
    assert len(result.issues) > 0


def test_evaluate_document_missing_headings():
    bundle = get_bundle_spec("tech_decision")
    doc_spec = bundle.docs[0]
    md = "# 문서\n\n내용만 있고 필수 헤딩이 없습니다. " * 5
    result = evaluate_document(doc_spec, md)
    assert any("누락" in issue for issue in result.issues)


def test_evaluate_document_with_placeholder():
    bundle = get_bundle_spec("tech_decision")
    doc_spec = bundle.docs[0]
    md = _make_good_doc(doc_spec.validator_headings, extra="[TODO: 나중에 작성]")
    result = evaluate_document(doc_spec, md)
    assert any("플레이스홀더" in issue for issue in result.issues)


# ── unit: evaluate_bundle_docs ─────────────────────────────────────────────────

def test_evaluate_bundle_docs_tech_decision():
    bundle = get_bundle_spec("tech_decision")
    docs = _make_docs(bundle)
    result = evaluate_bundle_docs(bundle, docs)
    assert isinstance(result, BundleEvalResult)
    assert result.bundle_id == "tech_decision"
    assert 0.0 <= result.overall_score <= 1.0
    assert len(result.doc_results) == len(bundle.docs)


def test_evaluate_bundle_docs_empty_docs():
    """When docs list is empty, each doc is evaluated with empty markdown.
    Score is low (only placeholder check passes for empty string) but not exactly 0.0."""
    bundle = get_bundle_spec("tech_decision")
    result = evaluate_bundle_docs(bundle, [])
    # Empty markdown: headings missing (0.0), critical sections missing (0.0),
    # length fails (0.0), but no placeholders (0.15) → score = 0.15 per doc
    assert result.overall_score < 0.5
    assert result.bundle_id == "tech_decision"
    assert len(result.doc_results) == len(bundle.docs)


def test_evaluate_bundle_docs_all_bundles():
    """Test that evaluate_bundle_docs works for all registered bundles."""
    for bundle in BUNDLE_REGISTRY.values():
        docs = _make_docs(bundle)
        result = evaluate_bundle_docs(bundle, docs)
        assert 0.0 <= result.overall_score <= 1.0, f"Invalid score for {bundle.id}"
        assert result.bundle_id == bundle.id


# ── unit: compute_bundle_heuristic_score ───────────────────────────────────────

def test_heuristic_score_returns_float():
    bundle = get_bundle_spec("tech_decision")
    docs = _make_docs(bundle)
    score = compute_bundle_heuristic_score(bundle, docs)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_heuristic_score_good_docs_above_threshold():
    bundle = get_bundle_spec("tech_decision")
    docs = _make_docs(bundle)
    score = compute_bundle_heuristic_score(bundle, docs)
    assert score >= 0.70, f"Good docs should score >= 0.70, got {score}"


def test_heuristic_score_bad_docs_below_threshold():
    bundle = get_bundle_spec("tech_decision")
    docs = [{"doc_type": spec.key, "markdown": "짧은 내용"} for spec in bundle.docs]
    score = compute_bundle_heuristic_score(bundle, docs)
    assert score < 0.70, f"Bad docs should score < 0.70, got {score}"


# ── bundle-specific tests ──────────────────────────────────────────────────────

@pytest.mark.parametrize("bundle_id", [
    "tech_decision", "proposal_kr", "business_plan_kr",
    "edu_plan_kr", "meeting_minutes_kr", "presentation_kr",
])
def test_bundle_eval_existing_bundles(bundle_id):
    bundle = get_bundle_spec(bundle_id)
    docs = _make_docs(bundle)
    result = evaluate_bundle_docs(bundle, docs)
    assert result.overall_score > 0.0


def test_bundle_eval_summary_format():
    bundle = get_bundle_spec("tech_decision")
    docs = _make_docs(bundle)
    result = evaluate_bundle_docs(bundle, docs)
    assert result.summary  # Non-empty
    assert any(c in result.summary for c in ["✅", "⚠️", "❌"])
