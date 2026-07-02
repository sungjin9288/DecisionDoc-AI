"""Build local procurement decision package artifacts.

This module is intentionally local and deterministic. It does not call providers,
AWS, training, model promotion, or service-resume paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import string
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple
from uuid import uuid4

from app.schemas import (
    NormalizedProcurementOpportunity,
    ProcurementChecklistItem,
    ProcurementDecisionRecord,
    ProcurementDecisionUpsert,
    ProcurementHardFilterResult,
    ProcurementRecommendation,
    ProcurementScoreBreakdownItem,
)
from app.storage.procurement_store import ProcurementDecisionStore


class _DemoReceiptContext(NamedTuple):
    artifact_check: dict[str, Any]
    artifact_inventory: dict[str, Any]
    operator_summary: str
    next_review_action: str


class _DemoReceiptValidationSummary(NamedTuple):
    operator_summary: str
    next_review_action: str


class _PackageIdentity(NamedTuple):
    package_id: str
    recommendation: str


class _SmokeEvidencePaths(NamedTuple):
    demo_result_path: Path
    demo_receipt_path: Path
    gate_result_path: Path
    smoke_result_recorded_path: Path


class _SmokeEvidenceContext(NamedTuple):
    output_dir: Path
    evidence_files: dict[str, Any]
    demo_result_path: Path
    demo_receipt_path: Path
    gate_result_path: Path
    smoke_result_recorded_path: Path


RECOMMENDATIONS = {"GO", "CONDITIONAL_GO", "NO_GO"}
EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE = "expected_decision_package"
PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE = "procurement_decision_package"
PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE = (
    "procurement_decision_package_sample_validation"
)
EXPLICIT_AUTHORIZATION_BOUNDARY = "explicit"
DECISION_PACKAGE_TOP_LEVEL_FIELD_ORDER = [
    "scenario_id",
    "schema_purpose",
    "updated_at",
    "package",
]
DECISION_PACKAGE_FIELD_ORDER = [
    "package_id",
    "recommendation",
    "recommendation_reason",
    "opportunity_ref",
    "hard_filters",
    "soft_fit_score",
    "evidence_summary",
    "bid_readiness_checklist",
    "validation_summary",
    "reviewer_handoff",
    "proposal_handoff",
    "pending_signoff",
    "audit_manifest",
    "export_manifest",
]
OPPORTUNITY_REF_FIELD_ORDER = [
    "opportunity_id",
    "title",
    "source_type",
]
HARD_FILTER_FIELD_ORDER = [
    "filter_id",
    "status",
    "reason",
]
PACKAGE_HARD_FILTER_STATUSES = {
    "pass",
    "fail",
    "unknown",
    "needs_review",
}
SOFT_FIT_SCORE_FIELD_ORDER = [
    "score",
    "band",
    "factors",
]
SOFT_FIT_FACTOR_FIELD_ORDER = [
    "name",
    "score",
    "evidence_ids",
]
PACKAGE_SOFT_FIT_BANDS = {
    "go",
    "conditional",
    "low_conditional",
    "no_go",
}
EVIDENCE_SUMMARY_FIELD_ORDER = [
    "evidence_id",
    "type",
    "source",
    "summary",
]
PACKAGE_EVIDENCE_TYPES = {
    "source_fact",
    "missing_evidence",
}
EVIDENCE_SUMMARY_REQUIRED_MARKERS = [
    "source_fact",
    "missing_evidence",
]
BID_READINESS_CHECKLIST_FIELD_ORDER = [
    "item_id",
    "label",
    "owner",
    "status",
    "required_before",
]
PACKAGE_CHECKLIST_STATUSES = {
    "blocked",
    "needs_review",
    "ready",
}
DECISION_PACKAGE_NAME = "decision_package.json"
PACKAGE_DOCUMENT_VALIDATION_PATH = "package_doc"
DECISION_PACKAGE_DOCUMENT_PATH = "decision_package"
DECISION_PACKAGE_ROOT_PATH = f"{DECISION_PACKAGE_DOCUMENT_PATH}.package"
DECISION_SUMMARY_NAME = "decision_summary.md"
EVIDENCE_SUMMARY_NAME = "evidence_summary.md"
BID_READINESS_CHECKLIST_NAME = "bid_readiness_checklist.md"
VALIDATION_SUMMARY_NAME = "validation_summary.json"
REVIEWER_HANDOFF_NAME = "reviewer_handoff.json"
PROPOSAL_HANDOFF_NAME = "proposal_handoff.json"
PENDING_SIGNOFF_NAME = "pending_signoff.json"
SIGNOFF_SUMMARY_NAME = "signoff_summary.md"
AUDIT_MANIFEST_NAME = "audit_manifest.json"
EXPORT_MANIFEST_NAME = "export_manifest.json"
INCLUDED_ARTIFACT_ORDER = [
    DECISION_PACKAGE_NAME,
    DECISION_SUMMARY_NAME,
    EVIDENCE_SUMMARY_NAME,
    BID_READINESS_CHECKLIST_NAME,
    VALIDATION_SUMMARY_NAME,
    REVIEWER_HANDOFF_NAME,
    PROPOSAL_HANDOFF_NAME,
    PENDING_SIGNOFF_NAME,
    SIGNOFF_SUMMARY_NAME,
    AUDIT_MANIFEST_NAME,
    EXPORT_MANIFEST_NAME,
]
JSON_ARTIFACT_PACKAGE_FIELDS = {
    VALIDATION_SUMMARY_NAME: "validation_summary",
    REVIEWER_HANDOFF_NAME: "reviewer_handoff",
    PROPOSAL_HANDOFF_NAME: "proposal_handoff",
    PENDING_SIGNOFF_NAME: "pending_signoff",
    AUDIT_MANIFEST_NAME: "audit_manifest",
    EXPORT_MANIFEST_NAME: "export_manifest",
}
ARTIFACT_INVENTORY_TABLE_HEADER = "| Artifact | Size bytes | SHA256 |"
ARTIFACT_INVENTORY_TABLE_SEPARATOR = "|---|---:|---|"
ARTIFACT_INVENTORY_TABLE_BODY_OFFSET = 2
PROVIDER_API_EXECUTION_ACTION = "provider_api_execution"
BID_SUBMISSION_ACTION = "bid_submission"
EXCLUDED_ACTION_ORDER = [
    PROVIDER_API_EXECUTION_ACTION,
    "aws_runtime_execution",
    "dataset_upload",
    "training_execution",
    "model_promotion",
    "production_service_resume",
    BID_SUBMISSION_ACTION,
    "legal_approval",
    "contractual_commitment",
]
EXTERNAL_RUNTIME_ACTION_ORDER = EXCLUDED_ACTION_ORDER[:6]
EXPORT_MANIFEST_FIELD_ORDER = [
    "included_artifacts",
    "excluded_actions",
]
VALIDATION_SUMMARY_FIELD_ORDER = [
    "schema_status",
    "boundary_status",
    "operator_summary",
    "next_review_action",
    "unresolved_gaps",
]
DEMO_RECEIPT_VALIDATION_SUMMARY_FIELDS = (
    "operator_summary",
    "next_review_action",
)
DEMO_EVIDENCE_CHECK_FIELDS = (
    "demo_result_checked",
    "artifact_inventory_checked",
    "demo_receipt_checked",
)
PROPOSAL_HANDOFF_FIELD_ORDER = [
    "handoff_scope",
    "source_package_id",
    "recommendation",
    "drafting_status",
    "required_inputs",
    "blocked_until",
    "allowed_next_steps",
    "excluded_actions",
    "non_authorization_note",
]
REVIEWER_HANDOFF_FIELD_ORDER = [
    "requested_reviewer",
    "requested_decision",
    "review_prompt",
    "non_authorization_note",
]
PENDING_SIGNOFF_FIELD_ORDER = [
    "status",
    "reviewer",
    "signoff_scope",
    "operational_approval",
]
AUDIT_MANIFEST_FIELD_ORDER = [
    "schema_purpose",
    "packet_status",
    "package_id",
    "recommendation",
    "included_artifacts",
    "decision_artifacts",
    "evidence_artifacts",
    "validation_artifacts",
    "handoff_artifacts",
    "signoff_artifacts",
    "excluded_actions",
    "non_authorization_note",
]
AUDIT_MANIFEST_SCHEMA_PURPOSE = "procurement_decision_package_audit_manifest"
AUDIT_MANIFEST_PACKET_STATUS = "local_review_packet"
AUDIT_MANIFEST_ARTIFACT_GROUPS = {
    "decision_artifacts": [
        DECISION_PACKAGE_NAME,
        DECISION_SUMMARY_NAME,
        BID_READINESS_CHECKLIST_NAME,
    ],
    "evidence_artifacts": [
        EVIDENCE_SUMMARY_NAME,
    ],
    "validation_artifacts": [
        VALIDATION_SUMMARY_NAME,
    ],
    "handoff_artifacts": [
        REVIEWER_HANDOFF_NAME,
        PROPOSAL_HANDOFF_NAME,
    ],
    "signoff_artifacts": [
        PENDING_SIGNOFF_NAME,
        SIGNOFF_SUMMARY_NAME,
    ],
}
NEXT_REVIEW_ACTION_WITH_GAPS = (
    "Assign an owner to each unresolved gap, then ask the named reviewer "
    "to sign off on the package scope only."
)
NON_AUTHORIZATION_NOTE = (
    "Review acceptance does not authorize provider calls, AWS runtime "
    "execution, dataset upload, training, model promotion, "
    "production service resume, bid submission, legal approval, "
    "or contractual commitment."
)
SIGNOFF_SCOPE = "decision_package_review_only"
PROPOSAL_HANDOFF_SCOPE = "proposal_drafting_preparation_only"
NON_AUTHORIZATION_MARKER = "does not authorize"
NON_APPROVAL_MARKER = "not approval to act"
SCOPED_REVIEW_MARKER = "package scope only"
DEMO_RECEIPT_REQUIRED_MARKERS = [
    NON_AUTHORIZATION_MARKER,
    "operational_approval: false",
    "demo_result_checked: true",
    "artifact_inventory_checked: true",
    "operator_summary:",
    "next_review_action:",
    "## Artifact Inventory",
]
DEMO_RESULT_NAME = "demo_run_result.json"
DEMO_RECEIPT_NAME = "demo_evidence_receipt.md"
DEMO_TENANT_ID = "demo-tenant"
DEMO_PROJECT_ID = "demo-procurement-project"
DEMO_RECOMMENDATION = "CONDITIONAL_GO"
LOCAL_DEMO_SCENARIO_ID = "procurement-decision-package-local-demo"
DEFAULT_DEMO_DATA_DIR = Path("/tmp/decisiondoc-procurement-package-demo-data")
DEFAULT_DEMO_OUT_DIR = Path("/tmp/decisiondoc-procurement-package-demo-output")
LOCAL_DEMO_SAMPLE_DIR = (
    Path("docs")
    / "samples"
    / "procurement_decision_package_local_demo"
)
LOCAL_DEMO_SAMPLE_INPUT_PATH = LOCAL_DEMO_SAMPLE_DIR / "sample_input.json"
LOCAL_DEMO_EXPECTED_PACKAGE_PATH = (
    LOCAL_DEMO_SAMPLE_DIR / "expected_decision_package.json"
)
LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH = (
    LOCAL_DEMO_SAMPLE_DIR / "cli_contract_manifest.json"
)
GATE_RESULT_NAME = "demo_gate_result.json"
GATE_NAME = "procurement_decision_package_demo"
SMOKE_NAME = "procurement_decision_package_demo_gate"
SMOKE_RESULT_NAME = "demo_smoke_result.json"
SMOKE_CHECK_NAME = "procurement_decision_package_smoke_result"
SMOKE_CHECK_RESULT_NAME = "demo_smoke_check_result.json"
CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE = (
    "procurement_decision_package_cli_contract_manifest"
)
CLI_CONTRACT_MANIFEST_CONTRACT_VERSION = "1.0.0"
CLI_CONTRACT_MANIFEST_WORKFLOW = "procurement_decision_package_local_demo"
CLI_CONTRACT_MANIFEST_CONTRACT_STATUS = "local_only"
CLI_CONTRACT_MANIFEST_IDENTITY_VALUES = (
    ("schema_purpose", CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE),
    ("contract_version", CLI_CONTRACT_MANIFEST_CONTRACT_VERSION),
    ("workflow", CLI_CONTRACT_MANIFEST_WORKFLOW),
    ("contract_status", CLI_CONTRACT_MANIFEST_CONTRACT_STATUS),
)
CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME = (
    "cli_contract_manifest_validation_result.json"
)
CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME = (
    "procurement_decision_package_cli_contract_manifest_result"
)
CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME = (
    "cli_contract_manifest_validation_check_result.json"
)
CLI_CONTRACT_MANIFEST_FIELDS = (
    "schema_purpose",
    "contract_version",
    "workflow",
    "contract_status",
    "stdout_json_contract",
    "external_actions_excluded",
    "cli_contracts",
)
CLI_CONTRACT_MANIFEST_STDOUT_CONTRACT_FIELDS = ("success", "handled_failure")
CLI_CONTRACT_MANIFEST_STDOUT_SUCCESS_FIELDS = (
    "exit_code",
    "status",
    "forbidden_fields",
)
CLI_CONTRACT_MANIFEST_STDOUT_FAILURE_FIELDS = ("exit_code", "status", "required_fields")
CLI_CONTRACT_MANIFEST_CLI_CONTRACT_FIELDS = (
    "case_name",
    "script",
    "success_required_fields",
    "failure_required_fields",
)
CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS = (
    "schema_purpose",
    "contract_version",
    "status",
    "manifest_path",
    "manifest_sha256",
    "manifest_size_bytes",
    "workflow",
    "contract_status",
    "contract_count",
    "script_count",
    "case_names",
    "scripts",
    "external_actions_excluded",
    "success_required_fields_by_case",
    "failure_required_fields_by_case",
    "cli_contract_fingerprint",
)
CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FIELDS = (
    "check",
    "status",
    "validation_result_path",
    "manifest_path",
    "contract_version",
    "manifest_sha256",
    "manifest_size_bytes",
    "workflow",
    "contract_status",
    "contract_count",
    "script_count",
    "case_names",
    "scripts",
    "external_actions_excluded",
    "success_required_fields_by_case",
    "failure_required_fields_by_case",
    "cli_contract_fingerprint",
    "validation_result_checked",
)
CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FAILURE_FIELDS = (
    "status",
    "check",
    "validation_result_path",
    "error_type",
    "error",
)
CLI_CONTRACT_MANIFEST_VALIDATION_FAILURE_FIELDS = (
    "schema_purpose",
    "contract_version",
    "status",
    "manifest_path",
    "error_type",
    "error",
)
CLI_CONTRACT_MANIFEST_CASE_MAP_FIELDS = (
    "success_required_fields_by_case",
    "failure_required_fields_by_case",
)
CLI_CONTRACT_MANIFEST_CURRENT_VALIDATION_MATCH_FIELDS = (
    "schema_purpose",
    "contract_version",
    "workflow",
    "contract_status",
    "contract_count",
    "script_count",
    "case_names",
    "scripts",
    "external_actions_excluded",
    "success_required_fields_by_case",
    "failure_required_fields_by_case",
    "cli_contract_fingerprint",
    "manifest_sha256",
    "manifest_size_bytes",
)
CLI_CONTRACT_MANIFEST_CURRENT_VALIDATION_FIELDS = (
    "contract_version",
    "manifest_sha256",
    "manifest_size_bytes",
    "workflow",
    "contract_status",
    "contract_count",
    "script_count",
    "case_names",
    "scripts",
    "external_actions_excluded",
    "success_required_fields_by_case",
    "failure_required_fields_by_case",
    "cli_contract_fingerprint",
)
CLI_CONTRACT_MANIFEST_CASE_ORDER = (
    "sample_validator",
    "sample_builder",
    "artifact_checker",
    "demo_runner",
    "project_export",
    "evidence_gate",
    "smoke_wrapper",
    "smoke_checker",
    "cli_contract_manifest_validator",
    "cli_contract_manifest_result_checker",
)
CLI_CONTRACT_MANIFEST_CASE_NAMES = set(CLI_CONTRACT_MANIFEST_CASE_ORDER)
CLI_CONTRACT_MANIFEST_CASE_SCRIPTS = {
    "sample_validator": "scripts/validate_procurement_decision_package_sample.py",
    "sample_builder": "scripts/build_procurement_decision_package_sample.py",
    "artifact_checker": "scripts/check_procurement_decision_package_artifacts.py",
    "demo_runner": "scripts/run_procurement_decision_package_demo.py",
    "project_export": "scripts/export_procurement_decision_package.py",
    "evidence_gate": "scripts/gate_procurement_decision_package_demo.py",
    "smoke_wrapper": "scripts/smoke_procurement_decision_package_demo_gate.py",
    "smoke_checker": "scripts/check_procurement_decision_package_smoke_result.py",
    "cli_contract_manifest_validator": (
        "scripts/validate_procurement_decision_package_cli_contract_manifest.py"
    ),
    "cli_contract_manifest_result_checker": (
        "scripts/check_procurement_decision_package_cli_contract_manifest_result.py"
    ),
}
CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS = ("status", "error_type", "error")
CLI_CONTRACT_MANIFEST_GLOBAL_SUCCESS_FORBIDDEN_FIELDS = ("error", "error_type")
CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE = {
    "sample_validator": (
        "schema_purpose",
        "status",
        "sample_input",
        "expected_package",
        "scenario_id",
        "recommendation",
        "authorization_boundary",
    ),
    "sample_builder": (
        "schema_purpose",
        "status",
        "output_dir",
        "artifacts",
        "recommendation",
        "authorization_boundary",
    ),
    "artifact_checker": (
        "status",
        "output_dir",
        "artifact_count",
        "recommendation",
        "authorization_boundary",
        "operational_approval",
        *DEMO_EVIDENCE_CHECK_FIELDS,
    ),
    "demo_runner": (
        "status",
        "schema_purpose",
        "output_dir",
        "demo_tenant_id",
        "demo_project_id",
        "seeded_decision_id",
        "demo_result_path",
        "demo_receipt_path",
        "artifact_check",
        "artifact_inventory",
        "artifacts",
        "tenant_id",
        "project_id",
        "decision_id",
        "recommendation",
        "authorization_boundary",
        "clean_output",
    ),
    "project_export": (
        "status",
        "schema_purpose",
        "tenant_id",
        "project_id",
        "decision_id",
        "output_dir",
        "artifacts",
        "recommendation",
        "authorization_boundary",
    ),
    "evidence_gate": (
        "status",
        "gate",
        "output_dir",
        "demo_result_path",
        "demo_receipt_path",
        "operational_approval",
        "artifact_count",
        "excluded_external_actions",
        "recommendation",
        "authorization_boundary",
        "artifacts",
        *DEMO_EVIDENCE_CHECK_FIELDS,
    ),
    "smoke_wrapper": (
        "status",
        "smoke",
        "output_dir",
        "demo_result_path",
        "gate_result_path",
        "smoke_result_path",
        "smoke_check_result_path",
        "evidence_files",
        "operational_approval",
        "data_dir",
        "demo_tenant_id",
        "demo_project_id",
        "seeded_decision_id",
        "demo_receipt_path",
        "gate_result_written",
        "smoke_result_written",
        "smoke_check_result_written",
        "package_artifacts_checked",
        "smoke_result_checked",
        *DEMO_EVIDENCE_CHECK_FIELDS,
        "artifact_count",
        "excluded_external_actions",
        "recommendation",
        "authorization_boundary",
        "clean_output",
    ),
    "smoke_checker": (
        "status",
        "check",
        "smoke_result_path",
        "output_dir",
        "package_artifacts_checked",
        "smoke_result_checked",
        "evidence_files",
        "smoke_check_result_path",
        "smoke_check_result_written",
        "demo_tenant_id",
        "demo_project_id",
        "seeded_decision_id",
        "artifact_count",
        "excluded_external_actions",
        "recommendation",
        "authorization_boundary",
        "operational_approval",
        "clean_output",
    ),
    "cli_contract_manifest_validator": CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
    "cli_contract_manifest_result_checker": CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FIELDS,
}
CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE = {
    "sample_validator": (
        "schema_purpose",
        "status",
        "sample_input",
        "expected_package",
        "error_type",
        "error",
    ),
    "sample_builder": (
        "schema_purpose",
        "status",
        "sample_input",
        "output_dir",
        "error_type",
        "error",
    ),
    "artifact_checker": ("status", "output_dir", "error_type", "error"),
    "demo_runner": (
        "schema_purpose",
        "status",
        "data_dir",
        "output_dir",
        "clean_output",
        "error_type",
        "error",
    ),
    "project_export": (
        "status",
        "schema_purpose",
        "data_dir",
        "tenant_id",
        "project_id",
        "output_dir",
        "error_type",
        "error",
    ),
    "evidence_gate": (
        "status",
        "gate",
        "output_dir",
        "error_type",
        "error",
    ),
    "smoke_wrapper": (
        "status",
        "smoke",
        "data_dir",
        "output_dir",
        "clean_output",
        "gate_result_path",
        "smoke_result_path",
        "smoke_check_result_path",
        "evidence_files",
        "gate_result_written",
        "smoke_result_written",
        "smoke_check_result_written",
        "package_artifacts_checked",
        "smoke_result_checked",
        "error_type",
        "error",
    ),
    "smoke_checker": (
        "check",
        "status",
        "smoke_result_path",
        "error_type",
        "error",
    ),
    "cli_contract_manifest_validator": CLI_CONTRACT_MANIFEST_VALIDATION_FAILURE_FIELDS,
    "cli_contract_manifest_result_checker": (
        CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FAILURE_FIELDS
    ),
}
EVIDENCE_FILE_FIELDS = (
    "demo_result",
    "demo_receipt",
    "gate_result",
    "smoke_result",
    "smoke_check_result",
)
SMOKE_EVIDENCE_PATH_FIELDS = (
    ("demo_result_path", "demo_result"),
    ("demo_receipt_path", "demo_receipt"),
    ("gate_result_path", "gate_result"),
    ("smoke_result_path", "smoke_result"),
    ("smoke_check_result_path", "smoke_check_result"),
)
SMOKE_PACKAGE_ARTIFACT_MATCH_FIELDS = (
    "recommendation",
    "authorization_boundary",
    "operational_approval",
    "artifact_count",
    *DEMO_EVIDENCE_CHECK_FIELDS,
)
SMOKE_DEMO_IDENTITY_FIELDS = (
    "demo_tenant_id",
    "demo_project_id",
    "seeded_decision_id",
)
SMOKE_DEMO_CONTEXT_FIELDS = (
    "output_dir",
    "clean_output",
)
SMOKE_DEMO_RESULT_MATCH_FIELDS = (
    "recommendation",
    "authorization_boundary",
)
SMOKE_DEMO_ARTIFACT_CHECK_FIELDS = (
    "operational_approval",
    *DEMO_EVIDENCE_CHECK_FIELDS,
)
SMOKE_REQUIRED_FALSE_FIELDS = (
    "operational_approval",
)
SMOKE_REQUIRED_TRUE_FIELDS = (
    "gate_result_written",
    "smoke_result_written",
    *DEMO_EVIDENCE_CHECK_FIELDS,
)
SMOKE_CHECK_CONTEXT_FIELDS = (
    "smoke_check_result_written",
    "demo_tenant_id",
    "demo_project_id",
    "seeded_decision_id",
    "artifact_count",
)
SMOKE_CHECK_DECISION_FIELDS = (
    "recommendation",
    "authorization_boundary",
)
DEFAULT_DECISION_PACKAGE_OUTPUT_BASE = Path(
    "/tmp/decisiondoc-procurement-decision-packages"
)
PROPOSAL_ALLOWED_NEXT_STEPS = [
    "prepare proposal outline",
    "assign evidence owner",
    "confirm reviewer sign-off",
]
SIGNOFF_SUMMARY_REQUIRED_MARKERS = [
    "Status: `pending`",
    f"Scope: `{SIGNOFF_SCOPE}`",
    "Operational approval: `false`",
    NON_AUTHORIZATION_MARKER,
]


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def _require_non_empty_string(value: Any, path: str) -> str:
    if not _is_non_empty_string(value):
        raise ValueError(f"{path} must be a non-empty string")
    return value


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def _require_keys(mapping: dict[str, Any], keys: set[str], path: str) -> None:
    missing_keys = _missing_values(keys, mapping)
    if missing_keys:
        raise ValueError(
            f"{path} missing required keys: {', '.join(missing_keys)}"
        )


def _require_exact_mapping_fields(
    mapping: dict[str, Any],
    expected: Sequence[str],
    path: str,
) -> None:
    actual_field_order = list(mapping)
    expected_field_order = list(expected)
    missing_fields = _missing_values(expected, mapping)
    if missing_fields:
        raise ValueError(f"{path} missing fields: {', '.join(missing_fields)}")
    unknown_fields = _unknown_values(mapping, expected)
    if unknown_fields:
        raise ValueError(
            f"{path} includes unknown fields: {', '.join(unknown_fields)}"
        )
    if actual_field_order != expected_field_order:
        raise ValueError(f"{path} fields must match the expected order")


def _require_non_empty_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty list")
    return value


def _require_non_empty_string_list(value: Any, path: str) -> list[str]:
    return _require_string_items(_require_non_empty_list(value, path), path)


def _require_string_items(items: Sequence[Any], path: str) -> list[str]:
    strings: list[str] = []
    for index, item in enumerate(items):
        if not _is_non_empty_string(item):
            raise ValueError(
                f"{_list_item_path(path, index)} must be a non-empty string"
            )
        strings.append(item)
    return strings


def _exception_fields(exc: Exception) -> dict[str, str]:
    return {
        "error_type": exc.__class__.__name__,
        "error": str(exc),
    }


def _optional_path(value: object | None) -> str | None:
    return str(value) if value is not None else None


def _bool_label(value: object) -> str:
    return str(value).lower()


def _project_fields(mapping: dict[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {field: mapping[field] for field in fields}


def _project_optional_fields(
    mapping: dict[str, Any],
    fields: Sequence[str],
) -> dict[str, Any]:
    return {field: mapping.get(field) for field in fields}


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


def build_decision_package(sample_input: dict[str, Any]) -> dict[str, Any]:
    validate_demo_input(sample_input)

    opportunity = sample_input["opportunity"]
    capability_profile = sample_input["capability_profile"]
    operator_notes = sample_input["operator_notes"]
    scenario_id = sample_input["scenario_id"]
    updated_at = sample_input["updated_at"]
    schema_purpose = EXPECTED_DECISION_PACKAGE_SCHEMA_PURPOSE
    package_id = f"{opportunity['opportunity_id']}-package"
    recommendation = DEMO_RECOMMENDATION
    unresolved_gaps = [
        "security-plan",
        "training-staffing",
        "proposal-reviewer",
    ]
    reviewer = operator_notes["reviewer_owner"]
    requested_decision = "review_conditional_go"
    review_prompt = (
        "Confirm whether proposal drafting may start after listed blockers "
        "receive owners."
    )
    package = {
        "package_id": package_id,
        "recommendation": recommendation,
        "recommendation_reason": (
            "The opportunity fits the team's document workflow "
            "and internal tooling capabilities, "
            "but proposal drafting should wait for security plan ownership, "
            "operator training staffing, "
            "and Korean proposal review confirmation."
        ),
        "opportunity_ref": {
            "opportunity_id": opportunity["opportunity_id"],
            "title": opportunity["title"],
            "source_type": opportunity["source_type"],
        },
        "hard_filters": [
            {
                "filter_id": "mandatory-certification",
                "status": "pass",
                "reason": (
                    "No unavailable mandatory certification is present "
                    "in the local fixture."
                ),
            },
            {
                "filter_id": "deadline-readiness",
                "status": "pass",
                "reason": (
                    "Deadline is 21 days, which does not violate "
                    "the sample excluded risk condition."
                ),
            },
            {
                "filter_id": "security-plan",
                "status": "needs_review",
                "reason": (
                    "A security handling plan is mandatory and currently "
                    "draft-required."
                ),
            },
        ],
        "soft_fit_score": {
            "score": 68,
            "band": "conditional",
            "factors": [
                {
                    "name": "domain_fit",
                    "score": 78,
                    "evidence_ids": ["evidence-service-line-document-workflow"],
                },
                {
                    "name": "reference_project_fit",
                    "score": 64,
                    "evidence_ids": ["evidence-public-sector-reference"],
                },
                {
                    "name": "staffing_readiness",
                    "score": 58,
                    "evidence_ids": ["gap-training-staffing-owner"],
                },
                {
                    "name": "security_readiness",
                    "score": 52,
                    "evidence_ids": ["gap-security-plan-owner"],
                },
                {
                    "name": "budget_fit",
                    "score": 82,
                    "evidence_ids": ["evidence-budget-fit"],
                },
            ],
        },
        "evidence_summary": [
            {
                "evidence_id": "evidence-service-line-document-workflow",
                "type": "source_fact",
                "source": "capability_profile.service_lines",
                "summary": (
                    "Capability profile includes "
                    f"{capability_profile['service_lines'][0]} and internal tooling."
                ),
            },
            {
                "evidence_id": "evidence-public-sector-reference",
                "type": "source_fact",
                "source": "capability_profile.public_sector_references",
                "summary": (
                    "A public-sector style reporting process reference is available, "
                    "but the fit should be reviewed."
                ),
            },
            {
                "evidence_id": "evidence-budget-fit",
                "type": "source_fact",
                "source": (
                    "opportunity.budget_range + "
                    "capability_profile.preferred_budget_range"
                ),
                "summary": (
                    "Opportunity budget range falls inside "
                    "the sample preferred budget range."
                ),
            },
            {
                "evidence_id": "gap-security-plan-owner",
                "type": "missing_evidence",
                "source": "operator_notes.known_uncertainty",
                "summary": "Security handling plan owner is not confirmed.",
            },
            {
                "evidence_id": "gap-training-staffing-owner",
                "type": "missing_evidence",
                "source": "operator_notes.known_uncertainty",
                "summary": operator_notes["known_uncertainty"][1],
            },
        ],
        "bid_readiness_checklist": [
            {
                "item_id": "security-plan",
                "label": "Finalize security handling plan",
                "owner": "unassigned",
                "status": "blocked",
                "required_before": "proposal_drafting",
            },
            {
                "item_id": "training-staffing",
                "label": "Assign operator training staffing owner",
                "owner": "unassigned",
                "status": "blocked",
                "required_before": "proposal_drafting",
            },
            {
                "item_id": "proposal-reviewer",
                "label": "Confirm Korean proposal package reviewer",
                "owner": "unassigned",
                "status": "needs_review",
                "required_before": "proposal_submission",
            },
        ],
        "validation_summary": build_validation_summary(
            schema_status="expected_shape_only",
            recommendation=recommendation,
            unresolved_gaps=unresolved_gaps,
        ),
        **_build_package_handoff_artifacts(
            reviewer=reviewer,
            requested_decision=requested_decision,
            review_prompt=review_prompt,
            package_id=package_id,
            recommendation=recommendation,
            unresolved_gaps=unresolved_gaps,
        ),
    }

    return {
        "scenario_id": scenario_id,
        "schema_purpose": schema_purpose,
        "updated_at": updated_at,
        "package": package,
    }


def seed_demo_decision_record(
    *,
    data_dir: Path,
    tenant_id: str = DEMO_TENANT_ID,
    project_id: str = DEMO_PROJECT_ID,
) -> str:
    store = ProcurementDecisionStore(base_dir=str(data_dir))

    record = store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id=tenant_id,
            opportunity=_demo_decision_opportunity(),
            hard_filters=_demo_decision_hard_filters(),
            score_breakdown=_demo_decision_score_breakdown(),
            soft_fit_score=68.0,
            soft_fit_status="scored",
            missing_data=_demo_decision_missing_data(),
            checklist_items=_demo_decision_checklist_items(),
            recommendation=_demo_decision_recommendation(),
            notes=(
                "Local package demo seed record. "
                "Does not authorize operational action."
            ),
        )
    )

    return record.decision_id


def _demo_decision_opportunity() -> NormalizedProcurementOpportunity:
    return NormalizedProcurementOpportunity(
        source_kind="local_demo",
        source_id="local-procurement-demo-001",
        title="Public Agency Document Workflow Modernization Pilot",
        issuer="Sample Public Agency",
        budget="KRW 80M-120M",
        deadline="21 days",
        bid_type="local_fixture",
        category="document_operations",
        region="sample",
        raw_text_preview="Local deterministic procurement package demo.",
    )


def _demo_decision_hard_filters() -> list[ProcurementHardFilterResult]:
    return [
        ProcurementHardFilterResult(
            code="security_plan",
            label="Security handling plan",
            status="unknown",
            blocking=True,
            reason=(
                "Security handling plan owner must be confirmed "
                "before proposal drafting."
            ),
        ),
    ]


def _demo_decision_score_breakdown() -> list[ProcurementScoreBreakdownItem]:
    return [
        ProcurementScoreBreakdownItem(
            key="domain_fit",
            label="Domain fit",
            score=78.0,
            weight=0.25,
            weighted_score=19.5,
            summary="Document workflow capability is aligned with the opportunity.",
            evidence=["document workflow consulting"],
        ),
        ProcurementScoreBreakdownItem(
            key="security_readiness",
            label="Security readiness",
            score=52.0,
            weight=0.25,
            weighted_score=13.0,
            summary="Security plan requires owner assignment.",
            evidence=["security plan draft required"],
        ),
    ]


def _demo_decision_checklist_items() -> list[ProcurementChecklistItem]:
    return [
        ProcurementChecklistItem(
            category="security_plan",
            title="Finalize security handling plan",
            status="action_needed",
            severity="high",
            remediation_note="Assign owner before proposal drafting.",
        ),
        ProcurementChecklistItem(
            category="training_staffing",
            title="Assign operator training staffing owner",
            status="action_needed",
            severity="medium",
            remediation_note="Confirm trainer availability before kickoff.",
        ),
    ]


def _demo_decision_recommendation() -> ProcurementRecommendation:
    return ProcurementRecommendation(
        value=DEMO_RECOMMENDATION,
        summary=(
            "Conditional go pending security and "
            "training ownership confirmation."
        ),
        evidence=[
            "Weighted fit score: 68.00",
            "Document workflow capability aligns with the opportunity.",
        ],
        missing_data=_demo_decision_missing_data(),
        remediation_notes=[
            "Assign security plan owner.",
            "Assign operator training staffing owner.",
        ],
    )


def _demo_decision_missing_data() -> list[str]:
    return [
        "security plan owner",
        "operator training staffing owner",
    ]


def build_decision_package_from_record(
    record: ProcurementDecisionRecord,
    *,
    reviewer_owner: str = "executive-reviewer",
) -> dict[str, Any]:
    if record.opportunity is None:
        raise ValueError("procurement decision record must include an opportunity")
    if record.recommendation is None:
        raise ValueError("procurement decision record must include a recommendation")

    opportunity = record.opportunity
    recommendation = record.recommendation
    recommendation_value = recommendation.value.value
    score = int(round(record.soft_fit_score or 0))
    package_id = f"{record.decision_id}-package"
    requested_decision = f"review_{recommendation_value.lower()}"
    review_prompt = (
        "Review the procurement decision package before proposal drafting "
        "or downstream handoff."
    )
    checklist = [
        {
            "item_id": item.category,
            "label": item.title,
            "owner": item.owner or "unassigned",
            "status": _package_checklist_status(item.status.value),
            "required_before": "proposal_drafting",
        }
        for item in record.checklist_items
    ]
    unresolved_gaps = [
        *[
            item["item_id"]
            for item in checklist
            if item["status"] in {"blocked", "needs_review"}
        ],
        *record.missing_data,
    ]
    source_evidence = [
        {
            "evidence_id": f"recommendation-evidence-{index + 1}",
            "type": "source_fact",
            "source": "record.recommendation.evidence",
            "summary": evidence,
        }
        for index, evidence in enumerate(recommendation.evidence)
    ]
    score_summary_evidence = []
    if record.score_breakdown:
        score_summary_evidence.append(
            {
                "evidence_id": "score-summary",
                "type": "source_fact",
                "source": "record.score_breakdown",
                "summary": f"Soft-fit score is {score}.",
            }
        )
    evidence_summary = [
        *(source_evidence or score_summary_evidence),
        *[
            {
                "evidence_id": f"missing-data-{index + 1}",
                "type": "missing_evidence",
                "source": "record.missing_data",
                "summary": missing_data,
            }
            for index, missing_data in enumerate(record.missing_data)
        ],
    ]
    package = {
        "package_id": package_id,
        "recommendation": recommendation_value,
        "recommendation_reason": recommendation.summary,
        "opportunity_ref": {
            "opportunity_id": opportunity.source_id,
            "title": opportunity.title,
            "source_type": opportunity.source_kind,
        },
        "hard_filters": [
            {
                "filter_id": item.code,
                "status": item.status.value,
                "reason": item.reason,
            }
            for item in record.hard_filters
        ],
        "soft_fit_score": {
            "score": score,
            "band": _score_band(recommendation_value, score),
            "factors": [
                {
                    "name": item.key,
                    "score": int(round(item.score)),
                    "evidence_ids": [f"score-{item.key}"],
                }
                for item in record.score_breakdown
            ],
        },
        "evidence_summary": evidence_summary,
        "bid_readiness_checklist": checklist,
        "validation_summary": build_validation_summary(
            schema_status="record_shape",
            recommendation=recommendation_value,
            unresolved_gaps=unresolved_gaps,
        ),
        **_build_package_handoff_artifacts(
            reviewer=reviewer_owner,
            requested_decision=requested_decision,
            review_prompt=review_prompt,
            package_id=package_id,
            recommendation=recommendation_value,
            unresolved_gaps=unresolved_gaps,
        ),
    }
    scenario_id = f"procurement-record-{record.project_id}"
    schema_purpose = PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE
    updated_at = record.updated_at

    return {
        "scenario_id": scenario_id,
        "schema_purpose": schema_purpose,
        "updated_at": updated_at,
        "package": package,
    }


def _build_package_handoff_artifacts(
    *,
    reviewer: str,
    requested_decision: str,
    review_prompt: str,
    package_id: str,
    recommendation: str,
    unresolved_gaps: list[str],
) -> dict[str, Any]:
    return {
        "reviewer_handoff": build_reviewer_handoff(
            reviewer=reviewer,
            requested_decision=requested_decision,
            review_prompt=review_prompt,
        ),
        "proposal_handoff": build_proposal_handoff(
            package_id=package_id,
            recommendation=recommendation,
            unresolved_gaps=unresolved_gaps,
        ),
        "pending_signoff": build_pending_signoff(reviewer=reviewer),
        "audit_manifest": build_audit_manifest(
            package_id=package_id,
            recommendation=recommendation,
        ),
        "export_manifest": build_export_manifest(),
    }


def export_project_decision_package(
    *,
    data_dir: Path,
    tenant_id: str,
    project_id: str,
    out_dir: Path | None = None,
    reviewer_owner: str = "executive-reviewer",
) -> dict[str, object]:
    store = ProcurementDecisionStore(base_dir=str(data_dir))
    record = store.get(project_id, tenant_id=tenant_id)
    if record is None:
        raise KeyError(
            "procurement decision record not found: "
            f"tenant_id={tenant_id} project_id={project_id}"
        )

    package_doc = build_decision_package_from_record(
        record,
        reviewer_owner=reviewer_owner,
    )
    default_output_dir = DEFAULT_DECISION_PACKAGE_OUTPUT_BASE / tenant_id / project_id
    output_dir = out_dir or default_output_dir
    artifact_write_result = write_package_artifacts(package_doc, output_dir)

    return {
        "status": artifact_write_result["status"],
        "schema_purpose": package_doc["schema_purpose"],
        "tenant_id": tenant_id,
        "project_id": project_id,
        "decision_id": record.decision_id,
        "output_dir": artifact_write_result["output_dir"],
        "artifacts": artifact_write_result["artifacts"],
        "recommendation": artifact_write_result["recommendation"],
        "authorization_boundary": artifact_write_result["authorization_boundary"],
    }


def _package_checklist_status(status: str) -> str:
    if status == "blocked":
        return "blocked"
    if status in {"action_needed", "unknown"}:
        return "needs_review"
    return "ready"


def _score_band(recommendation: str, score: int) -> str:
    if recommendation == "GO":
        return "go"
    if recommendation == "NO_GO":
        return "no_go"
    if score < 55:
        return "low_conditional"
    return "conditional"


def build_reviewer_handoff(
    *,
    reviewer: str,
    requested_decision: str,
    review_prompt: str,
) -> dict[str, Any]:
    return {
        "requested_reviewer": reviewer,
        "requested_decision": requested_decision,
        "review_prompt": review_prompt,
        "non_authorization_note": NON_AUTHORIZATION_NOTE,
    }


def build_pending_signoff(*, reviewer: str) -> dict[str, Any]:
    return {
        "status": "pending",
        "reviewer": reviewer,
        "signoff_scope": SIGNOFF_SCOPE,
        "operational_approval": False,
    }


def build_export_manifest() -> dict[str, Any]:
    return {
        "included_artifacts": list(INCLUDED_ARTIFACT_ORDER),
        "excluded_actions": list(EXCLUDED_ACTION_ORDER),
    }


def build_audit_manifest(*, package_id: str, recommendation: str) -> dict[str, Any]:
    return {
        "schema_purpose": AUDIT_MANIFEST_SCHEMA_PURPOSE,
        "packet_status": AUDIT_MANIFEST_PACKET_STATUS,
        "package_id": package_id,
        "recommendation": recommendation,
        "included_artifacts": list(INCLUDED_ARTIFACT_ORDER),
        "decision_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["decision_artifacts"]
        ),
        "evidence_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["evidence_artifacts"]
        ),
        "validation_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["validation_artifacts"]
        ),
        "handoff_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["handoff_artifacts"]
        ),
        "signoff_artifacts": list(
            AUDIT_MANIFEST_ARTIFACT_GROUPS["signoff_artifacts"]
        ),
        "excluded_actions": list(EXCLUDED_ACTION_ORDER),
        "non_authorization_note": NON_AUTHORIZATION_NOTE,
    }


def build_proposal_handoff(
    *,
    package_id: str,
    recommendation: str,
    unresolved_gaps: list[str],
) -> dict[str, Any]:
    ordered_unresolved_gaps = _unique_strings(unresolved_gaps)

    return {
        "handoff_scope": PROPOSAL_HANDOFF_SCOPE,
        "source_package_id": package_id,
        "recommendation": recommendation,
        "drafting_status": _proposal_handoff_drafting_status(
            ordered_unresolved_gaps
        ),
        "required_inputs": list(ordered_unresolved_gaps),
        "blocked_until": list(ordered_unresolved_gaps),
        "allowed_next_steps": list(PROPOSAL_ALLOWED_NEXT_STEPS),
        "excluded_actions": list(EXCLUDED_ACTION_ORDER),
        "non_authorization_note": NON_AUTHORIZATION_NOTE,
    }


def _unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def build_validation_summary(
    *,
    schema_status: str,
    recommendation: str,
    unresolved_gaps: list[str],
) -> dict[str, Any]:
    ordered_unresolved_gaps = _unique_strings(unresolved_gaps)

    return {
        "schema_status": schema_status,
        "boundary_status": "explicit_non_authorization_required",
        "operator_summary": _operator_validation_summary(
            recommendation=recommendation,
            unresolved_gaps=ordered_unresolved_gaps,
        ),
        "next_review_action": NEXT_REVIEW_ACTION_WITH_GAPS,
        "unresolved_gaps": ordered_unresolved_gaps,
    }


def _operator_validation_summary(
    *,
    recommendation: str,
    unresolved_gaps: list[str],
) -> str:
    boundary_sentence = f"This package is evidence for review, {NON_APPROVAL_MARKER}."
    if unresolved_gaps:
        review_sentence = (
            f"{recommendation} can be reviewed, but proposal work should wait "
            "until the listed gaps have owners."
        )
        return f"{review_sentence} {boundary_sentence}"

    review_sentence = (
        f"{recommendation} can move to reviewer sign-off "
        "for the package scope."
    )
    return f"{review_sentence} {boundary_sentence}"


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as file_obj:
        file_obj.write(text)
        file_obj.flush()
        os.fsync(file_obj.fileno())
    os.replace(tmp, path)


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(data, indent=2, sort_keys=False) + "\n")


def _render_decision_summary(package: dict[str, Any]) -> str:
    recommendation = package["recommendation"]
    recommendation_reason = package["recommendation_reason"]
    hard_filters = "\n".join(
        _render_decision_summary_hard_filter(item)
        for item in package["hard_filters"]
    )
    next_actions = "\n".join(
        _render_decision_summary_next_action(item)
        for item in package["bid_readiness_checklist"]
    )
    boundary_note = package["reviewer_handoff"]["non_authorization_note"]

    return f"""# Procurement Decision Summary

