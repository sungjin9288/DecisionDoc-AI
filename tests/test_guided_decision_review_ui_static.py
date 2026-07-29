from pathlib import Path


def _guided_review_source(html: str) -> str:
    start = html.index("const GUIDED_DECISION_REVIEW_AUTHORITY_KEYS")
    end = html.index("const DECISION_EVIDENCE_NODE_LABELS")
    return html[start:end]


def test_guided_decision_review_static_contract_is_read_only_and_fail_closed():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _guided_review_source(html)

    assert "isGuidedDecisionReviewMap" in source
    assert "map.contract_version === 'decision_evidence_map.v1'" in source
    assert "map.read_only === true" in source
    assert "map.snapshot_atomic === false" in source
    assert "map.project_id === projectId" in source
    assert "isGuidedDecisionReviewSha256(map.projection_fingerprint)" in source
    assert "isGuidedDecisionReviewCoverage(map.coverage)" in source
    assert "typeof map.truncated === 'boolean'" in source
    assert "isGuidedDecisionReviewSourceRevision" in source
    assert "isGuidedDecisionReviewNode" in source
    assert "isGuidedDecisionReviewEdge" in source
    assert "isGuidedDecisionReviewDiagnostic" in source
    assert "isGuidedDecisionReviewBlueprint" in source
    assert "counts.reduce((total, count) => total + count, 0) === coverage.total" in source
    assert "Object.keys(authority).length === GUIDED_DECISION_REVIEW_AUTHORITY_KEYS.length" in source
    assert "authority[key] === false" in source
    assert "renderGuidedDecisionReview" in source
    assert "return '';" in source
    assert 'id="guided-decision-review"' in source
    assert 'aria-labelledby="guided-decision-review-title"' in source
    assert '<ol class="guided-decision-review-steps"' in source
    assert source.count("Overall state:") == 1
    assert source.count("Recommended next check:") == 1
    assert "READ ONLY · NON-ATOMIC · NO APPROVAL/EXPORT/PROVIDER EXECUTION" in source
    assert 'aria-live="polite"' in source
    assert source.count("method: 'POST'") == 2
    assert "/guided-decision-review-handoff/recheck" in source
    assert (
        "contract_version: 'guided-decision-review-recheck-request.v1'"
        in source
    )
    assert "/guided-decision-review-handoff/review-disposition" in source
    assert (
        "contract_version: 'guided-decision-review-disposition-request.v1'"
        in source
    )
    assert "progressbar" not in source
    assert "ready" not in source
    assert "approved" not in source
    assert "complete" not in source


def test_guided_decision_review_static_contract_keeps_semantic_navigation_and_statuses():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _guided_review_source(html)

    for stage in ("Decision", "Evidence", "Review", "Documents"):
        assert stage in source
    for status in ("not_observed", "needs_attention", "in_review", "observed"):
        assert status in source
    assert "getGuidedDecisionReviewLatestReview" in source
    assert "prepared_at" in source
    assert "packet_sha256" in source
    assert "getGuidedDecisionReviewLatestDocument" in source
    assert "generated_at" in source
    assert "doc_id" in source
    assert "prefers-reduced-motion: reduce" in source
    assert "scrollIntoView" in source
    assert "target.focus({ preventScroll: true })" in source
    assert "data-guided-decision-review-target" in source
    assert 'id="project-decision-area"' in html
    assert 'id="project-review-workspace"' in html
    assert 'id="decision-evidence-map"' in html
    assert 'aria-label="Decision Evidence Map" tabindex="-1"' in html
    assert 'id="project-documents-heading"' in html
    assert ".guided-decision-review-steps { grid-template-columns: 1fr; }" in html
