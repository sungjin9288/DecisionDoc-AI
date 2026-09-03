"""Application service for immutable generated-document review handoffs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.generation_export_packet import (
    ExportFormatInvalidError,
    ExportPacketBuildError,
    build_generated_document_review_packet,
    canonicalize_export_formats,
    verify_generation_export_packet,
)
from app.storage.generated_document_review_models import GeneratedDocumentReviewRecord
from app.storage.generated_document_review_models import require_sha256
from app.storage.generated_document_review_store import (
    GeneratedDocumentReviewStore,
    GeneratedDocumentReviewStoreError,
)
from app.storage.project_store import Project, ProjectDocument, ProjectStore, ProjectStoreError
from app.storage.state_backend import StateBackend
from app.storage.user_store import User, get_user_store


class GeneratedDocumentReviewError(RuntimeError):
    """Base generated-document review service error."""


class GeneratedDocumentReviewNotFoundError(GeneratedDocumentReviewError):
    """Raised for unavailable resources without disclosing their existence."""


class GeneratedDocumentReviewForbiddenError(GeneratedDocumentReviewError):
    """Raised when a current member attempts another user's assignment."""


class GeneratedDocumentReviewConflictError(GeneratedDocumentReviewError):
    """Raised when source or immutable identity cannot support the operation."""


class GeneratedDocumentReviewUnavailableError(GeneratedDocumentReviewError):
    """Raised when persisted review evidence cannot be trusted."""


@dataclass(frozen=True)
class GeneratedDocumentReviewAccess:
    user_id: str
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def scope(self) -> str:
        return "tenant" if self.is_admin else "assigned"

    def assignment(self) -> dict[str, str]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
        }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate document snapshot key")
        result[key] = value
    return result


def parse_project_document_snapshot(document: ProjectDocument) -> list[dict[str, Any]]:
    try:
        value = json.loads(document.doc_snapshot, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise GeneratedDocumentReviewConflictError(
            "project document is not exportable"
        ) from exc
    if not isinstance(value, list) or not value:
        raise GeneratedDocumentReviewConflictError("project document is not exportable")
    for item in value:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("doc_type"), str)
            or not item["doc_type"]
            or not isinstance(item.get("markdown"), str)
        ):
            raise GeneratedDocumentReviewConflictError(
                "project document is not exportable"
            )
    return value


