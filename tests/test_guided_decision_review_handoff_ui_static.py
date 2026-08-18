from pathlib import Path


def _handoff_source(html: str) -> str:
    start = html.index("const GUIDED_DECISION_REVIEW_HANDOFF_SHA256_HEADER")
    end = html.index("const DECISION_EVIDENCE_NODE_LABELS")
    return html[start:end]


def test_guided_review_handoff_static_contract_verifies_before_download() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _handoff_source(html)

    assert 'data-guided-decision-review-handoff' in source
    assert "↓ Review handoff JSON" in source
    assert "/guided-decision-review-handoff?bundle_type=" in source
    assert "GUIDED_DECISION_REVIEW_HANDOFF_SHA256_HEADER" in source
    assert "bodySha256 !== await sha256Hex(bodyBytes)" in source
    assert "X-DecisionDoc-Projection-Fingerprint" in source
    assert "X-DecisionDoc-Operational-Approval" in source
    assert "X-Content-Type-Options" in source
    assert "Cache-Control" in source
    assert "Content-Disposition" in source
    assert "isGuidedDecisionReviewHandoff" in source
    assert "handoff.contract_version === 'guided-decision-review-handoff.v1'" in source
    assert "handoff.source_contract_version === 'decision_evidence_map.v1'" in source
    assert "isGuidedDecisionReviewText(handoff.source_generated_at)" in source
    assert "handoff.read_only === true" in source
    assert "handoff.snapshot_atomic === false" in source
    assert "handoff.requires_recheck_before_reliance === true" in source
    assert "handoff.handoff_persisted === false" in source
    assert "isGuidedDecisionReviewAuthority(handoff.authority)" in source
    assert "_triggerBrowserDownload(" in source


def test_guided_review_handoff_static_contract_rejects_stale_context() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _handoff_source(html)
    request_guard = source[
        source.index("function isGuidedDecisionReviewHandoffRequestCurrent"):
        source.index("async function recheckGuidedDecisionReviewHandoff")
    ]

    for field in (
        "requestId",
        "projectLoadId",
        "authRevision",
        "tenantId",
        "userId",
        "projectId",
        "projectionFingerprint",
    ):
        assert f"context.{field}" in request_guard
    assert "_currentProjectDetail?.decisionEvidenceMap?.projection_fingerprint" in request_guard
    assert "if (!requestIsCurrent()) return;" in request_guard
    assert "method: 'POST'" not in request_guard
    assert "localStorage" not in request_guard
    assert "sessionStorage" not in request_guard
    assert "_guidedDecisionReviewHandoffRequestId += 1;" in html
    assert "_clearScopedExportDownloadUrls(GUIDED_DECISION_REVIEW_HANDOFF_DOWNLOAD_SCOPE)" in html


def test_guided_review_handoff_control_is_responsive_and_accessible() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert (
        'aria-label="Download guided decision review handoff JSON"'
        in html
    )
    assert ".guided-decision-review-handoff:disabled" in html
    assert ".guided-decision-review-head-actions { justify-items: start; }" in html
    assert 'id="guided-decision-review-announcement"' in html
    assert 'aria-live="polite"' in html


def test_guided_review_recheck_static_contract_is_page_memory_and_hash_bound() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _handoff_source(html)

    assert 'data-guided-decision-review-recheck' in source
    assert "Recheck handoff" in source
    assert "/guided-decision-review-handoff/recheck" in source
    assert "method: 'POST'" in source
    assert "guided-decision-review-recheck-request.v1" in source
    assert "guided-decision-review-recheck-receipt.v1" in source
    assert "stringifyGuidedDecisionReviewAscii" in source
    assert "character.charCodeAt(0).toString(16).padStart(4, '0')" in source
    assert "source_handoff: verifiedSource.handoff" in source
    assert "source_handoff_sha256: verifiedSource.bodySha256" in source
    assert "source_generated_at" in source
    assert "source_review_state_fingerprint_sha256" in source
    assert "current_review_state_fingerprint_sha256" in source
    assert "review_state_status" in source
    assert "bodySha256 !== await sha256Hex(bodyBytes)" in source
    assert "currentHandoffSha256 !== await sha256Hex(currentCanonical)" in source
    assert "sourceFingerprintSha256 !== await sha256Hex(sourceFingerprint)" in source
    assert "currentFingerprintSha256 !== await sha256Hex(currentFingerprint)" in source
    assert "_guidedDecisionReviewVerifiedHandoff" in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source


