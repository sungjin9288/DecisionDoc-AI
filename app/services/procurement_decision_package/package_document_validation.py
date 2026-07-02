"""Whole-document structural validation for the decision package payload.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.procurement_decision_package.constants import (
    DECISION_PACKAGE_DOCUMENT_PATH,
    DECISION_PACKAGE_FIELD_ORDER,
    DECISION_PACKAGE_ROOT_PATH,
    DECISION_PACKAGE_TOP_LEVEL_FIELD_ORDER,
    EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE,
    PACKAGE_DOCUMENT_VALIDATION_PATH,
    PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    RECOMMENDATIONS,
    _PackageIdentity,
)
from app.services.procurement_decision_package.field_validators import (
    _require_non_empty_string_field,
    _require_non_empty_string_fields,
    _validate_audit_manifest,
    _validate_bid_readiness_checklist_item,
    _validate_evidence_summary_item,
    _validate_export_manifest,
    _validate_hard_filter_item,
    _validate_list_items,
    _validate_opportunity_ref,
    _validate_pending_signoff,
    _validate_proposal_handoff,
    _validate_reviewer_handoff,
    _validate_soft_fit_score,
    _validate_validation_summary,
)
from app.services.procurement_decision_package.json_helpers import (
    _field_path,
    _require_exact_mapping_fields,
    _require_mapping,
    load_json,
)

def validate_package_document(package_doc: dict[str, Any]) -> dict[str, Any]:
    _require_package_document_root(package_doc)
    package = _require_package_document_package(package_doc)
    identity = _require_package_identity(package)
    _validate_package_core_sections(package)
    _validate_package_review_handoff_sections(
        package,
        package_id=identity.package_id,
        recommendation=identity.recommendation,
    )
    _validate_package_operator_handoff_sections(
        package,
        package_id=identity.package_id,
        recommendation=identity.recommendation,
    )
    return package


def _require_package_document_root(package_doc: dict[str, Any]) -> None:
    _require_exact_mapping_fields(
        package_doc,
        DECISION_PACKAGE_TOP_LEVEL_FIELD_ORDER,
        "package_doc",
    )
    if package_doc.get("schema_purpose") not in {
        EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE,
        PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
    }:
        raise ValueError(
            "package_doc.schema_purpose must be a supported decision package schema"
        )
    _require_non_empty_string_fields(
        package_doc,
        ("scenario_id", "updated_at"),
        path="package_doc",
    )


def _require_package_document_package(package_doc: dict[str, Any]) -> dict[str, Any]:
    package_path = "package_doc.package"
    package = _require_mapping(package_doc.get("package"), package_path)
    _require_exact_mapping_fields(
        package,
        DECISION_PACKAGE_FIELD_ORDER,
        package_path,
    )
    return package


def _require_package_identity(package: dict[str, Any]) -> _PackageIdentity:
    package_path = "package_doc.package"
    package_id = _require_non_empty_string_field(
        package,
        "package_id",
        path=package_path,
    )
    recommendation = _require_non_empty_string_field(
        package,
        "recommendation",
        path=package_path,
    )
    if recommendation not in RECOMMENDATIONS:
        raise ValueError(
            f"{_field_path(package_path, 'recommendation')} "
            "must be GO, CONDITIONAL_GO, or NO_GO"
        )
    _require_non_empty_string_field(
        package,
        "recommendation_reason",
        path=package_path,
    )
    return _PackageIdentity(
        package_id=package_id,
        recommendation=recommendation,
    )


def _validate_package_core_sections(package: dict[str, Any]) -> None:
    opportunity_ref_value, opportunity_ref_path = _package_section(
        package,
        "opportunity_ref",
    )
    _validate_opportunity_ref(opportunity_ref_value, opportunity_ref_path)
    hard_filters_value, hard_filters_path = _package_section(package, "hard_filters")
    _validate_list_items(
        hard_filters_value,
        hard_filters_path,
        _validate_hard_filter_item,
    )
    soft_fit_score_value, soft_fit_score_path = _package_section(
        package,
        "soft_fit_score",
    )
    _validate_soft_fit_score(soft_fit_score_value, soft_fit_score_path)
    evidence_summary_value, evidence_summary_path = _package_section(
        package,
        "evidence_summary",
    )
    _validate_list_items(
        evidence_summary_value,
        evidence_summary_path,
        _validate_evidence_summary_item,
    )
    bid_readiness_checklist_value, bid_readiness_checklist_path = _package_section(
        package,
        "bid_readiness_checklist",
    )
    _validate_list_items(
        bid_readiness_checklist_value,
        bid_readiness_checklist_path,
        _validate_bid_readiness_checklist_item,
    )
    validation_summary_value, validation_summary_path = _package_section(
        package,
        "validation_summary",
    )
    _validate_validation_summary(validation_summary_value, validation_summary_path)


def _validate_package_review_handoff_sections(
    package: dict[str, Any],
    *,
    package_id: str,
    recommendation: str,
) -> None:
    reviewer_handoff_value, reviewer_handoff_path = _package_section(
        package,
        "reviewer_handoff",
    )
    _validate_reviewer_handoff(reviewer_handoff_value, reviewer_handoff_path)
    proposal_handoff_value, proposal_handoff_path = _package_section(
        package,
        "proposal_handoff",
    )
    _validate_proposal_handoff(
        proposal_handoff_value,
        proposal_handoff_path,
        package_id=package_id,
        recommendation=recommendation,
    )


def _validate_package_operator_handoff_sections(
    package: dict[str, Any],
    *,
    package_id: str,
    recommendation: str,
) -> None:
    pending_signoff_value, pending_signoff_path = _package_section(
        package,
        "pending_signoff",
    )
    _validate_pending_signoff(pending_signoff_value, pending_signoff_path)
    audit_manifest_value, audit_manifest_path = _package_section(
        package,
        "audit_manifest",
    )
    _validate_audit_manifest(
        audit_manifest_value,
        audit_manifest_path,
        package_id=package_id,
        recommendation=recommendation,
    )
    export_manifest_value, export_manifest_path = _package_section(
        package,
        "export_manifest",
    )
    _validate_export_manifest(export_manifest_value, export_manifest_path)


def _package_section(package: dict[str, Any], field: str) -> tuple[Any, str]:
    return package.get(field), _package_field_path(field)


def _package_field_path(field: str) -> str:
    return f"package_doc.package.{field}"


def _validation_path_message(
    exc: ValueError,
    *,
    source_path: str,
    target_path: str,
) -> str:
    return str(exc).replace(source_path, target_path)


def validate_package_document_for_path(
    package_doc: dict[str, Any],
    *,
    path: str,
) -> dict[str, Any]:
    try:
        return validate_package_document(package_doc)
    except ValueError as exc:
        raise ValueError(
            _validation_path_message(
                exc,
                source_path=PACKAGE_DOCUMENT_VALIDATION_PATH,
                target_path=path,
            )
        ) from exc


def validate_package_section_for_path(
    package_doc: dict[str, Any],
    *,
    package_field: str,
    section: dict[str, Any],
    section_path: str,
    document_path: str,
) -> None:
    document_section_path = f"{document_path}.package.{package_field}"
    try:
        validate_package_document_for_path(
            _package_document_with_section(
                package_doc,
                package_field=package_field,
                section=section,
            ),
            path=document_path,
        )
    except ValueError as exc:
        raise ValueError(
            _validation_path_message(
                exc,
                source_path=document_section_path,
                target_path=section_path,
            )
        ) from exc


def _package_document_with_section(
    package_doc: dict[str, Any],
    *,
    package_field: str,
    section: dict[str, Any],
) -> dict[str, Any]:
    return {
        **package_doc,
        "package": {
            **package_doc["package"],
            package_field: section,
        },
    }


def validate_json_artifact_matches_package(
    output_dir: Path,
    package_doc: dict[str, Any],
    package: dict[str, Any],
    *,
    artifact_name: str,
    package_field: str,
) -> dict[str, Any]:
    artifact_section = load_json(output_dir / artifact_name)
    validate_package_section_for_path(
        package_doc,
        package_field=package_field,
        section=artifact_section,
        section_path=_json_artifact_section_path(artifact_name),
        document_path=DECISION_PACKAGE_DOCUMENT_PATH,
    )
    if artifact_section != package[package_field]:
        raise ValueError(
            f"{artifact_name} must match "
            f"{DECISION_PACKAGE_ROOT_PATH}.{package_field}"
        )
    return artifact_section


def _json_artifact_section_path(artifact_name: str) -> str:
    return artifact_name.removesuffix(".json")
