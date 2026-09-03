"""Same-backend, hash-only issuance proof for canonical H128 receipts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any

from pydantic import ValidationError

from app.schemas.decision_evidence import (
    DecisionEvidenceBundleType,
    GuidedDecisionReviewDispositionIssuanceMetadata,
)
from app.services.decision_evidence.common import canonical_json
from app.storage.state_backend import StateBackend, StateBackendError


GUIDED_DECISION_REVIEW_DISPOSITION_ISSUANCE_CONTRACT_VERSION = (
    "guided-decision-review-disposition-issuance.v1"
)
_BUNDLE_TYPES = {
    "bid_decision_kr",
    "rfp_analysis_kr",
    "proposal_kr",
    "performance_plan_kr",
}
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_METADATA_FIELDS = set(GuidedDecisionReviewDispositionIssuanceMetadata.model_fields)


class GuidedDecisionReviewDispositionIssuanceRegistryError(RuntimeError):
    """Raised when H128 issuance provenance cannot be proven."""


class GuidedDecisionReviewDispositionIssuanceRegistryConflictError(
    GuidedDecisionReviewDispositionIssuanceRegistryError
):
    """Raised when a content-addressed issuance object has another binding."""


class GuidedDecisionReviewDispositionIssuanceRegistryValidationError(
    GuidedDecisionReviewDispositionIssuanceRegistryError
):
    """Raised when a caller supplies an invalid issuance scope or hash."""


def canonical_guided_review_issuance_json_bytes(value: object) -> bytes:
    """Return the only persisted representation accepted for H128 issuance."""
    return (canonical_json(value) + "\n").encode("utf-8")


def guided_review_issuance_sha256(value: object) -> str:
    return hashlib.sha256(canonical_guided_review_issuance_json_bytes(value)).hexdigest()


class GuidedDecisionReviewDispositionIssuanceRegistry:
    """Create and exact-read-back one immutable proof per H128 body hash."""

    def __init__(
        self,
        *,
        tenant_id: str,
        project_id: str,
        bundle_type: DecisionEvidenceBundleType | str,
        backend: StateBackend,
    ) -> None:
        self.tenant_id = _require_scope_component(tenant_id, field="tenant_id")
        self.project_id = _require_scope_component(project_id, field="project_id")
        self.bundle_type = _require_bundle_type(bundle_type)
        self.backend = backend

    @property
    def prefix(self) -> str:
        return (
            f"tenants/{self.tenant_id}/projects/{self.project_id}/"
            f"guided_decision_review_disposition_issuances/{self.bundle_type}"
        )

    def record_path(self, disposition_receipt_sha256: str) -> str:
        receipt_hash = _require_sha256(
            disposition_receipt_sha256,
            field="disposition_receipt_sha256",
        )
        return f"{self.prefix}/{receipt_hash}.json"

    def create(
        self,
        *,
        disposition_receipt_sha256: object,
    ) -> tuple[dict[str, Any], bool]:
        """Conditionally create then prove the authoritative canonical record."""
        try:
            receipt_hash = _require_sha256(
                disposition_receipt_sha256,
                field="disposition_receipt_sha256",
            )
        except GuidedDecisionReviewDispositionIssuanceRegistryError as exc:
            raise GuidedDecisionReviewDispositionIssuanceRegistryValidationError(
                "Guided review disposition issuance hash is invalid"
            ) from exc

        binding = self._issuance_binding_sha256(receipt_hash)
        metadata = self._build_metadata(
            disposition_receipt_sha256=receipt_hash,
            issuance_binding_sha256=binding,
        )
        raw = canonical_guided_review_issuance_json_bytes(metadata)
        path = self.record_path(receipt_hash)
        try:
            created = self.backend.write_bytes_if_absent(
                path,
                raw,
                content_type="application/json; charset=utf-8",
            )
        except StateBackendError:
            return self._reconcile_after_uncertain_write(
                disposition_receipt_sha256=receipt_hash,
                issuance_binding_sha256=binding,
            )

        try:
            stored, stored_raw = self._read_required(receipt_hash)
        except KeyError as exc:
            raise GuidedDecisionReviewDispositionIssuanceRegistryError(
                "H128 issuance exact read-back is unavailable"
            ) from exc
        if stored["issuance_binding_sha256"] != binding:
            raise GuidedDecisionReviewDispositionIssuanceRegistryConflictError(
                "H128 issuance record has another binding"
            )
        if created and stored_raw != raw:
            raise GuidedDecisionReviewDispositionIssuanceRegistryError(
                "Created H128 issuance record does not match exact read-back bytes"
            )
        return stored, created

    def read(self, disposition_receipt_sha256: str) -> dict[str, Any]:
        metadata, _ = self._read_required(disposition_receipt_sha256)
        return metadata

    def read_canonical(
        self,
        disposition_receipt_sha256: str,
    ) -> tuple[dict[str, Any], bytes]:
        return self._read_required(disposition_receipt_sha256)

    def _read_required(
        self,
        disposition_receipt_sha256: str,
    ) -> tuple[dict[str, Any], bytes]:
        receipt_hash = _require_sha256(
            disposition_receipt_sha256,
            field="disposition_receipt_sha256",
        )
        path = self.record_path(receipt_hash)
        try:
            raw = self.backend.read_bytes(path)
        except StateBackendError as exc:
            raise GuidedDecisionReviewDispositionIssuanceRegistryError(
                "H128 issuance registry is unavailable"
            ) from exc
        if raw is None:
            raise KeyError(path)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise GuidedDecisionReviewDispositionIssuanceRegistryError(
                "Corrupt H128 issuance record"
            ) from exc
        if canonical_guided_review_issuance_json_bytes(value) != raw:
            raise GuidedDecisionReviewDispositionIssuanceRegistryError(
                "H128 issuance record is not canonical JSON"
            )
        try:
            metadata = _validate_metadata(
                value,
                expected_tenant_id=self.tenant_id,
                expected_project_id=self.project_id,
                expected_bundle_type=self.bundle_type,
                expected_disposition_receipt_sha256=receipt_hash,
            )
        except (GuidedDecisionReviewDispositionIssuanceRegistryError, ValueError) as exc:
            raise GuidedDecisionReviewDispositionIssuanceRegistryError(
                "Corrupt H128 issuance record"
            ) from exc
        return metadata, raw

    def _reconcile_after_uncertain_write(
        self,
        *,
        disposition_receipt_sha256: str,
        issuance_binding_sha256: str,
    ) -> tuple[dict[str, Any], bool]:
        try:
            metadata, _ = self._read_required(disposition_receipt_sha256)
        except KeyError as exc:
            raise GuidedDecisionReviewDispositionIssuanceRegistryError(
                "H128 issuance create outcome is unavailable"
            ) from exc
        if metadata["issuance_binding_sha256"] != issuance_binding_sha256:
            raise GuidedDecisionReviewDispositionIssuanceRegistryConflictError(
                "H128 issuance record has another binding"
            )
        return metadata, False

    def _issuance_binding_sha256(self, disposition_receipt_sha256: str) -> str:
        return guided_review_issuance_sha256(
            {
                "contract_version": (
                    GUIDED_DECISION_REVIEW_DISPOSITION_ISSUANCE_CONTRACT_VERSION
                ),
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "bundle_type": self.bundle_type,
                "disposition_receipt_sha256": disposition_receipt_sha256,
            }
        )

    def _build_metadata(
        self,
        *,
        disposition_receipt_sha256: str,
        issuance_binding_sha256: str,
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "contract_version": (
                GUIDED_DECISION_REVIEW_DISPOSITION_ISSUANCE_CONTRACT_VERSION
            ),
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "bundle_type": self.bundle_type,
            "disposition_receipt_sha256": disposition_receipt_sha256,
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "issuance_binding_sha256": issuance_binding_sha256,
            "issuance_status": "issued",
            "evidence_only": True,
            "review_state_only": True,
            "review_only": True,
            "read_only": True,
            "reviewer_identity_bound": False,
            "snapshot_atomic": False,
            "requires_recheck_before_reliance": True,
            "disposition_receipt_persisted": False,
            "authority": {
                "mutation": False,
                "approval": False,
                "export_execution": False,
                "provider_call": False,
                "bid_submission": False,
                "legal_contractual_commitment": False,
            },
        }
        metadata["issuance_record_binding_sha256"] = guided_review_issuance_sha256(
            metadata
        )
        return metadata


def _validate_metadata(
    value: object,
    *,
    expected_tenant_id: str,
    expected_project_id: str,
    expected_bundle_type: str,
    expected_disposition_receipt_sha256: str,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _METADATA_FIELDS:
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            "Invalid H128 issuance record"
        )
    try:
        parsed = GuidedDecisionReviewDispositionIssuanceMetadata.model_validate(
            value,
            strict=True,
        )
    except ValidationError as exc:
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            "Invalid H128 issuance record"
        ) from exc
    if (
        parsed.tenant_id != expected_tenant_id
        or parsed.project_id != expected_project_id
        or parsed.bundle_type != expected_bundle_type
        or parsed.disposition_receipt_sha256
        != expected_disposition_receipt_sha256
    ):
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            "H128 issuance record scope identity drift"
        )
    _require_utc_timestamp(parsed.issued_at)
    binding = {
        "contract_version": GUIDED_DECISION_REVIEW_DISPOSITION_ISSUANCE_CONTRACT_VERSION,
        "tenant_id": expected_tenant_id,
        "project_id": expected_project_id,
        "bundle_type": expected_bundle_type,
        "disposition_receipt_sha256": expected_disposition_receipt_sha256,
    }
    if parsed.issuance_binding_sha256 != guided_review_issuance_sha256(binding):
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            "Invalid H128 issuance binding"
        )
    record_binding = {
        field: field_value
        for field, field_value in value.items()
        if field != "issuance_record_binding_sha256"
    }
    if parsed.issuance_record_binding_sha256 != guided_review_issuance_sha256(
        record_binding
    ):
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            "Invalid H128 issuance record binding"
        )
    return value


def _require_scope_component(value: object, *, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            f"Invalid {field}"
        )
    if value != value.strip() or "/" in value or "\\" in value:
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            f"Invalid {field}"
        )
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            f"Invalid {field}"
        )
    return value


def _require_bundle_type(value: object) -> str:
    if type(value) is not str or value not in _BUNDLE_TYPES:
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            "Invalid bundle_type"
        )
    return value


def _require_sha256(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256_PATTERN.fullmatch(value):
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(f"Invalid {field}")
    return value


def _require_utc_timestamp(value: object) -> str:
    if type(value) is not str:
        raise GuidedDecisionReviewDispositionIssuanceRegistryError("Invalid issued_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            "Invalid issued_at"
        ) from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timedelta(0)
        or parsed.isoformat() != value
    ):
        raise GuidedDecisionReviewDispositionIssuanceRegistryError(
            "issued_at must be canonical UTC"
        )
    return value


def get_guided_decision_review_disposition_issuance_registry(
    *,
    tenant_id: str,
    project_id: str,
    bundle_type: DecisionEvidenceBundleType | str,
    backend: StateBackend,
) -> GuidedDecisionReviewDispositionIssuanceRegistry:
    return GuidedDecisionReviewDispositionIssuanceRegistry(
        tenant_id=tenant_id,
        project_id=project_id,
        bundle_type=bundle_type,
        backend=backend,
    )
