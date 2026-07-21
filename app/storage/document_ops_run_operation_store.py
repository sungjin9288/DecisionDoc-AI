"""Shared retry authority for captured DocumentOps Agent runs."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.agents.schemas import DocumentOpsResult
from app.storage.state_backend import StateBackend, StateBackendError
from app.tenant import require_tenant_id

_SCHEMA_VERSION = "document_ops_agent_operation_v1"
_OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,119}")
_CONTENT_TYPE = "application/json; charset=utf-8"


class DocumentOpsRunOperationStoreError(RuntimeError):
    """Raised when an Agent run operation receipt cannot be trusted."""


class DocumentOpsRunOperationConflictError(ValueError):
    """Raised when one operation identity is reused for different input."""


class DocumentOpsRunOperationUnavailableError(RuntimeError):
    """Raised when a prior attempt has not produced a reusable result."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentOpsRunOperationStoreError(
                f"Duplicate key in DocumentOps Agent operation receipt: {key!r}"
            )
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise DocumentOpsRunOperationStoreError(
        f"Invalid numeric value in DocumentOps Agent operation receipt: {value}"
    )


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("DocumentOps Agent operation data must be JSON-compatible.") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _is_utc_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


class _StoredRunResult(DocumentOpsResult):
    trajectory_id: str = Field(..., min_length=1)
    trajectory_saved: Literal[True]


