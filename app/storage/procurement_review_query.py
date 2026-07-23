"""Access-aware query helpers for persisted procurement review evidence."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.storage.procurement_review_models import (
    ProcurementReviewRecord,
    ProcurementReviewStoreError,
    project_review_record_reference,
    require_reviewer_user_id,
    review_record_is_assigned_to,
    safe_segment,
    tenant_review_record_reference,
)
from app.storage.state_backend import StateBackend, StateBackendError
from app.tenant import require_tenant_id


class ProcurementReviewQueryStore(Protocol):
    _backend: StateBackend

    def _review_prefix(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str | None = None,
    ) -> Path: ...

    def _tenant_review_prefix(self, *, tenant_id: str) -> Path: ...

    def get(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> ProcurementReviewRecord | None: ...

    def _validate_record_evidence(self, record: ProcurementReviewRecord) -> None: ...


def list_project_review_records(
    store: ProcurementReviewQueryStore,
    *,
    tenant_id: str,
    project_id: str,
    reviewer_user_id: str | None,
) -> list[ProcurementReviewRecord]:
    tenant_id = require_tenant_id(tenant_id)
    project_id = safe_segment(project_id, field="project_id")
    reviewer_user_id = require_reviewer_user_id(reviewer_user_id)
    prefix = store._review_prefix(tenant_id=tenant_id, project_id=project_id)
    try:
        paths = store._backend.list_prefix(str(prefix))
    except StateBackendError as exc:
        raise ProcurementReviewStoreError(
            "Failed to list procurement review records"
        ) from exc

    records: list[ProcurementReviewRecord] = []
    for path in paths:
        packet_sha256 = project_review_record_reference(path, prefix=prefix)
        if packet_sha256 is None:
            continue
        record = store.get(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        if record is not None and review_record_is_assigned_to(
            record,
            reviewer_user_id,
        ):
            store._validate_record_evidence(record)
            records.append(record)
    return _sorted_records(records)


def list_tenant_review_records(
    store: ProcurementReviewQueryStore,
    *,
    tenant_id: str,
    reviewer_user_id: str | None,
) -> list[ProcurementReviewRecord]:
    tenant_id = require_tenant_id(tenant_id)
    reviewer_user_id = require_reviewer_user_id(reviewer_user_id)
    prefix = store._tenant_review_prefix(tenant_id=tenant_id)
    try:
        paths = store._backend.list_prefix(str(prefix))
    except StateBackendError as exc:
        raise ProcurementReviewStoreError(
            "Failed to list procurement review records"
        ) from exc

    records: list[ProcurementReviewRecord] = []
    for path in paths:
        reference = tenant_review_record_reference(path, prefix=prefix)
        if reference is None:
            continue
        project_id, packet_sha256 = reference
        record = store.get(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        if record is not None and review_record_is_assigned_to(
            record,
            reviewer_user_id,
        ):
            store._validate_record_evidence(record)
            records.append(record)
    return _sorted_records(records)


def has_project_review_records(
    store: ProcurementReviewQueryStore,
    *,
    tenant_id: str,
    project_id: str,
) -> bool:
    tenant_id = require_tenant_id(tenant_id)
    prefix = store._review_prefix(tenant_id=tenant_id, project_id=project_id)
    try:
        paths = store._backend.list_prefix(str(prefix))
    except StateBackendError as exc:
        raise ProcurementReviewStoreError(
            "Failed to list procurement review records"
        ) from exc
    return any(
        project_review_record_reference(path, prefix=prefix) is not None
        for path in paths
    )


def _sorted_records(
    records: list[ProcurementReviewRecord],
) -> list[ProcurementReviewRecord]:
    return sorted(
        records,
        key=lambda item: (item.prepared_at, item.packet_sha256),
        reverse=True,
    )
