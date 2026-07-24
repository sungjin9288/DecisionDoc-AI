"""app/storage/project_store.py — Tenant-scoped project history storage.

Documents are grouped by project with fiscal year archiving.
Storage: data/tenants/{tenant_id}/projects.json (one file per tenant).
Concurrent changes use process-local locking plus backend conditional writes.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal, TypeVar

from app.storage.project_state_mutation import (
    ProjectStateMutationMixin,
    ProjectStoreError,
)
from app.storage.state_backend import StateBackend, get_state_backend
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


_MutationResult = TypeVar("_MutationResult")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_source_evidence_refs(values: list[str] | None) -> list[str]:
    refs: set[str] = set()
    for value in values or []:
        ref = str(value).strip()
        if (
            not ref.startswith("requirement:")
            or len(ref) > 500
            or any(ord(char) < 32 for char in ref)
        ):
            raise ValueError("Invalid project document evidence reference")
        refs.add(ref)
    if len(refs) > 200:
        raise ValueError("Too many project document evidence references")
    return sorted(refs)


@dataclass
class ProjectDocument:
    doc_id: str
    request_id: str
    bundle_id: str
    title: str
    generated_at: str
    approval_id: str | None
    approval_status: str | None
    tags: list[str]
    doc_snapshot: str     # JSON string of docs list
    gov_options: dict | None
    file_size_chars: int
    source_kind: str | None = None
    source_recording_id: str | None = None
    source_summary_revision_id: str | None = None
    source_review_status: str | None = None
    source_sync_status: str | None = None
    source_use_case: str | None = None
    source_audio_url: str | None = None
    source_decision_council_session_id: str | None = None
    source_decision_council_session_revision: int | None = None
    source_decision_council_direction: str | None = None
    source_procurement_review_packet_sha256: str | None = None
    source_procurement_review_decision: str | None = None
    source_procurement_reviewed_at: str | None = None
    source_procurement_review_source_updated_at: str | None = None
    source_procurement_review_operational_approval: bool | None = None
    source_evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Project:
    project_id: str
    tenant_id: str
    name: str
    description: str
    client: str
    contract_number: str
    fiscal_year: int
    status: str           # "active" | "completed" | "archived"
    created_at: str
    updated_at: str
    documents: list[ProjectDocument]
    tags: list[str]


class ProjectStore(ProjectStateMutationMixin):
    """Thread-safe, tenant-scoped JSON-backed project history store."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _relative_path(self, tenant_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        return str(Path("tenants") / tenant_id / "projects.json")

    def _lock(self, tenant_id: str):
        relative_path = self._relative_path(tenant_id)
        return state_lock(
            self._backend,
            data_dir=self._base,
            relative_path=relative_path,
        )

    @staticmethod
    def _doc_from_dict(d: dict) -> ProjectDocument:
        if not isinstance(d, dict):
            raise ProjectStoreError("Invalid project document record")
        doc_id = d.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id:
            raise ProjectStoreError("Invalid project document identity")
        return ProjectDocument(
            doc_id=doc_id,
            request_id=d.get("request_id", ""),
            bundle_id=d.get("bundle_id", ""),
            title=d.get("title", ""),
            generated_at=d.get("generated_at", ""),
            approval_id=d.get("approval_id"),
            approval_status=d.get("approval_status"),
            tags=d.get("tags", []),
            doc_snapshot=d.get("doc_snapshot", "[]"),
            gov_options=d.get("gov_options"),
            file_size_chars=d.get("file_size_chars", 0),
            source_kind=d.get("source_kind"),
            source_recording_id=d.get("source_recording_id"),
            source_summary_revision_id=d.get("source_summary_revision_id"),
            source_review_status=d.get("source_review_status"),
            source_sync_status=d.get("source_sync_status"),
            source_use_case=d.get("source_use_case"),
            source_audio_url=d.get("source_audio_url"),
            source_decision_council_session_id=d.get("source_decision_council_session_id"),
            source_decision_council_session_revision=d.get("source_decision_council_session_revision"),
            source_decision_council_direction=d.get("source_decision_council_direction"),
            source_procurement_review_packet_sha256=d.get(
                "source_procurement_review_packet_sha256"
            ),
            source_procurement_review_decision=d.get("source_procurement_review_decision"),
            source_procurement_reviewed_at=d.get("source_procurement_reviewed_at"),
            source_procurement_review_source_updated_at=d.get(
                "source_procurement_review_source_updated_at"
            ),
            source_procurement_review_operational_approval=d.get(
                "source_procurement_review_operational_approval"
            ),
            source_evidence_refs=_normalize_source_evidence_refs(
                d.get("source_evidence_refs")
            ),
        )

    @staticmethod
    def _from_dict(d: dict) -> Project:
        if not isinstance(d, dict):
            raise ProjectStoreError("Invalid project record")
        project_id = d.get("project_id")
        tenant_id = d.get("tenant_id")
        created_at = d.get("created_at")
        documents = d.get("documents", [])
        if not isinstance(project_id, str) or not project_id:
            raise ProjectStoreError("Invalid project identity")
        if not isinstance(tenant_id, str) or not isinstance(created_at, str):
            raise ProjectStoreError("Invalid project identity")
        require_tenant_id(tenant_id)
        if not isinstance(documents, list):
            raise ProjectStoreError("Invalid project documents")

        docs = [ProjectStore._doc_from_dict(doc) for doc in documents]
        doc_ids = [doc.doc_id for doc in docs]
        if len(doc_ids) != len(set(doc_ids)):
            raise ProjectStoreError("Duplicate project document records")
        return Project(
            project_id=project_id,
            tenant_id=tenant_id,
            name=d.get("name", ""),
            description=d.get("description", ""),
            client=d.get("client", ""),
            contract_number=d.get("contract_number", ""),
            fiscal_year=d.get("fiscal_year", datetime.now().year),
            status=d.get("status", "active"),
            created_at=created_at,
            updated_at=d.get("updated_at", created_at),
            documents=docs,
            tags=d.get("tags", []),
        )

    def _owned_records(
        self,
        records: list[Any],
        *,
        tenant_id: str,
    ) -> list[tuple[int, Project]]:
        tenant_id = require_tenant_id(tenant_id)
        owned: list[tuple[int, Project]] = []
        project_ids: set[str] = set()
        for index, raw_record in enumerate(records):
            if not isinstance(raw_record, dict):
                continue
            if raw_record.get("tenant_id") != tenant_id:
                continue
            project_id = raw_record.get("project_id")
            if not isinstance(project_id, str) or not project_id:
                continue
            try:
                self._mutation_ids(raw_record)
                project = self._from_dict(raw_record)
            except (KeyError, TypeError, ValueError, ProjectStoreError) as exc:
                raise ProjectStoreError("Invalid owned project record") from exc
            if project.project_id in project_ids:
                raise ProjectStoreError("Duplicate project records")
            project_ids.add(project.project_id)
            owned.append((index, project))
        return owned

    def _find(
        self,
        project_id: str,
        *,
        tenant_id: str,
    ) -> tuple[int, Project] | None:
        """Locate a project only within the caller's tenant."""
        tenant_id = require_tenant_id(tenant_id)
        return self._find_in_records(
            project_id,
            records=self._load(tenant_id),
            tenant_id=tenant_id,
        )

    def _find_in_records(
        self,
        project_id: str,
        *,
        records: list[dict],
        tenant_id: str,
    ) -> tuple[int, Project] | None:
        for index, project in self._owned_records(records, tenant_id=tenant_id):
            if project.project_id == project_id:
                return index, project
        return None

    def _mutate_project(
        self,
        project_id: str,
        *,
        tenant_id: str,
        change: Callable[[Project], tuple[_MutationResult, bool]],
    ) -> _MutationResult:
        tenant_id = require_tenant_id(tenant_id)
        mutation_id = uuid.uuid4().hex

        def apply(records: list[dict]) -> tuple[_MutationResult, bool]:
            found = self._find_in_records(
                project_id,
                records=records,
                tenant_id=tenant_id,
            )
            if found is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")
            index, project = found
            result, changed = change(project)
            if changed:
                project.updated_at = _now_iso()
                records[index] = self._record_project(
                    project,
                    previous=records[index],
                    mutation_id=mutation_id,
                )
            return result, changed

        def mutation_committed(records: list[dict]) -> bool:
            found = self._find_in_records(
                project_id,
                records=records,
                tenant_id=tenant_id,
            )
            if found is None:
                return False
            index, _ = found
            return mutation_id in self._mutation_ids(records[index])

        with self._lock(tenant_id):
            return self._mutate_state(
                tenant_id,
                apply,
                committed=mutation_committed,
            )

    # ── Public API ──────────────────────────────────────────────────────

    def create(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        client: str = "",
        contract_number: str = "",
        fiscal_year: int | None = None,
    ) -> Project:
        tenant_id = require_tenant_id(tenant_id)
        now = _now_iso()
        project = Project(
            project_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=name,
            description=description,
            client=client,
            contract_number=contract_number,
            fiscal_year=fiscal_year or datetime.now().year,
            status="active",
            created_at=now,
            updated_at=now,
            documents=[],
            tags=[],
        )
        mutation_id = uuid.uuid4().hex

        def append_project(records: list[dict]) -> tuple[Project, bool]:
            records.append(
                self._record_project(
                    project,
                    previous=None,
                    mutation_id=mutation_id,
                )
            )
            return project, True

        def mutation_committed(records: list[dict]) -> bool:
            found = self._find_in_records(
                project.project_id,
                records=records,
                tenant_id=tenant_id,
            )
            if found is None:
                return False
            index, _ = found
            return mutation_id in self._mutation_ids(records[index])

        with self._lock(tenant_id):
            return self._mutate_state(
                tenant_id,
                append_project,
                committed=mutation_committed,
            )

    def get(self, project_id: str, *, tenant_id: str) -> Project | None:
        with self._lock(tenant_id):
            result = self._find(project_id, tenant_id=tenant_id)
            return result[1] if result else None

    def list_by_tenant(
        self,
        tenant_id: str,
        status: str | None = None,
        fiscal_year: int | None = None,
    ) -> list[Project]:
        tenant_id = require_tenant_id(tenant_id)
        with self._lock(tenant_id):
            records = [
                project
                for _, project in self._owned_records(
                    self._load(tenant_id),
                    tenant_id=tenant_id,
                )
            ]
        if status:
            records = [r for r in records if r.status == status]
        if fiscal_year:
            records = [r for r in records if r.fiscal_year == fiscal_year]
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def update(self, project_id: str, *, tenant_id: str, **kwargs: Any) -> Project:
        """Update allowed fields: name, description, client, contract_number, status, tags, fiscal_year."""
        allowed = {"name", "description", "client", "contract_number", "status", "tags", "fiscal_year"}

        def update_fields(project: Project) -> tuple[Project, bool]:
            for key, value in kwargs.items():
                if key in allowed and value is not None:
                    setattr(project, key, value)
            return project, True

        return self._mutate_project(
            project_id,
            tenant_id=tenant_id,
            change=update_fields,
        )

    def delete(self, project_id: str, *, tenant_id: str) -> None:
        """Permanently delete a project (documents are unlinked, not deleted)."""
        tenant_id = require_tenant_id(tenant_id)

        def delete_project(records: list[dict]) -> tuple[None, bool]:
            found = self._find_in_records(
                project_id,
                records=records,
                tenant_id=tenant_id,
            )
            if found is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")
            index, _ = found
            del records[index]
            return None, True

        def mutation_committed(records: list[dict]) -> bool:
            return self._find_in_records(
                project_id,
                records=records,
                tenant_id=tenant_id,
            ) is None

        with self._lock(tenant_id):
            self._mutate_state(
                tenant_id,
                delete_project,
                committed=mutation_committed,
            )

    def archive(self, project_id: str, *, tenant_id: str) -> Project:
        return self.update(project_id, tenant_id=tenant_id, status="archived")

    def add_document(
        self,
        project_id: str,
        request_id: str,
        bundle_id: str,
        title: str,
        docs: list[dict],
        *,
        tenant_id: str,
        approval_id: str | None = None,
        tags: list[str] | None = None,
        gov_options: dict | None = None,
        source_kind: str | None = None,
        source_recording_id: str | None = None,
        source_summary_revision_id: str | None = None,
        source_review_status: str | None = None,
        source_sync_status: str | None = None,
        source_use_case: str | None = None,
        source_audio_url: str | None = None,
        source_decision_council_session_id: str | None = None,
        source_decision_council_session_revision: int | None = None,
        source_decision_council_direction: str | None = None,
        source_procurement_review_packet_sha256: str | None = None,
        source_procurement_review_decision: str | None = None,
        source_procurement_reviewed_at: str | None = None,
        source_procurement_review_source_updated_at: str | None = None,
        source_procurement_review_operational_approval: bool | None = None,
        source_evidence_refs: list[str] | None = None,
    ) -> ProjectDocument:
        docs_json = json.dumps(docs, ensure_ascii=False)
        file_size = sum(len(d.get("markdown", "")) for d in docs)
        doc = ProjectDocument(
            doc_id=str(uuid.uuid4()),
            request_id=request_id,
            bundle_id=bundle_id,
            title=title,
            generated_at=_now_iso(),
            approval_id=approval_id,
            approval_status=None,
            tags=tags or [],
            doc_snapshot=docs_json,
            gov_options=gov_options,
            file_size_chars=file_size,
            source_kind=source_kind,
            source_recording_id=source_recording_id,
            source_summary_revision_id=source_summary_revision_id,
            source_review_status=source_review_status,
            source_sync_status=source_sync_status,
            source_use_case=source_use_case,
            source_audio_url=source_audio_url,
            source_decision_council_session_id=source_decision_council_session_id,
            source_decision_council_session_revision=source_decision_council_session_revision,
            source_decision_council_direction=source_decision_council_direction,
            source_procurement_review_packet_sha256=source_procurement_review_packet_sha256,
            source_procurement_review_decision=source_procurement_review_decision,
            source_procurement_reviewed_at=source_procurement_reviewed_at,
            source_procurement_review_source_updated_at=(
                source_procurement_review_source_updated_at
            ),
            source_procurement_review_operational_approval=(
                source_procurement_review_operational_approval
            ),
            source_evidence_refs=_normalize_source_evidence_refs(
                source_evidence_refs
            ),
        )

        def append_document(project: Project) -> tuple[ProjectDocument, bool]:
            project.documents.append(doc)
            return doc, True

        return self._mutate_project(
            project_id,
            tenant_id=tenant_id,
            change=append_document,
        )

    def upsert_voice_brief_document(
        self,
        *,
        project_id: str,
        tenant_id: str,
        request_id: str,
        title: str,
        docs: list[dict],
        tags: list[str] | None = None,
        generated_at: str | None = None,
        source_recording_id: str,
        source_summary_revision_id: str,
        source_review_status: str | None = None,
        source_sync_status: str | None = None,
        source_use_case: str | None = None,
        source_audio_url: str | None = None,
    ) -> tuple[ProjectDocument, Literal["created", "updated"]]:
        docs_json = json.dumps(docs, ensure_ascii=False)
        file_size = sum(len(d.get("markdown", "")) for d in docs)
        resolved_generated_at = generated_at or _now_iso()
        new_document = ProjectDocument(
            doc_id=str(uuid.uuid4()),
            request_id=request_id,
            bundle_id="voice_brief_import",
            title=title,
            generated_at=resolved_generated_at,
            approval_id=None,
            approval_status=None,
            tags=tags or [],
            doc_snapshot=docs_json,
            gov_options=None,
            file_size_chars=file_size,
            source_kind="voice_brief",
            source_recording_id=source_recording_id,
            source_summary_revision_id=source_summary_revision_id,
            source_review_status=source_review_status,
            source_sync_status=source_sync_status,
            source_use_case=source_use_case,
            source_audio_url=source_audio_url,
        )

        def upsert(
            project: Project,
        ) -> tuple[tuple[ProjectDocument, Literal["created", "updated"]], bool]:
            existing = next(
                (
                    doc for doc in project.documents
                    if doc.source_kind == "voice_brief"
                    and doc.source_recording_id == source_recording_id
                    and doc.source_summary_revision_id == source_summary_revision_id
                ),
                None,
            )
            if existing is None:
                existing = next(
                    (
                        doc for doc in reversed(project.documents)
                        if doc.source_kind == "voice_brief"
                        and doc.source_recording_id == source_recording_id
                    ),
                    None,
                )

            if existing is None:
                project.documents.append(new_document)
                return (new_document, "created"), True

            existing.request_id = request_id
            existing.bundle_id = "voice_brief_import"
            existing.title = title
            existing.generated_at = resolved_generated_at
            existing.approval_id = None
            existing.approval_status = None
            existing.tags = tags or []
            existing.doc_snapshot = docs_json
            existing.gov_options = None
            existing.file_size_chars = file_size
            existing.source_kind = "voice_brief"
            existing.source_recording_id = source_recording_id
            existing.source_summary_revision_id = source_summary_revision_id
            existing.source_review_status = source_review_status
            existing.source_sync_status = source_sync_status
            existing.source_use_case = source_use_case
            existing.source_audio_url = source_audio_url
            return (existing, "updated"), True

        return self._mutate_project(
            project_id,
            tenant_id=tenant_id,
            change=upsert,
        )

    def remove_document(
        self,
        project_id: str,
        doc_id: str,
        *,
        tenant_id: str,
    ) -> None:
        def remove(project: Project) -> tuple[None, bool]:
            project.documents = [
                document
                for document in project.documents
                if document.doc_id != doc_id
            ]
            return None, True

        self._mutate_project(
            project_id,
            tenant_id=tenant_id,
            change=remove,
        )

    def update_document_approval(
        self,
        project_id: str,
        request_id: str,
        approval_id: str,
        approval_status: str,
        *,
        tenant_id: str,
    ) -> None:
        """Update approval_id and approval_status on document(s) matching request_id."""
        tenant_id = require_tenant_id(tenant_id)
        mutation_id = uuid.uuid4().hex

        def update_approval(records: list[dict]) -> tuple[None, bool]:
            found = self._find_in_records(
                project_id,
                records=records,
                tenant_id=tenant_id,
            )
            if found is None:
                return None, False
            index, project = found
            updated = False
            for document in project.documents:
                if document.request_id == request_id:
                    document.approval_id = approval_id
                    document.approval_status = approval_status
                    updated = True
            if updated:
                project.updated_at = _now_iso()
                records[index] = self._record_project(
                    project,
                    previous=records[index],
                    mutation_id=mutation_id,
                )
            return None, updated

        def mutation_committed(records: list[dict]) -> bool:
            found = self._find_in_records(
                project_id,
                records=records,
                tenant_id=tenant_id,
            )
            if found is None:
                return False
            index, _ = found
            return mutation_id in self._mutation_ids(records[index])

        with self._lock(tenant_id):
            self._mutate_state(
                tenant_id,
                update_approval,
                committed=mutation_committed,
            )

    def search(
        self,
        tenant_id: str,
        query: str,
        fiscal_year: int | None = None,
    ) -> list[dict]:
        """Search across project name, client, document titles, tags.
        Returns list of {project_id, project_name, matched_docs: list}."""
        q = query.lower()
        if not q:
            return []
        projects = self.list_by_tenant(tenant_id, fiscal_year=fiscal_year)
        results = []
        for proj in projects:
            matched_docs = []
            # match on doc title / tags
            for doc in proj.documents:
                if q in doc.title.lower() or any(q in t.lower() for t in doc.tags):
                    matched_docs.append({"doc_id": doc.doc_id, "title": doc.title, "bundle_id": doc.bundle_id})
            # match on project-level fields
            project_match = (
                q in proj.name.lower()
                or q in proj.client.lower()
                or q in proj.description.lower()
                or any(q in t.lower() for t in proj.tags)
            )
            if project_match or matched_docs:
                results.append({
                    "project_id": proj.project_id,
                    "project_name": proj.name,
                    "matched_docs": matched_docs,
                })
        return results

    def get_yearly_archive(self, tenant_id: str, fiscal_year: int) -> dict:
        """Return archive summary for a given fiscal year."""
        projects = self.list_by_tenant(tenant_id, fiscal_year=fiscal_year)
        total_docs = sum(len(p.documents) for p in projects)
        bundle_breakdown: dict[str, int] = {}
        for proj in projects:
            for doc in proj.documents:
                bundle_breakdown[doc.bundle_id] = bundle_breakdown.get(doc.bundle_id, 0) + 1
        return {
            "fiscal_year": fiscal_year,
            "projects": [asdict(p) for p in projects],
            "total_docs": total_docs,
            "bundle_breakdown": bundle_breakdown,
        }

    def get_stats(self, tenant_id: str) -> dict:
        """Return dashboard stats for the tenant."""
        projects = self.list_by_tenant(tenant_id)
        total_projects = len(projects)
        active_projects = sum(1 for p in projects if p.status == "active")
        total_docs = sum(len(p.documents) for p in projects)
        by_year: dict[int, int] = {}
        by_bundle: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for proj in projects:
            by_year[proj.fiscal_year] = by_year.get(proj.fiscal_year, 0) + len(proj.documents)
            by_status[proj.status] = by_status.get(proj.status, 0) + 1
            for doc in proj.documents:
                by_bundle[doc.bundle_id] = by_bundle.get(doc.bundle_id, 0) + 1
        return {
            "total_projects": total_projects,
            "active_projects": active_projects,
            "total_docs": total_docs,
            "by_year": by_year,
            "by_bundle": by_bundle,
            "by_status": by_status,
        }
