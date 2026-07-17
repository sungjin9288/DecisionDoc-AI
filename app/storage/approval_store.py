"""app/storage/approval_store.py — Tenant-scoped approval workflow storage.

Documents go through: 기안(Draft) → 검토(Review) → 승인(Approval) stages.
Storage: data/tenants/{tenant_id}/approvals.json (one file per tenant).
Thread-safe within one process across stores that share a logical state object.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.storage.state_lock import state_lock
from app.tenant import require_tenant_id


class ApprovalStoreError(RuntimeError):
    """Raised when persisted approval state cannot be trusted."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ApprovalStoreError(f"Duplicate key in approval state: {key!r}")
        result[key] = value
    return result


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
    project_id: str = ""
    project_document_id: str = ""
    source_decision_council_document_status: str = ""
    source_decision_council_document_status_tone: str = ""
    source_decision_council_document_status_copy: str = ""
    source_decision_council_document_status_summary: str = ""
    source_procurement_review_document_status: str = ""
    source_procurement_review_document_status_tone: str = ""
    source_procurement_review_document_status_copy: str = ""
    source_procurement_review_document_status_summary: str = ""
    freshness_acknowledged: bool = False
    freshness_acknowledged_by: str = ""
    freshness_acknowledged_at: str = ""
    approved_source_fingerprint: str = ""


