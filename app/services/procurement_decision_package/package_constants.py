"""Package, artifact, and local demo constants for procurement decisions."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, NamedTuple


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
PROCUREMENT_REVIEW_NAME = "procurement_review.html"
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
    PROCUREMENT_REVIEW_NAME,
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
        PROCUREMENT_REVIEW_NAME,
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
_SYSTEM_TEMP_DIR = Path(tempfile.gettempdir())
DEFAULT_DEMO_DATA_DIR = _SYSTEM_TEMP_DIR / "decisiondoc-procurement-package-demo-data"
DEFAULT_DEMO_OUT_DIR = _SYSTEM_TEMP_DIR / "decisiondoc-procurement-package-demo-output"
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
