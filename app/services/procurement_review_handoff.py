"""Freshness rules for procurement review evidence used by downstream documents."""
from __future__ import annotations

from typing import Any


PROCUREMENT_REVIEW_HANDOFF_BUNDLE_IDS = {
    "rfp_analysis_kr",
    "proposal_kr",
    "performance_plan_kr",
}


def load_validated_procurement_review_evidence(
    review_store: Any,
    *,
    tenant_id: str,
    project_id: str,
    packet_sha256: str,
) -> Any | None:
    """Load a review record only after its persisted artifacts still verify."""
    record = review_store.get(
        tenant_id=tenant_id,
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    if record is None:
        return None
    review_store.read_packet(
        record,
        tenant_id=tenant_id,
        project_id=project_id,
        packet_sha256=packet_sha256,
    )
    if record.review_status == "completed":
        review_store.read_reviewed_package(
            record,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
    return record


def describe_procurement_review_document_status(
    *,
    bundle_id: str,
    packet_sha256: str | None,
    source_updated_at: str | None,
    source_decision: str | None,
    review_record: Any | None,
    procurement_record: Any | None,
) -> dict[str, str] | None:
    """Describe whether a saved document still matches its review evidence."""
    if bundle_id not in PROCUREMENT_REVIEW_HANDOFF_BUNDLE_IDS or not packet_sha256:
        return None

    if review_record is None:
        return {
            "status": "review_evidence_missing",
            "tone": "danger",
            "copy": "검토 증빙 없음",
            "summary": "이 문서가 참조한 procurement review packet을 현재 tenant에서 찾을 수 없습니다.",
        }

    review_is_valid = (
        review_record.packet_sha256 == packet_sha256
        and review_record.review_status == "completed"
        and review_record.decision == source_decision
        and review_record.operational_approval is False
    )
    if not review_is_valid:
        return {
            "status": "review_evidence_invalid",
            "tone": "danger",
            "copy": "검토 증빙 불일치",
            "summary": "저장된 procurement review 상태가 이 문서의 provenance와 일치하지 않습니다.",
        }

    if not source_updated_at:
        return {
            "status": "review_source_unverified",
            "tone": "warning",
            "copy": "검토 source 확인 필요",
            "summary": "이 문서에는 review packet의 source timestamp가 없어 현재 procurement 기준과 비교할 수 없습니다.",
        }

    if procurement_record is None:
        return {
            "status": "procurement_source_missing",
            "tone": "danger",
            "copy": "procurement source 없음",
            "summary": "현재 procurement decision을 찾을 수 없어 review-bound 문서의 freshness를 확인할 수 없습니다.",
        }

    if source_updated_at != procurement_record.updated_at:
        return {
            "status": "stale_procurement_review",
            "tone": "danger",
            "copy": "현재 procurement 대비 이전 review 기준",
            "summary": "procurement decision이 review 완료 뒤 변경되었습니다. 새 review를 완료한 뒤 문서를 다시 생성해야 최신 근거가 반영됩니다.",
        }

    return {
        "status": "current",
        "tone": "success",
        "copy": "현재 review 기준",
        "summary": "현재 procurement decision과 완료된 review packet이 같은 source 기준입니다.",
    }