class ApprovalStore:
    """Thread-safe, tenant-scoped JSON-backed approval workflow store."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    # ── Persistence helpers ─────────────────────────────────────────────

    def _relative_path(self, tenant_id: str) -> str:
        tenant_id = require_tenant_id(tenant_id)
        return str(Path("tenants") / tenant_id / "approvals.json")

    def _lock(self, tenant_id: str):
        relative_path = self._relative_path(tenant_id)
        return state_lock(
            self._backend,
            data_dir=self._base,
            relative_path=relative_path,
        )

    def _load(self, tenant_id: str) -> list[dict]:
        tenant_id = require_tenant_id(tenant_id)
        try:
            raw = self._backend.read_text(self._relative_path(tenant_id))
        except (StateBackendError, UnicodeError) as exc:
            raise ApprovalStoreError("Invalid approval state document") from exc
        if raw is None:
            return []
        if not raw.strip():
            raise ApprovalStoreError("Invalid approval state document")
        try:
            records = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, ApprovalStoreError) as exc:
            raise ApprovalStoreError("Invalid approval state document") from exc
        if not isinstance(records, list):
            raise ApprovalStoreError("Invalid approval state document")
        return records

    def _save(self, tenant_id: str, records: list[dict]) -> None:
        self._owned_records(records, tenant_id=tenant_id)
        payload = json.dumps(records, ensure_ascii=False, indent=2)
        try:
            self._backend.write_text(self._relative_path(tenant_id), payload)
        except StateBackendError as exc:
            raise ApprovalStoreError("Failed to persist approval state") from exc

    @staticmethod
    def _to_dict(rec: ApprovalRecord) -> dict:
        return asdict(rec)

    @staticmethod
    def _from_dict(d: dict) -> ApprovalRecord:
        if not isinstance(d, dict):
            raise ApprovalStoreError("Invalid approval record")
        approval_id = d.get("approval_id")
        tenant_id = d.get("tenant_id")
        status = d.get("status")
        created_at = d.get("created_at")
        raw_comments = d.get("comments", [])
        if not isinstance(approval_id, str) or not approval_id:
            raise ApprovalStoreError("Invalid approval identity")
        if not isinstance(tenant_id, str) or not isinstance(created_at, str):
            raise ApprovalStoreError("Invalid approval identity")
        require_tenant_id(tenant_id)
        if status not in {item.value for item in ApprovalStatus}:
            raise ApprovalStoreError("Invalid approval status")
        if not isinstance(raw_comments, list):
            raise ApprovalStoreError("Invalid approval comments")
        comments = [ApprovalComment(**comment) for comment in raw_comments]
        return ApprovalRecord(
            approval_id=approval_id,
            tenant_id=tenant_id,
            request_id=d.get("request_id", ""),
            bundle_id=d.get("bundle_id", ""),
            title=d.get("title", ""),
            status=status,
            drafter=d.get("drafter", ""),
            reviewer=d.get("reviewer"),
            approver=d.get("approver"),
            created_at=created_at,
            submitted_at=d.get("submitted_at"),
            reviewed_at=d.get("reviewed_at"),
            approved_at=d.get("approved_at"),
            rejected_at=d.get("rejected_at"),
            comments=comments,
            doc_snapshot=d.get("doc_snapshot", "[]"),
            current_docs=d.get("current_docs", "[]"),
            gov_options=d.get("gov_options"),
            reviewer_approved=d.get("reviewer_approved", False),
            project_id=d.get("project_id", ""),
            project_document_id=d.get("project_document_id", ""),
            source_decision_council_document_status=d.get(
                "source_decision_council_document_status", ""
            ),
            source_decision_council_document_status_tone=d.get(
                "source_decision_council_document_status_tone", ""
            ),
            source_decision_council_document_status_copy=d.get(
                "source_decision_council_document_status_copy", ""
            ),
            source_decision_council_document_status_summary=d.get(
                "source_decision_council_document_status_summary", ""
            ),
            source_procurement_review_document_status=d.get(
                "source_procurement_review_document_status", ""
            ),
            source_procurement_review_document_status_tone=d.get(
                "source_procurement_review_document_status_tone", ""
            ),
            source_procurement_review_document_status_copy=d.get(
                "source_procurement_review_document_status_copy", ""
            ),
            source_procurement_review_document_status_summary=d.get(
                "source_procurement_review_document_status_summary", ""
            ),
            freshness_acknowledged=d.get("freshness_acknowledged", False),
            freshness_acknowledged_by=d.get("freshness_acknowledged_by", ""),
            freshness_acknowledged_at=d.get("freshness_acknowledged_at", ""),
            approved_source_fingerprint=d.get("approved_source_fingerprint", ""),
        )

    def _owned_records(
        self,
        records: list[Any],
        *,
        tenant_id: str,
    ) -> list[tuple[int, ApprovalRecord]]:
        tenant_id = require_tenant_id(tenant_id)
        owned: list[tuple[int, ApprovalRecord]] = []
        approval_ids: set[str] = set()
        for index, raw_record in enumerate(records):
            if not isinstance(raw_record, dict):
                continue
            if raw_record.get("tenant_id") != tenant_id:
                continue
            approval_id = raw_record.get("approval_id")
            if not isinstance(approval_id, str) or not approval_id:
                continue
            try:
                record = self._from_dict(raw_record)
            except (KeyError, TypeError, ValueError, ApprovalStoreError) as exc:
                raise ApprovalStoreError("Invalid owned approval record") from exc
            if record.approval_id in approval_ids:
                raise ApprovalStoreError("Duplicate approval records")
            approval_ids.add(record.approval_id)
            owned.append((index, record))
        return owned

    def _find(
        self,
        approval_id: str,
        *,
        tenant_id: str,
    ) -> tuple[str, list[dict], int, ApprovalRecord] | None:
        """Locate an approval only within the caller's tenant."""
        tenant_id = require_tenant_id(tenant_id)
        records = self._load(tenant_id)
        for index, record in self._owned_records(records, tenant_id=tenant_id):
            if record.approval_id == approval_id:
                return tenant_id, records, index, record
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
        project_id: str = "",
        project_document_id: str = "",
        decision_council_document_status: str = "",
        decision_council_document_status_tone: str = "",
        decision_council_document_status_copy: str = "",
        decision_council_document_status_summary: str = "",
        procurement_review_document_status: str = "",
        procurement_review_document_status_tone: str = "",
        procurement_review_document_status_copy: str = "",
        procurement_review_document_status_summary: str = "",
    ) -> ApprovalRecord:
        tenant_id = require_tenant_id(tenant_id)
        with self._lock(tenant_id):
            records = self._load(tenant_id)
            self._owned_records(records, tenant_id=tenant_id)
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
                project_id=project_id,
                project_document_id=project_document_id,
                source_decision_council_document_status=decision_council_document_status,
                source_decision_council_document_status_tone=decision_council_document_status_tone,
                source_decision_council_document_status_copy=decision_council_document_status_copy,
                source_decision_council_document_status_summary=decision_council_document_status_summary,
                source_procurement_review_document_status=procurement_review_document_status,
                source_procurement_review_document_status_tone=procurement_review_document_status_tone,
                source_procurement_review_document_status_copy=procurement_review_document_status_copy,
                source_procurement_review_document_status_summary=procurement_review_document_status_summary,
            )
            records.append(self._to_dict(rec))
            self._save(tenant_id, records)
            return rec

    def get(self, approval_id: str, *, tenant_id: str) -> ApprovalRecord | None:
        with self._lock(tenant_id):
            result = self._find(approval_id, tenant_id=tenant_id)
            return result[3] if result else None

    def list_by_tenant(
        self, tenant_id: str, status: str | None = None
    ) -> list[ApprovalRecord]:
        tenant_id = require_tenant_id(tenant_id)
        with self._lock(tenant_id):
            records = [
                record
                for _, record in self._owned_records(
                    self._load(tenant_id),
                    tenant_id=tenant_id,
                )
            ]
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

    def submit_for_review(
        self,
        approval_id: str,
        reviewer: str,
        *,
        tenant_id: str,
    ) -> ApprovalRecord:
        with self._lock(tenant_id):
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

    def request_changes(
        self,
        approval_id: str,
        author: str,
        comment: str,
        *,
        tenant_id: str,
    ) -> ApprovalRecord:
        with self._lock(tenant_id):
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

    def approve_review(
        self,
        approval_id: str,
        author: str,
        comment: str = "",
        *,
        tenant_id: str,
    ) -> ApprovalRecord:
        with self._lock(tenant_id):
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

    def submit_for_approval(
        self,
        approval_id: str,
        approver: str,
        *,
        tenant_id: str,
    ) -> ApprovalRecord:
        with self._lock(tenant_id):
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            rec.approver = approver or rec.approver
            return self._flush(tenant_id, records, idx, rec)

    def approve_final(
        self,
        approval_id: str,
        author: str,
        comment: str = "",
        *,
        tenant_id: str,
        freshness_acknowledged: bool = False,
        approved_source_fingerprint: str = "",
    ) -> ApprovalRecord:
        with self._lock(tenant_id):
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
            rec.approved_source_fingerprint = approved_source_fingerprint
            if freshness_acknowledged:
                rec.freshness_acknowledged = True
                rec.freshness_acknowledged_by = author
                rec.freshness_acknowledged_at = rec.approved_at
            if comment:
                rec.comments.append(ApprovalComment(
                    comment_id=str(uuid.uuid4()), stage="approval", author=author,
                    content=comment, created_at=_now_iso(), is_change_request=False,
                ))
            return self._flush(tenant_id, records, idx, rec)

    def reject(
        self,
        approval_id: str,
        author: str,
        comment: str,
        *,
        tenant_id: str,
    ) -> ApprovalRecord:
        with self._lock(tenant_id):
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

    def update(self, approval_id: str, *, tenant_id: str, **kwargs: Any) -> ApprovalRecord:
        """Update allowed fields: drafter, reviewer, approver.

        Used primarily for cascade operations (e.g., user withdrawal).
        """
        _ALLOWED = {"drafter", "reviewer", "approver"}
        with self._lock(tenant_id):
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tid, records, idx, rec = result
            for k, v in kwargs.items():
                if k in _ALLOWED:
                    setattr(rec, k, v)
            return self._flush(tid, records, idx, rec)

    def _set_status_direct(
        self,
        approval_id: str,
        status: ApprovalStatus,
        *,
        tenant_id: str,
    ) -> None:
        """Test-only helper — set status bypassing transition guards."""
        with self._lock(tenant_id):
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tid, records, idx, rec = result
            rec.status = status.value
            self._flush(tid, records, idx, rec)

    def update_docs(
        self,
        approval_id: str,
        docs: list[dict],
        *,
        tenant_id: str,
    ) -> ApprovalRecord:
        with self._lock(tenant_id):
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
        *,
        tenant_id: str,
        is_change_request: bool = False,
    ) -> ApprovalRecord:
        with self._lock(tenant_id):
            result = self._find(approval_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"결재 문서를 찾을 수 없습니다: {approval_id}")
            tenant_id, records, idx, rec = result
            rec.comments.append(ApprovalComment(
                comment_id=str(uuid.uuid4()), stage=stage, author=author,
                content=content, created_at=_now_iso(), is_change_request=is_change_request,
            ))
            return self._flush(tenant_id, records, idx, rec)
