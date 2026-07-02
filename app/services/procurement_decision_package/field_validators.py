"""Field-level validators for individual decision-package sections.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.services.procurement_decision_package.constants import (
    AUDIT_MANIFEST_ARTIFACT_GROUPS,
    AUDIT_MANIFEST_FIELD_ORDER,
    AUDIT_MANIFEST_PACKET_STATUS,
    AUDIT_MANIFEST_SCHEMA_PURPOSE,
    BID_READINESS_CHECKLIST_FIELD_ORDER,
    EVIDENCE_SUMMARY_FIELD_ORDER,
    EXCLUDED_ACTION_ORDER,
    EXPORT_MANIFEST_FIELD_ORDER,
    HARD_FILTER_FIELD_ORDER,
    INCLUDED_ARTIFACT_ORDER,
    NON_APPROVAL_MARKER,
    NON_AUTHORIZATION_MARKER,
    OPPORTUNITY_REF_FIELD_ORDER,
    PACKAGE_CHECKLIST_STATUSES,
    PACKAGE_EVIDENCE_TYPES,
    PACKAGE_HARD_FILTER_STATUSES,
    PACKAGE_SOFT_FIT_BANDS,
    PENDING_SIGNOFF_FIELD_ORDER,
    PROPOSAL_ALLOWED_NEXT_STEPS,
    PROPOSAL_HANDOFF_FIELD_ORDER,
    PROPOSAL_HANDOFF_SCOPE,
    REVIEWER_HANDOFF_FIELD_ORDER,
    SCOPED_REVIEW_MARKER,
    SIGNOFF_SCOPE,
    SOFT_FIT_FACTOR_FIELD_ORDER,
    SOFT_FIT_SCORE_FIELD_ORDER,
    VALIDATION_SUMMARY_FIELD_ORDER,
)
from app.services.procurement_decision_package.json_helpers import (
    _field_path,
    _is_non_negative_int,
    _list_item_path,
    _require_exact_mapping_fields,
    _require_exact_ordered_values,
    _require_mapping,
    _require_non_empty_string,
    _require_non_empty_string_list,
    _require_string_items,
    _require_unique_values,
)

def _validate_opportunity_ref(value: Any, path: str) -> None:
    opportunity_ref = _require_mapping(value, path)
    _require_exact_mapping_fields(
        opportunity_ref,
        OPPORTUNITY_REF_FIELD_ORDER,
        path,
    )
    _require_non_empty_string_fields(
        opportunity_ref,
        OPPORTUNITY_REF_FIELD_ORDER,
        path=path,
    )


def _require_non_empty_string_fields(
    mapping: Mapping[str, Any],
    fields: Sequence[str],
    *,
    path: str,
) -> None:
    for field in fields:
        _require_non_empty_string_field(mapping, field, path=path)


def _require_non_empty_string_field(
    mapping: Mapping[str, Any],
    field: str,
    *,
    path: str,
) -> str:
    return _require_non_empty_string(mapping.get(field), _field_path(path, field))


def _validate_hard_filter_item(value: Any, path: str) -> None:
    hard_filter = _require_mapping(value, path)
    _require_exact_mapping_fields(
        hard_filter,
        HARD_FILTER_FIELD_ORDER,
        path,
    )
    _require_non_empty_string_fields(
        hard_filter,
        ("filter_id", "reason"),
        path=path,
    )
    status = _require_non_empty_string_field(hard_filter, "status", path=path)
    if status not in PACKAGE_HARD_FILTER_STATUSES:
        raise ValueError(
            f"{_field_path(path, 'status')} "
            "must be a reviewed package hard-filter status"
        )


def _validate_soft_fit_score(value: Any, path: str) -> None:
    soft_fit_score = _require_mapping(value, path)
    _require_exact_mapping_fields(
        soft_fit_score,
        SOFT_FIT_SCORE_FIELD_ORDER,
        path,
    )
    _require_score(soft_fit_score.get("score"), _field_path(path, "score"))
    band = _require_non_empty_string_field(soft_fit_score, "band", path=path)
    if band not in PACKAGE_SOFT_FIT_BANDS:
        raise ValueError(
            f"{_field_path(path, 'band')} must be a reviewed package score band"
        )
    factors = soft_fit_score.get("factors")
    factors_path = _field_path(path, "factors")
    _validate_list_items(
        factors,
        factors_path,
        _validate_soft_fit_factor,
    )


def _validate_soft_fit_factor(value: Any, path: str) -> None:
    factor = _require_mapping(value, path)
    _require_exact_mapping_fields(
        factor,
        SOFT_FIT_FACTOR_FIELD_ORDER,
        path,
    )
    _require_non_empty_string_field(factor, "name", path=path)
    _require_score(factor.get("score"), _field_path(path, "score"))
    _require_non_empty_string_list(
        factor.get("evidence_ids"),
        _field_path(path, "evidence_ids"),
    )


def _require_score(value: Any, path: str) -> int:
    if not _is_non_negative_int(value) or value > 100:
        raise ValueError(f"{path} must be an integer from 0 to 100")
    return value


def _validate_list_items(
    value: Any,
    path: str,
    validate_item: Callable[[Any, str], None],
) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    for index, item in enumerate(value):
        validate_item(item, _list_item_path(path, index))


def _validate_evidence_summary_item(value: Any, path: str) -> None:
    evidence = _require_mapping(value, path)
    _require_exact_mapping_fields(
        evidence,
        EVIDENCE_SUMMARY_FIELD_ORDER,
        path,
    )
    _require_non_empty_string_field(evidence, "evidence_id", path=path)
    evidence_type = _require_non_empty_string_field(evidence, "type", path=path)
    if evidence_type not in PACKAGE_EVIDENCE_TYPES:
        raise ValueError(
            f"{_field_path(path, 'type')} must be a reviewed evidence type"
        )
    _require_non_empty_string_fields(
        evidence,
        ("source", "summary"),
        path=path,
    )


def _validate_bid_readiness_checklist_item(value: Any, path: str) -> None:
    checklist_item = _require_mapping(value, path)
    _require_exact_mapping_fields(
        checklist_item,
        BID_READINESS_CHECKLIST_FIELD_ORDER,
        path,
    )
    _require_non_empty_string_fields(
        checklist_item,
        ("item_id", "label", "owner", "required_before"),
        path=path,
    )
    status = _require_non_empty_string_field(
        checklist_item,
        "status",
        path=path,
    )
    if status not in PACKAGE_CHECKLIST_STATUSES:
        raise ValueError(
            f"{_field_path(path, 'status')} must be a reviewed bid-readiness status"
        )


def _validate_validation_summary(value: Any, path: str) -> None:
    validation_summary = _require_mapping(value, path)
    _require_exact_mapping_fields(
        validation_summary,
        VALIDATION_SUMMARY_FIELD_ORDER,
        path,
    )
    _require_non_empty_string_fields(
        validation_summary,
        ("schema_status", "boundary_status"),
        path=path,
    )
    operator_summary = _require_non_empty_string_field(
        validation_summary,
        "operator_summary",
        path=path,
    )
    next_review_action = _require_non_empty_string_field(
        validation_summary,
        "next_review_action",
        path=path,
    )
    if NON_APPROVAL_MARKER not in operator_summary:
        raise ValueError(
            f"{_field_path(path, 'operator_summary')} "
            "must describe the non-approval boundary"
        )
    if SCOPED_REVIEW_MARKER not in next_review_action:
        raise ValueError(
            f"{_field_path(path, 'next_review_action')} "
            "must keep review scoped to the package"
        )
    if not isinstance(validation_summary.get("unresolved_gaps"), list):
        raise ValueError(f"{_field_path(path, 'unresolved_gaps')} must be a list")


def _require_non_authorization_note_field(value: dict[str, Any], *, path: str) -> None:
    non_authorization_note = _require_non_empty_string_field(
        value,
        "non_authorization_note",
        path=path,
    )
    if NON_AUTHORIZATION_MARKER not in non_authorization_note:
        raise ValueError(
            f"{_field_path(path, 'non_authorization_note')} must describe "
            "the non-authorization boundary"
        )


def _validate_reviewer_handoff(value: Any, path: str) -> None:
    reviewer_handoff = _require_mapping(value, path)
    _require_exact_mapping_fields(
        reviewer_handoff,
        REVIEWER_HANDOFF_FIELD_ORDER,
        path,
    )
    _require_non_empty_string_fields(
        reviewer_handoff,
        ("requested_reviewer", "requested_decision", "review_prompt"),
        path=path,
    )
    _require_non_authorization_note_field(reviewer_handoff, path=path)


def _validate_proposal_handoff(
    value: Any,
    path: str,
    *,
    package_id: str,
    recommendation: str,
) -> None:
    proposal_handoff = _require_mapping(value, path)
    _require_exact_mapping_fields(
        proposal_handoff,
        PROPOSAL_HANDOFF_FIELD_ORDER,
        path,
    )
    handoff_scope = proposal_handoff.get("handoff_scope")
    source_package_id = proposal_handoff.get("source_package_id")
    handoff_recommendation = proposal_handoff.get("recommendation")
    if handoff_scope != PROPOSAL_HANDOFF_SCOPE:
        raise ValueError(
            f"{_field_path(path, 'handoff_scope')} must be {PROPOSAL_HANDOFF_SCOPE}"
        )
    if source_package_id != package_id:
        raise ValueError(
            f"{_field_path(path, 'source_package_id')} "
            "must match package_doc.package.package_id"
        )
    if handoff_recommendation != recommendation:
        raise ValueError(
            f"{_field_path(path, 'recommendation')} "
            "must match package_doc.package.recommendation"
        )
    required_inputs_path = _field_path(path, "required_inputs")
    blocked_until_path = _field_path(path, "blocked_until")
    drafting_status_path = _field_path(path, "drafting_status")
    required_inputs = _require_string_list(
        proposal_handoff.get("required_inputs"),
        required_inputs_path,
    )
    blocked_until = _require_string_list(
        proposal_handoff.get("blocked_until"),
        blocked_until_path,
    )
    if blocked_until != required_inputs:
        raise ValueError(f"{blocked_until_path} must match required_inputs")

    drafting_status = proposal_handoff.get("drafting_status")
    expected_drafting_status = _proposal_handoff_drafting_status(required_inputs)
    if drafting_status != expected_drafting_status:
        raise ValueError(f"{drafting_status_path} must match required_inputs")

    _require_exact_string_list(
        proposal_handoff.get("allowed_next_steps"),
        PROPOSAL_ALLOWED_NEXT_STEPS,
        _field_path(path, "allowed_next_steps"),
    )
    _require_excluded_actions_field(proposal_handoff, path=path)
    _require_non_authorization_note_field(proposal_handoff, path=path)


def _proposal_handoff_drafting_status(required_inputs: Sequence[str]) -> str:
    return "blocked_until_review" if required_inputs else "ready_for_scoped_draft"


def _require_string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be a list")
    return _require_string_items(value, path)


def _require_exact_string_list(
    value: Any,
    expected: Sequence[str],
    path: str,
) -> list[str]:
    strings = _require_non_empty_string_list(value, path)
    _require_unique_values(strings, path)
    _require_exact_ordered_values(
        strings,
        expected,
        path=path,
        missing_label="required values",
    )
    return strings


def _require_included_artifacts_field(value: dict[str, Any], *, path: str) -> None:
    _require_exact_string_list(
        value.get("included_artifacts"),
        INCLUDED_ARTIFACT_ORDER,
        _field_path(path, "included_artifacts"),
    )


def _require_excluded_actions_field(value: dict[str, Any], *, path: str) -> None:
    _require_exact_string_list(
        value.get("excluded_actions"),
        EXCLUDED_ACTION_ORDER,
        _field_path(path, "excluded_actions"),
    )


def _validate_pending_signoff(value: Any, path: str) -> None:
    pending_signoff = _require_mapping(value, path)
    _require_exact_mapping_fields(
        pending_signoff,
        PENDING_SIGNOFF_FIELD_ORDER,
        path,
    )
    if pending_signoff.get("status") != "pending":
        raise ValueError(f"{_field_path(path, 'status')} must be pending")
    _require_non_empty_string_field(pending_signoff, "reviewer", path=path)
    if pending_signoff.get("signoff_scope") != SIGNOFF_SCOPE:
        raise ValueError(
            f"{_field_path(path, 'signoff_scope')} must be {SIGNOFF_SCOPE}"
        )
    if pending_signoff.get("operational_approval") is not False:
        raise ValueError(f"{_field_path(path, 'operational_approval')} must be false")


def _validate_audit_manifest(
    value: Any,
    path: str,
    *,
    package_id: str,
    recommendation: str,
) -> None:
    audit_manifest = _require_mapping(value, path)
    _require_exact_mapping_fields(
        audit_manifest,
        AUDIT_MANIFEST_FIELD_ORDER,
        path,
    )
    if audit_manifest.get("schema_purpose") != AUDIT_MANIFEST_SCHEMA_PURPOSE:
        raise ValueError(
            f"{_field_path(path, 'schema_purpose')} "
            f"must be {AUDIT_MANIFEST_SCHEMA_PURPOSE}"
        )
    if audit_manifest.get("packet_status") != AUDIT_MANIFEST_PACKET_STATUS:
        raise ValueError(
            f"{_field_path(path, 'packet_status')} "
            f"must be {AUDIT_MANIFEST_PACKET_STATUS}"
        )
    if audit_manifest.get("package_id") != package_id:
        raise ValueError(
            f"{_field_path(path, 'package_id')} "
            "must match package_doc.package.package_id"
        )
    if audit_manifest.get("recommendation") != recommendation:
        raise ValueError(
            f"{_field_path(path, 'recommendation')} "
            "must match package_doc.package.recommendation"
        )
    _require_included_artifacts_field(audit_manifest, path=path)
    for group_name, expected_artifacts in AUDIT_MANIFEST_ARTIFACT_GROUPS.items():
        group_artifacts = audit_manifest.get(group_name)
        group_path = _field_path(path, group_name)
        _require_exact_string_list(
            group_artifacts,
            expected_artifacts,
            group_path,
        )
    _require_excluded_actions_field(audit_manifest, path=path)
    _require_non_authorization_note_field(audit_manifest, path=path)


def _validate_export_manifest(value: Any, path: str) -> None:
    export_manifest = _require_mapping(value, path)
    _require_exact_mapping_fields(
        export_manifest,
        EXPORT_MANIFEST_FIELD_ORDER,
        path,
    )
    _require_included_artifacts_field(export_manifest, path=path)
    _require_excluded_actions_field(export_manifest, path=path)