def document_source_sha256(
    *,
    tenant_id: str,
    project_id: str,
    document: ProjectDocument,
    docs: list[dict[str, Any]],
) -> str:
    source = {
        "bundle_id": document.bundle_id,
        "document_snapshot": docs,
        "project_document_id": document.doc_id,
        "project_id": project_id,
        "request_id": document.request_id,
        "tenant_id": tenant_id,
        "title": document.title,
    }
    canonical = json.dumps(
        source,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class GeneratedDocumentReviewService:
    def __init__(
        self,
        *,
        project_store: ProjectStore,
        review_store: GeneratedDocumentReviewStore,
        data_dir: Path,
        state_backend: StateBackend,
    ) -> None:
        self._project_store = project_store
        self._review_store = review_store
        self._data_dir = Path(data_dir)
        self._state_backend = state_backend

    def resolve_access(
        self,
        *,
        tenant_id: str,
        user_id: str,
        username: str,
        role: str,
    ) -> GeneratedDocumentReviewAccess:
        store = get_user_store(
            tenant_id,
            data_dir=self._data_dir,
            backend=self._state_backend,
        )
        user = store.get_by_id(user_id)
        if (
            user is None
            or not user.is_active
            or user.username != username
            or user.role.value != role
            or user.role.value not in {"admin", "member"}
        ):
            raise GeneratedDocumentReviewNotFoundError("current reviewer is unavailable")
        return GeneratedDocumentReviewAccess(
            user_id=user.user_id,
            username=user.username,
            role=user.role.value,
        )

    def _resolve_reviewer(
        self,
        *,
        tenant_id: str,
        reviewer_username: str,
        access: GeneratedDocumentReviewAccess,
    ) -> User:
        if reviewer_username != reviewer_username.strip():
            raise GeneratedDocumentReviewNotFoundError("reviewer is unavailable")
        store = get_user_store(
            tenant_id,
            data_dir=self._data_dir,
            backend=self._state_backend,
        )
        reviewer = store.get_by_username(reviewer_username)
        if (
            reviewer is None
            or not reviewer.is_active
            or reviewer.role.value not in {"admin", "member"}
        ):
            raise GeneratedDocumentReviewNotFoundError("reviewer is unavailable")
        if not access.is_admin and reviewer.user_id != access.user_id:
            raise GeneratedDocumentReviewForbiddenError(
                "member assignment must target the current user"
            )
        return reviewer

    def _project_document(
        self,
        *,
        tenant_id: str,
        project_id: str,
        project_document_id: str,
    ) -> tuple[Project, ProjectDocument]:
        try:
            project = self._project_store.get(project_id, tenant_id=tenant_id)
        except (ProjectStoreError, ValueError) as exc:
            raise GeneratedDocumentReviewUnavailableError(
                "project state is unavailable"
            ) from exc
        if project is None:
            raise GeneratedDocumentReviewNotFoundError("project is unavailable")
        document = next(
            (
                item
                for item in project.documents
                if item.doc_id == project_document_id
            ),
            None,
        )
        if document is None:
            raise GeneratedDocumentReviewNotFoundError("document is unavailable")
        if not all(
            isinstance(value, str) and value
            for value in (
                document.doc_id,
                document.request_id,
                document.bundle_id,
                document.title,
            )
        ):
            raise GeneratedDocumentReviewConflictError(
                "project document is not exportable"
            )
        return project, document

    async def prepare(
        self,
        *,
        tenant_id: str,
        project_id: str,
        project_document_id: str,
        reviewer_username: str,
        formats: list[str],
        access: GeneratedDocumentReviewAccess,
    ) -> tuple[GeneratedDocumentReviewRecord, bytes, bool]:
        try:
            canonical_formats = canonicalize_export_formats(formats)
        except ExportFormatInvalidError:
            raise
        _project, document = self._project_document(
            tenant_id=tenant_id,
            project_id=project_id,
            project_document_id=project_document_id,
        )
        reviewer = self._resolve_reviewer(
            tenant_id=tenant_id,
            reviewer_username=reviewer_username,
            access=access,
        )
        docs = parse_project_document_snapshot(document)
        source_sha256 = document_source_sha256(
            tenant_id=tenant_id,
            project_id=project_id,
            document=document,
            docs=docs,
        )
        try:
            packet = await build_generated_document_review_packet(
                docs=docs,
                title=document.title,
                tenant_id=tenant_id,
                project_id=project_id,
                project_document_id=document.doc_id,
                request_id=document.request_id,
                bundle_id=document.bundle_id,
                document_source_sha256=source_sha256,
                formats=canonical_formats,
            )
            packet_verification = verify_generation_export_packet(packet["content"])
            record, created = self._review_store.prepare(
                tenant_id=tenant_id,
                project_id=project_id,
                project_document_id=document.doc_id,
                packet_content=packet["content"],
                packet_verification=packet_verification,
                prepared_at=datetime.now(timezone.utc).isoformat(),
                creator_assignment=access.assignment(),
                reviewer_assignment={
                    "user_id": reviewer.user_id,
                    "username": reviewer.username,
                    "role": reviewer.role.value,
                },
            )
        except ExportPacketBuildError as exc:
            raise GeneratedDocumentReviewConflictError(
                "project document export failed"
            ) from exc
        except GeneratedDocumentReviewStoreError as exc:
            raise GeneratedDocumentReviewUnavailableError(
                "generated document review state is unavailable"
            ) from exc
        except ValueError as exc:
            raise GeneratedDocumentReviewConflictError(
                "generated document review identity drift"
            ) from exc
        return record, packet["content"], created

    @staticmethod
    def _authorized(
        records: list[GeneratedDocumentReviewRecord],
        access: GeneratedDocumentReviewAccess,
    ) -> list[GeneratedDocumentReviewRecord]:
        if access.is_admin:
            return records
        return [
            record
            for record in records
            if record.reviewer_assignment["user_id"] == access.user_id
        ]

    def source_status(self, record: GeneratedDocumentReviewRecord) -> str:
        try:
            project = self._project_store.get(
                record.project_id,
                tenant_id=record.tenant_id,
            )
        except (ProjectStoreError, ValueError) as exc:
            raise GeneratedDocumentReviewUnavailableError(
                "project state is unavailable"
            ) from exc
        if project is None:
            return "missing"
        document = next(
            (
                item
                for item in project.documents
                if item.doc_id == record.project_document_id
            ),
            None,
        )
        if document is None:
            return "missing"
        try:
            docs = parse_project_document_snapshot(document)
        except GeneratedDocumentReviewConflictError:
            return "changed"
        current_sha256 = document_source_sha256(
            tenant_id=record.tenant_id,
            project_id=record.project_id,
            document=document,
            docs=docs,
        )
        return "current" if current_sha256 == record.document_source_sha256 else "changed"

    def summary(
        self,
        record: GeneratedDocumentReviewRecord,
        *,
        access: GeneratedDocumentReviewAccess,
    ) -> dict[str, Any]:
        summary = record.to_public_dict()
        summary["assigned_to_current_user"] = (
            record.reviewer_assignment["user_id"] == access.user_id
        )
        summary["access_scope"] = access.scope
        summary["source_status"] = self.source_status(record)
        return summary

    def list_inbox(
        self,
        *,
        tenant_id: str,
        access: GeneratedDocumentReviewAccess,
    ) -> list[GeneratedDocumentReviewRecord]:
        try:
            records = self._review_store.list_by_tenant(tenant_id=tenant_id)
        except GeneratedDocumentReviewStoreError as exc:
            raise GeneratedDocumentReviewUnavailableError(
                "generated document reviews are unavailable"
            ) from exc
        return self._authorized(records, access)

    def list_project(
        self,
        *,
        tenant_id: str,
        project_id: str,
        access: GeneratedDocumentReviewAccess,
    ) -> list[GeneratedDocumentReviewRecord]:
        try:
            project = self._project_store.get(project_id, tenant_id=tenant_id)
            records = self._review_store.list_by_project(
                tenant_id=tenant_id,
                project_id=project_id,
            )
        except ValueError as exc:
            raise GeneratedDocumentReviewNotFoundError(
                "project is unavailable"
            ) from exc
        except (ProjectStoreError, GeneratedDocumentReviewStoreError) as exc:
            raise GeneratedDocumentReviewUnavailableError(
                "generated document reviews are unavailable"
            ) from exc
        if project is None:
            raise GeneratedDocumentReviewNotFoundError("project is unavailable")
        authorized = self._authorized(records, access)
        if records and not authorized and not access.is_admin:
            raise GeneratedDocumentReviewNotFoundError(
                "project reviews are unavailable"
            )
        return authorized

    def download(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
        access: GeneratedDocumentReviewAccess,
    ) -> tuple[GeneratedDocumentReviewRecord, bytes, str]:
        try:
            packet_sha256 = require_sha256(packet_sha256, field="packet_sha256")
        except ValueError as exc:
            raise GeneratedDocumentReviewNotFoundError(
                "generated document review is unavailable"
            ) from exc
        records = self.list_project(
            tenant_id=tenant_id,
            project_id=project_id,
            access=access,
        )
        record = next(
            (item for item in records if item.packet_sha256 == packet_sha256),
            None,
        )
        if record is None:
            raise GeneratedDocumentReviewNotFoundError(
                "generated document review is unavailable"
            )
        try:
            content = self._review_store.read_packet(record, tenant_id=tenant_id)
        except (GeneratedDocumentReviewStoreError, ValueError) as exc:
            raise GeneratedDocumentReviewUnavailableError(
                "generated document review packet is unavailable"
            ) from exc
        return record, content, self.source_status(record)
