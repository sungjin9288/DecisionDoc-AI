"""app/storage/approval_store.py — Tenant-scoped approval workflow storage.

Documents go through: 기안(Draft) → 검토(Review) → 승인(Approval) stages.
Storage: data/tenants/{tenant_id}/approvals.json (one file per tenant).
Thread-safe via a single threading.Lock per store instance.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.storage.base import BaseJsonStore, atomic_write_text
from app.storage.state_backend import StateBackend, get_state_backend


class ApprovalStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    REJECTED = "rejected"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ApprovalComment:
    comment_id: str
    stage: str              # "review" | "approval"
    author: str
    content: str
    created_at: str
    is_change_request: bool = False


@dataclass
class ApprovalRecord:
    approval_id: str
    tenant_id: str
    request_id: str
    bundle_id: str
    title: str
    status: str             # ApprovalStatus value
    drafter: str
    reviewer: str | None
    approver: str | None
    created_at: str
    submitted_at: str | None
    reviewed_at: str | None
    approved_at: str | None
    rejected_at: str | None
    comments: list[ApprovalComment]
    doc_snapshot: str       # JSON string of docs at first submission (immutable)
    current_docs: str       # JSON string of latest docs
    gov_options: dict | None
    reviewer_approved: bool = False   # internal: reviewer has approved


class ApprovalStore(BaseJsonStore):
    """Thread-safe, tenant-scoped JSON-backed approval workflow store."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        super().__init__()
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _get_path(self) -> Path:  # multi-tenant: use tenant-specific path helpers below
        return self._base / "tenants"

    # ── Persistence helpers ─────────────────────────────────────────────

    def _path(self, tenant_id: str) -> Path:
        p = self._base / "tenants" / tenant_id
        if self._backend.kind == "local":
            p.mkdir(parents=True, exist_ok=True)
        return p / "approvals.json"

    def _relative_path(self, tenant_id: str) -> str:
        return str(Path("tenants") / tenant_id / "approvals.json")

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
    def _to_dict(rec: ApprovalRecord) -> dict:
        return asdict(rec)

    @staticmethod
    def _from_dict(d: dict) -> ApprovalRecord:
        comments = [ApprovalComment(**c) for c in d.get("comments", [])]
        return ApprovalRecord(
            approval_id=d["approval_id"],
            tenant_id=d["tenant_id"],
            request_id=d.get("request_id", ""),
            bundle_id=d.get("bundle_id", ""),
            title=d.get("title", ""),
            status=d["status"],
            drafter=d.get("drafter", ""),
            reviewer=d.get("reviewer"),
            approver=d.get("approver"),
            created_at=d["created_at"],
            submitted_at=d.get("submitted_at"),
            reviewed_at=d.get("reviewed_at"),
            approved_at=d.get("approved_at"),
            rejected_at=d.get("rejected_at"),
            comments=comments,
            doc_snapshot=d.get("doc_snapshot", "[]"),
            current_docs=d.get("current_docs", "[]"),
            gov_options=d.get("gov_options"),
            reviewer_approved=d.get("reviewer_approved", False),
        )

    def _find(self, approval_id: str, tenant_id: str | None = None) -> tuple[str, list[dict], int, ApprovalRecord] | None:
        """Locate a record scoped to the given tenant (caller holds lock).

        If tenant_id is provided, only that tenant's records are searched,
        preventing cross-tenant IDOR. Falls back to full scan only when
        tenant_id is None (internal maintenance use).
        """
        if tenant_id is not None:
            # Scoped lookup — only search within the specified tenant
            records = self._load(tenant_id)
            for i, r in enumerate(records):
                if r.get("approval_id") == approval_id:
                    rec = self._from_dict(r)
                    if rec.tenant_id != tenant_id:
                        return None  # Mismatch — deny access
                    return tenant_id, records, i, rec
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
                if r.get("approval_id") == approval_id:
                    return tid, records, i, self._from_dict(r)
        return None

    def _flush(self, tenant_id: str, records: list[dict], idx: int, rec: ApprovalRecord) -> ApprovalRecord:
        records[idx] = self._to_dict(rec)
        self._save(tenant_id, records)
        return rec

    # ── Public API ──────────────────────────────────────────────────────

    def create(
        self,
        tenant_id: str,
        request_id: str,
        bundle_id: str,
        title: str,
        drafter: str,
        docs: list[dict],
        gov_options: dict | None = None,
    ) -> ApprovalRecord:
        with self._lock:
            records = self._load(tenant_id)
            docs_json = json.dumps(docs, ensure_ascii=False)
            rec = ApprovalRecord(
                approval_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                request_id=request_id,
                bundle_id=bundle_id,
                title=title,
                status=ApprovalStatus.DRAFT.value,
                drafter=drafter,
                reviewer=None,
                approver=None,
                created_at=_now_iso(),
                submitted_at=None,
                reviewed_at=None,
                approved_at=None,
                rejected_at=None,
                comments=[],
                doc_snapshot=docs_json,
                current_docs=docs_json,
                gov_options=gov_options,
                reviewer_approved=False,
            )
            records.append(self._to_dict(rec))
            self._save(tenant_id, records)
            return rec

    def get(self, approval_id: str, tenant_id: str | None = None) -> ApprovalRecord | None:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            return result[3] if result else None

    def list_by_tenant(
        self, tenant_id: str, status: str | None = None
    ) -> list[ApprovalRecord]:
        with self._lock:
            records = [self._from_dict(r) for r in self._load(tenant_id)]
        if status:
            records = [r for r in records if r.status == status]
        return sorted(records, key=lambda r: r.created_at, reverse=True)

    def list_by_user(
        self, tenant_id: str, username: str, role: str
    ) -> list[ApprovalRecord]:
        all_recs = self.list_by_tenant(tenant_id)
        field_map = {"drafter": "drafter", "reviewer": "reviewer", "approver": "approver"}
        attr = field_map.get(role)
        if attr:
            return [r for r in all_recs if getattr(r, attr) == username]
        return all_recs

    def submit_for_review(self, approval_id: str, reviewer: str, tenant_id: str | None = None) -> ApprovalRecord:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            allowed = {ApprovalStatus.DRAFT.value, ApprovalStatus.CHANGES_REQUESTED.value}
            if rec.status not in allowed:
                raise ValueError(
                    f"상태 전환 오류: '{rec.status}' 상태에서는 검토 요청을 할 수 없습니다. "
                    f"(허용 상태: draft, changes_requested)"
                )
            rec.status = ApprovalStatus.IN_REVIEW.value
            rec.reviewer = reviewer or rec.reviewer
            rec.submitted_at = _now_iso()
            rec.reviewer_approved = False
            return self._flush(tenant_id, records, idx, rec)

    def request_changes(self, approval_id: str, author: str, comment: str, tenant_id: str | None = None) -> ApprovalRecord:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            if rec.status != ApprovalStatus.IN_REVIEW.value:
                raise ValueError(
                    f"상태 전환 오류: '{rec.status}' 상태에서는 수정 요청을 할 수 없습니다. "
                    f"(허용 상태: in_review)"
                )
            rec.status = ApprovalStatus.CHANGES_REQUESTED.value
            rec.reviewer_approved = False
            rec.comments.append(ApprovalComment(
                comment_id=str(uuid.uuid4()), stage="review", author=author,
                content=comment, created_at=_now_iso(), is_change_request=True,
            ))
            return self._flush(tenant_id, records, idx, rec)

    def approve_review(self, approval_id: str, author: str, comment: str = "", tenant_id: str | None = None) -> ApprovalRecord:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            if rec.status != ApprovalStatus.IN_REVIEW.value:
                raise ValueError(
                    f"상태 전환 오류: '{rec.status}' 상태에서는 검토 승인을 할 수 없습니다. "
                    f"(허용 상태: in_review)"
                )
            rec.reviewer_approved = True
            rec.reviewed_at = _now_iso()
            if comment:
                rec.comments.append(ApprovalComment(
                    comment_id=str(uuid.uuid4()), stage="review", author=author,
                    content=comment, created_at=_now_iso(), is_change_request=False,
                ))
            return self._flush(tenant_id, records, idx, rec)

    def submit_for_approval(self, approval_id: str, approver: str, tenant_id: str | None = None) -> ApprovalRecord:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            rec.approver = approver or rec.approver
            return self._flush(tenant_id, records, idx, rec)

    def approve_final(self, approval_id: str, author: str, comment: str = "", tenant_id: str | None = None) -> ApprovalRecord:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            if rec.status != ApprovalStatus.IN_REVIEW.value:
                raise ValueError(
                    f"상태 전환 오류: '{rec.status}' 상태에서는 최종 승인을 할 수 없습니다. "
                    f"(허용 상태: in_review)"
                )
            if not rec.reviewer_approved:
                raise ValueError(
                    "검토자 승인이 완료되지 않았습니다. 검토자 승인 후 최종 결재가 가능합니다."
                )
            rec.status = ApprovalStatus.APPROVED.value
            rec.approved_at = _now_iso()
            if comment:
                rec.comments.append(ApprovalComment(
                    comment_id=str(uuid.uuid4()), stage="approval", author=author,
                    content=comment, created_at=_now_iso(), is_change_request=False,
                ))
            return self._flush(tenant_id, records, idx, rec)

    def reject(self, approval_id: str, author: str, comment: str, tenant_id: str | None = None) -> ApprovalRecord:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            if rec.status != ApprovalStatus.IN_REVIEW.value:
                raise ValueError(
                    f"상태 전환 오류: '{rec.status}' 상태에서는 반려할 수 없습니다. "
                    f"(허용 상태: in_review)"
                )
            rec.status = ApprovalStatus.REJECTED.value
            rec.rejected_at = _now_iso()
            rec.comments.append(ApprovalComment(
                comment_id=str(uuid.uuid4()), stage="approval", author=author,
                content=comment, created_at=_now_iso(), is_change_request=False,
            ))
            return self._flush(tenant_id, records, idx, rec)

    def update(self, approval_id: str, tenant_id: str | None = None, **kwargs: Any) -> ApprovalRecord:
        """Update allowed fields: drafter, reviewer, approver.

        Used primarily for cascade operations (e.g., user withdrawal).
        """
        _ALLOWED = {"drafter", "reviewer", "approver"}
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tid, records, idx, rec = result
            for k, v in kwargs.items():
                if k in _ALLOWED:
                    setattr(rec, k, v)
            return self._flush(tid, records, idx, rec)

    def _set_status_direct(self, approval_id: str, status: ApprovalStatus, tenant_id: str | None = None) -> None:
        """Test-only helper — set status bypassing transition guards."""
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tid, records, idx, rec = result
            rec.status = status.value
            self._flush(tid, records, idx, rec)

    def update_docs(self, approval_id: str, docs: list[dict], tenant_id: str | None = None) -> ApprovalRecord:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            rec.current_docs = json.dumps(docs, ensure_ascii=False)
            return self._flush(tenant_id, records, idx, rec)

    def add_comment(
        self,
        approval_id: str,
        author: str,
        content: str,
        stage: str,
        is_change_request: bool = False,
        tenant_id: str | None = None,
    ) -> ApprovalRecord:
        with self._lock:
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            rec.comments.append(ApprovalComment(
                comment_id=str(uuid.uuid4()), stage=stage, author=author,
                content=content, created_at=_now_iso(), is_change_request=is_change_request,
            ))
            return self._flush(tenant_id, records, idx, rec)
