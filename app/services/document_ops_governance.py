"""Reviewer-facing overview for DocumentOps governance evidence."""

from __future__ import annotations

from typing import Any


_GOVERNANCE_GUARD_FLAGS = (
    "training_execution_allowed",
    "provider_api_calls_allowed",
    "external_upload_allowed",
    "provider_job_started",
    "model_promotion_allowed",
)
_SIGNOFF_AUTHORIZATION_FLAGS = (
    "training_execution_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "model_promotion_authorized",
)
_SIGNOFF_SIDE_EFFECT_FLAGS = (
    "actual_reviewer_approval_recorded_by_summary",
    "training_execution_started",
    "external_dataset_uploaded",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "model_promoted",
)
_INVENTORY_ISSUE_COUNTS = (
    "invalid_reference",
    "referenced_missing",
    "referenced_tampered",
    "unreferenced",
)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _count(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _all_false(payload: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(payload.get(field) is False for field in fields)


def _governance_boundary_is_clear(summary: dict[str, Any]) -> bool:
    return (
        summary.get("read_only") is True
        and summary.get("no_side_effects") is True
        and _all_false(summary, _GOVERNANCE_GUARD_FLAGS)
    )


def _inventory_boundary_is_clear(inventory: dict[str, Any]) -> bool:
    observation = _mapping(inventory.get("observation_boundary"))
    cleanup = _mapping(inventory.get("cleanup_boundary"))
    return (
        inventory.get("read_only") is True
        and observation.get("metadata_snapshot_atomic") is True
        and observation.get("multi_object_snapshot_atomic") is False
        and cleanup.get("automatic_cleanup_allowed") is False
        and cleanup.get("objects_deleted") is False
        and cleanup.get("manual_recheck_required") is True
    )


def _signoff_boundary_is_clear(summary: dict[str, Any]) -> bool:
    aggregate = _mapping(summary.get("aggregate"))
    side_effects = _mapping(summary.get("side_effect_boundary"))
    return (
        summary.get("read_only") is True
        and aggregate.get("all_protected_training_flags_false") is True
        and _all_false(summary, _GOVERNANCE_GUARD_FLAGS)
        and _all_false(aggregate, _SIGNOFF_AUTHORIZATION_FLAGS)
        and _all_false(side_effects, _SIGNOFF_SIDE_EFFECT_FLAGS)
    )


def _inventory_issue_count(inventory: dict[str, Any]) -> int:
    counts = _mapping(inventory.get("counts"))
    return sum(_count(counts.get(field)) for field in _INVENTORY_ISSUE_COUNTS)


def _check_status(*, boundary_clear: bool, passed: bool) -> str:
    if not boundary_clear:
        return "boundary_attention"
    return "passed" if passed else "attention"


def build_document_ops_governance_overview(
    *,
    tenant_id: str,
    generated_at: str,
    training_governance_summary: dict[str, Any],
    artifact_inventory: dict[str, Any],
    reviewer_signoff_summary: dict[str, Any],
) -> dict[str, Any]:
    """Combine three read models without claiming a transactional snapshot."""
    inventory_counts = _mapping(artifact_inventory.get("counts"))
    governance_blockers = _items(training_governance_summary.get("blockers"))
    signoff_aggregate = _mapping(reviewer_signoff_summary.get("aggregate"))

    inventory_issue_count = _inventory_issue_count(artifact_inventory)
    inventory_clean = artifact_inventory.get("status") == "clean" and inventory_issue_count == 0
    governance_ready = (
        training_governance_summary.get("status")
        == "governance_ready_for_human_review"
    )
    signoff_complete = (
        reviewer_signoff_summary.get("overall_status")
        == "manual_signoff_complete_no_training_authorization"
    )

    governance_boundary_clear = _governance_boundary_is_clear(
        training_governance_summary
    )
    inventory_boundary_clear = _inventory_boundary_is_clear(artifact_inventory)
    signoff_boundary_clear = _signoff_boundary_is_clear(reviewer_signoff_summary)
    boundaries_clear = (
        governance_boundary_clear
        and inventory_boundary_clear
        and signoff_boundary_clear
    )

    checks = [
        {
            "id": "artifact_integrity",
            "status": _check_status(
                boundary_clear=inventory_boundary_clear,
                passed=inventory_clean,
            ),
            "summary": (
                f"권위 reference {_count(inventory_counts.get('authoritative_references'))}개, "
                f"검증 완료 {_count(inventory_counts.get('referenced_verified'))}개, "
                f"문제 {inventory_issue_count}개"
            ),
        },
        {
            "id": "governance_chain",
            "status": _check_status(
                boundary_clear=governance_boundary_clear,
                passed=governance_ready,
            ),
            "summary": f"governance blocker {len(governance_blockers)}개",
        },
        {
            "id": "reviewer_signoff",
            "status": _check_status(
                boundary_clear=signoff_boundary_clear,
                passed=signoff_complete,
            ),
            "summary": (
                f"완료 {_count(signoff_aggregate.get('completed_record_count'))}개, "
                f"pending {_count(signoff_aggregate.get('pending_record_count'))}개, "
                f"follow-up {_count(signoff_aggregate.get('manual_follow_up_record_count'))}개"
            ),
        },
    ]

    if not boundaries_clear:
        status = "boundary_attention"
        next_review_action = (
            "권한 경계가 예상과 다릅니다. 세 원본 summary를 확인하고 외부 실행을 "
            "중단한 상태에서 다시 점검하세요."
        )
    elif not inventory_clean:
        status = "artifact_integrity_attention"
        next_review_action = (
            "권위 metadata와 selected backend artifact 차이를 먼저 확인하고 정리 판단 "
            "전에 inventory를 다시 조회하세요. 이 overview는 파일을 삭제하지 않습니다."
        )
    elif not governance_ready:
        status = "governance_review_needed"
        next_review_action = (
            "Governance blocker를 해소하고 pre-execution audit까지 다시 검증한 뒤 "
            "overview를 새로고침하세요."
        )
    elif not signoff_complete:
        status = "reviewer_signoff_pending"
        next_review_action = (
            "Tenant-local reviewer sign-off를 별도 사람 검토 절차에서 완료한 뒤 "
            "overview를 새로고침하세요."
        )
    else:
        status = "review_evidence_ready"
        next_review_action = (
            "세 read-only 검토가 각각 통과했습니다. 필요하면 sign-off JSON을 handoff "
            "증적으로 내려받으세요. 외부 실행 권한은 별도 승인 대상입니다."
        )

    return {
        "report_type": "document_ops_governance_review_overview",
        "tenant_id": tenant_id,
        "generated_at": generated_at,
        "read_only": True,
        "status": status,
        "checks": checks,
        "next_review_action": next_review_action,
        "observation_boundary": {
            "source_reports_read_independently": True,
            "combined_snapshot_atomic": False,
            "manual_recheck_required": True,
        },
        "authorization_boundary": {
            "dataset_upload_authorized": False,
            "provider_api_call_authorized": False,
            "training_execution_authorized": False,
            "provider_job_creation_authorized": False,
            "model_promotion_authorized": False,
        },
        "training_governance_summary": training_governance_summary,
        "artifact_inventory": artifact_inventory,
        "reviewer_signoff_summary": reviewer_signoff_summary,
    }