def test_guided_review_recheck_static_contract_invalidates_stale_scope() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _handoff_source(html)

    for field in (
        "requestId",
        "projectLoadId",
        "authRevision",
        "tenantId",
        "userId",
        "projectId",
        "sourceHandoffSha256",
    ):
        assert f"context.{field}" in source
    assert "clearGuidedDecisionReviewHandoffSource()" in html
    assert "_guidedDecisionReviewRecheckRequestId += 1;" in html
    assert "_clearScopedExportDownloadUrls(GUIDED_DECISION_REVIEW_RECHECK_DOWNLOAD_SCOPE)" in html
    assert "receipt.review_state_status === 'changed'" in source
    assert "_guidedDecisionReviewVerifiedHandoff = null;" in source


def test_guided_review_disposition_static_contract_is_receipt_bound() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _handoff_source(html)

    assert 'data-guided-decision-review-disposition' in source
    assert 'data-guided-decision-review-disposition-download' in source
    assert "/guided-decision-review-handoff/review-disposition" in source
    assert "guided-decision-review-disposition-request.v1" in source
    assert "guided-decision-review-disposition-receipt.v1" in source
    assert "source_recheck_receipt: verifiedRecheck.receipt" in source
    assert "source_recheck_receipt_sha256: verifiedRecheck.bodySha256" in source
    assert "disposition_binding_sha256" in source
    assert "reviewer_identity_bound" in source
    assert "disposition_receipt_persisted" in source
    assert "acknowledged_unchanged" in source
    assert "new_handoff_required" in source
    assert "review_deferred" in source
    assert "_guidedDecisionReviewVerifiedRecheck" in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source


def test_guided_review_disposition_static_contract_invalidates_stale_scope() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _handoff_source(html)

    for field in (
        "requestId",
        "projectLoadId",
        "authRevision",
        "tenantId",
        "userId",
        "projectId",
        "sourceRecheckReceiptSha256",
        "reviewDisposition",
    ):
        assert f"context.{field}" in source
    assert "_guidedDecisionReviewDispositionRequestId += 1;" in source
    assert "clearGuidedDecisionReviewVerifiedRecheck()" in source
    assert "_clearScopedExportDownloadUrls(" in source
    assert "GUIDED_DECISION_REVIEW_DISPOSITION_DOWNLOAD_SCOPE" in source
    assert "dispositionSelect.value !== context.reviewDisposition" in source


def test_guided_review_registry_static_contract_is_page_memory_bound_and_single_flight() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _handoff_source(html)

    assert 'data-guided-decision-review-registry-create' in source
    assert 'data-guided-decision-review-registry-refresh' in source
    assert 'data-guided-decision-review-registry-list' in source
    assert "/guided-decision-review-dispositions?bundle_type=" in source
    assert "guided-decision-review-disposition-record-request.v1" in source
    assert "guided-decision-review-disposition-record.v1" in source
    assert "source_disposition_receipt: source.receipt" in source
    assert "source_disposition_receipt_sha256: source.bodySha256" in source
    assert "crypto.randomUUID().toLowerCase()" in source
    assert "_guidedDecisionReviewRegistryOperation?.scopeKey === scopeKey" in source
    assert "if (_guidedDecisionReviewRegistryPending) return;" in source
    assert "_guidedDecisionReviewRegistryPending === token" in source
    assert "if (_guidedDecisionReviewRegistryPending === token)" in source
    assert "_guidedDecisionReviewRegistryPending = null;" in source
    assert "normalizeIndependentGuidedDecisionReviewDispositionReceipt" in source
    assert "record.request_binding_sha256 !== await sha256Hex" in source
    assert "record.record_binding_sha256 !== await sha256Hex" in source
    assert "bodySha256 !== await sha256Hex(bodyBytes)" in source
    assert "new Blob([bodyBytes]" in source
    assert "localStorage" not in source
    assert "sessionStorage" not in source


def test_guided_review_registry_static_contract_discards_scope_and_source_drift() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _handoff_source(html)

    for field in (
        "projectLoadId",
        "authRevision",
        "tenantId",
        "userId",
        "projectId",
        "bundleType",
        "sourceDispositionReceiptSha256",
        "operationId",
    ):
        assert field in source
    assert "clearGuidedDecisionReviewDispositionRegistrySource();" in source
    assert "_guidedDecisionReviewRegistryRequestId += 1;" in source
    assert "_guidedDecisionReviewRegistryListRequestId += 1;" in source
    assert "_guidedDecisionReviewRegistryDownloadRequestId += 1;" in source
    assert "_guidedDecisionReviewVerifiedDisposition = null;" in source
    assert "_guidedDecisionReviewRegistryOperation = null;" in source
    assert "_guidedDecisionReviewRegistryPending = null;" in source


def test_procurement_review_invalidation_clears_guided_review_page_memory() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    start = html.index("function invalidateProcurementReviewViews()")
    end = html.index("function wireProcurementReviewInboxActions", start)
    source = html[start:end]

    assert "clearGuidedDecisionReviewHandoffSource();" in source