class _OperationReceipt(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    schema_version: Literal["document_ops_agent_operation_v1"]
    tenant_id: str = Field(..., min_length=1)
    operation_id: str = Field(
        ...,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    request_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    status: Literal["running", "succeeded", "failed"]
    owner_id: str = Field(..., pattern=r"^[0-9a-f]{32}$")
    started_at: str = Field(..., min_length=1)
    completed_at: str | None = None
    result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    result: _StoredRunResult | None = None

    @model_validator(mode="after")
    def validate_state(self) -> "_OperationReceipt":
        require_tenant_id(self.tenant_id)
        if not _is_utc_timestamp(self.started_at):
            raise ValueError("started_at must be a timezone-aware timestamp.")

        common_fields = {
            "schema_version",
            "tenant_id",
            "operation_id",
            "request_sha256",
            "status",
            "owner_id",
            "started_at",
        }
        expected_fields = {
            "running": common_fields,
            "failed": common_fields | {"completed_at"},
            "succeeded": common_fields
            | {"completed_at", "result_sha256", "result"},
        }[self.status]
        if self.model_fields_set != expected_fields:
            raise ValueError("receipt fields do not match its status.")

        if self.status == "running":
            return self
        if self.completed_at is None or not _is_utc_timestamp(self.completed_at):
            raise ValueError("completed_at must be a timezone-aware timestamp.")
        if self.status == "succeeded":
            if self.result is None or self.result_sha256 != _sha256(self.result.model_dump()):
                raise ValueError("result hash does not match.")
        return self


@dataclass(frozen=True)
class DocumentOpsRunClaim:
    tenant_id: str
    operation_id: str
    request_sha256: str
    owner_id: str | None
    expected_state: str | None
    result: dict[str, Any] | None = None

    @property
    def should_execute(self) -> bool:
        return self.owner_id is not None


class DocumentOpsRunOperationStore:
    """Claim one caller operation before a captured Agent run reaches a provider."""

    def __init__(self, *, backend: StateBackend) -> None:
        self._backend = backend

    def operation_path(self, *, tenant_id: str, operation_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        operation_id = self._validate_operation_id(operation_id)
        operation_key = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        return f"tenants/{tenant_id}/document_ops_agent_operations/{operation_key}.json"

    def claim(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        request_payload: dict[str, Any],
    ) -> DocumentOpsRunClaim:
        tenant_id = require_tenant_id(tenant_id)
        operation_id = self._validate_operation_id(operation_id)
        request_sha256 = _sha256(request_payload)
        owner_id = uuid.uuid4().hex
        receipt = _OperationReceipt(
            schema_version=_SCHEMA_VERSION,
            tenant_id=tenant_id,
            operation_id=operation_id,
            request_sha256=request_sha256,
            status="running",
            owner_id=owner_id,
            started_at=_utc_now(),
        )
        raw = self._serialize(receipt)
        path = self.operation_path(tenant_id=tenant_id, operation_id=operation_id)

        try:
            created = self._backend.write_text_if_absent(
                path,
                raw,
                content_type=_CONTENT_TYPE,
            )
        except StateBackendError:
            current_raw, current = self._read(path)
            if current_raw != raw or current != receipt:
                raise DocumentOpsRunOperationStoreError(
                    "DocumentOps Agent operation claim could not be persisted."
                )
            created = True
        if created:
            return DocumentOpsRunClaim(
                tenant_id=tenant_id,
                operation_id=operation_id,
                request_sha256=request_sha256,
                owner_id=owner_id,
                expected_state=raw,
            )

        _, current = self._read(path)
        self._assert_identity(
            current,
            tenant_id=tenant_id,
            operation_id=operation_id,
            request_sha256=request_sha256,
        )
        if current.status == "succeeded":
            return DocumentOpsRunClaim(
                tenant_id=tenant_id,
                operation_id=operation_id,
                request_sha256=request_sha256,
                owner_id=None,
                expected_state=None,
                result=current.result.model_dump() if current.result else None,
            )
        if current.status == "running":
            raise DocumentOpsRunOperationUnavailableError(
                "DocumentOps Agent operation is already in progress."
            )
        raise DocumentOpsRunOperationUnavailableError(
            "DocumentOps Agent operation did not complete; inspect trajectory and usage evidence before using a new operation_id."
        )

    def complete(
        self,
        claim: DocumentOpsRunClaim,
        *,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        running = self._running_receipt(claim)
        try:
            stored_result = _StoredRunResult.model_validate(result)
        except ValidationError as exc:
            raise DocumentOpsRunOperationStoreError(
                "DocumentOps Agent operation result is invalid."
            ) from exc
        completed = _OperationReceipt.model_validate(
            {
                **running.model_dump(exclude_none=True),
                "status": "succeeded",
                "completed_at": _utc_now(),
                "result_sha256": _sha256(stored_result.model_dump()),
                "result": stored_result.model_dump(),
            }
        )
        path = self.operation_path(
            tenant_id=claim.tenant_id,
            operation_id=claim.operation_id,
        )
        replacement = self._serialize(completed)
        try:
            persisted = self._backend.replace_text_if_equal(
                path,
                expected=claim.expected_state or "",
                replacement=replacement,
                content_type=_CONTENT_TYPE,
            )
        except StateBackendError:
            persisted = False
        if not persisted:
            _, current = self._read(path)
            self._assert_identity(
                current,
                tenant_id=claim.tenant_id,
                operation_id=claim.operation_id,
                request_sha256=claim.request_sha256,
            )
            if current != completed:
                raise DocumentOpsRunOperationStoreError(
                    "DocumentOps Agent operation result could not be reconciled."
                )
        return stored_result.model_dump()

    def fail(self, claim: DocumentOpsRunClaim) -> None:
        running = self._running_receipt(claim)
        failed = _OperationReceipt.model_validate(
            {
                **running.model_dump(exclude_none=True),
                "status": "failed",
                "completed_at": _utc_now(),
            }
        )
        path = self.operation_path(
            tenant_id=claim.tenant_id,
            operation_id=claim.operation_id,
        )
        try:
            self._backend.replace_text_if_equal(
                path,
                expected=claim.expected_state or "",
                replacement=self._serialize(failed),
                content_type=_CONTENT_TYPE,
            )
        except StateBackendError:
            return

    def _running_receipt(self, claim: DocumentOpsRunClaim) -> _OperationReceipt:
        if not claim.should_execute or claim.expected_state is None or claim.owner_id is None:
            raise ValueError("DocumentOps Agent operation claim does not own execution.")
        receipt = self._decode(claim.expected_state)
        if (
            receipt.status != "running"
            or receipt.tenant_id != claim.tenant_id
            or receipt.operation_id != claim.operation_id
            or receipt.request_sha256 != claim.request_sha256
            or receipt.owner_id != claim.owner_id
        ):
            raise ValueError("DocumentOps Agent operation claim does not match its receipt.")
        return receipt

    def _read(self, path: str) -> tuple[str, _OperationReceipt]:
        try:
            raw = self._backend.read_text(path)
        except (StateBackendError, UnicodeError) as exc:
            raise DocumentOpsRunOperationStoreError(
                "DocumentOps Agent operation receipt could not be read."
            ) from exc
        if raw is None:
            raise DocumentOpsRunOperationStoreError(
                "DocumentOps Agent operation receipt is missing."
            )
        return raw, self._decode(raw)

    @staticmethod
    def _decode(raw: str) -> _OperationReceipt:
        if not raw:
            raise DocumentOpsRunOperationStoreError(
                "DocumentOps Agent operation receipt is blank."
            )
        try:
            data = json.loads(
                raw,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_nonfinite,
            )
            return _OperationReceipt.model_validate(data)
        except (
            json.JSONDecodeError,
            TypeError,
            ValueError,
            ValidationError,
            DocumentOpsRunOperationStoreError,
        ) as exc:
            raise DocumentOpsRunOperationStoreError(
                "DocumentOps Agent operation receipt is invalid."
            ) from exc

    @staticmethod
    def _serialize(receipt: _OperationReceipt) -> str:
        return _canonical_json(receipt.model_dump(exclude_none=True))

    @staticmethod
    def _validate_operation_id(operation_id: Any) -> str:
        if not isinstance(operation_id, str) or _OPERATION_ID.fullmatch(operation_id) is None:
            raise ValueError("Invalid DocumentOps Agent operation_id.")
        return operation_id

    @staticmethod
    def _assert_identity(
        receipt: _OperationReceipt,
        *,
        tenant_id: str,
        operation_id: str,
        request_sha256: str,
    ) -> None:
        if receipt.tenant_id != tenant_id or receipt.operation_id != operation_id:
            raise DocumentOpsRunOperationStoreError(
                "DocumentOps Agent operation receipt ownership does not match."
            )
        if receipt.request_sha256 != request_sha256:
            raise DocumentOpsRunOperationConflictError(
                "DocumentOps Agent operation identity was reused with a different payload."
            )
