"""Immutable StateBackend storage for generated-document review handoffs."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from app.services.generation_export_packet import (
    PERSISTED_PACKET_SCHEMA,
    PERSISTED_PACKET_SCHEMA_V2,
    GenerationExportPacketError,
    verify_generation_export_packet,
)
from app.storage.generated_document_review_models import (
    COMPLETED_RECORD_SCHEMA,
    RECORD_SCHEMA,
    GeneratedDocumentReviewRecord,
    GeneratedDocumentReviewRecordError,
    GeneratedDocumentReviewedPackageError,
    build_generated_document_reviewed_package,
    parse_record,
    require_sha256,
    safe_segment,
    serialize_record,
    verify_generated_document_reviewed_package,
)
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id


class GeneratedDocumentReviewStoreError(RuntimeError):
    """Raised when generated-document review state cannot be trusted."""


class GeneratedDocumentReviewStore:
    def __init__(
        self,
        base_dir: str = "data",
        *,
        backend: StateBackend | None = None,
    ) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    @staticmethod
    def _root(tenant_id: str) -> Path:
        return Path("tenants") / require_tenant_id(tenant_id) / "generated_document_reviews"

    def packet_path(self, *, tenant_id: str, packet_sha256: str) -> str:
        packet_sha256 = require_sha256(packet_sha256, field="packet_sha256")
        return str(self._root(tenant_id) / "packets" / f"{packet_sha256}.zip")

    def reviewed_package_path(
        self,
        *,
        tenant_id: str,
        reviewed_package_sha256: str,
    ) -> str:
        reviewed_package_sha256 = require_sha256(
            reviewed_package_sha256,
            field="reviewed_package_sha256",
        )
        return str(
            self._root(tenant_id)
            / "reviewed_packages"
            / f"{reviewed_package_sha256}.zip"
        )

    def record_path(
        self,
        *,
        tenant_id: str,
        project_id: str,
        project_document_id: str,
        packet_sha256: str,
    ) -> str:
        project_id = safe_segment(project_id, field="project_id")
        project_document_id = safe_segment(
            project_document_id, field="project_document_id"
        )
        packet_sha256 = require_sha256(packet_sha256, field="packet_sha256")
        return str(
            self._root(tenant_id)
            / "projects"
            / project_id
            / project_document_id
            / packet_sha256
            / "record.json"
        )

    @staticmethod
    def _read_bytes(
        backend: StateBackend,
        path: str,
        *,
        label: str,
    ) -> bytes | None:
        try:
            return backend.read_bytes(path)
        except StateBackendError as exc:
            raise GeneratedDocumentReviewStoreError(f"failed to read {label}") from exc

    @staticmethod
    def _read_text(
        backend: StateBackend,
        path: str,
        *,
        label: str,
    ) -> str | None:
        try:
            return backend.read_text(path)
        except StateBackendError as exc:
            raise GeneratedDocumentReviewStoreError(f"failed to read {label}") from exc

    def _load_record(self, path: str) -> GeneratedDocumentReviewRecord | None:
        raw = self._read_text(self._backend, path, label="generated document review record")
        if raw is None:
            return None
        try:
            return parse_record(raw)
        except GeneratedDocumentReviewRecordError as exc:
            raise GeneratedDocumentReviewStoreError(
                "generated document review record is invalid"
            ) from exc

    @staticmethod
    def _require_assignment(
        assignment: Mapping[str, str],
        *,
        field: str,
    ) -> dict[str, str]:
        value = dict(assignment)
        if set(value) != {"user_id", "username", "role"}:
            raise ValueError(f"{field} is invalid")
        for item in value.values():
            if not isinstance(item, str) or not item or item != item.strip():
                raise ValueError(f"{field} is invalid")
        if value["role"] not in {"admin", "member"}:
            raise ValueError(f"{field} is invalid")
        return value

    @staticmethod
    def _verified_packet(
        packet_content: bytes,
        packet_verification: Mapping[str, Any],
    ) -> dict[str, Any]:
        try:
            verified = verify_generation_export_packet(packet_content)
        except GenerationExportPacketError as exc:
            raise ValueError("generated document review packet is invalid") from exc
        if verified["schema"] not in {
            PERSISTED_PACKET_SCHEMA,
            PERSISTED_PACKET_SCHEMA_V2,
        }:
            raise ValueError("generated document review packet schema is invalid")
        compared_fields = {
            "artifact_count",
            "formats",
            "manifest_sha256",
            "packet_persisted",
            "packet_sha256",
            "schema",
            "source",
            "source_procurement_binding",
            "verified",
        }
        if any(packet_verification.get(key) != verified[key] for key in compared_fields):
            raise ValueError("generated document review packet evidence is inconsistent")
        return verified

    @staticmethod
    def _matches_replay(
        existing: GeneratedDocumentReviewRecord,
        candidate: GeneratedDocumentReviewRecord,
    ) -> bool:
        return existing == replace(candidate, prepared_at=existing.prepared_at)

    def _validate_record_path_binding(
        self,
        record: GeneratedDocumentReviewRecord,
        *,
        tenant_id: str,
        project_id: str,
        project_document_id: str,
        packet_sha256: str,
    ) -> None:
        if (
            record.tenant_id != tenant_id
            or record.project_id != project_id
            or record.project_document_id != project_document_id
            or record.packet_sha256 != packet_sha256
        ):
            raise GeneratedDocumentReviewStoreError(
                "generated document review record ownership is invalid"
            )

    def prepare(
        self,
        *,
        tenant_id: str,
        project_id: str,
        project_document_id: str,
        packet_content: bytes,
        packet_verification: Mapping[str, Any],
        prepared_at: str,
        creator_assignment: Mapping[str, str],
        reviewer_assignment: Mapping[str, str],
    ) -> tuple[GeneratedDocumentReviewRecord, bool]:
        tenant_id = require_tenant_id(tenant_id)
        project_id = safe_segment(project_id, field="project_id")
        project_document_id = safe_segment(
            project_document_id, field="project_document_id"
        )
        creator = self._require_assignment(creator_assignment, field="creator_assignment")
        reviewer = self._require_assignment(
            reviewer_assignment, field="reviewer_assignment"
        )
        verified = self._verified_packet(packet_content, packet_verification)
        source = verified["source"]
        if (
            source["tenant_id"] != tenant_id
            or source["project_id"] != project_id
            or source["project_document_id"] != project_document_id
        ):
            raise ValueError("generated document review source identity drift")

        packet_sha256 = verified["packet_sha256"]
        packet_path = self.packet_path(
            tenant_id=tenant_id,
            packet_sha256=packet_sha256,
        )
        record_path = self.record_path(
            tenant_id=tenant_id,
            project_id=project_id,
            project_document_id=project_document_id,
            packet_sha256=packet_sha256,
        )
        candidate = GeneratedDocumentReviewRecord(
            schema_version=RECORD_SCHEMA,
            tenant_id=tenant_id,
            project_id=project_id,
            project_document_id=project_document_id,
            request_id=source["request_id"],
            bundle_id=source["bundle_id"],
            title=source["title"],
            document_source_sha256=source["document_source_sha256"],
            packet_sha256=packet_sha256,
            packet_size_bytes=len(packet_content),
            manifest_sha256=verified["manifest_sha256"],
            artifact_count=verified["artifact_count"],
            formats=list(verified["formats"]),
            prepared_at=prepared_at,
            creator_assignment=creator,
            reviewer_assignment=reviewer,
            review_status="pending",
            review_only=True,
            packet_persisted=True,
            human_review_completed=False,
            operational_approval=False,
            authority={key: False for key in sorted(verified["manifest"]["authority"])},
        )
        canonical_record = serialize_record(candidate)

        try:
            self._backend.write_bytes_if_absent(
                packet_path,
                packet_content,
                content_type="application/zip",
            )
        except StateBackendError as exc:
            observed = self._read_bytes(
                self._backend, packet_path, label="generated document review packet"
            )
            if observed != packet_content:
                raise GeneratedDocumentReviewStoreError(
                    "failed to persist generated document review packet"
                ) from exc
        observed_packet = self._read_bytes(
            self._backend, packet_path, label="generated document review packet"
        )
        if observed_packet != packet_content:
            raise GeneratedDocumentReviewStoreError(
                "generated document review packet is inconsistent"
            )

        existing = self._load_record(record_path)
        if existing is not None:
            self._validate_record_path_binding(
                existing,
                tenant_id=tenant_id,
                project_id=project_id,
                project_document_id=project_document_id,
                packet_sha256=packet_sha256,
            )
            if not self._matches_replay(existing, candidate):
                raise ValueError("generated document review identity drift")
            self.read_packet(existing, tenant_id=tenant_id)
            return existing, False

        try:
            record_created = self._backend.write_text_if_absent(
                record_path,
                canonical_record,
            )
        except StateBackendError as exc:
            observed_raw = self._read_text(
                self._backend, record_path, label="generated document review record"
            )
            if observed_raw != canonical_record:
                raise GeneratedDocumentReviewStoreError(
                    "failed to persist generated document review record"
                ) from exc
            record_created = False

        stored = self._load_record(record_path)
        if stored is None:
            raise GeneratedDocumentReviewStoreError(
                "generated document review record is unavailable"
            )
        self._validate_record_path_binding(
            stored,
            tenant_id=tenant_id,
            project_id=project_id,
            project_document_id=project_document_id,
            packet_sha256=packet_sha256,
        )
        if not self._matches_replay(stored, candidate):
            raise ValueError("generated document review identity drift")
        self.read_packet(stored, tenant_id=tenant_id)
        return stored, record_created

    def get(
        self,
        *,
        tenant_id: str,
        project_id: str,
        project_document_id: str,
        packet_sha256: str,
    ) -> GeneratedDocumentReviewRecord | None:
        tenant_id = require_tenant_id(tenant_id)
        project_id = safe_segment(project_id, field="project_id")
        project_document_id = safe_segment(
            project_document_id, field="project_document_id"
        )
        packet_sha256 = require_sha256(packet_sha256, field="packet_sha256")
        path = self.record_path(
            tenant_id=tenant_id,
            project_id=project_id,
            project_document_id=project_document_id,
            packet_sha256=packet_sha256,
        )
        record = self._load_record(path)
        if record is not None:
            self._validate_record_path_binding(
                record,
                tenant_id=tenant_id,
                project_id=project_id,
                project_document_id=project_document_id,
                packet_sha256=packet_sha256,
            )
        return record

    def read_packet(
        self,
        record: GeneratedDocumentReviewRecord,
        *,
        tenant_id: str,
    ) -> bytes:
        tenant_id = require_tenant_id(tenant_id)
        if record.tenant_id != tenant_id:
            raise ValueError("generated document review tenant identity drift")
        packet_path = self.packet_path(
            tenant_id=tenant_id,
            packet_sha256=record.packet_sha256,
        )
        content = self._read_bytes(
            self._backend,
            packet_path,
            label="generated document review packet",
        )
        if (
            content is None
            or len(content) != record.packet_size_bytes
            or hashlib.sha256(content).hexdigest() != record.packet_sha256
        ):
            raise GeneratedDocumentReviewStoreError(
                "generated document review packet is invalid"
            )
        try:
            verified = verify_generation_export_packet(content)
        except GenerationExportPacketError as exc:
            raise GeneratedDocumentReviewStoreError(
                "generated document review packet is invalid"
            ) from exc
        source = verified["source"]
        if (
            verified["schema"]
            not in {PERSISTED_PACKET_SCHEMA, PERSISTED_PACKET_SCHEMA_V2}
            or verified["manifest_sha256"] != record.manifest_sha256
            or verified["artifact_count"] != record.artifact_count
            or verified["formats"] != record.formats
            or source["tenant_id"] != record.tenant_id
            or source["project_id"] != record.project_id
            or source["project_document_id"] != record.project_document_id
            or source["request_id"] != record.request_id
            or source["bundle_id"] != record.bundle_id
            or source["title"] != record.title
            or source["document_source_sha256"] != record.document_source_sha256
        ):
            raise GeneratedDocumentReviewStoreError(
                "generated document review packet binding is invalid"
            )
        return content

    @staticmethod
    def _same_handoff_identity(
        first: GeneratedDocumentReviewRecord,
        second: GeneratedDocumentReviewRecord,
    ) -> bool:
        fields = (
            "tenant_id",
            "project_id",
            "project_document_id",
            "request_id",
            "bundle_id",
            "title",
            "document_source_sha256",
            "packet_sha256",
            "packet_size_bytes",
            "manifest_sha256",
            "artifact_count",
            "formats",
            "prepared_at",
            "creator_assignment",
            "reviewer_assignment",
        )
        return all(getattr(first, field) == getattr(second, field) for field in fields)

    @staticmethod
    def _matches_completion(
        record: GeneratedDocumentReviewRecord,
        *,
        completion_assignment: Mapping[str, str],
        operation_id: str,
        decision: str,
        rationale: str,
    ) -> bool:
        return (
            record.review_status == "completed"
            and record.completion_assignment == dict(completion_assignment)
            and record.completion_operation_id == operation_id
            and record.review_decision == decision
            and record.review_rationale == rationale
        )

    def complete(
        self,
        record: GeneratedDocumentReviewRecord,
        *,
        tenant_id: str,
        completion_assignment: Mapping[str, str],
        operation_id: str,
        decision: str,
        rationale: str,
        reviewed_at: str,
    ) -> tuple[GeneratedDocumentReviewRecord, bytes, bool]:
        """Complete one pending review through immutable package write and record CAS."""
        tenant_id = require_tenant_id(tenant_id)
        if record.tenant_id != tenant_id:
            raise ValueError("generated document review tenant identity drift")
        completion = self._require_assignment(
            completion_assignment,
            field="completion_assignment",
        )
        record_path = self.record_path(
            tenant_id=tenant_id,
            project_id=record.project_id,
            project_document_id=record.project_document_id,
            packet_sha256=record.packet_sha256,
        )
        current = self._load_record(record_path)
        if current is None:
            raise GeneratedDocumentReviewStoreError(
                "generated document review record is unavailable"
            )
        self._validate_record_path_binding(
            current,
            tenant_id=tenant_id,
            project_id=record.project_id,
            project_document_id=record.project_document_id,
            packet_sha256=record.packet_sha256,
        )
        if not self._same_handoff_identity(current, record):
            raise ValueError("generated document review completion conflict")
        if current.review_status == "completed":
            if not self._matches_completion(
                current,
                completion_assignment=completion,
                operation_id=operation_id,
                decision=decision,
                rationale=rationale,
            ):
                raise ValueError("generated document review completion conflict")
            return (
                current,
                self.read_reviewed_package(current, tenant_id=tenant_id),
                False,
            )

        packet_content = self.read_packet(current, tenant_id=tenant_id)
        reviewed_package, _receipt, receipt_sha256 = (
            build_generated_document_reviewed_package(
                current,
                packet_content,
                completion_assignment=completion,
                operation_id=operation_id,
                decision=decision,
                rationale=rationale,
                reviewed_at=reviewed_at,
            )
        )
        package_sha256 = hashlib.sha256(reviewed_package).hexdigest()
        candidate = replace(
            current,
            schema_version=COMPLETED_RECORD_SCHEMA,
            review_status="completed",
            human_review_completed=True,
            completion_operation_id=operation_id,
            review_decision=decision,
            review_rationale=rationale,
            reviewed_at=reviewed_at,
            completion_assignment=completion,
            completion_receipt_sha256=receipt_sha256,
            reviewed_package_sha256=package_sha256,
            reviewed_package_size_bytes=len(reviewed_package),
        )
        pending_raw = serialize_record(current)
        completed_raw = serialize_record(candidate)
        package_path = self.reviewed_package_path(
            tenant_id=tenant_id,
            reviewed_package_sha256=package_sha256,
        )
        try:
            self._backend.write_bytes_if_absent(
                package_path,
                reviewed_package,
                content_type="application/zip",
            )
        except StateBackendError as exc:
            observed = self._read_bytes(
                self._backend,
                package_path,
                label="generated document reviewed package",
            )
            if observed != reviewed_package:
                raise GeneratedDocumentReviewStoreError(
                    "failed to persist generated document reviewed package"
                ) from exc
        observed_package = self._read_bytes(
            self._backend,
            package_path,
            label="generated document reviewed package",
        )
        if observed_package != reviewed_package:
            raise GeneratedDocumentReviewStoreError(
                "generated document reviewed package is inconsistent"
            )

        try:
            transitioned = self._backend.replace_text_if_equal(
                record_path,
                expected=pending_raw,
                replacement=completed_raw,
            )
        except StateBackendError as exc:
            observed = self._load_record(record_path)
            if observed != candidate:
                raise GeneratedDocumentReviewStoreError(
                    "failed to complete generated document review"
                ) from exc
            transitioned = True
        stored = self._load_record(record_path)
        if stored is None:
            raise GeneratedDocumentReviewStoreError(
                "completed generated document review is unavailable"
            )
        if stored != candidate:
            if self._matches_completion(
                stored,
                completion_assignment=completion,
                operation_id=operation_id,
                decision=decision,
                rationale=rationale,
            ):
                return (
                    stored,
                    self.read_reviewed_package(stored, tenant_id=tenant_id),
                    False,
                )
            raise ValueError("generated document review completion conflict")
        verified_package = self.read_reviewed_package(stored, tenant_id=tenant_id)
        return stored, verified_package, transitioned

    def read_reviewed_package(
        self,
        record: GeneratedDocumentReviewRecord,
        *,
        tenant_id: str,
    ) -> bytes:
        tenant_id = require_tenant_id(tenant_id)
        if record.tenant_id != tenant_id or record.review_status != "completed":
            raise ValueError("generated document review completion identity drift")
        package_path = self.reviewed_package_path(
            tenant_id=tenant_id,
            reviewed_package_sha256=record.reviewed_package_sha256,
        )
        content = self._read_bytes(
            self._backend,
            package_path,
            label="generated document reviewed package",
        )
        if (
            content is None
            or len(content) != record.reviewed_package_size_bytes
            or hashlib.sha256(content).hexdigest() != record.reviewed_package_sha256
        ):
            raise GeneratedDocumentReviewStoreError(
                "generated document reviewed package is invalid"
            )
        packet_content = self.read_packet(record, tenant_id=tenant_id)
        try:
            verify_generated_document_reviewed_package(
                content,
                expected_record=record,
                expected_packet_content=packet_content,
            )
        except GeneratedDocumentReviewedPackageError as exc:
            raise GeneratedDocumentReviewStoreError(
                "generated document reviewed package is invalid"
            ) from exc
        return content

    def list_by_tenant(
        self,
        *,
        tenant_id: str,
    ) -> list[GeneratedDocumentReviewRecord]:
        tenant_id = require_tenant_id(tenant_id)
        prefix = self._root(tenant_id) / "projects"
        try:
            paths = self._backend.list_prefix(str(prefix))
        except StateBackendError as exc:
            raise GeneratedDocumentReviewStoreError(
                "failed to list generated document reviews"
            ) from exc
        records: list[GeneratedDocumentReviewRecord] = []
        for path in paths:
            try:
                parts = Path(path).relative_to(prefix).parts
            except ValueError:
                continue
            if len(parts) != 4 or parts[3] != "record.json":
                continue
            project_id, project_document_id, packet_sha256, _filename = parts
            try:
                record = self.get(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    project_document_id=project_document_id,
                    packet_sha256=packet_sha256,
                )
            except ValueError:
                continue
            if record is not None:
                records.append(record)
        return sorted(records, key=lambda record: record.prepared_at, reverse=True)

    def list_by_project(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> list[GeneratedDocumentReviewRecord]:
        tenant_id = require_tenant_id(tenant_id)
        project_id = safe_segment(project_id, field="project_id")
        return [
            record
            for record in self.list_by_tenant(tenant_id=tenant_id)
            if record.project_id == project_id
        ]
