"""Shared constants for the trajectory store package: filename/id regexes and
reviewer sign-off constant sets."""
from __future__ import annotations

import re

_SIGNOFF_REQUIRED_REVIEWER_ROLES = {
    "product_pm_reviewer",
    "ml_ai_owner",
    "compliance_security_reviewer",
    "release_owner",
}
_SIGNOFF_DEFAULT_ALLOWED_DECISIONS = {
    "pending",
    "sign_off_ready_for_human_review",
    "changes_requested",
    "blocked",
}
_SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS = {
    "reviewed_phase20_handoff_for_role",
    "does_not_authorize_model_training",
    "does_not_authorize_dataset_upload",
    "does_not_authorize_provider_fine_tune_api_calls",
    "does_not_authorize_provider_job_creation_or_polling",
    "does_not_authorize_model_promotion",
    "blocking_issues_recorded_in_notes",
}
_SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS = {
    "training_execution_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
}
_SIGNOFF_PROTECTED_FALSE_GENERATION_KEYS = {
    "training_execution_started",
    "external_dataset_uploaded",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "model_promoted",
}


_SENSITIVE_KEY_PARTS = (
    "raw",
    "attachment",
    "file_bytes",
    "base64",
    "document_text",
    "source_document",
)


_EXPORT_FILENAME_RE = re.compile(r"^sft(?:_[A-Za-z0-9_-]+)?_[0-9]{8}T[0-9]{6}(?:_[a-f0-9]{8})?\.jsonl$")
_FREEZE_FILENAME_RE = re.compile(
    r"^freeze_sft(?:_[A-Za-z0-9_-]+)?_[0-9]{8}T[0-9]{6}(?:_[a-f0-9]{8})?_[0-9]{8}T[0-9]{6}_[a-f0-9]{8}\.json$"
)
_MANIFEST_ID_RE = re.compile(r"^dsf_[a-f0-9]{32}$")
_TRAINING_APPROVAL_FILENAME_RE = re.compile(r"^training_approval_dsf_[a-f0-9]{32}_[0-9]{8}T[0-9]{6}_[a-f0-9]{8}\.json$")
_TRAINING_EXECUTION_REQUEST_FILENAME_RE = re.compile(r"^training_execution_request_ter_[a-f0-9]{32}_[0-9]{8}T[0-9]{6}\.json$")
_TRAINING_AUDIT_FILENAME_RE = re.compile(r"^training_pre_execution_audit_tea_[a-f0-9]{32}_[0-9]{8}T[0-9]{6}\.json$")
