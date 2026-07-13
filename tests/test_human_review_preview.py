from __future__ import annotations

from app.eval.human_review_receipt import (
    build_pending_human_review_receipt,
    record_bundle_review,
    validate_human_review_receipt,
)
from app.services.human_review_preview import build_human_review_summary


MANIFEST_SHA256 = "a" * 64
MANIFEST = {
    "schema_version": "decisiondoc.finished_document_review.v3",
    "generated_at": "2026-07-13T10:00:00+00:00",
    "bundles": {
        "proposal_kr": {
            "title": "공공 서비스 제안서",
            "request": {
                "goal": "검토 가능한 제안서 작성",
                "context": "발주처 입력 근거",
                "constraints": "개인정보 보호",
                "audience": "평가위원",
            },
            "quality": {
                "validator_pass": True,
                "lint_pass": True,
                "numeric_grounding_review": {"status": "passed"},
            },
            "markdown_docs": {
                "proposal": "proposal_kr/markdown/proposal.md",
            },
        },
    },
    "external_actions": {
        "provider_api_execution": False,
        "production_service_resume": False,
    },
}
DOCUMENTS = {
    "proposal_kr": {
        "proposal": "# 제안서\n\n<script>alert('document')</script>",
    }
}


def _render(receipt: dict) -> str:
    validation = validate_human_review_receipt(
        receipt,
        MANIFEST,
        manifest_sha256=MANIFEST_SHA256,
    )
    return build_human_review_summary(
        manifest=MANIFEST,
        receipt=receipt,
        validation=validation,
        bundle_documents=DOCUMENTS,
    )


def test_human_review_summary_shows_pending_state_and_evidence_boundary() -> None:
    receipt = build_pending_human_review_receipt(
        MANIFEST,
        manifest_sha256=MANIFEST_SHA256,
    )

    summary = _render(receipt)

    assert "문서 검토 작업공간" in summary
    assert "검토 대기" in summary
    assert "공공 서비스 제안서" in summary
    assert "발주처 입력 근거" in summary
    assert "Schema validator" in summary
    assert "# 제안서" in summary
    assert "&lt;script&gt;alert(&#x27;document&#x27;)&lt;/script&gt;" in summary
    assert MANIFEST_SHA256 in summary
    assert summary.count("승인 안 됨") == 2
    assert 'href="review.html"' in summary
    assert 'href="human_review_receipt.json"' in summary
    assert "<script" not in summary
    assert summary.count("<div") == summary.count("</div>")


def test_human_review_summary_escapes_reviewer_content_and_shows_completion() -> None:
    pending = build_pending_human_review_receipt(
        MANIFEST,
        manifest_sha256=MANIFEST_SHA256,
    )
    completed = record_bundle_review(
        pending,
        bundle_type="proposal_kr",
        reviewer="<Reviewer & Owner>",
        factual_grounding="passed",
        visual_review="passed",
        notes="<script>alert('unsafe')</script>",
        reviewed_at="2026-07-13T11:00:00+00:00",
    )

    summary = _render(completed)

    assert "검토 완료" in summary
    assert "수락" in summary
    assert "&lt;Reviewer &amp; Owner&gt;" in summary
    assert "&lt;script&gt;alert(&#x27;unsafe&#x27;)&lt;/script&gt;" in summary
    assert "<script>alert('unsafe')</script>" not in summary

    validation = validate_human_review_receipt(
        completed,
        MANIFEST,
        manifest_sha256=MANIFEST_SHA256,
    )
    encoded_link_summary = build_human_review_summary(
        manifest=MANIFEST,
        receipt=completed,
        validation=validation,
        receipt_path="javascript:alert.json",
    )
    assert 'href="javascript%3Aalert.json"' in encoded_link_summary
    assert 'href="javascript:alert.json"' not in encoded_link_summary
