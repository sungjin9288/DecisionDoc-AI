"""Immutable reviewer identity records for H118 retention disposition receipts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any
from uuid import UUID

from app.storage.auth_session_retention import (
    AuthSessionRetentionContractError,
    RETENTION_REVIEW_DISPOSITION_RECORD_CONTRACT_VERSION,
    canonical_retention_json_bytes,
    retention_sha256,
    validate_retention_review_disposition_receipt,
)
from app.storage.state_backend import StateBackend, StateBackendError


_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_RECORD_NAME_PATTERN = re.compile(r"^[a-f0-9]{64}\.json$")
_RECORD_FIELDS = {
    "contract_version",
    "operation_id",
    "request_sha256",
    "record_binding_sha256",
    "tenant_id",
    "reviewer_user_id",
    "reviewer_username",
    "reviewer_role",
    "recorded_at",
    "source_disposition_receipt",
    "source_disposition_receipt_sha256",
    "source_recheck_receipt_sha256",
    "current_handoff_sha256",
    "current_aggregate_fingerprint_sha256",
    "selected_policy_days",
    "aggregate_status",
    "review_disposition",
    "disposition_binding_sha256",
    "record_status",
    "review_only",
    "reviewer_identity_bound",
    "registry_record_persisted",
    "approval_granted",
    "execution_authorized",
    "policy_change_authorized",
    "deletion_authorized",
    "scheduler_authorized",
    "mass_revoke_authorized",
    "snapshot_atomic",
    "requires_recheck_before_mutation",
}


class AuthSessionRetentionRegistryError(RuntimeError):
    """Raised when immutable registry state cannot be trusted."""


class AuthSessionRetentionRegistryConflictError(AuthSessionRetentionRegistryError):
    """Raised when one operation ID is reused for a different request binding."""


class AuthSessionRetentionRegistryValidationError(AuthSessionRetentionRegistryError):
    """Raised when a caller supplies an invalid immutable registry request."""


class AuthSessionRetentionRegistry:
    """Store one canonical H119 record per tenant-scoped operation ID."""

    def __init__(self, *, tenant_id: str, backend: StateBackend) -> None:
        self.tenant_id = _require_tenant_id(tenant_id)
        self.backend = backend

    @property
    def prefix(self) -> str:
        return (
            f"tenants/{self.tenant_id}/"
            "auth_session_retention_review_dispositions"
        )

    def record_path(self, operation_id: str) -> str:
        operation_id = _require_operation_id(operation_id)
        return f"{self.prefix}/{hashlib.sha256(operation_id.encode('utf-8')).hexdigest()}.json"

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
        """Create once, or return the exact prior bytes for an idempotent replay."""
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
            source_hash = _require_sha256(
                source_disposition_receipt_sha256,
                field="source_disposition_receipt_sha256",
            )
        except AuthSessionRetentionRegistryError as exc:
            raise AuthSessionRetentionRegistryValidationError(str(exc)) from exc
        if reviewer_role != "admin":
            raise AuthSessionRetentionRegistryValidationError("Reviewer role must be admin")
        try:
            source = validate_retention_review_disposition_receipt(
                source_disposition_receipt,
                expected_tenant_id=self.tenant_id,
                expected_sha256=source_hash,
            )
        except AuthSessionRetentionContractError as exc:
            raise AuthSessionRetentionRegistryValidationError(
                "Retention disposition receipt is invalid"
            ) from exc

        request_sha256 = self._request_sha256(
            operation_id=operation_id,
            reviewer_user_id=reviewer_user_id,
            source_disposition_receipt_sha256=source_hash,
        )
        record = self._build_record(
            operation_id=operation_id,
            request_sha256=request_sha256,
            reviewer_user_id=reviewer_user_id,
            reviewer_username=reviewer_username,
            source=source,
            source_hash=source_hash,
        )
        raw = canonical_retention_json_bytes(record)
        path = self.record_path(operation_id)
        try:
            created = self.backend.write_text_if_absent(path, raw.decode("utf-8"))
        except StateBackendError:
            return self._reconcile_after_uncertain_write(
                operation_id=operation_id,
                request_sha256=request_sha256,
            )

        stored, stored_raw = self._read_required(operation_id)
        if stored["request_sha256"] != request_sha256:
            raise AuthSessionRetentionRegistryConflictError(
                "Operation ID is already bound to another retention disposition"
            )
        if created and stored_raw != raw:
            raise AuthSessionRetentionRegistryError(
                "Created retention disposition record does not match read-back bytes"
            )
        return stored, created

    def read(self, operation_id: str) -> dict[str, Any]:
        record, _ = self._read_required(operation_id)
        return record

    def read_canonical(self, operation_id: str) -> tuple[dict[str, Any], bytes]:
        """Read and validate one record and its exact canonical bytes together."""
        return self._read_required(operation_id)

    def list_summaries(self) -> list[dict[str, Any]]:
        try:
            paths = self.backend.list_prefix(self.prefix)
        except StateBackendError as exc:
            raise AuthSessionRetentionRegistryError(
                "Retention disposition registry is unavailable"
            ) from exc
        if len(paths) != len(set(paths)):
            raise AuthSessionRetentionRegistryError("Duplicate registry object path")

        records: list[dict[str, Any]] = []
        operation_ids: set[str] = set()
        prefix = f"{self.prefix}/"
        for path in paths:
            if not isinstance(path, str) or not path.startswith(prefix):
                raise AuthSessionRetentionRegistryError("Unexpected registry object path")
            name = path.removeprefix(prefix)
            if "/" in name or not _RECORD_NAME_PATTERN.fullmatch(name):
                raise AuthSessionRetentionRegistryError("Unexpected registry object path")
            try:
                record, _ = self._read_path(path, expected_operation_id=None)
            except KeyError as exc:
                raise AuthSessionRetentionRegistryError(
                    "Retention disposition registry changed during list"
                ) from exc
            expected_path = self.record_path(record["operation_id"])
            if path != expected_path or record["operation_id"] in operation_ids:
                raise AuthSessionRetentionRegistryError("Registry record path identity drift")
            operation_ids.add(record["operation_id"])
            records.append(record)

        records.sort(
            key=lambda record: (record["recorded_at"], record["operation_id"]),
            reverse=True,
        )
        return [self._summary(record) for record in records]

    def _read_required(self, operation_id: str) -> tuple[dict[str, Any], bytes]:
        operation_id = _require_operation_id(operation_id)
        path = self.record_path(operation_id)
        record, raw = self._read_path(path, expected_operation_id=operation_id)
        return record, raw

    def _read_path(
        self,
        path: str,
        *,
        expected_operation_id: str | None,
    ) -> tuple[dict[str, Any], bytes]:
        try:
            text = self.backend.read_text(path)
        except StateBackendError as exc:
            raise AuthSessionRetentionRegistryError(
                "Retention disposition registry is unavailable"
            ) from exc
        if text is None:
            raise KeyError(path)
        raw = text.encode("utf-8")
        try:
            value = json.loads(text)
        except (TypeError, ValueError) as exc:
            raise AuthSessionRetentionRegistryError("Corrupt retention disposition record") from exc
        if canonical_retention_json_bytes(value) != raw:
            raise AuthSessionRetentionRegistryError(
                "Retention disposition record is not canonical JSON"
            )
        try:
            record = _validate_record(
                value,
                expected_tenant_id=self.tenant_id,
                expected_operation_id=expected_operation_id,
            )
        except AuthSessionRetentionRegistryError as exc:
            raise AuthSessionRetentionRegistryError(
                "Corrupt retention disposition record"
            ) from exc
        return record, raw

    def _reconcile_after_uncertain_write(
        self,
        *,
        operation_id: str,
        request_sha256: str,
    ) -> tuple[dict[str, Any], bool]:
        try:
            record, _ = self._read_required(operation_id)
        except KeyError as exc:
            raise AuthSessionRetentionRegistryError(
                "Retention disposition create outcome is unavailable"
            ) from exc
        if record["request_sha256"] != request_sha256:
            raise AuthSessionRetentionRegistryConflictError(
                "Operation ID is already bound to another retention disposition"
            )
        return record, False

    def _request_sha256(
        self,
        *,
        operation_id: str,
        reviewer_user_id: str,
        source_disposition_receipt_sha256: str,
    ) -> str:
        return retention_sha256(
            {
                "tenant_id": self.tenant_id,
                "operation_id": operation_id,
                "reviewer_user_id": reviewer_user_id,
                "source_disposition_receipt_sha256": source_disposition_receipt_sha256,
            }
        )

    def _build_record(
        self,
        *,
        operation_id: str,
        request_sha256: str,
        reviewer_user_id: str,
        reviewer_username: str,
        source: dict[str, Any],
        source_hash: str,
    ) -> dict[str, Any]:
        record = {
            "contract_version": RETENTION_REVIEW_DISPOSITION_RECORD_CONTRACT_VERSION,
            "operation_id": operation_id,
            "request_sha256": request_sha256,
            "tenant_id": self.tenant_id,
            "reviewer_user_id": reviewer_user_id,
            "reviewer_username": reviewer_username,
            "reviewer_role": "admin",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "source_disposition_receipt": source,
            "source_disposition_receipt_sha256": source_hash,
            "source_recheck_receipt_sha256": source["source_recheck_receipt_sha256"],
            "current_handoff_sha256": source["current_handoff_sha256"],
            "current_aggregate_fingerprint_sha256": source[
                "current_aggregate_fingerprint_sha256"
            ],
            "selected_policy_days": source["selected_policy_days"],
            "aggregate_status": source["aggregate_status"],
            "review_disposition": source["review_disposition"],
            "disposition_binding_sha256": source["disposition_binding_sha256"],
            "record_status": "recorded",
            "review_only": True,
            "reviewer_identity_bound": True,
            "registry_record_persisted": True,
            "approval_granted": False,
            "execution_authorized": False,
            "policy_change_authorized": False,
            "deletion_authorized": False,
            "scheduler_authorized": False,
            "mass_revoke_authorized": False,
            "snapshot_atomic": False,
            "requires_recheck_before_mutation": True,
        }
        record["record_binding_sha256"] = retention_sha256(record)
        return record

    @staticmethod
    def _summary(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation_id": record["operation_id"],
            "tenant_id": record["tenant_id"],
            "reviewer_user_id": record["reviewer_user_id"],
            "reviewer_username": record["reviewer_username"],
            "reviewer_role": record["reviewer_role"],
            "recorded_at": record["recorded_at"],
            "record_sha256": retention_sha256(record),
            "source_disposition_receipt_sha256": record[
                "source_disposition_receipt_sha256"
            ],
            "selected_policy_days": record["selected_policy_days"],
            "aggregate_status": record["aggregate_status"],
            "review_disposition": record["review_disposition"],
            "record_status": record["record_status"],
            "read_only": True,
            "snapshot_atomic": False,
        }


def _validate_record(
    value: object,
    *,
    expected_tenant_id: str,
    expected_operation_id: str | None,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _RECORD_FIELDS:
        raise AuthSessionRetentionRegistryError("Invalid retention disposition record")
    record = value
    operation_id = _require_operation_id(record["operation_id"])
    if expected_operation_id is not None and operation_id != expected_operation_id:
        raise AuthSessionRetentionRegistryError("Registry record operation identity drift")
    if record["contract_version"] != RETENTION_REVIEW_DISPOSITION_RECORD_CONTRACT_VERSION:
        raise AuthSessionRetentionRegistryError("Unsupported retention disposition record")
    if record["tenant_id"] != expected_tenant_id:
        raise AuthSessionRetentionRegistryError("Registry record tenant identity drift")
    reviewer_user_id = _require_non_empty_string(record["reviewer_user_id"], field="reviewer_user_id")
    _require_non_empty_string(record["reviewer_username"], field="reviewer_username")
    if record["reviewer_role"] != "admin":
        raise AuthSessionRetentionRegistryError("Invalid registry reviewer role")
    _require_utc_timestamp(record["recorded_at"])
    request_sha256 = _require_sha256(record["request_sha256"], field="request_sha256")
    record_binding_sha256 = _require_sha256(
        record["record_binding_sha256"],
        field="record_binding_sha256",
    )
    record_binding = {
        field: field_value
        for field, field_value in record.items()
        if field != "record_binding_sha256"
    }
    if record_binding_sha256 != retention_sha256(record_binding):
        raise AuthSessionRetentionRegistryError("Invalid registry record binding")
    source_hash = _require_sha256(
        record["source_disposition_receipt_sha256"],
        field="source_disposition_receipt_sha256",
    )
    try:
        source = validate_retention_review_disposition_receipt(
            record["source_disposition_receipt"],
            expected_tenant_id=expected_tenant_id,
            expected_sha256=source_hash,
        )
    except AuthSessionRetentionContractError as exc:
        raise AuthSessionRetentionRegistryError("Invalid registry source receipt") from exc
    expected_request_sha256 = retention_sha256(
        {
            "tenant_id": expected_tenant_id,
            "operation_id": operation_id,
            "reviewer_user_id": reviewer_user_id,
            "source_disposition_receipt_sha256": source_hash,
        }
    )
    if request_sha256 != expected_request_sha256:
        raise AuthSessionRetentionRegistryError("Invalid registry request binding")
    projected_fields = (
        "source_recheck_receipt_sha256",
        "current_handoff_sha256",
        "current_aggregate_fingerprint_sha256",
        "selected_policy_days",
        "aggregate_status",
        "review_disposition",
        "disposition_binding_sha256",
    )
    if any(record[field] != source[field] for field in projected_fields):
        raise AuthSessionRetentionRegistryError("Invalid registry source projection")
    if (
        record["record_status"] != "recorded"
        or record["review_only"] is not True
        or record["reviewer_identity_bound"] is not True
        or record["registry_record_persisted"] is not True
        or record["approval_granted"] is not False
        or record["execution_authorized"] is not False
        or record["policy_change_authorized"] is not False
        or record["deletion_authorized"] is not False
        or record["scheduler_authorized"] is not False
        or record["mass_revoke_authorized"] is not False
        or record["snapshot_atomic"] is not False
        or record["requires_recheck_before_mutation"] is not True
    ):
        raise AuthSessionRetentionRegistryError("Invalid registry authority")
    return record


def _require_tenant_id(value: object) -> str:
    value = _require_non_empty_string(value, field="tenant_id")
    if "/" in value or "\\" in value:
        raise AuthSessionRetentionRegistryError("Invalid tenant ID")
    return value


def _require_operation_id(value: object) -> str:
    if type(value) is not str:
        raise AuthSessionRetentionRegistryError("Invalid operation ID")
    try:
        parsed = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise AuthSessionRetentionRegistryError("Invalid operation ID") from exc
    if parsed.version != 4 or str(parsed) != value:
        raise AuthSessionRetentionRegistryError("Invalid operation ID")
    return value


def _require_non_empty_string(value: object, *, field: str) -> str:
    if type(value) is not str or not value.strip():
        raise AuthSessionRetentionRegistryError(f"Invalid {field}")
    return value


def _require_sha256(value: object, *, field: str) -> str:
    if type(value) is not str or not _SHA256_PATTERN.fullmatch(value):
        raise AuthSessionRetentionRegistryError(f"Invalid {field}")
    return value


def _require_utc_timestamp(value: object) -> str:
    if type(value) is not str:
        raise AuthSessionRetentionRegistryError("Invalid recorded_at")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise AuthSessionRetentionRegistryError("Invalid recorded_at") from exc
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != timedelta(0)
        or parsed.isoformat() != value
    ):
        raise AuthSessionRetentionRegistryError("recorded_at must be canonical UTC")
    return value


def get_auth_session_retention_registry(
    *,
    tenant_id: str,
    backend: StateBackend,
) -> AuthSessionRetentionRegistry:
    """Build the tenant-scoped registry on the application's selected backend."""
    return AuthSessionRetentionRegistry(tenant_id=tenant_id, backend=backend)
