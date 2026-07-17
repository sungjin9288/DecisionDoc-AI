"""Tenant-scoped persistence for packet-bound procurement reviews."""
from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Mapping

from app.storage.procurement_review_models import (
    REVIEW_RECORD_SCHEMA_VERSION,
    SHA256_PATTERN as _SHA256_PATTERN,
    ProcurementReviewRecord,
    ProcurementReviewStoreError,
    delete_unreferenced_review_artifact,
    ensure_review_artifact,
    record_from_dict,
    read_review_artifact,
    require_sha256,
    safe_segment,
    sha256_content,
    unique_object as _unique_object,
    validate_record,
)
from app.storage.state_backend import (
    StateBackend,
    StateBackendError,
    get_state_backend,
)
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


PacketEvidenceValidator = Callable[[ProcurementReviewRecord, bytes], None]
ReviewedPackageEvidenceValidator = Callable[[ProcurementReviewRecord, bytes], None]
class ProcurementReviewStore:
    """Persist original packets, review state, and completed review packages."""

    def __init__(
        self,
        base_dir: str = "data",
        *,
        backend: StateBackend | None = None,
        packet_evidence_validator: PacketEvidenceValidator | None = None,
        reviewed_package_evidence_validator: ReviewedPackageEvidenceValidator | None = None,
    ) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._packet_evidence_validator = packet_evidence_validator
        self._reviewed_package_evidence_validator = (
            reviewed_package_evidence_validator
        )
    _safe_segment = staticmethod(safe_segment)
    _require_sha256 = staticmethod(require_sha256)
    _from_dict = staticmethod(record_from_dict)
    _validate_record = staticmethod(validate_record)

    def _review_prefix(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str | None = None,
    ) -> Path:
        project = self._safe_segment(project_id, field="project_id")
        prefix = self._tenant_review_prefix(tenant_id=tenant_id) / project
        if packet_sha256 is not None:
            prefix /= self._require_sha256(packet_sha256)
        return prefix

    def _tenant_review_prefix(self, *, tenant_id: str) -> Path:
        tenant = require_tenant_id(tenant_id)
        return Path("tenants") / tenant / "procurement_reviews"

    def _review_lock(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ):
        relative_path = self._relative_path(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
            filename="record.json",
        )
        return state_lock(
            self._backend,
            data_dir=self._base,
            relative_path=relative_path,
        )

    def _relative_path(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
        filename: str,
    ) -> str:
        return str(
            self._review_prefix(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            / filename
        )

    @classmethod
    def _require_record_scope(
        cls,
        record: ProcurementReviewRecord,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> tuple[str, str, str]:
        tenant_id = require_tenant_id(tenant_id)
        project_id = cls._safe_segment(project_id, field="project_id")
        packet_sha256 = cls._require_sha256(packet_sha256)
        if not isinstance(record, ProcurementReviewRecord) or (
            record.tenant_id != tenant_id
            or record.project_id != project_id
            or record.packet_sha256 != packet_sha256
        ):
            raise ValueError("procurement review record does not match caller scope")
        return tenant_id, project_id, packet_sha256

    def _record_path(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> str:
        return self._relative_path(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
            filename="record.json",
        )

    def _reviewed_package_path(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
        reviewed_package_sha256: str,
    ) -> str:
        reviewed_package_sha256 = self._require_sha256(
            reviewed_package_sha256,
            field="reviewed_package_sha256",
        )
        return self._relative_path(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
            filename=f"reviewed_packages/{reviewed_package_sha256}.zip",
        )

    def _serialize_record(self, record: ProcurementReviewRecord) -> str:
        self._validate_record(record)
        try:
            return json.dumps(asdict(record), ensure_ascii=False, indent=2)
        except (TypeError, ValueError) as exc:
            raise ProcurementReviewStoreError(
                "Failed to serialize procurement review record"
            ) from exc

    def _read_record_raw(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> str | None:
        try:
            return self._backend.read_text(
                self._record_path(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    packet_sha256=packet_sha256,
                )
            )
        except (StateBackendError, UnicodeError) as exc:
            raise ProcurementReviewStoreError(
                "Invalid procurement review record"
            ) from exc

    def _record_from_raw(
        self,
        raw: str | None,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> ProcurementReviewRecord | None:
        if raw is None:
            return None
        if not raw.strip():
            raise ProcurementReviewStoreError(
                "Invalid procurement review record"
            )
        try:
            payload = json.loads(raw, object_pairs_hook=_unique_object)
            if not isinstance(payload, dict):
                raise TypeError("procurement review record must be an object")
            record = self._from_dict(payload)
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            ProcurementReviewStoreError,
        ) as exc:
            raise ProcurementReviewStoreError(
                "Invalid procurement review record"
            ) from exc
        if (
            record.tenant_id != tenant_id
            or record.project_id != project_id
            or record.packet_sha256 != packet_sha256
        ):
            raise ProcurementReviewStoreError(
                "Procurement review record identity is inconsistent"
            )
        return record

    def _load_record(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> tuple[ProcurementReviewRecord | None, str | None]:
        raw = self._read_record_raw(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        return (
            self._record_from_raw(
                raw,
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            ),
            raw,
        )

    def _save_record_if_current(
        self,
        record: ProcurementReviewRecord,
        *,
        expected_raw: str | None,
    ) -> bool:
        replacement = self._serialize_record(record)
        relative_path = self._record_path(
            tenant_id=record.tenant_id,
            project_id=record.project_id,
            packet_sha256=record.packet_sha256,
        )
        try:
            if expected_raw is None:
                return self._backend.write_text_if_absent(
                    relative_path,
                    replacement,
                )
            return self._backend.replace_text_if_equal(
                relative_path,
                expected=expected_raw,
                replacement=replacement,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_text(relative_path)
            except (StateBackendError, UnicodeError):
                observed = None
            if observed == replacement:
                return True
            raise ProcurementReviewStoreError(
                "Failed to persist procurement review record"
            ) from exc

    def _list_review_artifacts(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> list[str]:
        prefix = self._review_prefix(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        try:
            return self._backend.list_prefix(str(prefix))
        except StateBackendError as exc:
            raise ProcurementReviewStoreError(
                "Failed to list procurement review artifacts"
            ) from exc

    def _validate_record_evidence(
        self,
        record: ProcurementReviewRecord,
    ) -> None:
        self.read_packet(
            record,
            tenant_id=record.tenant_id,
            project_id=record.project_id,
            packet_sha256=record.packet_sha256,
        )
        if record.review_status == "completed":
            self.read_reviewed_package(
                record,
                tenant_id=record.tenant_id,
                project_id=record.project_id,
                packet_sha256=record.packet_sha256,
            )

    def prepare(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_content: bytes,
        receipt: Mapping[str, Any],
        prepared_at: str,
    ) -> tuple[ProcurementReviewRecord, bool]:
        """Create an idempotent pending review bound to exact packet bytes."""
        tenant_id = require_tenant_id(tenant_id)
        project_id = self._safe_segment(project_id, field="project_id")
        packet_sha256 = sha256_content(packet_content)
        pending_receipt = dict(receipt)
        record = ProcurementReviewRecord(
            schema_version=REVIEW_RECORD_SCHEMA_VERSION,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
            packet_size_bytes=len(packet_content),
            package_id=pending_receipt.get("package_id", ""),
            recommendation=pending_receipt.get("recommendation", ""),
            reviewer=pending_receipt.get("reviewer", ""),
            review_status=pending_receipt.get("status", ""),
            decision=pending_receipt.get("decision"),
            prepared_at=prepared_at,
            reviewed_at=pending_receipt.get("reviewed_at"),
            reviewed_package_sha256=None,
            reviewed_package_size_bytes=None,
            operational_approval=False,
            receipt=pending_receipt,
        )
        self._validate_record(record)

        with self._review_lock(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        ):
            existing, _existing_raw = self._load_record(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if existing is not None:
                stored_packet = self.read_packet(
                    existing,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    packet_sha256=packet_sha256,
                )
                if stored_packet != packet_content:
                    raise ValueError("stored procurement review packet content is inconsistent")
                return existing, False

            packet_path = self._relative_path(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
                filename="packet.zip",
            )
            artifact_paths = self._list_review_artifacts(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            unexpected_paths = set(artifact_paths) - {packet_path}
            if unexpected_paths:
                raise ProcurementReviewStoreError(
                    "Unexpected procurement review artifacts exist without a record"
                )

            ensure_review_artifact(
                self._backend,
                packet_path,
                packet_content,
                label="procurement review packet",
            )
            if self._save_record_if_current(record, expected_raw=None):
                return record, True

            existing, _existing_raw = self._load_record(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if existing is not None:
                stored_packet = self.read_packet(
                    existing,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    packet_sha256=packet_sha256,
                )
                if stored_packet != packet_content:
                    raise ProcurementReviewStoreError(
                        "Stored procurement review packet content is inconsistent"
                    )
                return existing, False
            raise ProcurementReviewStoreError(
                "Procurement review record changed during preparation"
            )

    def get(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> ProcurementReviewRecord | None:
        tenant_id = require_tenant_id(tenant_id)
        project_id = self._safe_segment(project_id, field="project_id")
        packet_sha256 = self._require_sha256(packet_sha256)
        with self._review_lock(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        ):
            record, _raw = self._load_record(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            return record

    def list_by_project(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> list[ProcurementReviewRecord]:
        tenant_id = require_tenant_id(tenant_id)
        project_id = self._safe_segment(project_id, field="project_id")
        prefix = self._review_prefix(tenant_id=tenant_id, project_id=project_id)
        records: list[ProcurementReviewRecord] = []
        try:
            paths = self._backend.list_prefix(str(prefix))
        except StateBackendError as exc:
            raise ProcurementReviewStoreError(
                "Failed to list procurement review records"
            ) from exc
        for path in paths:
            try:
                packet_sha256, filename = Path(path).relative_to(prefix).parts
            except (ValueError, TypeError):
                continue
            if (
                filename != "record.json"
                or not _SHA256_PATTERN.fullmatch(packet_sha256)
            ):
                continue
            record = self.get(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if record is not None:
                self._validate_record_evidence(record)
                records.append(record)
        return sorted(
            records,
            key=lambda item: (item.prepared_at, item.packet_sha256),
            reverse=True,
        )

    def list_by_tenant(self, *, tenant_id: str) -> list[ProcurementReviewRecord]:
        """List every packet-bound review owned by one tenant."""
        tenant_id = require_tenant_id(tenant_id)
        prefix = self._tenant_review_prefix(tenant_id=tenant_id)
        records: list[ProcurementReviewRecord] = []
        try:
            paths = self._backend.list_prefix(str(prefix))
        except StateBackendError as exc:
            raise ProcurementReviewStoreError(
                "Failed to list procurement review records"
            ) from exc
        for path in paths:
            try:
                project_id, packet_sha256, filename = Path(path).relative_to(prefix).parts
            except (ValueError, TypeError):
                continue
            if filename != "record.json" or not _SHA256_PATTERN.fullmatch(packet_sha256):
                continue
            try:
                project_id = self._safe_segment(project_id, field="project_id")
            except ValueError:
                continue
            record = self.get(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if record is not None:
                self._validate_record_evidence(record)
                records.append(record)
        return sorted(
            records,
            key=lambda item: (item.prepared_at, item.packet_sha256),
            reverse=True,
        )

    def read_packet(
        self,
        record: ProcurementReviewRecord,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> bytes:
        tenant_id, project_id, packet_sha256 = self._require_record_scope(
            record,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        with self._review_lock(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        ):
            stored = self.get(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if stored is None:
                raise ProcurementReviewStoreError(
                    "Procurement review record is missing before packet read"
                )
            if stored != record:
                raise ValueError("procurement review record changed before packet read")
            content = read_review_artifact(
                self._backend,
                self._relative_path(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    packet_sha256=packet_sha256,
                    filename="packet.zip",
                ),
                label="procurement review packet",
            )
            if content is None:
                raise ProcurementReviewStoreError(
                    "Procurement review packet is missing"
                )
            if (
                len(content) != stored.packet_size_bytes
                or sha256_content(content) != packet_sha256
            ):
                raise ProcurementReviewStoreError(
                    "Procurement review packet evidence is inconsistent"
                )
            if self._packet_evidence_validator is not None:
                try:
                    self._packet_evidence_validator(stored, content)
                except (KeyError, OSError, TypeError, ValueError) as exc:
                    raise ProcurementReviewStoreError(
                        "Procurement review packet semantics are invalid"
                    ) from exc
            return content

    def complete(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
        current: ProcurementReviewRecord,
        completed_receipt: Mapping[str, Any],
        reviewed_package_content: bytes,
    ) -> ProcurementReviewRecord:
        """Persist one completed decision after its reviewed package is built."""
        tenant_id, project_id, packet_sha256 = self._require_record_scope(
            current,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        completed = ProcurementReviewRecord(
            **{
                **asdict(current),
                "review_status": completed_receipt.get("status"),
                "decision": completed_receipt.get("decision"),
                "reviewed_at": completed_receipt.get("reviewed_at"),
                "reviewed_package_sha256": sha256_content(reviewed_package_content),
                "reviewed_package_size_bytes": len(reviewed_package_content),
                "receipt": dict(completed_receipt),
            }
        )
        self._validate_record(completed)
        if self._reviewed_package_evidence_validator is not None:
            try:
                self._reviewed_package_evidence_validator(
                    completed,
                    reviewed_package_content,
                )
            except (KeyError, OSError, TypeError, ValueError) as exc:
                raise ProcurementReviewStoreError(
                    "Procurement reviewed package semantics are invalid"
                ) from exc

        with self._review_lock(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        ):
            stored, stored_raw = self._load_record(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if stored is None:
                raise ProcurementReviewStoreError(
                    "Procurement review record is missing before completion"
                )
            if stored != current:
                raise ValueError("procurement review record changed before completion")
            if stored.review_status != "pending":
                raise ValueError("procurement review record is already completed")
            self.read_packet(
                stored,
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )

            reviewed_package_path = self._relative_path(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
                filename="reviewed_package.zip",
            )
            if read_review_artifact(
                self._backend,
                reviewed_package_path,
                label="procurement reviewed package",
            ) is not None:
                raise ProcurementReviewStoreError(
                    "Procurement reviewed package exists before completion"
                )

            immutable_package_path = self._reviewed_package_path(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
                reviewed_package_sha256=completed.reviewed_package_sha256 or "",
            )
            ensure_review_artifact(
                self._backend,
                immutable_package_path,
                reviewed_package_content,
                label="procurement reviewed package",
            )
            if self._save_record_if_current(
                completed,
                expected_raw=stored_raw,
            ):
                return completed

            observed, _observed_raw = self._load_record(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if observed == completed:
                return observed
            if observed is None:
                raise ProcurementReviewStoreError(
                    "Procurement review record disappeared during completion"
                )
            if (
                observed.review_status == "completed"
                and observed.reviewed_package_sha256
                != completed.reviewed_package_sha256
            ):
                delete_unreferenced_review_artifact(
                    self._backend,
                    immutable_package_path,
                    label="procurement reviewed package",
                )
            raise ValueError(
                "procurement review record changed before completion"
            )

    def read_reviewed_package(
        self,
        record: ProcurementReviewRecord,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> bytes:
        tenant_id, project_id, packet_sha256 = self._require_record_scope(
            record,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        )
        with self._review_lock(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
        ):
            stored = self.get(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if stored is None:
                raise ProcurementReviewStoreError(
                    "Procurement review record is missing before package read"
                )
            if stored != record:
                raise ValueError("procurement review record changed before package read")
            if stored.review_status != "completed":
                raise ValueError("procurement review is not completed")
            immutable_path = self._reviewed_package_path(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
                reviewed_package_sha256=stored.reviewed_package_sha256 or "",
            )
            legacy_path = self._relative_path(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
                filename="reviewed_package.zip",
            )
            immutable_content = read_review_artifact(
                self._backend,
                immutable_path,
                label="procurement reviewed package",
            )
            legacy_content = read_review_artifact(
                self._backend,
                legacy_path,
                label="legacy procurement reviewed package",
            )
            if (
                immutable_content is not None
                and legacy_content is not None
                and immutable_content != legacy_content
            ):
                raise ProcurementReviewStoreError(
                    "Procurement reviewed package aliases are inconsistent"
                )
            content = immutable_content or legacy_content
            if content is None:
                raise ProcurementReviewStoreError(
                    "Procurement reviewed package is missing"
                )
            if (
                len(content) != stored.reviewed_package_size_bytes
                or sha256_content(content) != stored.reviewed_package_sha256
            ):
                raise ProcurementReviewStoreError(
                    "Procurement reviewed package evidence is inconsistent"
                )
            if self._reviewed_package_evidence_validator is not None:
                try:
                    self._reviewed_package_evidence_validator(stored, content)
                except (KeyError, OSError, TypeError, ValueError) as exc:
                    raise ProcurementReviewStoreError(
                        "Procurement reviewed package semantics are invalid"
                    ) from exc
            return content
