"""Tenant-scoped report workflow storage.

This store owns the intermediate production workflow for staged report
creation: planning approval, slide-level approval, final approval, and
opt-in learning artifacts.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.storage.base import BaseJsonStore, atomic_write_text
from app.storage.state_backend import StateBackend, get_state_backend


class ReportWorkflowStatus(str, Enum):
    PLANNING_REQUIRED = "planning_required"
    PLANNING_DRAFT = "planning_draft"
    PLANNING_CHANGES_REQUESTED = "planning_changes_requested"
    PLANNING_APPROVED = "planning_approved"
    SLIDES_DRAFT = "slides_draft"
    SLIDES_CHANGES_REQUESTED = "slides_changes_requested"
    SLIDES_APPROVED = "slides_approved"
    FINAL_REVIEW = "final_review"
    FINAL_APPROVED = "final_approved"
    DELIVERED = "delivered"


class SlideStatus(str, Enum):
    DRAFT = "draft"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkflowComment:
    comment_id: str
    target_type: str
    target_id: str
    author: str
    content: str
    created_at: str
    is_change_request: bool = False


@dataclass
class SlidePlan:
    slide_id: str
    page: int
    title: str
    purpose: str = ""
    key_message: str = ""
    layout: str = ""
    visual_direction: str = ""
    required_evidence: list[str] = field(default_factory=list)
    approval_status: str = "pending"


@dataclass
class PlanningVersion:
    plan_id: str
    version: int
    status: str
    objective: str
    audience: str
    executive_message: str
    table_of_contents: list[str]
    slide_plans: list[SlidePlan]
    open_questions: list[str]
    risk_notes: list[str]
    created_by: str
    created_at: str
    approved_by: str | None = None
    approved_at: str | None = None


@dataclass
class SlideDraft:
    slide_id: str
    page: int
    title: str
    body: str
    visual_spec: str
    speaker_note: str
    source_refs: list[str]
    status: str = SlideStatus.DRAFT.value
    draft_version: int = 1
    approved_by: str | None = None
    approved_at: str | None = None
    comments: list[WorkflowComment] = field(default_factory=list)


@dataclass
class ReportWorkflowRecord:
    report_workflow_id: str
    tenant_id: str
    title: str
    goal: str
    client: str
    report_type: str
    audience: str
    owner: str
    status: str
    source_bundle_id: str
    source_request_id: str
    slide_count: int
    attachments_context: str
    source_refs: list[str]
    learning_opt_in: bool
    created_at: str
    updated_at: str
    current_plan_version: int = 0
    current_slide_version: int = 0
    planning: PlanningVersion | None = None
    slides: list[SlideDraft] = field(default_factory=list)
    comments: list[WorkflowComment] = field(default_factory=list)
    quality_warnings: list[str] = field(default_factory=list)
    learning_artifacts: list[dict[str, Any]] = field(default_factory=list)
    final_submitted_at: str | None = None
    final_approved_by: str | None = None
    final_approved_at: str | None = None


class ReportWorkflowStore(BaseJsonStore):
    """Thread-safe, tenant-scoped JSON-backed report workflow store."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        super().__init__()
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)

    def _get_path(self) -> Path:
        return self._base / "tenants"

    def _path(self, tenant_id: str) -> Path:
        p = self._base / "tenants" / tenant_id
        if self._backend.kind == "local":
            p.mkdir(parents=True, exist_ok=True)
        return p / "report_workflows.json"

    def _relative_path(self, tenant_id: str) -> str:
        return str(Path("tenants") / tenant_id / "report_workflows.json")

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
    def _comment_from_dict(data: dict) -> WorkflowComment:
        return WorkflowComment(
            comment_id=data.get("comment_id") or str(uuid.uuid4()),
            target_type=data.get("target_type", ""),
            target_id=data.get("target_id", ""),
            author=data.get("author", ""),
            content=data.get("content", ""),
            created_at=data.get("created_at", _now_iso()),
            is_change_request=bool(data.get("is_change_request", False)),
        )

    @classmethod
    def _slide_plan_from_dict(cls, data: dict) -> SlidePlan:
        return SlidePlan(
            slide_id=data.get("slide_id", ""),
            page=int(data.get("page") or 0),
            title=data.get("title", ""),
            purpose=data.get("purpose", ""),
            key_message=data.get("key_message", ""),
            layout=data.get("layout", ""),
            visual_direction=data.get("visual_direction", ""),
            required_evidence=list(data.get("required_evidence") or []),
            approval_status=data.get("approval_status", "pending"),
        )

    @classmethod
    def _planning_from_dict(cls, data: dict | None) -> PlanningVersion | None:
        if not data:
            return None
        return PlanningVersion(
            plan_id=data.get("plan_id") or str(uuid.uuid4()),
            version=int(data.get("version") or 1),
            status=data.get("status", "draft"),
            objective=data.get("objective", ""),
            audience=data.get("audience", ""),
            executive_message=data.get("executive_message", ""),
            table_of_contents=list(data.get("table_of_contents") or []),
            slide_plans=[cls._slide_plan_from_dict(item) for item in data.get("slide_plans", [])],
            open_questions=list(data.get("open_questions") or []),
            risk_notes=list(data.get("risk_notes") or []),
            created_by=data.get("created_by", "ai"),
            created_at=data.get("created_at", _now_iso()),
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
        )

    @classmethod
    def _slide_from_dict(cls, data: dict) -> SlideDraft:
        return SlideDraft(
            slide_id=data.get("slide_id", ""),
            page=int(data.get("page") or 0),
            title=data.get("title", ""),
            body=data.get("body", ""),
            visual_spec=data.get("visual_spec", ""),
            speaker_note=data.get("speaker_note", ""),
            source_refs=list(data.get("source_refs") or []),
            status=data.get("status", SlideStatus.DRAFT.value),
            draft_version=int(data.get("draft_version") or 1),
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
            comments=[cls._comment_from_dict(item) for item in data.get("comments", [])],
        )

    @classmethod
    def _from_dict(cls, data: dict) -> ReportWorkflowRecord:
        return ReportWorkflowRecord(
            report_workflow_id=data["report_workflow_id"],
            tenant_id=data["tenant_id"],
            title=data.get("title", ""),
            goal=data.get("goal", ""),
            client=data.get("client", ""),
            report_type=data.get("report_type", ""),
            audience=data.get("audience", ""),
            owner=data.get("owner", ""),
            status=data.get("status", ReportWorkflowStatus.PLANNING_REQUIRED.value),
            source_bundle_id=data.get("source_bundle_id", "presentation_kr"),
            source_request_id=data.get("source_request_id", ""),
            slide_count=int(data.get("slide_count") or 6),
            attachments_context=data.get("attachments_context", ""),
            source_refs=list(data.get("source_refs") or []),
            learning_opt_in=bool(data.get("learning_opt_in", False)),
            created_at=data.get("created_at", _now_iso()),
            updated_at=data.get("updated_at", _now_iso()),
            current_plan_version=int(data.get("current_plan_version") or 0),
            current_slide_version=int(data.get("current_slide_version") or 0),
            planning=cls._planning_from_dict(data.get("planning")),
            slides=[cls._slide_from_dict(item) for item in data.get("slides", [])],
            comments=[cls._comment_from_dict(item) for item in data.get("comments", [])],
            quality_warnings=list(data.get("quality_warnings") or []),
            learning_artifacts=list(data.get("learning_artifacts") or []),
            final_submitted_at=data.get("final_submitted_at"),
            final_approved_by=data.get("final_approved_by"),
            final_approved_at=data.get("final_approved_at"),
        )

    def _find(
        self,
        report_workflow_id: str,
        tenant_id: str | None = None,
    ) -> tuple[str, list[dict], int, ReportWorkflowRecord] | None:
        if tenant_id is not None:
            records = self._load(tenant_id)
            for idx, raw in enumerate(records):
                if raw.get("report_workflow_id") == report_workflow_id:
                    rec = self._from_dict(raw)
                    if rec.tenant_id != tenant_id:
                        return None
                    return tenant_id, records, idx, rec
            return None

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
            for idx, raw in enumerate(records):
                if raw.get("report_workflow_id") == report_workflow_id:
                    return tid, records, idx, self._from_dict(raw)
        return None

    def _flush(
        self,
        tenant_id: str,
        records: list[dict],
        idx: int,
        rec: ReportWorkflowRecord,
    ) -> ReportWorkflowRecord:
        rec.updated_at = _now_iso()
        records[idx] = asdict(rec)
        self._save(tenant_id, records)
        return rec

    @staticmethod
    def _ensure_mutable(rec: ReportWorkflowRecord) -> None:
        if rec.status in {ReportWorkflowStatus.FINAL_APPROVED.value, ReportWorkflowStatus.DELIVERED.value}:
            raise ValueError("최종 승인된 보고서 워크플로우는 수정할 수 없습니다.")

    @staticmethod
    def _learning_artifact(kind: str, payload: dict[str, Any], *, actor: str = "") -> dict[str, Any]:
        return {
            "artifact_id": str(uuid.uuid4()),
            "kind": kind,
            "actor": actor,
            "created_at": _now_iso(),
            "payload": payload,
        }

    def create(
        self,
        *,
        tenant_id: str,
        title: str,
        goal: str = "",
        client: str = "",
        report_type: str = "proposal_presentation",
        audience: str = "",
        owner: str = "",
        source_bundle_id: str = "presentation_kr",
        source_request_id: str = "",
        slide_count: int = 6,
        attachments_context: str = "",
        source_refs: list[str] | None = None,
        learning_opt_in: bool = False,
    ) -> ReportWorkflowRecord:
        with self._lock:
            records = self._load(tenant_id)
            now = _now_iso()
            rec = ReportWorkflowRecord(
                report_workflow_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                title=title,
                goal=goal,
                client=client,
                report_type=report_type,
                audience=audience,
                owner=owner,
                status=ReportWorkflowStatus.PLANNING_REQUIRED.value,
                source_bundle_id=source_bundle_id or "presentation_kr",
                source_request_id=source_request_id,
                slide_count=max(1, min(int(slide_count or 6), 40)),
                attachments_context=attachments_context,
                source_refs=list(source_refs or []),
                learning_opt_in=learning_opt_in,
                created_at=now,
                updated_at=now,
            )
            records.append(asdict(rec))
            self._save(tenant_id, records)
            return rec

    def get(self, report_workflow_id: str, tenant_id: str | None = None) -> ReportWorkflowRecord | None:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            return result[3] if result else None

    def list_by_tenant(self, tenant_id: str, status: str | None = None) -> list[ReportWorkflowRecord]:
        with self._lock:
            records = [self._from_dict(raw) for raw in self._load(tenant_id)]
        if status:
            records = [rec for rec in records if rec.status == status]
        return sorted(records, key=lambda rec: rec.created_at, reverse=True)

    def save_planning(
        self,
        report_workflow_id: str,
        planning: PlanningVersion,
        *,
        tenant_id: str | None = None,
        quality_warnings: list[str] | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            rec.current_plan_version += 1
            planning.version = rec.current_plan_version
            planning.status = "draft"
            rec.planning = planning
            rec.slides = []
            rec.current_slide_version = 0
            rec.final_submitted_at = None
            rec.final_approved_by = None
            rec.final_approved_at = None
            rec.status = ReportWorkflowStatus.PLANNING_DRAFT.value
            rec.quality_warnings.extend(quality_warnings or [])
            return self._flush(tid, records, idx, rec)

    def request_planning_changes(
        self,
        report_workflow_id: str,
        *,
        author: str,
        comment: str,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            if rec.planning is None:
                raise ValueError("수정 요청할 기획안이 없습니다.")
            rec.status = ReportWorkflowStatus.PLANNING_CHANGES_REQUESTED.value
            rec.planning.status = "changes_requested"
            rec.comments.append(WorkflowComment(
                comment_id=str(uuid.uuid4()),
                target_type="plan",
                target_id=rec.planning.plan_id,
                author=author,
                content=comment,
                created_at=_now_iso(),
                is_change_request=True,
            ))
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "planning_change_request",
                    {"comment": comment, "plan_version": rec.planning.version},
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)

    def approve_planning(
        self,
        report_workflow_id: str,
        *,
        author: str,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            if rec.planning is None:
                raise ValueError("승인할 기획안이 없습니다.")
            rec.planning.status = "approved"
            rec.planning.approved_by = author
            rec.planning.approved_at = _now_iso()
            rec.status = ReportWorkflowStatus.PLANNING_APPROVED.value
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "planning_approved",
                    asdict(rec.planning),
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)

    def save_slides(
        self,
        report_workflow_id: str,
        slides: list[SlideDraft],
        *,
        tenant_id: str | None = None,
        quality_warnings: list[str] | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            if rec.status != ReportWorkflowStatus.PLANNING_APPROVED.value and not (
                rec.planning and rec.planning.status == "approved"
            ):
                raise ValueError("기획안 승인 후 장표를 생성할 수 있습니다.")
            rec.current_slide_version += 1
            for slide in slides:
                slide.draft_version = rec.current_slide_version
                slide.status = SlideStatus.DRAFT.value
                slide.approved_by = None
                slide.approved_at = None
            rec.slides = slides
            rec.status = ReportWorkflowStatus.SLIDES_DRAFT.value
            rec.quality_warnings.extend(quality_warnings or [])
            return self._flush(tid, records, idx, rec)

    def request_slide_changes(
        self,
        report_workflow_id: str,
        slide_id: str,
        *,
        author: str,
        comment: str,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            slide = next((item for item in rec.slides if item.slide_id == slide_id), None)
            if slide is None:
                raise KeyError(f"장표를 찾을 수 없습니다: {slide_id}")
            slide.status = SlideStatus.CHANGES_REQUESTED.value
            slide.approved_by = None
            slide.approved_at = None
            slide.comments.append(WorkflowComment(
                comment_id=str(uuid.uuid4()),
                target_type="slide",
                target_id=slide_id,
                author=author,
                content=comment,
                created_at=_now_iso(),
                is_change_request=True,
            ))
            rec.status = ReportWorkflowStatus.SLIDES_CHANGES_REQUESTED.value
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "slide_change_request",
                    {"slide_id": slide_id, "comment": comment, "draft_version": slide.draft_version},
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)

    def approve_slide(
        self,
        report_workflow_id: str,
        slide_id: str,
        *,
        author: str,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            slide = next((item for item in rec.slides if item.slide_id == slide_id), None)
            if slide is None:
                raise KeyError(f"장표를 찾을 수 없습니다: {slide_id}")
            slide.status = SlideStatus.APPROVED.value
            slide.approved_by = author
            slide.approved_at = _now_iso()
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "slide_approved",
                    asdict(slide),
                    actor=author,
                ))
            if rec.slides and all(item.status == SlideStatus.APPROVED.value for item in rec.slides):
                rec.status = ReportWorkflowStatus.SLIDES_APPROVED.value
            else:
                rec.status = ReportWorkflowStatus.SLIDES_DRAFT.value
            return self._flush(tid, records, idx, rec)

    def submit_final(
        self,
        report_workflow_id: str,
        *,
        author: str,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            self._ensure_mutable(rec)
            if not rec.slides or any(item.status != SlideStatus.APPROVED.value for item in rec.slides):
                raise ValueError("모든 장표가 승인되어야 최종 검토로 이동할 수 있습니다.")
            rec.status = ReportWorkflowStatus.FINAL_REVIEW.value
            rec.final_submitted_at = _now_iso()
            rec.comments.append(WorkflowComment(
                comment_id=str(uuid.uuid4()),
                target_type="final",
                target_id=report_workflow_id,
                author=author,
                content="최종 검토 요청",
                created_at=_now_iso(),
                is_change_request=False,
            ))
            return self._flush(tid, records, idx, rec)

    def approve_final(
        self,
        report_workflow_id: str,
        *,
        author: str,
        tenant_id: str | None = None,
    ) -> ReportWorkflowRecord:
        with self._lock:
            result = self._find(report_workflow_id, tenant_id=tenant_id)
            if result is None:
                raise KeyError(f"보고서 워크플로우를 찾을 수 없습니다: {report_workflow_id}")
            tid, records, idx, rec = result
            if rec.status != ReportWorkflowStatus.FINAL_REVIEW.value:
                raise ValueError("최종 검토 상태에서만 최종 승인할 수 있습니다.")
            rec.status = ReportWorkflowStatus.FINAL_APPROVED.value
            rec.final_approved_by = author
            rec.final_approved_at = _now_iso()
            if rec.learning_opt_in:
                rec.learning_artifacts.append(self._learning_artifact(
                    "final_approved",
                    {
                        "planning": asdict(rec.planning) if rec.planning else None,
                        "slides": [asdict(item) for item in rec.slides],
                        "quality_warnings": rec.quality_warnings,
                    },
                    actor=author,
                ))
            return self._flush(tid, records, idx, rec)
