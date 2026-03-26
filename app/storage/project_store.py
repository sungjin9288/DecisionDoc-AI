"""app/storage/project_store.py — Tenant-scoped project history storage.

Documents are grouped by project with fiscal year archiving.
Storage: data/tenants/{tenant_id}/projects.json (one file per tenant).
Thread-safe via threading.Lock.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import BaseJsonStore, atomic_write_text
from app.storage.state_backend import StateBackend, get_state_backend


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class ProjectStore(BaseJsonStore):
    """Thread-safe, tenant-scoped JSON-backed project history store."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        super().__init__()
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _get_path(self) -> Path:  # multi-tenant: use tenant-specific path helpers below
        return self._base / "tenants"

    def _path(self, tenant_id: str) -> Path:
        p = self._base / "tenants" / tenant_id
        if self._backend.kind == "local":
            p.mkdir(parents=True, exist_ok=True)
        return p / "projects.json"

    def _relative_path(self, tenant_id: str) -> str:
        return str(Path("tenants") / tenant_id / "projects.json")

    def _load(self, tenant_id: str) -> list[dict]:
        raw = self._backend.read_text(self._relative_path(tenant_id))
        if raw is None:
            return []
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return []

    def _save(self, tenant_id: str, records: list[dict]) -> None:
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        if self._backend.kind == "local":
            atomic_write_text(self._path(tenant_id), payload)
            return
        self._backend.write_text(self._relative_path(tenant_id), payload)

    @staticmethod
    def _doc_from_dict(d: dict) -> ProjectDocument:
        return ProjectDocument(
            doc_id=d["doc_id"],
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
        )

    @staticmethod
    def _from_dict(d: dict) -> Project:
        docs = [ProjectStore._doc_from_dict(doc) for doc in d.get("documents", [])]
        return Project(
            project_id=d["project_id"],
            tenant_id=d["tenant_id"],
            name=d.get("name", ""),
            description=d.get("description", ""),
            client=d.get("client", ""),
            contract_number=d.get("contract_number", ""),
            fiscal_year=d.get("fiscal_year", datetime.now().year),
            status=d.get("status", "active"),
            created_at=d["created_at"],
            updated_at=d.get("updated_at", d["created_at"]),
            documents=docs,
            tags=d.get("tags", []),
        )

    def _find(self, project_id: str, tenant_id: str | None = None) -> tuple[str, list[dict], int, Project] | None:
        """Find a project scoped to the given tenant (caller holds lock).

        If tenant_id is provided, only that tenant's records are searched,
        preventing cross-tenant IDOR. Falls back to full scan only when
        tenant_id is None (internal maintenance use).
        """
        if tenant_id is not None:
            # Scoped lookup — only search within the specified tenant
            records = self._load(tenant_id)
            for i, r in enumerate(records):
                if r.get("project_id") == project_id:
                    proj = self._from_dict(r)
                    if proj.tenant_id != tenant_id:
                        return None  # Mismatch — deny access
                    return tenant_id, records, i, proj
            return None
        # Unscoped fallback (for backward compatibility with internal callers)
        tenant_paths = self._backend.list_prefix("tenants/")
        tenant_ids = sorted(
            {
                Path(path).parts[1]
                for path in tenant_paths
                if len(Path(path).parts) >= 3 and Path(path).parts[0] == "tenants"
            }
        )
        for tid in tenant_ids:
            records = self._load(tid)
            for i, r in enumerate(records):
                if r.get("project_id") == project_id:
                    return tid, records, i, self._from_dict(r)
        return None

    def _flush(self, tenant_id: str, records: list[dict], idx: int, proj: Project) -> Project:
        proj.updated_at = _now_iso()
        records[idx] = asdict(proj)
        self._save(tenant_id, records)
        return proj

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
        with self._lock:
            records = self._load(tenant_id)
            now = _now_iso()
            proj = Project(
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
            records.append(asdict(proj))
            self._save(tenant_id, records)
            return proj

    def get(self, project_id: str, tenant_id: str | None = None) -> Project | None:
        with self._lock:
            result = self._find(project_id, tenant_id=tenant_id)
            return result[3] if result else None

    def list_by_tenant(
        self,
        tenant_id: str,
        status: str | None = None,
        fiscal_year: int | None = None,
    ) -> list[Project]:
        with self._lock:
            records = [self._from_dict(r) for r in self._load(tenant_id)]
        if status:
            records = [r for r in records if r.status == status]
        if fiscal_year:
            records = [r for r in records if r.fiscal_year == fiscal_year]
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def update(self, project_id: str, tenant_id: str | None = None, **kwargs: Any) -> Project:
        """Update allowed fields: name, description, client, contract_number, status, tags, fiscal_year."""
        ALLOWED = {"name", "description", "client", "contract_number", "status", "tags", "fiscal_year"}
        with self._lock:
            result = self._find(project_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")
            tenant_id, records, idx, proj = result
            for k, v in kwargs.items():
                if k in ALLOWED and v is not None:
                    setattr(proj, k, v)
            return self._flush(tenant_id, records, idx, proj)

    def delete(self, project_id: str, tenant_id: str | None = None) -> None:
        """Permanently delete a project (documents are unlinked, not deleted)."""
        with self._lock:
            result = self._find(project_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")
            tid, records, idx, _ = result
            del records[idx]
            self._save(tid, records)

    def archive(self, project_id: str, tenant_id: str | None = None) -> Project:
        return self.update(project_id, tenant_id=tenant_id, status="archived")

    def add_document(
        self,
        project_id: str,
        request_id: str,
        bundle_id: str,
        title: str,
        docs: list[dict],
        approval_id: str | None = None,
        tags: list[str] | None = None,
        gov_options: dict | None = None,
        tenant_id: str | None = None,
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
        )
        with self._lock:
            result = self._find(project_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")
            tenant_id, records, idx, proj = result
            proj.documents.append(doc)
            self._flush(tenant_id, records, idx, proj)
        return doc

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
    ) -> tuple[ProjectDocument, str]:
        docs_json = json.dumps(docs, ensure_ascii=False)
        file_size = sum(len(d.get("markdown", "")) for d in docs)
        resolved_generated_at = generated_at or _now_iso()
        with self._lock:
            result = self._find(project_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

            tenant_id, records, idx, proj = result
            existing = next(
                (
                    doc for doc in proj.documents
                    if doc.source_kind == "voice_brief"
                    and doc.source_recording_id == source_recording_id
                    and doc.source_summary_revision_id == source_summary_revision_id
                ),
                None,
            )

            if existing is None:
                doc = ProjectDocument(
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
                proj.documents.append(doc)
                operation = "created"
            else:
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
                doc = existing
                operation = "updated"

            self._flush(tenant_id, records, idx, proj)
            return doc, operation

    def remove_document(self, project_id: str, doc_id: str, tenant_id: str | None = None) -> None:
        with self._lock:
            result = self._find(project_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")
            tenant_id, records, idx, proj = result
            proj.documents = [d for d in proj.documents if d.doc_id != doc_id]
            self._flush(tenant_id, records, idx, proj)

    def update_document_approval(
        self,
        project_id: str,
        request_id: str,
        approval_id: str,
        approval_status: str,
        tenant_id: str | None = None,
    ) -> None:
        """Update approval_id and approval_status on document(s) matching request_id."""
        with self._lock:
            result = self._find(project_id, tenant_id=tenant_id)
            if result is None:
                return  # silently ignore missing project
            tenant_id, records, idx, proj = result
            updated = False
            for doc in proj.documents:
                if doc.request_id == request_id:
                    doc.approval_id = approval_id
                    doc.approval_status = approval_status
                    updated = True
            if updated:
                self._flush(tenant_id, records, idx, proj)

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
