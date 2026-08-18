"""Immutable reviewer-bound records for H128 guided-review dispositions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from app.schemas.decision_evidence import (
    DecisionEvidenceBundleType,
    GuidedDecisionReviewDispositionReceipt,
    GuidedDecisionReviewDispositionRecord,
    require_complete_guided_decision_review_disposition_receipt,
)
from app.services.decision_evidence.common import canonical_json
from app.services.guided_decision_review_service import GuidedDecisionReviewService
from app.storage.state_backend import StateBackend, StateBackendError


GUIDED_DECISION_REVIEW_DISPOSITION_RECORD_CONTRACT_VERSION = (
    "guided-decision-review-disposition-record.v1"
)
_BUNDLE_TYPES = {
    "bid_decision_kr",
    "rfp_analysis_kr",
    "proposal_kr",
    "performance_plan_kr",
}
_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_RECORD_NAME_PATTERN = re.compile(r"^[a-f0-9]{64}\.json$")
_RECORD_FIELDS = set(GuidedDecisionReviewDispositionRecord.model_fields)


class GuidedDecisionReviewDispositionRegistryError(RuntimeError):
    """Raised when immutable H129 registry state cannot be trusted."""


class GuidedDecisionReviewDispositionRegistryConflictError(
    GuidedDecisionReviewDispositionRegistryError
):
    """Raised when an operation ID is rebound to another stable request."""


class GuidedDecisionReviewDispositionRegistryValidationError(
    GuidedDecisionReviewDispositionRegistryError
):
    """Raised when a caller supplies an invalid H129 create request."""


def canonical_guided_review_registry_json_bytes(value: object) -> bytes:
    """Return the canonical JSON representation used by H129 records."""
    return (canonical_json(value) + "\n").encode("utf-8")


def guided_review_registry_sha256(value: object) -> str:
    return hashlib.sha256(canonical_guided_review_registry_json_bytes(value)).hexdigest()


class GuidedDecisionReviewDispositionRegistry:
    """Store one canonical H129 record per tenant/project/bundle operation."""

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
        self._service = GuidedDecisionReviewService()

    @property
    def prefix(self) -> str:
        return (
            f"tenants/{self.tenant_id}/projects/{self.project_id}/"
            f"guided_decision_review_dispositions/{self.bundle_type}"
        )

    def record_path(self, operation_id: str) -> str:
        operation_id = _require_operation_id(operation_id)
        filename = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        return f"{self.prefix}/{filename}.json"

    def create(
        self,
        *,
        operation_id: str,
        reviewer_user_id: str,
        reviewer_username: str,
        reviewer_role: str,
        source_disposition_receipt: object,
        source_disposition_receipt_sha256: object,
    ) -> tuple[dict[str, Any], bool]:
        """Create once or return the exact authoritative replay record."""
        try:
            operation_id = _require_operation_id(operation_id)
            reviewer_user_id = _require_non_empty_string(
                reviewer_user_id,
                field="reviewer_user_id",
            )
            reviewer_username = _require_non_empty_string(
                reviewer_username,
                field="reviewer_username",
            )
            reviewer_role = _require_reviewer_role(reviewer_role)
            source_hash = _require_sha256(
                source_disposition_receipt_sha256,
                field="source_disposition_receipt_sha256",
            )
            source = _parse_source_receipt(source_disposition_receipt)
            source = self._service.validate_disposition_receipt(
                source,
                expected_sha256=source_hash,
                expected_project_id=self.project_id,
                expected_bundle_type=self.bundle_type,
            )
        except (GuidedDecisionReviewDispositionRegistryError, ValueError) as exc:
            raise GuidedDecisionReviewDispositionRegistryValidationError(
                "Guided review disposition receipt is invalid"
            ) from exc

        request_binding_sha256 = self._request_binding_sha256(
            operation_id=operation_id,
            reviewer_user_id=reviewer_user_id,
            source_disposition_receipt_sha256=source_hash,
        )
        record = self._build_record(
            operation_id=operation_id,
            request_binding_sha256=request_binding_sha256,
            reviewer_user_id=reviewer_user_id,
            reviewer_username=reviewer_username,
            reviewer_role=reviewer_role,
            source=source,
            source_hash=source_hash,
        )
        raw = canonical_guided_review_registry_json_bytes(record)
        path = self.record_path(operation_id)
        try:
            created = self.backend.write_bytes_if_absent(
                path,
                raw,
                content_type="application/json; charset=utf-8",
            )
        except StateBackendError:
            return self._reconcile_after_uncertain_write(
                operation_id=operation_id,
                request_binding_sha256=request_binding_sha256,
            )

        stored, stored_raw = self._read_required(operation_id)
        if stored["request_binding_sha256"] != request_binding_sha256:
            raise GuidedDecisionReviewDispositionRegistryConflictError(
                "Operation ID is already bound to another guided review disposition"
            )
        if created and stored_raw != raw:
            raise GuidedDecisionReviewDispositionRegistryError(
                "Created guided review disposition record does not match read-back bytes"
            )
        return stored, created

    def read(
        self,
        operation_id: str,
        *,
        reviewer_user_id: str | None = None,
    ) -> dict[str, Any]:
        record, _ = self._read_required(operation_id)
        self._require_visible_owner(record, reviewer_user_id=reviewer_user_id)
        return record

    def read_canonical(
        self,
        operation_id: str,
        *,
        reviewer_user_id: str | None = None,
    ) -> tuple[dict[str, Any], bytes]:
        record, raw = self._read_required(operation_id)
        self._require_visible_owner(record, reviewer_user_id=reviewer_user_id)
        return record, raw

    def list_summaries(
        self,
        *,
        reviewer_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        try:
            paths = self.backend.list_prefix(self.prefix)
        except StateBackendError as exc:
            raise GuidedDecisionReviewDispositionRegistryError(
                "Guided review disposition registry is unavailable"
            ) from exc
        if len(paths) != len(set(paths)):
            raise GuidedDecisionReviewDispositionRegistryError(
                "Duplicate registry object path"
            )

        records: list[dict[str, Any]] = []
        operation_ids: set[str] = set()
        prefix = f"{self.prefix}/"
        for path in paths:
            if not isinstance(path, str) or not path.startswith(prefix):
                raise GuidedDecisionReviewDispositionRegistryError(
                    "Unexpected registry object path"
                )
            name = path.removeprefix(prefix)
            if "/" in name or not _RECORD_NAME_PATTERN.fullmatch(name):
                raise GuidedDecisionReviewDispositionRegistryError(
                    "Unexpected registry object path"
                )
            try:
                record, _ = self._read_path(path, expected_operation_id=None)
            except KeyError as exc:
                raise GuidedDecisionReviewDispositionRegistryError(
                    "Guided review disposition registry changed during list"
                ) from exc
            if (
                path != self.record_path(record["operation_id"])
                or record["operation_id"] in operation_ids
            ):
                raise GuidedDecisionReviewDispositionRegistryError(
                    "Registry record path identity drift"
                )
            operation_ids.add(record["operation_id"])
            records.append(record)

        records.sort(
            key=lambda record: (record["recorded_at"], record["operation_id"]),
            reverse=True,
        )
        return [
            self._summary(record)
            for record in records
            if reviewer_user_id is None
            or record["reviewer_user_id"] == reviewer_user_id
        ]

    def _read_required(self, operation_id: str) -> tuple[dict[str, Any], bytes]:
        operation_id = _require_operation_id(operation_id)
        return self._read_path(
            self.record_path(operation_id),
            expected_operation_id=operation_id,
        )

    def _read_path(
        self,
        path: str,
        *,
        expected_operation_id: str | None,
    ) -> tuple[dict[str, Any], bytes]:
        try:
            raw = self.backend.read_bytes(path)
        except StateBackendError as exc:
            raise GuidedDecisionReviewDispositionRegistryError(
                "Guided review disposition registry is unavailable"
            ) from exc
        if raw is None:
            raise KeyError(path)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, TypeError, ValueError) as exc:
            raise GuidedDecisionReviewDispositionRegistryError(
                "Corrupt guided review disposition record"
            ) from exc
        if canonical_guided_review_registry_json_bytes(value) != raw:
            raise GuidedDecisionReviewDispositionRegistryError(
                "Guided review disposition record is not canonical JSON"
            )
        try:
            record = _validate_record(
                value,
                expected_tenant_id=self.tenant_id,
                expected_project_id=self.project_id,
                expected_bundle_type=self.bundle_type,
                expected_operation_id=expected_operation_id,
                service=self._service,
            )
        except (GuidedDecisionReviewDispositionRegistryError, ValueError) as exc:
            raise GuidedDecisionReviewDispositionRegistryError(
                "Corrupt guided review disposition record"
            ) from exc
        return record, raw

    def _reconcile_after_uncertain_write(
        self,
        *,
        operation_id: str,
        request_binding_sha256: str,
    ) -> tuple[dict[str, Any], bool]:
        try:
            record, _ = self._read_required(operation_id)
        except KeyError as exc:
            raise GuidedDecisionReviewDispositionRegistryError(
                "Guided review disposition create outcome is unavailable"
            ) from exc
        if record["request_binding_sha256"] != request_binding_sha256:
            raise GuidedDecisionReviewDispositionRegistryConflictError(
                "Operation ID is already bound to another guided review disposition"
            )
        return record, False

    def _request_binding_sha256(
        self,
        *,
        operation_id: str,
        reviewer_user_id: str,
        source_disposition_receipt_sha256: str,
    ) -> str:
        return guided_review_registry_sha256(
            {
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "bundle_type": self.bundle_type,
                "operation_id": operation_id,
                "reviewer_user_id": reviewer_user_id,
                "source_disposition_receipt_sha256": (
                    source_disposition_receipt_sha256
                ),
            }
        )

    def _build_record(
        self,
        *,
        operation_id: str,
        request_binding_sha256: str,
        reviewer_user_id: str,
        reviewer_username: str,
        reviewer_role: str,
        source: GuidedDecisionReviewDispositionReceipt,
        source_hash: str,
    ) -> dict[str, Any]:
        source_value = source.model_dump(mode="json")
        record: dict[str, Any] = {
            "contract_version": (
                GUIDED_DECISION_REVIEW_DISPOSITION_RECORD_CONTRACT_VERSION
            ),
            "operation_id": operation_id,
            "request_binding_sha256": request_binding_sha256,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "bundle_type": self.bundle_type,
            "reviewer_user_id": reviewer_user_id,
            "reviewer_username": reviewer_username,
            "reviewer_role": reviewer_role,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "source_disposition_receipt": source_value,
            "source_disposition_receipt_sha256": source_hash,
            "source_recheck_receipt_sha256": source.source_recheck_receipt_sha256,
            "current_handoff_sha256": source.current_handoff_sha256,
            "current_review_state_fingerprint_sha256": (
                source.current_review_state_fingerprint_sha256
            ),
            "review_state_status": source.review_state_status,
            "review_disposition": source.review_disposition,
            "disposition_binding_sha256": source.disposition_binding_sha256,
            "record_status": "recorded",
            "review_state_only": True,
            "review_only": True,
            "read_only": True,
            "reviewer_identity_bound": True,
            "registry_record_persisted": True,
            "snapshot_atomic": False,
            "requires_recheck_before_reliance": True,
            "authority": source.authority.model_dump(mode="json"),
        }
        record["record_binding_sha256"] = guided_review_registry_sha256(record)
        return record

    @staticmethod
    def _require_visible_owner(
        record: dict[str, Any],
        *,
        reviewer_user_id: str | None,
    ) -> None:
        if (
            reviewer_user_id is not None
            and record["reviewer_user_id"] != reviewer_user_id
        ):
            raise KeyError(record["operation_id"])

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "contract_version": record["contract_version"],
            "operation_id": record["operation_id"],
            "tenant_id": record["tenant_id"],
            "project_id": record["project_id"],
            "bundle_type": record["bundle_type"],
            "reviewer_username": record["reviewer_username"],
            "reviewer_role": record["reviewer_role"],
            "recorded_at": record["recorded_at"],
            "record_sha256": guided_review_registry_sha256(record),
            "source_disposition_receipt_sha256": record[
                "source_disposition_receipt_sha256"
            ],
            "source_recheck_receipt_sha256": record[
                "source_recheck_receipt_sha256"
            ],
            "current_handoff_sha256": record["current_handoff_sha256"],
            "current_review_state_fingerprint_sha256": record[
                "current_review_state_fingerprint_sha256"
            ],
            "review_state_status": record["review_state_status"],
            "review_disposition": record["review_disposition"],
            "disposition_binding_sha256": record[
                "disposition_binding_sha256"
            ],
            "record_status": record["record_status"],
            "review_state_only": True,
            "review_only": True,
            "read_only": True,
            "reviewer_identity_bound": True,
            "registry_record_persisted": True,
            "snapshot_atomic": False,
            "requires_recheck_before_reliance": True,
            "authority": record["authority"],
        }


def _parse_source_receipt(value: object) -> GuidedDecisionReviewDispositionReceipt:
    if isinstance(value, GuidedDecisionReviewDispositionReceipt):
        require_complete_guided_decision_review_disposition_receipt(value)
        return value
    try:
        return GuidedDecisionReviewDispositionReceipt.model_validate(value, strict=True)
    except ValidationError as exc:
        raise GuidedDecisionReviewDispositionRegistryError(
            "Invalid source disposition receipt"
        ) from exc


def _validate_record(
    value: object,
    *,
    expected_tenant_id: str,
    expected_project_id: str,
    expected_bundle_type: str,
    expected_operation_id: str | None,
    service: GuidedDecisionReviewService,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _RECORD_FIELDS:
        raise GuidedDecisionReviewDispositionRegistryError(
            "Invalid guided review disposition record"
        )
    record = value
    try:
        parsed = GuidedDecisionReviewDispositionRecord.model_validate(
            record,
            strict=True,
        )
    except ValidationError as exc:
        raise GuidedDecisionReviewDispositionRegistryError(
            "Invalid guided review disposition record"
        ) from exc
    operation_id = _require_operation_id(parsed.operation_id)
    if expected_operation_id is not None and operation_id != expected_operation_id:
        raise GuidedDecisionReviewDispositionRegistryError(
            "Registry record operation identity drift"
        )
    if (
        parsed.tenant_id != expected_tenant_id
        or parsed.project_id != expected_project_id
        or parsed.bundle_type != expected_bundle_type
    ):
        raise GuidedDecisionReviewDispositionRegistryError(
            "Registry record scope identity drift"
        )
    _require_non_empty_string(parsed.reviewer_user_id, field="reviewer_user_id")
    _require_non_empty_string(parsed.reviewer_username, field="reviewer_username")
    _require_utc_timestamp(parsed.recorded_at)
    record_binding = {
        field: field_value
        for field, field_value in record.items()
        if field != "record_binding_sha256"
    }
    if parsed.record_binding_sha256 != guided_review_registry_sha256(record_binding):
        raise GuidedDecisionReviewDispositionRegistryError(
            "Invalid registry record binding"
        )
    source = service.validate_disposition_receipt(
        parsed.source_disposition_receipt,
        expected_sha256=parsed.source_disposition_receipt_sha256,
        expected_project_id=expected_project_id,
        expected_bundle_type=expected_bundle_type,
    )
    expected_request_binding = guided_review_registry_sha256(
        {
            "tenant_id": expected_tenant_id,
            "project_id": expected_project_id,
            "bundle_type": expected_bundle_type,
            "operation_id": operation_id,
            "reviewer_user_id": parsed.reviewer_user_id,
            "source_disposition_receipt_sha256": (
                parsed.source_disposition_receipt_sha256
            ),
        }
    )
    if parsed.request_binding_sha256 != expected_request_binding:
        raise GuidedDecisionReviewDispositionRegistryError(
            "Invalid registry request binding"
        )
    projected_fields = (
        "source_recheck_receipt_sha256",
        "current_handoff_sha256",
        "current_review_state_fingerprint_sha256",
        "review_state_status",
        "review_disposition",
        "disposition_binding_sha256",
    )
    source_value = source.model_dump(mode="json")
    if any(record[field] != source_value[field] for field in projected_fields):
        raise GuidedDecisionReviewDispositionRegistryError(
            "Invalid registry source projection"
        )
    return record


def _require_scope_component(value: object, *, field: str) -> str:
    value = _require_non_empty_string(value, field=field)
    if value != value.strip() or "/" in value or "\\" in value:
        raise GuidedDecisionReviewDispositionRegistryError(f"Invalid {field}")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise GuidedDecisionReviewDispositionRegistryError(f"Invalid {field}")
    return value


def _require_bundle_type(value: object) -> str:
    if type(value) is not str or value not in _BUNDLE_TYPES:
        raise GuidedDecisionReviewDispositionRegistryError("Invalid bundle_type")
    return value


def _require_operation_id(value: object) -> str:
    if type(value) is not str:
        raise GuidedDecisionReviewDispositionRegistryError("Invalid operation ID")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise GuidedDecisionReviewDispositionRegistryError(
            "Invalid operation ID"
        ) from exc
    if parsed.version != 4 or str(parsed) != value:
        raise GuidedDecisionReviewDispositionRegistryError("Invalid operation ID")
    return value


def _require_non_empty_string(value: object, *, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise GuidedDecisionReviewDispositionRegistryError(f"Invalid {field}")
    return value


def _require_reviewer_role(value: object) -> str:
    if type(value) is not str or value not in {"admin", "member"}:
        raise GuidedDecisionReviewDispositionRegistryError(
            "Reviewer role must be admin or member"
        )
    return value


def _require_sha256(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256_PATTERN.fullmatch(value):
        raise GuidedDecisionReviewDispositionRegistryError(f"Invalid {field}")
    return value


def _require_utc_timestamp(value: object) -> str:
    if type(value) is not str:
        raise GuidedDecisionReviewDispositionRegistryError("Invalid recorded_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise GuidedDecisionReviewDispositionRegistryError(
            "Invalid recorded_at"
        ) from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timedelta(0)
        or parsed.isoformat() != value
    ):
        raise GuidedDecisionReviewDispositionRegistryError(
            "recorded_at must be canonical UTC"
        )
    return value


def get_guided_decision_review_disposition_registry(
    *,
    tenant_id: str,
    project_id: str,
    bundle_type: DecisionEvidenceBundleType | str,
    backend: StateBackend,
) -> GuidedDecisionReviewDispositionRegistry:
    return GuidedDecisionReviewDispositionRegistry(
        tenant_id=tenant_id,
        project_id=project_id,
        bundle_type=bundle_type,
        backend=backend,
    )