Recommendation: `{recommendation}`

{recommendation_reason}

## Hard Filters

{hard_filters}

## Next Actions

{next_actions}

## Boundary

{boundary_note}
"""


def _render_decision_summary_hard_filter(item: dict[str, str]) -> str:
    return f"- `{item['filter_id']}`: {item['status']} - {item['reason']}"


def _render_decision_summary_next_action(item: dict[str, str]) -> str:
    return f"- {item['label']} (`{item['status']}`, owner: {item['owner']})"


def _render_evidence_summary(package: dict[str, Any]) -> str:
    evidence_rows = [
        f"- `{item['evidence_id']}` ({item['type']}): {item['summary']}"
        for item in package["evidence_summary"]
    ]
    return "\n".join([
        "# Evidence Summary",
        "",
        *evidence_rows,
    ])


def _render_bid_readiness_checklist(package: dict[str, Any]) -> str:
    checklist_rows = []
    for item in package["bid_readiness_checklist"]:
        checklist_rows.append(
            f"| {item['label']} | `{item['status']}` | "
            f"{item['owner']} | `{item['required_before']}` |"
        )
    return "\n".join([
        "# Bid Readiness Checklist",
        "",
        "| Item | Status | Owner | Required Before |",
        "|---|---|---|---|",
        *checklist_rows,
    ])


def _render_signoff_summary(package: dict[str, Any]) -> str:
    pending_signoff = _require_mapping(
        package["pending_signoff"],
        "package.pending_signoff",
    )

    return f"""# Sign-Off Summary

