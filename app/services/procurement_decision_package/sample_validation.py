"""Sample input and expected-package validation for the local demo fixtures.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.procurement_decision_package.constants import (
    EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    OPPORTUNITY_REF_FIELD_ORDER,
    PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
)
from app.services.procurement_decision_package.field_validators import (
    _require_non_empty_string_field,
)
from app.services.procurement_decision_package.json_helpers import (
    _field_path,
    _require_keys,
    _require_mapping,
    _require_non_empty_string_list,
    load_json,
)
from app.services.procurement_decision_package.artifact_evidence import (
    validate_local_package_coverage,
)
from app.services.procurement_decision_package.package_document_validation import (
    validate_package_document_for_path,
)

def validate_demo_input(sample_input: dict[str, Any]) -> None:
    required_root_keys = {
        "scenario_id",
        "schema_purpose",
        "updated_at",
        "opportunity",
        "capability_profile",
        "operator_notes",
    }
    _require_keys(
        sample_input,
        required_root_keys,
        "sample_input",
    )
    if sample_input["schema_purpose"] != "local_demo_input":
        raise ValueError("sample_input.schema_purpose must be local_demo_input")
    _require_demo_opportunity(sample_input["opportunity"])
    _require_demo_capability_profile(sample_input["capability_profile"])
    _require_demo_operator_notes(sample_input["operator_notes"])


def _require_demo_opportunity(value: Any) -> None:
    required_opportunity_keys = {
        "opportunity_id",
        "title",
        "budget_range",
        "deadline_days",
        "required_capabilities",
        "mandatory_requirements",
        "source_type",
    }
    opportunity = _require_mapping(value, "sample_input.opportunity")
    _require_keys(
        opportunity,
        required_opportunity_keys,
        "sample_input.opportunity",
    )
    _require_non_empty_string_list(
        opportunity["required_capabilities"],
        "sample_input.opportunity.required_capabilities",
    )
    _require_non_empty_string_list(
        opportunity["mandatory_requirements"],
        "sample_input.opportunity.mandatory_requirements",
    )


def _require_demo_capability_profile(value: Any) -> None:
    required_capability_profile_keys = {
        "service_lines",
        "public_sector_references",
        "preferred_budget_range",
        "internal_go_no_go_rules",
    }
    capability_profile = _require_mapping(value, "sample_input.capability_profile")
    _require_keys(
        capability_profile,
        required_capability_profile_keys,
        "sample_input.capability_profile",
    )
    _require_non_empty_string_list(
        capability_profile["service_lines"],
        "sample_input.capability_profile.service_lines",
    )
    _require_non_empty_string_list(
        capability_profile["internal_go_no_go_rules"],
        "sample_input.capability_profile.internal_go_no_go_rules",
    )


def _require_demo_operator_notes(value: Any) -> None:
    required_operator_notes_keys = {
        "known_uncertainty",
        "reviewer_owner",
        "required_follow_up",
    }
    operator_notes = _require_mapping(value, "sample_input.operator_notes")
    _require_keys(
        operator_notes,
        required_operator_notes_keys,
        "sample_input.operator_notes",
    )
    _require_non_empty_string_list(
        operator_notes["known_uncertainty"],
        "sample_input.operator_notes.known_uncertainty",
    )
    _require_non_empty_string_list(
        operator_notes["required_follow_up"],
        "sample_input.operator_notes.required_follow_up",
    )


def validate_sample_input(sample_input: dict[str, Any]) -> None:
    validate_demo_input(sample_input)

    _require_keys(
        _require_mapping(sample_input["opportunity"], "sample_input.opportunity"),
        {"buyer"},
        "sample_input.opportunity",
    )

    capability_profile = _require_mapping(
        sample_input["capability_profile"],
        "sample_input.capability_profile",
    )
    _require_keys(
        capability_profile,
        {
            "profile_id",
            "organization_name",
            "service_lines",
            "public_sector_references",
            "delivery_team",
            "security_and_compliance",
        },
        "sample_input.capability_profile",
    )

    operator_notes = _require_mapping(
        sample_input["operator_notes"],
        "sample_input.operator_notes",
    )
    _require_keys(
        operator_notes,
        {"target_outcome"},
        "sample_input.operator_notes",
    )


def validate_expected_package_for_sample(
    expected_package: dict[str, Any],
    *,
    sample_input: dict[str, Any],
    path: str = "expected_package",
    sample_path: str = "sample_input",
) -> dict[str, Any]:
    validate_sample_input(sample_input)

    package = validate_package_document_for_path(expected_package, path=path)
    if expected_package["schema_purpose"] != EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE:
        raise ValueError(
            f"{_field_path(path, 'schema_purpose')} "
            f"must be {EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE}"
        )

    if expected_package["scenario_id"] != sample_input["scenario_id"]:
        raise ValueError(
            f"{_field_path(path, 'scenario_id')} "
            f"must match {_field_path(sample_path, 'scenario_id')}"
        )

    if expected_package["updated_at"] != sample_input["updated_at"]:
        raise ValueError(
            f"{_field_path(path, 'updated_at')} "
            f"must match {_field_path(sample_path, 'updated_at')}"
        )

    package_path = _field_path(path, "package")
    opportunity_ref_path = _field_path(package_path, "opportunity_ref")
    source_opportunity_path = _field_path(sample_path, "opportunity")
    opportunity_ref = _require_mapping(package["opportunity_ref"], opportunity_ref_path)
    source_opportunity = _require_mapping(
        sample_input["opportunity"],
        source_opportunity_path,
    )
    for field in OPPORTUNITY_REF_FIELD_ORDER:
        source_value = _require_non_empty_string_field(
            source_opportunity,
            field,
            path=source_opportunity_path,
        )
        if opportunity_ref[field] != source_value:
            raise ValueError(
                f"{_field_path(opportunity_ref_path, field)} must match sample input"
            )
    validate_local_package_coverage(package, path=package_path)
    return package


def validate_expected_package(
    expected_package: dict[str, Any],
    *,
    sample_input: dict[str, Any],
) -> None:
    validate_expected_package_for_sample(expected_package, sample_input=sample_input)


def display_path(path: Path, *, base_dir: Path | None = None) -> str:
    if base_dir is None:
        return str(path)
    try:
        return str(path.relative_to(base_dir))
    except ValueError:
        return str(path)


def validate_sample_pair(
    *,
    sample_input_path: Path,
    expected_package_path: Path,
    display_base_dir: Path | None = None,
) -> dict[str, Any]:
    sample_input = load_json(sample_input_path)
    expected_package = load_json(expected_package_path)

    package = validate_expected_package_for_sample(
        expected_package,
        sample_input=sample_input,
    )

    return {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
        "status": "passed",
        "sample_input": display_path(sample_input_path, base_dir=display_base_dir),
        "expected_package": display_path(
            expected_package_path,
            base_dir=display_base_dir,
        ),
        "scenario_id": sample_input["scenario_id"],
        "recommendation": package["recommendation"],
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
    }
