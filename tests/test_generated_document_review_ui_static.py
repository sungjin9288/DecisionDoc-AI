from pathlib import Path


def _review_source(html: str) -> str:
    start = html.index("const GENERATED_DOCUMENT_REVIEW_FORMATS")
    end = html.index("function getProcurementReviewInboxStatusLabel", start)
    return html[start:end]


def test_generated_document_review_ui_exposes_creation_history_and_inbox() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _review_source(html)

    assert 'data-project-detail-action="generated-document-review-create"' in html
    assert "검토 패킷 전달" in html
    assert "검토 증빙이며 운영 승인 아님" in source
    assert "GENERATED_DOCUMENT_REVIEW_FORMATS = ['docx', 'pdf', 'xlsx', 'hwp', 'pptx']" in source
    assert "/documents/${encodeURIComponent(context.documentId)}/generated-reviews" in source
    assert "'/generated-document-reviews?review_status=pending&limit=50&offset=0'" in source
    assert "/generated-document-reviews/${encodeURIComponent(context.packetSha256)}/packet" in source
    assert 'id="generated-document-review-inbox"' in html
    assert 'data-review-inbox-tab="generated"' in html
    assert 'data-review-inbox-tab="procurement"' in html
    assert "activeInbox: 'procurement'" in source
    assert "if (!canUseGeneratedDocumentReviews()) return '';" in source
    assert "문서 검토 전달" in html


def test_generated_document_review_download_fails_closed_before_blob() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _review_source(html)
    verification = source[
        source.index("async function readVerifiedGeneratedDocumentReviewPacket") :
        source.index("function generatedDocumentReviewSourceStatusMeta")
    ]

    for header in (
        "Content-Length",
        "X-DecisionDoc-Packet-SHA256",
        "X-DecisionDoc-Manifest-SHA256",
        "X-DecisionDoc-Artifact-Count",
        "X-DecisionDoc-Review-Status",
        "X-DecisionDoc-Reviewer-Identity-Bound",
        "X-DecisionDoc-Review-Only",
        "X-DecisionDoc-Packet-Persisted",
        "X-DecisionDoc-Human-Review-Completed",
        "X-DecisionDoc-Operational-Approval",
    ):
        assert header in verification
    for authority in (
        "Approval-Authorized",
        "Aws-Execution-Authorized",
        "Dataset-Upload-Authorized",
        "Deployment-Authorized",
        "G2b-Submission-Authorized",
        "Provider-Execution-Authorized",
        "Training-Execution-Authorized",
    ):
        assert f"X-DecisionDoc-Authority-{authority}" in source
    assert "GENERATED_DOCUMENT_REVIEW_AUTHORITY_HEADERS.every(" in verification
    assert "header => response.headers.get(header) === 'false'" in verification
    assert "contentType !== 'application/zip'" in verification
    assert "contentLength !== packetBytes.byteLength" in verification
    assert "actualPacketSha256 !== packetSha256" in verification
    assert "new Blob([packetBytes], { type: 'application/zip' })" in verification
    assert verification.index("actualPacketSha256 !== packetSha256") < verification.index(
        "new Blob([packetBytes], { type: 'application/zip' })"
    )


def test_generated_document_review_requests_are_context_bound_and_single_flight() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _review_source(html)

    assert "requestEpoch: 0" in source
    assert "objectUrls: new Set()" in source
    assert "pendingOperations: new Set()" in source
    for field in (
        "requestEpoch",
        "authRevision",
        "tenantId",
        "userId",
        "projectId",
        "documentId",
        "packetSha256",
    ):
        assert f"context.{field}" in source
    assert "_generatedDocumentReviewState.pendingOperations.has(operationKey)" in source
    assert "URL.revokeObjectURL(url)" in source
    assert "clearGeneratedDocumentReviewObjectUrls()" in source
    assert "invalidateGeneratedDocumentReviewState()" in html
    assert "if (!requestIsCurrent()) return;" in source


def test_generated_document_review_source_drift_requires_confirmation() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    source = _review_source(html)

    assert "현재 문서가 전달 시점 이후 변경되었습니다." in source
    assert "현재 프로젝트에서 원본 문서를 찾을 수 없습니다." in source
    assert "window.confirm(sourceMeta.confirmation)" in source
    assert "expectedSourceStatus" in source
    assert "X-DecisionDoc-Source-Status" in source
    assert "검토 대기" in source
    assert "운영 승인 아님" in source


def test_generated_document_review_layout_has_mobile_overflow_guards() -> None:
    html = Path("app/static/index.html").read_text(encoding="utf-8")

    assert ".generated-document-review-row" in html
    assert ".generated-document-review-dialog" in html
    assert ".generated-document-review-actions" in html
    assert ".generated-document-review-row { grid-template-columns: 1fr; }" in html
    assert ".generated-document-review-actions { justify-content: flex-start; }" in html
    assert ".generated-document-review-dialog { width: min(100%, 560px); }" in html