Status: `{pending_signoff['status']}`

Reviewer: `{pending_signoff['reviewer']}`

Scope: `{pending_signoff['signoff_scope']}`

Operational approval: `{_bool_label(pending_signoff['operational_approval'])}`

## Boundary

{package['reviewer_handoff']['non_authorization_note']}
"""


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


def validate_local_package_artifacts(output_dir: Path) -> dict[str, Any]:
    package_doc_path = output_dir / DECISION_PACKAGE_NAME

    validate_package_artifact_files(output_dir)

    package_doc = load_json(package_doc_path)
    package = validate_package_document_for_path(
        package_doc,
        path=DECISION_PACKAGE_DOCUMENT_PATH,
    )
    validate_local_package_coverage(package, path=DECISION_PACKAGE_ROOT_PATH)

    for artifact_name, package_field in JSON_ARTIFACT_PACKAGE_FIELDS.items():
        validate_json_artifact_matches_package(
            output_dir,
            package_doc,
            package,
            artifact_name=artifact_name,
            package_field=package_field,
        )

    validate_markdown_artifact_files(output_dir)
    return package


def validate_local_package_coverage(package: dict[str, Any], *, path: str) -> None:
    _require_non_empty_list(
        package.get("hard_filters"),
        _field_path(path, "hard_filters"),
    )

    _require_local_soft_fit_coverage(
        package.get("soft_fit_score"),
        path=_field_path(path, "soft_fit_score"),
    )

    evidence_summary_path = _field_path(path, "evidence_summary")
    evidence_summary = _require_non_empty_list(
        package.get("evidence_summary"),
        evidence_summary_path,
    )
    _require_package_evidence_types(evidence_summary, evidence_summary_path)

    _require_non_empty_list(
        package.get("bid_readiness_checklist"),
        _field_path(path, "bid_readiness_checklist"),
    )


def _require_local_soft_fit_coverage(value: object, *, path: str) -> None:
    soft_fit_score = _require_mapping(value, path)
    _require_non_empty_list(
        soft_fit_score.get("factors"),
        _field_path(path, "factors"),
    )


def _require_package_evidence_types(evidence_summary: Sequence[Any], path: str) -> None:
    missing_types = _missing_values(
        PACKAGE_EVIDENCE_TYPES,
        [
            item.get("type")
            for item in evidence_summary
            if isinstance(item, dict)
        ],
    )
    if missing_types:
        raise ValueError(f"{path} must include source_fact and missing_evidence")


def build_artifact_fingerprint(path: Path) -> dict[str, object]:
    artifact_bytes = path.read_bytes()
    return {
        "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "size_bytes": len(artifact_bytes),
    }


def build_artifact_inventory(output_dir: Path) -> dict[str, dict[str, object]]:
    inventory: dict[str, dict[str, object]] = {}
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        inventory[artifact_name] = build_artifact_fingerprint(
            output_dir / artifact_name
        )
    return inventory


def validate_artifact_fingerprint(value: Any, *, path: str) -> dict[str, object]:
    fingerprint = _require_mapping(value, path)

    sha256 = fingerprint.get("sha256")
    sha256_path = _field_path(path, "sha256")
    if not _is_sha256_hex(sha256):
        raise ValueError(f"{sha256_path} must be a 64-character hex string")

    size_bytes = fingerprint.get("size_bytes")
    size_bytes_path = _field_path(path, "size_bytes")
    if not _is_non_negative_int(size_bytes):
        raise ValueError(f"{size_bytes_path} must be a non-negative integer")
    return fingerprint


def _field_path(path: str, field: str) -> str:
    return f"{path}.{field}"


def _list_item_path(path: str, index: int) -> str:
    return f"{path}[{index}]"


def _is_sha256_hex(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in string.hexdigits for char in value)
    )


def _is_non_negative_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def validate_artifact_inventory(value: Any, *, path: str) -> dict[str, Any]:
    artifact_inventory = _require_mapping(value, path)
    _require_exact_ordered_values(
        list(artifact_inventory),
        INCLUDED_ARTIFACT_ORDER,
        path=path,
        missing_label="artifacts",
        unknown_label="artifacts",
    )
    return artifact_inventory


def validate_artifact_list(value: Any, *, path: str) -> list[str]:
    artifacts = _require_non_empty_string_list(value, path)
    _require_unique_values(artifacts, path)
    _require_exact_ordered_values(
        artifacts,
        INCLUDED_ARTIFACT_ORDER,
        path=path,
        missing_label="package artifacts",
        unknown_label="package artifacts",
    )
    return artifacts


def validate_package_artifact_files(output_dir: Path) -> None:
    if not output_dir.exists() or not output_dir.is_dir():
        raise FileNotFoundError(f"package output directory not found: {output_dir}")
    missing_artifacts = [
        artifact_name
        for artifact_name in INCLUDED_ARTIFACT_ORDER
        if not (output_dir / artifact_name).is_file()
    ]
    if missing_artifacts:
        raise ValueError(
            f"missing package artifacts: {', '.join(missing_artifacts)}"
        )


def render_artifact_inventory_row(
    artifact_name: str,
    fingerprint: dict[str, object],
) -> str:
    return (
        f"| {artifact_name} | {fingerprint['size_bytes']} | "
        f"{fingerprint['sha256']} |"
    )


def build_artifact_inventory_rows(value: Any, *, path: str) -> list[str]:
    return list(_build_artifact_inventory_row_map(value, path=path).values())


def _build_artifact_inventory_row_map(value: Any, *, path: str) -> dict[str, str]:
    artifact_inventory = validate_artifact_inventory(value, path=path)
    rows: dict[str, str] = {}
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        fingerprint = validate_artifact_fingerprint(
            artifact_inventory.get(artifact_name),
            path=_field_path(path, artifact_name),
        )
        rows[artifact_name] = render_artifact_inventory_row(
            artifact_name,
            fingerprint,
        )
    return rows


def render_demo_evidence_receipt(demo_result: dict[str, object]) -> str:
    context = _require_demo_receipt_context(demo_result)
    summary_and_table_header_lines = _build_demo_evidence_receipt_lines(
        demo_result=demo_result,
        artifact_check=context.artifact_check,
        operator_summary=context.operator_summary,
        next_review_action=context.next_review_action,
    )
    artifact_inventory_rows = build_artifact_inventory_rows(
        context.artifact_inventory,
        path="artifact_inventory",
    )
    receipt_lines = [
        *summary_and_table_header_lines,
        *artifact_inventory_rows,
        "",
    ]
    return "\n".join(receipt_lines)


def _require_demo_receipt_context(
    demo_result: dict[str, object],
) -> _DemoReceiptContext:
    artifact_check = _require_mapping(
        demo_result.get("artifact_check"),
        "artifact_check",
    )
    artifact_inventory = _require_mapping(
        demo_result.get("artifact_inventory"),
        "artifact_inventory",
    )
    output_dir = demo_result.get("output_dir")
    if not isinstance(output_dir, str):
        raise ValueError("output_dir must be a string")
    validation_summary = _load_demo_receipt_validation_summary(output_dir)
    return _DemoReceiptContext(
        artifact_check=artifact_check,
        artifact_inventory=artifact_inventory,
        operator_summary=validation_summary.operator_summary,
        next_review_action=validation_summary.next_review_action,
    )


def _load_demo_receipt_validation_summary(
    output_dir: str,
) -> _DemoReceiptValidationSummary:
    validation_summary = load_json(Path(output_dir) / VALIDATION_SUMMARY_NAME)
    return _DemoReceiptValidationSummary(
        operator_summary=_require_non_empty_string_field(
            validation_summary,
            "operator_summary",
            path="validation_summary",
        ),
        next_review_action=_require_non_empty_string_field(
            validation_summary,
            "next_review_action",
            path="validation_summary",
        ),
    )


def _build_demo_evidence_receipt_lines(
    *,
    demo_result: dict[str, object],
    artifact_check: dict[str, Any],
    operator_summary: str,
    next_review_action: str,
) -> list[str]:
    summary_lines = [
        f"- status: {artifact_check.get('status')}",
        f"- recommendation: {demo_result.get('recommendation')}",
        f"- authorization_boundary: {demo_result.get('authorization_boundary')}",
        _demo_receipt_bool_line(
            "operational_approval",
            artifact_check.get("operational_approval"),
        ),
        _demo_receipt_bool_line(
            "demo_result_checked",
            artifact_check.get("demo_result_checked"),
        ),
        _demo_receipt_bool_line(
            "artifact_inventory_checked",
            artifact_check.get("artifact_inventory_checked"),
        ),
        _demo_receipt_bool_line(
            "demo_receipt_checked",
            artifact_check.get("demo_receipt_checked"),
        ),
        f"- operator_summary: {operator_summary}",
        f"- next_review_action: {next_review_action}",
    ]
    return [
        "# Procurement Decision Package Demo Evidence Receipt",
        "",
        "## Summary",
        "",
        *summary_lines,
        "",
        "## Boundary",
        "",
        _demo_evidence_receipt_boundary_text(),
        "",
        "## Artifact Inventory",
        "",
        ARTIFACT_INVENTORY_TABLE_HEADER,
        ARTIFACT_INVENTORY_TABLE_SEPARATOR,
    ]


def _demo_receipt_bool_line(field: str, value: Any) -> str:
    return f"- {field}: {_bool_label(value)}"


def _demo_evidence_receipt_boundary_text() -> str:
    return (
        "This receipt does not authorize provider API execution, AWS runtime "
        "execution, dataset upload, training execution, model promotion, "
        "production service resume, bid submission, legal approval, or "
        "contractual commitment."
    )


def validate_demo_evidence_receipt_text(
    receipt_text: str,
    *,
    artifact_inventory: Any,
    validation_summary: Any,
    inventory_path: str = "demo_run_result.artifact_inventory",
) -> None:
    missing_markers = _missing_markers(DEMO_RECEIPT_REQUIRED_MARKERS, receipt_text)
    if missing_markers:
        raise ValueError(
            f"demo evidence receipt missing markers: {', '.join(missing_markers)}"
        )

    _require_demo_receipt_artifact_inventory_rows(
        receipt_text,
        artifact_inventory=artifact_inventory,
        inventory_path=inventory_path,
    )
    validation_summary = _require_mapping(validation_summary, "validation_summary")
    for field in DEMO_RECEIPT_VALIDATION_SUMMARY_FIELDS:
        if f"{field}: {validation_summary[field]}" not in receipt_text:
            raise ValueError(
                "demo evidence receipt missing validation summary field: "
                f"{field}"
            )


def _require_demo_receipt_artifact_inventory_rows(
    receipt_text: str,
    *,
    artifact_inventory: Any,
    inventory_path: str,
) -> None:
    expected_row_map = _build_artifact_inventory_row_map(
        artifact_inventory,
        path=inventory_path,
    )
    for artifact_name, expected_row in expected_row_map.items():
        if expected_row not in receipt_text:
            raise ValueError(
                f"demo evidence receipt missing artifact inventory row: "
                f"{artifact_name}"
            )

    expected_rows = list(expected_row_map.values())
    receipt_rows = _artifact_inventory_rows_from_receipt(receipt_text)
    if receipt_rows != expected_rows:
        raise ValueError(
            "demo evidence receipt artifact inventory rows "
            "must match the expected order"
        )

def _artifact_inventory_rows_from_receipt(receipt_text: str) -> list[str]:
    receipt_lines = receipt_text.splitlines()
    try:
        table_header_index = receipt_lines.index(ARTIFACT_INVENTORY_TABLE_HEADER)
    except ValueError as exc:
        raise ValueError(
            "demo evidence receipt missing artifact inventory table header"
        ) from exc
    table_body_start = table_header_index + ARTIFACT_INVENTORY_TABLE_BODY_OFFSET
    table_body_end = table_body_start + len(INCLUDED_ARTIFACT_ORDER)
    return receipt_lines[table_body_start:table_body_end]


def validate_demo_evidence_receipt_file(
    *,
    receipt_path: Path,
    demo_result: dict[str, Any],
    artifact_inventory: Any,
    validation_summary: Any,
) -> None:
    if demo_result.get("demo_receipt_path") != str(receipt_path):
        raise ValueError(
            "demo_run_result.demo_receipt_path must match "
            "the checked receipt file"
        )
    if not receipt_path.is_file():
        raise ValueError("demo evidence receipt file is missing")

    validate_demo_evidence_receipt_text(
        receipt_path.read_text(encoding="utf-8"),
        artifact_inventory=artifact_inventory,
        validation_summary=validation_summary,
    )


def validate_signoff_summary_text(signoff_summary: str) -> None:
    missing_markers = _missing_markers(
        SIGNOFF_SUMMARY_REQUIRED_MARKERS,
        signoff_summary,
    )
    if missing_markers:
        raise ValueError(
            f"{SIGNOFF_SUMMARY_NAME} missing sign-off markers: "
            f"{', '.join(missing_markers)}"
        )


def validate_decision_summary_text(decision_summary: str) -> None:
    if NON_AUTHORIZATION_MARKER not in decision_summary:
        raise ValueError(
            f"{DECISION_SUMMARY_NAME} must include the non-authorization boundary"
        )


def validate_evidence_summary_text(evidence_summary: str) -> None:
    missing_markers = _missing_markers(
        EVIDENCE_SUMMARY_REQUIRED_MARKERS,
        evidence_summary,
    )
    if missing_markers:
        raise ValueError(
            f"{EVIDENCE_SUMMARY_NAME} missing evidence type markers: "
            f"{', '.join(missing_markers)}"
        )


def _missing_markers(markers: Sequence[str], text: str) -> list[str]:
    return [marker for marker in markers if marker not in text]


def validate_markdown_artifact_files(output_dir: Path) -> None:
    validate_signoff_summary_text(
        (output_dir / SIGNOFF_SUMMARY_NAME).read_text(encoding="utf-8")
    )
    validate_decision_summary_text(
        (output_dir / DECISION_SUMMARY_NAME).read_text(encoding="utf-8")
    )
    validate_evidence_summary_text(
        (output_dir / EVIDENCE_SUMMARY_NAME).read_text(encoding="utf-8")
    )


def validate_demo_run_result(
    demo_result: dict[str, Any],
    *,
    output_dir: Path,
    demo_result_path: Path,
    require_demo_result_checked: bool = True,
) -> dict[str, Any]:
    artifact_check_path = _demo_run_result_field_path("artifact_check")
    artifact_check = _require_mapping(
        demo_result.get("artifact_check"),
        artifact_check_path,
    )
    _require_passed_status(artifact_check, artifact_check_path)
    _require_boolean_fields(
        artifact_check,
        ("operational_approval",),
        expected=False,
        path=artifact_check_path,
    )
    if require_demo_result_checked:
        _require_boolean_fields(
            artifact_check,
            ("demo_result_checked",),
            expected=True,
            path=artifact_check_path,
        )

    recorded_demo_result_path = demo_result.get("demo_result_path")
    expected_demo_result_path = str(demo_result_path)
    recorded_output_dir = demo_result.get("output_dir")
    expected_output_dir = str(output_dir)

    if recorded_demo_result_path != expected_demo_result_path:
        raise ValueError(
            "demo_run_result.demo_result_path must match "
            "the checked evidence file"
        )

    if recorded_output_dir != expected_output_dir:
        raise ValueError(
            "demo_run_result.output_dir must match "
            "the checked output directory"
        )

    validate_artifact_list(
        demo_result.get("artifacts"),
        path=_demo_run_result_field_path("artifacts"),
    )
    return artifact_check


def _demo_run_result_field_path(field: str) -> str:
    return f"demo_run_result.{field}"


def validate_artifact_inventory_matches_files(
    value: Any,
    *,
    output_dir: Path,
    path: str,
) -> dict[str, Any]:
    artifact_inventory = validate_artifact_inventory(value, path=path)
    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        recorded_fingerprint = validate_artifact_fingerprint(
            artifact_inventory.get(artifact_name),
            path=_field_path(path, artifact_name),
        )
        current_fingerprint = build_artifact_fingerprint(output_dir / artifact_name)
        recorded_sha256 = recorded_fingerprint.get("sha256")
        current_sha256 = current_fingerprint["sha256"]
        recorded_size_bytes = recorded_fingerprint.get("size_bytes")
        current_size_bytes = current_fingerprint["size_bytes"]

        if recorded_sha256 != current_sha256:
            raise ValueError(f"artifact inventory sha256 mismatch: {artifact_name}")

        if recorded_size_bytes != current_size_bytes:
            raise ValueError(f"artifact inventory size mismatch: {artifact_name}")

    return artifact_inventory


def validate_demo_evidence_files(
    output_dir: Path,
    *,
    require_demo_result_checked: bool = True,
    require_demo_receipt: bool = True,
) -> dict[str, bool]:
    evidence_flags = {field: False for field in DEMO_EVIDENCE_CHECK_FIELDS}
    demo_result_path = output_dir / DEMO_RESULT_NAME
    if not demo_result_path.exists():
        return evidence_flags

    demo_result = load_json(demo_result_path)
    validate_demo_run_result(
        demo_result,
        output_dir=output_dir,
        demo_result_path=demo_result_path,
        require_demo_result_checked=require_demo_result_checked,
    )
    validate_artifact_inventory_matches_files(
        demo_result.get("artifact_inventory"),
        output_dir=output_dir,
        path=_demo_run_result_field_path("artifact_inventory"),
    )
    evidence_flags["artifact_inventory_checked"] = True

    if require_demo_receipt:
        validation_summary = load_json(output_dir / VALIDATION_SUMMARY_NAME)
        validate_demo_evidence_receipt_file(
            receipt_path=output_dir / DEMO_RECEIPT_NAME,
            demo_result=demo_result,
            artifact_inventory=demo_result.get("artifact_inventory"),
            validation_summary=validation_summary,
        )
        evidence_flags["demo_receipt_checked"] = True

    evidence_flags["demo_result_checked"] = True
    return evidence_flags


def build_package_artifact_check_result(
    output_dir: Path,
    *,
    require_demo_result_checked: bool = True,
    require_demo_receipt: bool = True,
) -> dict[str, object]:
    package = validate_local_package_artifacts(output_dir)
    demo_evidence_flags = validate_demo_evidence_files(
        output_dir,
        require_demo_result_checked=require_demo_result_checked,
        require_demo_receipt=require_demo_receipt,
    )
    artifact_count = len(INCLUDED_ARTIFACT_ORDER)
    recommendation = package["recommendation"]

    return {
        "status": "passed",
        "output_dir": str(output_dir),
        "artifact_count": artifact_count,
        "recommendation": recommendation,
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        "operational_approval": False,
        **demo_evidence_flags,
    }


def build_package_artifact_check_failure_result(
    output_dir: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "status": "failed",
        "output_dir": str(output_dir),
        **_exception_fields(exc),
    }


def gate_demo_output(output_dir: Path) -> dict[str, object]:
    artifact_check_result = build_package_artifact_check_result(output_dir)
    demo_result_path = output_dir / DEMO_RESULT_NAME
    demo_receipt_path = output_dir / DEMO_RECEIPT_NAME
    if not demo_result_path.is_file():
        raise ValueError(f"demo result file is missing: {demo_result_path}")

    if not demo_receipt_path.is_file():
        raise ValueError(f"demo evidence receipt is missing: {demo_receipt_path}")

    demo_result = load_json(demo_result_path)
    artifact_list_path = _demo_run_result_field_path("artifacts")
    artifacts = validate_artifact_list(
        demo_result.get("artifacts"),
        path=artifact_list_path,
    )
    demo_evidence_flags = _project_fields(
        artifact_check_result,
        DEMO_EVIDENCE_CHECK_FIELDS,
    )

    return {
        "status": "passed",
        "gate": GATE_NAME,
        "output_dir": str(output_dir),
        "demo_result_path": str(demo_result_path),
        "demo_receipt_path": str(demo_receipt_path),
        "operational_approval": artifact_check_result["operational_approval"],
        "artifact_count": artifact_check_result["artifact_count"],
        "excluded_external_actions": list(EXTERNAL_RUNTIME_ACTION_ORDER),
        "recommendation": artifact_check_result["recommendation"],
        "authorization_boundary": artifact_check_result["authorization_boundary"],
        "artifacts": artifacts,
        **demo_evidence_flags,
    }


def build_gate_failure_result(output_dir: Path, exc: Exception) -> dict[str, object]:
    return {
        "status": "failed",
        "gate": GATE_NAME,
        "output_dir": str(output_dir),
        **_exception_fields(exc),
    }


def build_sample_builder_failure_result(
    *,
    sample_input_path: Path,
    output_dir: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "status": "failed",
        "sample_input": str(sample_input_path),
        "output_dir": str(output_dir),
        **_exception_fields(exc),
    }


def build_sample_validation_failure_result(
    *,
    sample_input_path: Path,
    expected_package_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SAMPLE_VALIDATION_SCHEMA_PURPOSE,
        "status": "failed",
        "sample_input": str(sample_input_path),
        "expected_package": str(expected_package_path),
        **_exception_fields(exc),
    }


def build_export_package_failure_result(
    *,
    data_dir: Path,
    tenant_id: str,
    project_id: str,
    out_dir: Path | None,
    exc: Exception,
) -> dict[str, object]:
    return {
        "status": "failed",
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "data_dir": str(data_dir),
        "tenant_id": tenant_id,
        "project_id": project_id,
        "output_dir": _optional_path(out_dir),
        **_exception_fields(exc),
    }


def build_demo_run_result(
    export_result: dict[str, object],
    *,
    output_dir: Path,
    artifact_check: dict[str, object],
    seeded_decision_id: str,
    demo_tenant_id: str,
    demo_project_id: str,
    clean_output: bool,
) -> dict[str, object]:
    return {
        "status": export_result["status"],
        "schema_purpose": export_result["schema_purpose"],
        "output_dir": export_result["output_dir"],
        "demo_tenant_id": demo_tenant_id,
        "demo_project_id": demo_project_id,
        "seeded_decision_id": seeded_decision_id,
        "demo_result_path": str(output_dir / DEMO_RESULT_NAME),
        "demo_receipt_path": str(output_dir / DEMO_RECEIPT_NAME),
        "artifact_check": artifact_check,
        "artifact_inventory": build_artifact_inventory(output_dir),
        "artifacts": export_result["artifacts"],
        "tenant_id": export_result["tenant_id"],
        "project_id": export_result["project_id"],
        "decision_id": export_result["decision_id"],
        "recommendation": export_result["recommendation"],
        "authorization_boundary": export_result["authorization_boundary"],
        "clean_output": clean_output,
    }


def build_demo_run_failure_result(
    *,
    data_dir: Path,
    out_dir: Path,
    clean_output: bool,
    exc: Exception,
) -> dict[str, object]:
    return {
        "schema_purpose": PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE,
        "status": "failed",
        "data_dir": str(data_dir),
        "output_dir": str(out_dir),
        "clean_output": clean_output,
        **_exception_fields(exc),
    }


def write_demo_evidence_state(
    demo_result: dict[str, object],
    *,
    demo_result_path: Path,
    artifact_check: dict[str, object],
    receipt_path: Path | None = None,
) -> dict[str, object]:
    demo_result["artifact_check"] = artifact_check
    write_json_atomic(demo_result_path, demo_result)

    if receipt_path is not None:
        write_text_atomic(receipt_path, render_demo_evidence_receipt(demo_result))

    return demo_result


def write_validated_demo_evidence(
    demo_result: dict[str, object],
    *,
    output_dir: Path,
    demo_result_path: Path,
    receipt_path: Path,
    initial_artifact_check: dict[str, object],
) -> dict[str, object]:
    write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=initial_artifact_check,
    )
    first_written_artifact_check = build_package_artifact_check_result(
        output_dir,
        require_demo_result_checked=False,
        require_demo_receipt=False,
    )
    write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=first_written_artifact_check,
    )
    receipt_ready_artifact_check = build_package_artifact_check_result(
        output_dir,
        require_demo_receipt=False,
    )
    write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=receipt_ready_artifact_check,
        receipt_path=receipt_path,
    )
    final_artifact_check = build_package_artifact_check_result(output_dir)
    return write_demo_evidence_state(
        demo_result,
        demo_result_path=demo_result_path,
        artifact_check=final_artifact_check,
        receipt_path=receipt_path,
    )


def run_demo(
    *,
    data_dir: Path = DEFAULT_DEMO_DATA_DIR,
    out_dir: Path = DEFAULT_DEMO_OUT_DIR,
    reviewer_owner: str = "executive-reviewer",
    clean_output: bool = False,
) -> dict[str, object]:
    output_dir = out_dir
    prepare_demo_output_dir(output_dir, clean_output=clean_output)

    seeded_decision_id = seed_demo_decision_record(data_dir=data_dir)
    export_result = export_demo_decision_package(
        data_dir=data_dir,
        out_dir=output_dir,
        reviewer_owner=reviewer_owner,
    )
    initial_artifact_check_result = build_package_artifact_check_result(output_dir)
    demo_run_result = build_demo_run_result(
        export_result,
        output_dir=output_dir,
        artifact_check=initial_artifact_check_result,
        seeded_decision_id=seeded_decision_id,
        demo_tenant_id=DEMO_TENANT_ID,
        demo_project_id=DEMO_PROJECT_ID,
        clean_output=clean_output,
    )
    return write_validated_demo_evidence(
        demo_run_result,
        output_dir=output_dir,
        demo_result_path=output_dir / DEMO_RESULT_NAME,
        receipt_path=output_dir / DEMO_RECEIPT_NAME,
        initial_artifact_check=initial_artifact_check_result,
    )


def prepare_demo_output_dir(out_dir: Path, *, clean_output: bool) -> None:
    if clean_output and out_dir.exists():
        shutil.rmtree(out_dir)


def export_demo_decision_package(
    *,
    data_dir: Path,
    out_dir: Path,
    reviewer_owner: str,
) -> dict[str, object]:
    return export_project_decision_package(
        data_dir=data_dir,
        tenant_id=DEMO_TENANT_ID,
        project_id=DEMO_PROJECT_ID,
        out_dir=out_dir,
        reviewer_owner=reviewer_owner,
    )


def build_evidence_files(
    *,
    demo_result_path: object | None = None,
    demo_receipt_path: object | None = None,
    gate_result_path: object | None = None,
    smoke_result_path: object | None = None,
    smoke_check_result_path: object | None = None,
) -> dict[str, object | None]:
    evidence_file_slots = {
        "demo_result": _optional_path(demo_result_path),
        "demo_receipt": _optional_path(demo_receipt_path),
        "gate_result": _optional_path(gate_result_path),
        "smoke_result": _optional_path(smoke_result_path),
        "smoke_check_result": _optional_path(smoke_check_result_path),
    }

    return _project_fields(evidence_file_slots, EVIDENCE_FILE_FIELDS)


def _build_smoke_gate_result(
    *,
    data_dir: Path,
    out_dir: Path,
    demo_result: dict[str, object],
    gate_result: dict[str, object],
    gate_result_path: Path | None,
    evidence_files: dict[str, object | None],
    gate_result_written: bool,
    clean_output: bool,
) -> dict[str, object]:
    demo_evidence_flags = _project_fields(
        gate_result,
        DEMO_EVIDENCE_CHECK_FIELDS,
    )

    return {
        "status": "passed",
        "smoke": SMOKE_NAME,
        "output_dir": str(out_dir),
        "demo_result_path": demo_result["demo_result_path"],
        "gate_result_path": _optional_path(gate_result_path),
        "smoke_result_path": None,
        "smoke_check_result_path": None,
        "evidence_files": evidence_files,
        "operational_approval": gate_result["operational_approval"],
        "data_dir": str(data_dir),
        "demo_tenant_id": demo_result["demo_tenant_id"],
        "demo_project_id": demo_result["demo_project_id"],
        "seeded_decision_id": demo_result["seeded_decision_id"],
        "demo_receipt_path": demo_result["demo_receipt_path"],
        "gate_result_written": gate_result_written,
        "smoke_result_written": False,
        "smoke_check_result_written": False,
        "package_artifacts_checked": False,
        "smoke_result_checked": False,
        **demo_evidence_flags,
        "artifact_count": gate_result["artifact_count"],
        "excluded_external_actions": gate_result["excluded_external_actions"],
        "recommendation": gate_result["recommendation"],
        "authorization_boundary": gate_result["authorization_boundary"],
        "clean_output": clean_output,
    }


def smoke_demo_gate(
    *,
    data_dir: Path = DEFAULT_DEMO_DATA_DIR,
    out_dir: Path = DEFAULT_DEMO_OUT_DIR,
    reviewer_owner: str = "executive-reviewer",
    clean_output: bool = True,
    write_gate_result: bool = True,
    gate_result_path: Path | None = None,
) -> dict[str, object]:
    output_dir = out_dir
    demo_result = run_demo(
        data_dir=data_dir,
        out_dir=output_dir,
        reviewer_owner=reviewer_owner,
        clean_output=clean_output,
    )
    gate_result = gate_demo_output(output_dir)
    recorded_gate_result_path = None
    if write_gate_result:
        recorded_gate_result_path = gate_result_path or output_dir / GATE_RESULT_NAME
        write_json_atomic(recorded_gate_result_path, gate_result)

    evidence_files = build_evidence_files(
        demo_result_path=demo_result["demo_result_path"],
        demo_receipt_path=demo_result["demo_receipt_path"],
        gate_result_path=recorded_gate_result_path,
    )
    return _build_smoke_gate_result(
        data_dir=data_dir,
        out_dir=output_dir,
        demo_result=demo_result,
        gate_result=gate_result,
        gate_result_path=recorded_gate_result_path,
        evidence_files=evidence_files,
        gate_result_written=write_gate_result,
        clean_output=clean_output,
    )


def build_smoke_failure_result(
    *,
    data_dir: Path,
    out_dir: Path,
    clean_output: bool,
    gate_result_path: Path | None,
    gate_result_written: bool,
    smoke_result_path: Path | None,
    smoke_result_written: bool,
    smoke_check_result_path: Path | None,
    smoke_check_result_written: bool,
    exc: Exception,
) -> dict[str, object]:
    evidence_files = build_evidence_files(
        gate_result_path=gate_result_path,
        smoke_result_path=smoke_result_path,
        smoke_check_result_path=smoke_check_result_path,
    )

    return {
        "status": "failed",
        "smoke": SMOKE_NAME,
        "data_dir": str(data_dir),
        "output_dir": str(out_dir),
        "clean_output": clean_output,
        "gate_result_path": _optional_path(gate_result_path),
        "smoke_result_path": _optional_path(smoke_result_path),
        "smoke_check_result_path": _optional_path(smoke_check_result_path),
        "evidence_files": evidence_files,
        "gate_result_written": gate_result_written,
        "smoke_result_written": smoke_result_written,
        "smoke_check_result_written": smoke_check_result_written,
        "package_artifacts_checked": False,
        "smoke_result_checked": False,
        **_exception_fields(exc),
    }


def _require_existing_file_path(path_value: Any, path_name: str) -> Path:
    path_text = _require_path_string(path_value, path_name)
    path = Path(path_text)
    if not path.is_file():
        raise ValueError(f"{path_name} file is missing: {path}")
    return path


def _require_existing_dir(path_value: Any, path_name: str) -> Path:
    path_text = _require_path_string(path_value, path_name)
    path = Path(path_text)
    if not path.is_dir():
        raise ValueError(f"{path_name} directory is missing: {path}")
    return path


def _require_path_string(path_value: Any, path_name: str) -> str:
    if not _is_non_empty_string(path_value):
        raise ValueError(f"{path_name} must be a non-empty string")
    return path_value


def _require_matching_field(
    left: dict[str, Any],
    right: dict[str, Any],
    field: str,
    *,
    left_label: str = "demo_smoke_result",
    right_label: str,
) -> None:
    left_field_value = left.get(field)
    right_field_value = right.get(field)
    if left_field_value != right_field_value:
        left_field_path = _field_path(left_label, field)
        right_field_path = _field_path(right_label, field)
        raise ValueError(f"{left_field_path} must match {right_field_path}")


def _require_matching_fields(
    left: dict[str, Any],
    right: dict[str, Any],
    fields: Sequence[str],
    *,
    left_label: str = "demo_smoke_result",
    right_label: str,
) -> None:
    for field in fields:
        _require_matching_field(
            left,
            right,
            field,
            left_label=left_label,
            right_label=right_label,
        )


def _require_smoke_evidence_file_paths(
    evidence_files: dict[str, Any],
) -> _SmokeEvidencePaths:
    demo_result_path = _require_smoke_evidence_file_path(
        evidence_files,
        "demo_result",
    )
    demo_receipt_path = _require_smoke_evidence_file_path(
        evidence_files,
        "demo_receipt",
    )
    gate_result_path = _require_smoke_evidence_file_path(
        evidence_files,
        "gate_result",
    )
    smoke_result_recorded_path = _require_smoke_evidence_file_path(
        evidence_files,
        "smoke_result",
    )

    return _SmokeEvidencePaths(
        demo_result_path=demo_result_path,
        demo_receipt_path=demo_receipt_path,
        gate_result_path=gate_result_path,
        smoke_result_recorded_path=smoke_result_recorded_path,
    )


def _require_smoke_evidence_file_path(
    evidence_files: dict[str, Any],
    evidence_file_field: str,
) -> Path:
    return _require_existing_file_path(
        evidence_files.get(evidence_file_field),
        f"evidence_files.{evidence_file_field}",
    )


def _require_checked_smoke_result_path(
    recorded_smoke_result_path: Path,
    checked_smoke_result_path: Path,
) -> None:
    if str(recorded_smoke_result_path) != str(checked_smoke_result_path):
        raise ValueError(
            "evidence_files.smoke_result must match "
            "the checked smoke result file"
        )


def _require_recorded_smoke_check_result(
    smoke_result: dict[str, Any],
    evidence_files: dict[str, Any],
    current_smoke_check_result: dict[str, object],
) -> None:
    smoke_check_result_written = smoke_result.get("smoke_check_result_written")
    if smoke_check_result_written is not True:
        raise ValueError(
            f"{_field_path('demo_smoke_result', 'smoke_check_result_written')} "
            "must be true"
        )

    smoke_check_result_path = _require_existing_file_path(
        evidence_files.get("smoke_check_result"),
        "evidence_files.smoke_check_result",
    )

    recorded_smoke_check_result_payload = load_json(smoke_check_result_path)
    if recorded_smoke_check_result_payload != current_smoke_check_result:
        raise ValueError(
            "demo_smoke_check_result must match "
            "the current smoke check result"
        )


def _require_gate_result_paths(
    gate_result: dict[str, Any],
    smoke_result: dict[str, Any],
    *,
    demo_result_path: Path,
    demo_receipt_path: Path,
) -> None:
    expected_smoke_demo_paths = {
        "demo_result_path": str(demo_result_path),
        "demo_receipt_path": str(demo_receipt_path),
    }

    _require_matching_field(
        gate_result,
        smoke_result,
        "output_dir",
        left_label="demo_gate_result",
        right_label="demo_smoke_result",
    )
    _require_matching_fields(
        gate_result,
        expected_smoke_demo_paths,
        ("demo_result_path", "demo_receipt_path"),
        left_label="demo_gate_result",
        right_label="demo_smoke_result",
    )


def _require_boolean_fields(
    mapping: dict[str, Any],
    fields: Sequence[str],
    *,
    expected: bool,
    path: str,
) -> None:
    expected_label = _bool_label(expected)

    for field in fields:
        field_value = mapping.get(field)
        field_path = _field_path(path, field)
        if field_value is not expected:
            raise ValueError(f"{field_path} must be {expected_label}")


def _require_unique_values(
    items: Sequence[str],
    path: str,
    *,
    message: str | None = None,
) -> None:
    unique_items = set(items)
    if len(unique_items) != len(items):
        raise ValueError(message or f"{path} must not contain duplicate values")


def _missing_values(
    expected_values: Iterable[str],
    actual_values: Iterable[str],
) -> list[str]:
    expected_value_set = set(expected_values)
    actual_value_set = set(actual_values)
    return sorted(expected_value_set - actual_value_set)


def _unknown_values(
    actual_values: Iterable[str],
    expected_values: Iterable[str],
) -> list[str]:
    actual_value_set = set(actual_values)
    expected_value_set = set(expected_values)
    return sorted(actual_value_set - expected_value_set)


def _shared_values(
    left_values: Iterable[str],
    right_values: Iterable[str],
) -> list[str]:
    left_value_set = set(left_values)
    right_value_set = set(right_values)
    return sorted(left_value_set & right_value_set)


def _require_exact_ordered_values(
    recorded_values: list[str],
    expected: Sequence[str],
    *,
    path: str,
    missing_label: str = "values",
    unknown_label: str = "values",
) -> None:
    expected_order = list(expected)
    missing_values = _missing_values(expected_order, recorded_values)
    if missing_values:
        raise ValueError(
            f"{path} missing {missing_label}: {', '.join(missing_values)}"
        )
    unknown_values = _unknown_values(recorded_values, expected_order)
    if unknown_values:
        raise ValueError(
            f"{path} includes unknown {unknown_label}: "
            f"{', '.join(unknown_values)}"
        )
    if recorded_values != expected_order:
        raise ValueError(f"{path} must match the expected order")


def _require_excluded_external_actions(value: Any, path: str) -> list[str]:
    excluded_external_actions = _require_string_list(value, path)
    _require_unique_values(excluded_external_actions, path)
    _require_excluded_external_action_order(
        excluded_external_actions,
        path=path,
    )
    return excluded_external_actions


def _require_excluded_external_action_order(
    recorded_excluded_external_actions: list[str],
    *,
    path: str,
) -> None:
    expected_external_actions = EXTERNAL_RUNTIME_ACTION_ORDER

    _require_exact_ordered_values(
        recorded_excluded_external_actions,
        expected_external_actions,
        path=path,
        missing_label="external actions",
        unknown_label="external actions",
    )


def _require_matching_excluded_external_actions(
    recorded_smoke_result_actions: list[str],
    comparison_actions_value: Any,
    *,
    comparison_path: str,
    comparison_label: str,
) -> None:
    comparison_actions = _require_excluded_external_actions(
        comparison_actions_value,
        comparison_path,
    )
    if recorded_smoke_result_actions != comparison_actions:
        smoke_result_actions_path = _field_path(
            "demo_smoke_result",
            "excluded_external_actions",
        )
        comparison_actions_path = _field_path(
            comparison_label,
            "excluded_external_actions",
        )
        raise ValueError(
            f"{smoke_result_actions_path} must match {comparison_actions_path}"
        )


def _require_smoke_result_check_state(
    smoke_result: dict[str, Any],
    *,
    require_smoke_result_checked: bool,
) -> None:
    _require_boolean_fields(
        smoke_result,
        SMOKE_REQUIRED_FALSE_FIELDS,
        expected=False,
        path="demo_smoke_result",
    )
    _require_boolean_fields(
        smoke_result,
        SMOKE_REQUIRED_TRUE_FIELDS,
        expected=True,
        path="demo_smoke_result",
    )
    smoke_result_checked = smoke_result.get("smoke_result_checked")
    if require_smoke_result_checked and smoke_result_checked is not True:
        raise ValueError(
            f"{_field_path('demo_smoke_result', 'smoke_result_checked')} "
            "must be true"
        )
    _require_smoke_result_checked_after_artifact_check(smoke_result)


def _require_smoke_result_checked_after_artifact_check(
    smoke_result: dict[str, Any],
) -> None:
    smoke_result_checked = smoke_result.get("smoke_result_checked")
    package_artifacts_checked = smoke_result.get("package_artifacts_checked")
    smoke_result_is_checked = smoke_result_checked is True
    artifact_check_is_missing = package_artifacts_checked is not True

    if smoke_result_is_checked and artifact_check_is_missing:
        raise ValueError(
            "package_artifacts_checked must be true "
            "when smoke_result_checked is true "
            f"({_field_path('demo_smoke_result', 'package_artifacts_checked')} "
            "depends on "
            f"{_field_path('demo_smoke_result', 'smoke_result_checked')})"
        )


def _build_smoke_check_result(
    *,
    smoke_result_path: Path,
    smoke_result: dict[str, Any],
    evidence_context: _SmokeEvidenceContext,
    excluded_external_actions: list[str],
) -> dict[str, object]:
    smoke_check_result_path_value = smoke_result.get("smoke_check_result_path")
    evidence_files = build_evidence_files(
        demo_result_path=evidence_context.demo_result_path,
        demo_receipt_path=evidence_context.demo_receipt_path,
        gate_result_path=evidence_context.gate_result_path,
        smoke_result_path=evidence_context.smoke_result_recorded_path,
        smoke_check_result_path=smoke_check_result_path_value,
    )
    smoke_context = _project_optional_fields(
        smoke_result,
        SMOKE_CHECK_CONTEXT_FIELDS,
    )
    smoke_decision = _project_optional_fields(
        smoke_result,
        SMOKE_CHECK_DECISION_FIELDS,
    )

    return {
        "status": "passed",
        "check": SMOKE_CHECK_NAME,
        "smoke_result_path": str(smoke_result_path),
        "output_dir": smoke_result.get("output_dir"),
        "package_artifacts_checked": True,
        "smoke_result_checked": True,
        "evidence_files": evidence_files,
        "smoke_check_result_path": smoke_check_result_path_value,
        **smoke_context,
        "excluded_external_actions": excluded_external_actions,
        **smoke_decision,
        "operational_approval": False,
        "clean_output": smoke_result.get("clean_output"),
    }


def check_smoke_result(
    smoke_result_path: Path,
    *,
    require_recorded_smoke_check: bool = True,
    require_recorded_smoke_check_result: bool = True,
) -> dict[str, object]:
    if not smoke_result_path.is_file():
        raise FileNotFoundError(f"smoke result file is missing: {smoke_result_path}")

    smoke_result = load_json(smoke_result_path)
    smoke_name = smoke_result.get("smoke")
    if smoke_name != SMOKE_NAME:
        raise ValueError(
            f"{_field_path('demo_smoke_result', 'smoke')} must be {SMOKE_NAME}"
        )
    _require_passed_status(smoke_result, "demo_smoke_result")
    _require_smoke_result_check_state(
        smoke_result,
        require_smoke_result_checked=require_recorded_smoke_check,
    )
    excluded_external_actions = _require_excluded_external_actions(
        smoke_result.get("excluded_external_actions"),
        "demo_smoke_result.excluded_external_actions",
    )
    evidence_context = _require_smoke_evidence_context(smoke_result, smoke_result_path)
    current_artifact_check_result = build_package_artifact_check_result(
        evidence_context.output_dir
    )
    _require_matching_fields(
        smoke_result,
        current_artifact_check_result,
        SMOKE_PACKAGE_ARTIFACT_MATCH_FIELDS,
        right_label="package_artifact_check",
    )
    demo_result = load_json(evidence_context.demo_result_path)
    schema_purpose = demo_result.get("schema_purpose")
    if schema_purpose != PROCUREMENT_DECISION_PACKAGE_SCHEMA_PURPOSE:
        raise ValueError(
            "demo_run_result.schema_purpose must be procurement_decision_package"
        )
    _require_demo_result_matches_smoke_result(demo_result, smoke_result)
    demo_artifact_check_value = demo_result.get("artifact_check")
    demo_artifact_check = _require_mapping(
        demo_artifact_check_value,
        "demo_run_result.artifact_check",
    )
    _require_matching_fields(
        smoke_result,
        demo_artifact_check,
        SMOKE_DEMO_ARTIFACT_CHECK_FIELDS,
        right_label="demo_run_result.artifact_check",
    )
    _require_gate_result_for_smoke(
        smoke_result,
        evidence_context.gate_result_path,
        demo_result_path=evidence_context.demo_result_path,
        demo_receipt_path=evidence_context.demo_receipt_path,
        excluded_external_actions=excluded_external_actions,
    )
    smoke_check_result = _build_smoke_check_result(
        smoke_result_path=smoke_result_path,
        smoke_result=smoke_result,
        evidence_context=evidence_context,
        excluded_external_actions=excluded_external_actions,
    )
    if require_recorded_smoke_check_result:
        _require_recorded_smoke_check_result(
            smoke_result,
            evidence_context.evidence_files,
            smoke_check_result,
        )
    return smoke_check_result


def _require_smoke_evidence_context(
    smoke_result: dict[str, Any],
    smoke_result_path: Path,
) -> _SmokeEvidenceContext:
    output_dir_value = smoke_result.get("output_dir")
    output_dir = _require_existing_dir(
        output_dir_value,
        "demo_smoke_result.output_dir",
    )
    evidence_files_value = smoke_result.get("evidence_files")
    evidence_files = _require_mapping(
        evidence_files_value,
        "demo_smoke_result.evidence_files",
    )
    recorded_evidence_file_fields = list(evidence_files)

    _require_exact_ordered_values(
        recorded_evidence_file_fields,
        EVIDENCE_FILE_FIELDS,
        path="demo_smoke_result.evidence_files",
        missing_label="fields",
        unknown_label="fields",
    )
    for smoke_result_field, evidence_file_field in SMOKE_EVIDENCE_PATH_FIELDS:
        if smoke_result.get(smoke_result_field) != evidence_files.get(
            evidence_file_field
        ):
            smoke_result_field_path = _field_path(
                "demo_smoke_result",
                smoke_result_field,
            )
            evidence_file_field_path = _field_path(
                "demo_smoke_result.evidence_files",
                evidence_file_field,
            )
            raise ValueError(
                f"{smoke_result_field_path} must match "
                f"{evidence_file_field_path}"
            )
    required_evidence_paths = _require_smoke_evidence_file_paths(evidence_files)
    _require_checked_smoke_result_path(
        required_evidence_paths.smoke_result_recorded_path,
        smoke_result_path,
    )
    return _SmokeEvidenceContext(
        output_dir=output_dir,
        evidence_files=evidence_files,
        demo_result_path=required_evidence_paths.demo_result_path,
        demo_receipt_path=required_evidence_paths.demo_receipt_path,
        gate_result_path=required_evidence_paths.gate_result_path,
        smoke_result_recorded_path=required_evidence_paths.smoke_result_recorded_path,
    )


def _require_demo_result_matches_smoke_result(
    demo_result: dict[str, Any],
    smoke_result: dict[str, Any],
) -> None:
    _require_matching_fields(
        demo_result,
        smoke_result,
        SMOKE_DEMO_CONTEXT_FIELDS,
        left_label="demo_run_result",
        right_label="demo_smoke_result",
    )
    _require_matching_fields(
        demo_result,
        smoke_result,
        SMOKE_DEMO_IDENTITY_FIELDS,
        left_label="demo_run_result",
        right_label="demo_smoke_result",
    )
    _require_matching_fields(
        smoke_result,
        demo_result,
        SMOKE_DEMO_RESULT_MATCH_FIELDS,
        right_label="demo_run_result",
    )


def _require_gate_result_for_smoke(
    smoke_result: dict[str, Any],
    gate_result_path: Path,
    *,
    demo_result_path: Path,
    demo_receipt_path: Path,
    excluded_external_actions: list[str],
) -> None:
    gate_result = load_json(gate_result_path)
    gate_name = gate_result.get("gate")
    if gate_name != GATE_NAME:
        raise ValueError(
            f"{_field_path('demo_gate_result', 'gate')} must be {GATE_NAME}"
        )
    _require_passed_status(gate_result, "demo_gate_result")
    _require_gate_result_paths(
        gate_result,
        smoke_result,
        demo_result_path=demo_result_path,
        demo_receipt_path=demo_receipt_path,
    )
    gate_excluded_external_actions = gate_result.get("excluded_external_actions")
    _require_matching_excluded_external_actions(
        excluded_external_actions,
        gate_excluded_external_actions,
        comparison_path="demo_gate_result.excluded_external_actions",
        comparison_label="demo_gate_result",
    )
    _require_matching_fields(
        smoke_result,
        gate_result,
        SMOKE_PACKAGE_ARTIFACT_MATCH_FIELDS,
        right_label="demo_gate_result",
    )


def build_smoke_check_failure_result(
    smoke_result_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return {
        "check": SMOKE_CHECK_NAME,
        "status": "failed",
        "smoke_result_path": str(smoke_result_path),
        **_exception_fields(exc),
    }


def _require_passed_status(mapping: dict[str, Any], path: str) -> None:
    status_path = _field_path(path, "status")

    if mapping.get("status") != "passed":
        raise ValueError(f"{status_path} must be passed")


def _validation_result_field_path(field: str) -> str:
    return f"validation_result.{field}"


def check_cli_contract_manifest_validation_result(
    validation_result_path: Path,
    *,
    expected_schema_purpose: str,
    validate_current_manifest: Callable[[Path], dict[str, Any]],
    display_base_dir: Path | None = None,
) -> dict[str, object]:
    if not validation_result_path.is_file():
        raise FileNotFoundError(
            "manifest validation result file is missing: "
            f"{validation_result_path}"
        )

    recorded_validation_result = load_json(validation_result_path)
    _require_exact_mapping_fields(
        recorded_validation_result,
        CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
        "validation_result",
    )
    _validate_cli_validation_result_identity(
        recorded_validation_result,
        expected_schema_purpose=expected_schema_purpose,
    )
    manifest_path, current_manifest_validation = _load_current_manifest_validation(
        recorded_validation_result,
        validate_current_manifest=validate_current_manifest,
    )
    _validate_cli_validation_result_matches_current_manifest(
        recorded_validation_result,
        current_manifest_validation,
    )

    return _build_cli_manifest_validation_check_result(
        validation_result_path=validation_result_path,
        manifest_path=manifest_path,
        current_manifest_validation=current_manifest_validation,
        display_base_dir=display_base_dir,
    )


def _validate_cli_validation_result_identity(
    recorded_validation_result: dict[str, Any],
    *,
    expected_schema_purpose: str,
) -> None:
    schema_purpose_path = _validation_result_field_path("schema_purpose")
    if (
        recorded_validation_result.get("schema_purpose")
        != expected_schema_purpose
    ):
        raise ValueError(
            f"{schema_purpose_path} must be {expected_schema_purpose}"
        )

    _require_passed_status(recorded_validation_result, "validation_result")


def _load_current_manifest_validation(
    recorded_validation_result: dict[str, Any],
    *,
    validate_current_manifest: Callable[[Path], dict[str, Any]],
) -> tuple[Path, dict[str, Any]]:
    manifest_path = _cli_manifest_path_from_validation_result(
        recorded_validation_result
    )
    current_manifest_validation = validate_current_manifest(manifest_path)

    return manifest_path, current_manifest_validation


def _validate_cli_validation_result_matches_current_manifest(
    recorded_validation_result: dict[str, Any],
    current_manifest_validation: dict[str, Any],
) -> None:
    current_manifest_case_names = current_manifest_validation["case_names"]
    _validate_cli_validation_result_case_maps(
        recorded_validation_result,
        current_manifest_case_names=current_manifest_case_names,
    )
    _require_matching_fields(
        recorded_validation_result,
        current_manifest_validation,
        CLI_CONTRACT_MANIFEST_CURRENT_VALIDATION_MATCH_FIELDS,
        left_label="validation_result",
        right_label="current_manifest_validation",
    )


def _cli_manifest_path_from_validation_result(
    recorded_validation_result: dict[str, Any],
) -> Path:
    manifest_path = _require_non_empty_string_field(
        recorded_validation_result,
        "manifest_path",
        path="validation_result",
    )

    return Path(manifest_path)


def _build_cli_manifest_validation_check_result(
    *,
    validation_result_path: Path,
    manifest_path: Path,
    current_manifest_validation: dict[str, Any],
    display_base_dir: Path | None = None,
) -> dict[str, Any]:
    current_manifest_check_fields = _project_fields(
        current_manifest_validation,
        CLI_CONTRACT_MANIFEST_CURRENT_VALIDATION_FIELDS,
    )

    return _project_fields(
        {
            "check": CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
            "status": "passed",
            "validation_result_path": display_path(
                validation_result_path,
                base_dir=display_base_dir,
            ),
            "manifest_path": display_path(
                manifest_path,
                base_dir=display_base_dir,
            ),
            **current_manifest_check_fields,
            "validation_result_checked": True,
        },
        CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FIELDS,
    )


def _validate_cli_validation_result_case_maps(
    recorded_validation_result: dict[str, Any],
    *,
    current_manifest_case_names: Sequence[str],
) -> None:
    current_manifest_case_order = list(current_manifest_case_names)
    case_names_path = _validation_result_field_path("case_names")

    for case_map_field in CLI_CONTRACT_MANIFEST_CASE_MAP_FIELDS:
        recorded_case_map = recorded_validation_result.get(case_map_field)
        case_map_path = _validation_result_field_path(case_map_field)

        if not isinstance(recorded_case_map, dict):
            raise ValueError(f"{case_map_path} must be an object")
        if list(recorded_case_map) != current_manifest_case_order:
            raise ValueError(
                f"{case_map_path} case order must match "
                f"{case_names_path}"
            )


def build_cli_contract_manifest_validation_check_failure_result(
    validation_result_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return _project_fields(
        {
            "status": "failed",
            "check": CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_NAME,
            "validation_result_path": str(validation_result_path),
            **_exception_fields(exc),
        },
        CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_FAILURE_FIELDS,
    )


def build_cli_contract_manifest_validation_failure_result(
    *,
    manifest_path: Path,
    exc: Exception,
) -> dict[str, object]:
    return _project_fields(
        {
            "schema_purpose": CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
            "contract_version": CLI_CONTRACT_MANIFEST_CONTRACT_VERSION,
            "status": "failed",
            "manifest_path": str(manifest_path),
            **_exception_fields(exc),
        },
        CLI_CONTRACT_MANIFEST_VALIDATION_FAILURE_FIELDS,
    )


def _build_cli_contract_manifest_validation_result(
    *,
    manifest_path: Path,
    manifest_bytes: bytes,
    manifest: dict[str, Any],
    contracts: list[dict[str, Any]],
    case_names: list[str],
    scripts: list[str],
    excluded_external_actions: list[str],
    display_base_dir: Path | None = None,
) -> dict[str, Any]:
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    success_required_fields_by_case = _cli_contract_required_fields_by_case(
        contracts,
        "success_required_fields",
    )
    failure_required_fields_by_case = _cli_contract_required_fields_by_case(
        contracts,
        "failure_required_fields",
    )
    cli_contract_fingerprint = build_cli_contract_manifest_fingerprint(
        contracts,
        excluded_external_actions,
    )

    return _project_fields(
        {
            "schema_purpose": CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE,
            "status": "passed",
            "contract_version": manifest["contract_version"],
            "manifest_path": display_path(
                manifest_path,
                base_dir=display_base_dir,
            ),
            "manifest_sha256": manifest_sha256,
            "manifest_size_bytes": len(manifest_bytes),
            "workflow": manifest["workflow"],
            "contract_status": manifest["contract_status"],
            "contract_count": len(contracts),
            "script_count": len(scripts),
            "case_names": case_names,
            "scripts": scripts,
            "external_actions_excluded": excluded_external_actions,
            "success_required_fields_by_case": success_required_fields_by_case,
            "failure_required_fields_by_case": failure_required_fields_by_case,
            "cli_contract_fingerprint": cli_contract_fingerprint,
        },
        CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_FIELDS,
    )


def _cli_contract_required_fields_by_case(
    contracts: Sequence[dict[str, Any]],
    field_name: str,
) -> dict[str, list[str]]:
    return {
        contract["case_name"]: contract[field_name]
        for contract in contracts
    }


def validate_cli_contract_manifest(
    manifest_path: Path,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = load_json(manifest_path)
    _require_exact_mapping_fields(
        manifest,
        CLI_CONTRACT_MANIFEST_FIELDS,
        "manifest",
    )
    _validate_cli_contract_manifest_identity(manifest)
    _validate_cli_contract_manifest_stdout_contract(manifest)
    excluded_external_actions = _validate_cli_contract_manifest_excluded_actions(
        manifest
    )
    contracts, case_names, scripts = _validate_cli_contract_manifest_contracts(
        manifest,
        repo_root=repo_root,
    )

    return _build_cli_contract_manifest_validation_result(
        manifest_path=manifest_path,
        manifest_bytes=manifest_bytes,
        manifest=manifest,
        contracts=contracts,
        case_names=case_names,
        scripts=scripts,
        excluded_external_actions=excluded_external_actions,
        display_base_dir=repo_root,
    )


def _validate_cli_contract_manifest_identity(
    manifest: dict[str, Any],
) -> None:
    manifest_field_path = "manifest"
    for field, expected_value in CLI_CONTRACT_MANIFEST_IDENTITY_VALUES:
        _require_cli_contract_value(
            manifest,
            field,
            expected_value,
            manifest_field_path,
        )


def _validate_cli_contract_manifest_excluded_actions(
    manifest: dict[str, Any],
) -> list[str]:
    excluded_external_actions_path = "manifest.external_actions_excluded"
    excluded_external_actions = _require_non_empty_string_list(
        manifest.get("external_actions_excluded"),
        excluded_external_actions_path,
    )
    _require_unique_values(
        excluded_external_actions,
        excluded_external_actions_path,
    )
    _require_exact_ordered_values(
        excluded_external_actions,
        EXCLUDED_ACTION_ORDER,
        path=excluded_external_actions_path,
    )

    return excluded_external_actions


def _validate_cli_contract_manifest_contracts(
    manifest: dict[str, Any],
    *,
    repo_root: Path,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    contracts_path = "manifest.cli_contracts"
    manifest_contract_entries = _require_non_empty_list(
        manifest.get("cli_contracts"),
        contracts_path,
    )
    contracts: list[dict[str, Any]] = []
    case_names: list[str] = []
    scripts: list[str] = []

    for index, contract_entry in enumerate(manifest_contract_entries):
        contract_path = _list_item_path(contracts_path, index)
        contract, case_name, script = _validate_cli_contract_manifest_entry(
            contract_entry,
            contract_path=contract_path,
            repo_root=repo_root,
        )
        contracts.append(contract)
        case_names.append(case_name)
        scripts.append(script)

    _validate_cli_contract_manifest_contract_collection(
        case_names=case_names,
        scripts=scripts,
    )

    return contracts, case_names, scripts


def _validate_cli_contract_manifest_entry(
    contract_entry: Any,
    *,
    contract_path: str,
    repo_root: Path,
) -> tuple[dict[str, Any], str, str]:
    contract = _require_mapping(contract_entry, contract_path)
    _require_exact_mapping_fields(
        contract,
        CLI_CONTRACT_MANIFEST_CLI_CONTRACT_FIELDS,
        contract_path,
    )
    case_name = _require_non_empty_string_field(
        contract,
        "case_name",
        path=contract_path,
    )
    script = _require_non_empty_string_field(
        contract,
        "script",
        path=contract_path,
    )
    _validate_cli_contract_manifest_contract_script(
        case_name=case_name,
        script=script,
        contract_path=contract_path,
        repo_root=repo_root,
    )
    _validate_cli_contract_manifest_success_fields(
        contract,
        case_name=case_name,
        contract_path=contract_path,
    )
    _validate_cli_contract_manifest_failure_fields(
        contract,
        case_name=case_name,
        contract_path=contract_path,
    )

    return contract, case_name, script


def _validate_cli_contract_manifest_contract_collection(
    *,
    case_names: Sequence[str],
    scripts: Sequence[str],
) -> None:
    _require_unique_values(
        case_names,
        "manifest.cli_contracts.case_name",
        message="manifest.cli_contracts case_name values must be unique",
    )
    _require_unique_values(
        scripts,
        "manifest.cli_contracts.script",
        message="manifest.cli_contracts script values must be unique",
    )

    missing_cases = _missing_values(CLI_CONTRACT_MANIFEST_CASE_NAMES, case_names)
    unknown_cases = _unknown_values(
        case_names,
        CLI_CONTRACT_MANIFEST_CASE_NAMES,
    )
    if missing_cases or unknown_cases:
        detail_text = _cli_contract_case_set_mismatch_detail(
            missing_cases,
            unknown_cases,
        )
        raise ValueError(
            f"manifest.cli_contracts case_name set mismatch: {detail_text}"
        )
    if list(case_names) != list(CLI_CONTRACT_MANIFEST_CASE_ORDER):
        raise ValueError(
            "manifest.cli_contracts case_name values must match the expected order"
        )


def _cli_contract_case_set_mismatch_detail(
    missing_cases: Sequence[str],
    unknown_cases: Sequence[str],
) -> str:
    details: list[str] = []
    if missing_cases:
        details.append(f"missing: {', '.join(missing_cases)}")
    if unknown_cases:
        details.append(f"extra: {', '.join(unknown_cases)}")

    return "; ".join(details)


def _validate_cli_contract_manifest_contract_script(
    *,
    case_name: str,
    script: str,
    contract_path: str,
    repo_root: Path,
) -> None:
    script_field_path = _field_path(contract_path, "script")
    script_path = Path(script)
    is_repo_scripts_path = (
        not script_path.is_absolute()
        and script_path.parts[:1] == ("scripts",)
    )
    if not is_repo_scripts_path:
        raise ValueError(
            f"{script_field_path} must be a repo-relative scripts/ path"
        )
    if not (repo_root / script_path).is_file():
        raise ValueError(f"{script_field_path} file is missing: {script}")

    expected_case_script = CLI_CONTRACT_MANIFEST_CASE_SCRIPTS.get(case_name)
    if expected_case_script is not None and script != expected_case_script:
        raise ValueError(
            f"{script_field_path} must be {expected_case_script!r} "
            f"for case_name {case_name!r}"
        )


def _validate_cli_contract_manifest_success_fields(
    contract: dict[str, Any],
    *,
    case_name: str,
    contract_path: str,
) -> list[str]:
    success_fields, fields_path = _require_cli_contract_manifest_case_fields(
        contract,
        case_name=case_name,
        contract_path=contract_path,
        field_name="success_required_fields",
        expected_fields_by_case=CLI_CONTRACT_MANIFEST_SUCCESS_FIELDS_BY_CASE,
    )
    if "status" not in success_fields:
        raise ValueError(f"{fields_path} must include status")
    forbidden_fields = _shared_values(
        success_fields,
        CLI_CONTRACT_MANIFEST_GLOBAL_SUCCESS_FORBIDDEN_FIELDS,
    )
    if forbidden_fields:
        raise ValueError(
            f"{fields_path} includes forbidden fields: "
            f"{', '.join(forbidden_fields)}"
        )

    return success_fields


def _require_cli_contract_manifest_case_fields(
    contract: dict[str, Any],
    *,
    case_name: str,
    contract_path: str,
    field_name: str,
    expected_fields_by_case: dict[str, Sequence[str]],
) -> tuple[list[str], str]:
    fields = _require_cli_contract_exact_case_fields(
        contract.get(field_name),
        expected_fields_by_case,
        case_name=case_name,
        field_name=field_name,
        path=contract_path,
    )
    fields_path = _field_path(contract_path, field_name)

    return fields, fields_path


def _validate_cli_contract_manifest_failure_fields(
    contract: dict[str, Any],
    *,
    case_name: str,
    contract_path: str,
) -> list[str]:
    failure_fields, fields_path = _require_cli_contract_manifest_case_fields(
        contract,
        case_name=case_name,
        contract_path=contract_path,
        field_name="failure_required_fields",
        expected_fields_by_case=CLI_CONTRACT_MANIFEST_FAILURE_FIELDS_BY_CASE,
    )
    missing_fields = _missing_values(
        CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS,
        failure_fields,
    )
    if missing_fields:
        raise ValueError(
            f"{fields_path} missing values: {', '.join(missing_fields)}"
        )

    return failure_fields


def build_cli_contract_manifest_fingerprint(
    contracts: list[dict[str, Any]],
    excluded_external_actions: list[str],
) -> str:
    fingerprint_payload = _build_cli_contract_manifest_fingerprint_payload(
        contracts,
        excluded_external_actions,
    )
    canonical_payload = json.dumps(
        fingerprint_payload,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _build_cli_contract_manifest_fingerprint_payload(
    contracts: list[dict[str, Any]],
    excluded_external_actions: list[str],
) -> dict[str, Any]:
    return {
        "stdout_json_contract": _build_cli_contract_stdout_fingerprint_payload(),
        "external_actions_excluded": excluded_external_actions,
        "cli_contracts": [
            _build_cli_contract_entry_fingerprint_payload(contract)
            for contract in contracts
        ],
    }


def _build_cli_contract_stdout_fingerprint_payload() -> dict[str, Any]:
    return {
        "success": _build_cli_contract_stdout_success_fingerprint_payload(),
        "handled_failure": _build_cli_contract_stdout_failure_fingerprint_payload(),
    }


def _build_cli_contract_stdout_success_fingerprint_payload() -> dict[str, Any]:
    return {
        "exit_code": 0,
        "status": "passed",
        "forbidden_fields": list(
            CLI_CONTRACT_MANIFEST_GLOBAL_SUCCESS_FORBIDDEN_FIELDS
        ),
    }


def _build_cli_contract_stdout_failure_fingerprint_payload() -> dict[str, Any]:
    return {
        "exit_code": 1,
        "status": "failed",
        "required_fields": list(
            CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS
        ),
    }


def _build_cli_contract_entry_fingerprint_payload(
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "case_name": contract["case_name"],
        "script": contract["script"],
        "success_required_fields": contract["success_required_fields"],
        "failure_required_fields": contract["failure_required_fields"],
    }


def _validate_cli_contract_manifest_stdout_contract(
    manifest: dict[str, Any],
) -> None:
    stdout_contract_path = "manifest.stdout_json_contract"
    stdout_contract = _require_mapping(
        manifest.get("stdout_json_contract"),
        stdout_contract_path,
    )
    _require_exact_mapping_fields(
        stdout_contract,
        CLI_CONTRACT_MANIFEST_STDOUT_CONTRACT_FIELDS,
        stdout_contract_path,
    )
    success, success_path = _require_stdout_contract_section(
        stdout_contract,
        "success",
    )
    handled_failure, handled_failure_path = _require_stdout_contract_section(
        stdout_contract,
        "handled_failure",
    )
    _validate_cli_contract_manifest_stdout_success(success, success_path)
    _validate_cli_contract_manifest_stdout_failure(
        handled_failure,
        handled_failure_path,
    )


def _require_stdout_contract_section(
    stdout_contract: dict[str, Any],
    field: str,
) -> tuple[dict[str, Any], str]:
    section_path = _stdout_contract_field_path(field)
    section = _require_mapping(stdout_contract.get(field), section_path)

    return section, section_path


def _validate_cli_contract_manifest_stdout_success(
    success: dict[str, Any],
    success_path: str,
) -> None:
    _require_exact_mapping_fields(
        success,
        CLI_CONTRACT_MANIFEST_STDOUT_SUCCESS_FIELDS,
        success_path,
    )
    _require_stdout_contract_outcome(
        success,
        exit_code=0,
        status="passed",
        path=success_path,
    )
    _require_cli_contract_exact_string_list(
        success.get("forbidden_fields"),
        CLI_CONTRACT_MANIFEST_GLOBAL_SUCCESS_FORBIDDEN_FIELDS,
        _field_path(success_path, "forbidden_fields"),
    )


def _validate_cli_contract_manifest_stdout_failure(
    handled_failure: dict[str, Any],
    handled_failure_path: str,
) -> None:
    _require_exact_mapping_fields(
        handled_failure,
        CLI_CONTRACT_MANIFEST_STDOUT_FAILURE_FIELDS,
        handled_failure_path,
    )
    _require_stdout_contract_outcome(
        handled_failure,
        exit_code=1,
        status="failed",
        path=handled_failure_path,
    )
    _require_cli_contract_exact_string_list(
        handled_failure.get("required_fields"),
        CLI_CONTRACT_MANIFEST_GLOBAL_FAILURE_FIELDS,
        _field_path(handled_failure_path, "required_fields"),
    )


def _stdout_contract_field_path(field: str) -> str:
    return f"manifest.stdout_json_contract.{field}"


def _require_stdout_contract_outcome(
    section: dict[str, Any],
    *,
    exit_code: int,
    status: str,
    path: str,
) -> None:
    _require_cli_contract_value(section, "exit_code", exit_code, path)
    _require_cli_contract_value(section, "status", status, path)


def _require_cli_contract_exact_string_list(
    value: Any,
    expected_values: Sequence[str],
    path: str,
) -> list[str]:
    string_items = _require_non_empty_string_list(value, path)
    _require_unique_values(string_items, path)

    _require_exact_ordered_values(
        string_items,
        expected_values,
        path=path,
    )
    return string_items


def _require_cli_contract_exact_case_fields(
    value: Any,
    expected_fields_by_case: dict[str, Sequence[str]],
    *,
    case_name: str,
    field_name: str,
    path: str,
) -> list[str]:
    field_path = _field_path(path, field_name)
    expected_case_fields = expected_fields_by_case.get(case_name)
    if expected_case_fields is None:
        raise ValueError(
            f"{field_path} has no exact field contract for case_name {case_name!r}"
        )

    return _require_cli_contract_exact_string_list(
        value,
        expected_case_fields,
        field_path,
    )


def _require_cli_contract_value(
    mapping: dict[str, Any],
    key: str,
    contract_value: Any,
    path: str,
) -> None:
    field_path = _field_path(path, key)

    if mapping.get(key) != contract_value:
        raise ValueError(f"{field_path} must be {contract_value!r}")


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


def write_package_artifacts(
    package_doc: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    package = validate_package_document(package_doc)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_artifacts: dict[str, Any] = {
        DECISION_PACKAGE_NAME: package_doc,
    }
    for artifact_name, package_field in JSON_ARTIFACT_PACKAGE_FIELDS.items():
        json_artifacts[artifact_name] = package[package_field]
    for artifact_name, artifact_data in json_artifacts.items():
        write_json_atomic(output_dir / artifact_name, artifact_data)

    markdown_artifacts = {
        DECISION_SUMMARY_NAME: _render_decision_summary(package),
        EVIDENCE_SUMMARY_NAME: _render_evidence_summary(package),
        BID_READINESS_CHECKLIST_NAME: _render_bid_readiness_checklist(package),
        SIGNOFF_SUMMARY_NAME: _render_signoff_summary(package),
    }
    for artifact_name, artifact_text in markdown_artifacts.items():
        write_text_atomic(output_dir / artifact_name, artifact_text.rstrip() + "\n")

    return {
        "schema_purpose": package_doc["schema_purpose"],
        "status": "passed",
        "output_dir": str(output_dir),
        "artifacts": list(INCLUDED_ARTIFACT_ORDER),
        "recommendation": package["recommendation"],
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
    }


def build_and_write(*, sample_input_path: Path, output_dir: Path) -> dict[str, Any]:
    sample_input = load_json(sample_input_path)
    package_doc = build_decision_package(sample_input)
    validate_expected_package_for_sample(package_doc, sample_input=sample_input)
    return write_package_artifacts(package_doc, output_dir)
