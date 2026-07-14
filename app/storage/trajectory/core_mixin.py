"""Core trajectory persistence: init, save, get_records, mark_reviewed, get_stats,
and the shared tenant path / JSONL / metadata plumbing used by every other mixin."""
from __future__ import annotations

import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.storage.trajectory.redaction import _now_iso, _redact_input
from app.storage.trajectory.sft_quality import _is_accepted, _sft_export_blockers, _source_references

_log = logging.getLogger("decisiondoc.storage.trajectory")


class TrajectoryCoreMixin:
    """Init, save/get/review, stats, and shared tenant file-path plumbing."""

    def __init__(self, data_dir: str | Path) -> None:
        self._base_dir = Path(data_dir)
        self._lock = threading.Lock()

    def save(self, trajectory: dict[str, Any], *, tenant_id: str = "system") -> str:
        """Persist one trajectory and return its trajectory_id.

        Duplicate ``trajectory_id`` values are ignored to keep repeated agent
        retries from polluting reviewed-data exports.
        """
        record = self._normalize_record(trajectory)
        trajectory_id = str(record["trajectory_id"])
        with self._lock:
            existing_ids = {str(item.get("trajectory_id")) for item in self._read_records_unlocked(tenant_id)}
            if trajectory_id in existing_ids:
                return trajectory_id
            path = self._jsonl_path(tenant_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return trajectory_id

    def get_records(
        self,
        *,
        tenant_id: str = "system",
        task_type: str | None = None,
        human_review_status: str | None = None,
        accepted_only: bool = False,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return newest matching records up to ``limit``."""
        records, _ = self.get_record_page(
            tenant_id=tenant_id,
            task_type=task_type,
            human_review_status=human_review_status,
            accepted_only=accepted_only,
            offset=0,
            limit=limit,
        )
        return records

    def get_record_page(
        self,
        *,
        tenant_id: str = "system",
        task_type: str | None = None,
        human_review_status: str | None = None,
        accepted_only: bool = False,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page measured from the newest match and its filtered total."""
        with self._lock:
            records = self._read_records_unlocked(tenant_id)
        if task_type:
            records = [item for item in records if item.get("task_type") == task_type]
        if human_review_status:
            records = [item for item in records if item.get("human_review_status") == human_review_status]
        if accepted_only:
            records = [item for item in records if _is_accepted(item)]

        total = len(records)
        page_offset = max(0, offset)
        page_limit = max(1, limit)
        end = max(0, total - page_offset)
        start = max(0, end - page_limit)
        return records[start:end], total

    def mark_reviewed(
        self,
        trajectory_id: str,
        *,
        tenant_id: str = "system",
        accepted: bool,
        reviewer: str = "",
        notes: str = "",
        quality_score: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Attach human review metadata to an existing trajectory."""
        reviewer = reviewer.strip()
        if not reviewer or reviewer.casefold() == "anonymous":
            raise ValueError("reviewer identity is required.")
        if len(reviewer) > 120:
            raise ValueError("reviewer identity must be 120 characters or fewer.")

        notes = notes.strip()
        if len(notes) > 2000:
            raise ValueError("review notes must be 2000 characters or fewer.")

        score: float | None = None
        if quality_score is not None:
            if isinstance(quality_score, bool) or not isinstance(quality_score, (int, float)):
                raise ValueError("quality_score must be a number between 0 and 1.")
            score = float(quality_score)
            if not 0.0 <= score <= 1.0:
                raise ValueError("quality_score must be between 0 and 1.")

        review_metadata = _validate_review_metadata(metadata)
        review_content: dict[str, Any] = {
            "accepted": bool(accepted),
            "reviewer": reviewer,
            "notes": notes,
        }
        if score is not None:
            review_content["quality_score"] = score
        if review_metadata:
            review_content["metadata"] = review_metadata

        with self._lock:
            records = self._read_records_unlocked(tenant_id)
            updated: dict[str, Any] | None = None
            for record in records:
                if str(record.get("trajectory_id")) != trajectory_id:
                    continue
                current = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
                if record.get("human_review_status") in {"accepted", "rejected"} and _review_content(current) == review_content:
                    return record

                version = int(current.get("review_version") or 0) + 1
                feedback = {**review_content, "review_version": version, "reviewed_at": _now_iso()}
                if record.get("human_review_status") in {"accepted", "rejected"}:
                    history = record.get("human_review_history")
                    if not isinstance(history, list):
                        history = []
                    history.append(current)
                    record["human_review_history"] = history
                record["human_feedback"] = feedback
                record["human_review_status"] = "accepted" if accepted else "rejected"
                updated = record
                break
            if updated is None:
                return None
            self._write_records_unlocked(tenant_id, records)
        return updated

    def get_stats(self, *, tenant_id: str = "system") -> dict[str, Any]:
        with self._lock:
            records = self._read_records_unlocked(tenant_id)
            meta = self._load_meta_unlocked(tenant_id)
        per_task: dict[str, int] = {}
        accepted = 0
        rejected = 0
        pending = 0
        last_created: str | None = None
        for record in records:
            task_type = str(record.get("task_type") or "unknown")
            per_task[task_type] = per_task.get(task_type, 0) + 1
            status = record.get("human_review_status")
            if _is_accepted(record):
                accepted += 1
            elif status == "rejected":
                rejected += 1
            else:
                pending += 1
            created_at = record.get("created_at")
            if created_at and (last_created is None or str(created_at) > last_created):
                last_created = str(created_at)
        return {
            "total_records": len(records),
            "accepted_records": accepted,
            "rejected_records": rejected,
            "pending_records": pending,
            "per_task_count": per_task,
            "last_created_at": last_created,
            "export_count": int(meta.get("export_count") or 0),
        }

    def _select_sft_export_records(
        self,
        *,
        tenant_id: str,
        task_type: str | None,
        accepted_only: bool,
    ) -> list[dict[str, Any]]:
        records = self.get_records(
            tenant_id=tenant_id,
            task_type=task_type,
            limit=100_000,
        )
        selected: list[dict[str, Any]] = []
        for record in records:
            blockers = _sft_export_blockers(record, accepted_only=accepted_only)
            if not blockers:
                selected.append(record)
        return selected

    def _normalize_record(self, trajectory: dict[str, Any]) -> dict[str, Any]:
        record = dict(trajectory or {})
        record.setdefault("trajectory_id", f"trj_{uuid.uuid4().hex}")
        record.setdefault("schema_version", "document_ops_trajectory_v1")
        record.setdefault("created_at", _now_iso())
        record.setdefault("human_review_status", "pending")
        if "skill" not in record or not isinstance(record["skill"], dict):
            record["skill"] = {"name": str(record.get("skill_name") or "unknown"), "version": str(record.get("skill_version") or "unknown")}
        if "qa" not in record or not isinstance(record["qa"], dict):
            record["qa"] = {}
        if "human_feedback" not in record or not isinstance(record["human_feedback"], dict):
            record["human_feedback"] = {"accepted": False}
        if "input" in record:
            record["input"] = _redact_input(record["input"])
        return record

    def _to_sft_record(self, record: dict[str, Any], *, include_metadata: bool) -> dict[str, Any]:
        task_type = str(record.get("task_type") or "document_ops")
        skill = record.get("skill") if isinstance(record.get("skill"), dict) else {}
        feedback = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
        skill_name = str(skill.get("name") or "unknown")
        skill_version = str(skill.get("version") or "unknown")
        assistant_payload = {
            "plan": record.get("plan") or [],
            "critique": record.get("critique") or [],
            "revision_tasks": record.get("revision_tasks") or [],
            "draft": record.get("final_output") or record.get("draft_output") or record.get("draft") or "",
            "evidence_status": record.get("evidence_status") or record.get("context_summary") or {},
            "qa": record.get("qa") or {},
        }
        sft = {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are DecisionDoc DocumentOps Agent. "
                        f"Use curated skill {skill_name}@{skill_version}. "
                        "Keep confirmed facts, assumptions, and evidence gaps separated."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "task_type": task_type,
                            "input": record.get("input") or {},
                            "source_references": _source_references(record),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
                {
                    "role": "assistant",
                    "content": json.dumps(assistant_payload, ensure_ascii=False, sort_keys=True),
                },
            ]
        }
        if include_metadata:
            sft["metadata"] = {
                "trajectory_id": record.get("trajectory_id"),
                "task_type": task_type,
                "skill": skill_name,
                "skill_version": skill_version,
                "human_review_status": record.get("human_review_status"),
                "reviewer": feedback.get("reviewer"),
                "review_version": feedback.get("review_version"),
                "reviewed_at": feedback.get("reviewed_at"),
                "quality_score": feedback.get("quality_score"),
            }
        return sft

    def _read_records_unlocked(self, tenant_id: str) -> list[dict[str, Any]]:
        path = self._jsonl_path(tenant_id)
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError as exc:
                _log.warning("Skipping malformed trajectory record: %s", exc)
                continue
            if isinstance(item, dict):
                records.append(item)
        return records

    def _write_records_unlocked(self, tenant_id: str, records: list[dict[str, Any]]) -> None:
        text = "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in records)
        atomic_write_text(self._jsonl_path(tenant_id), f"{text}\n" if text else "")

    def _load_meta_unlocked(self, tenant_id: str) -> dict[str, Any]:
        path = self._meta_path(tenant_id)
        if not path.exists():
            return {"export_count": 0, "exports": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"export_count": 0, "exports": []}
        return data if isinstance(data, dict) else {"export_count": 0, "exports": []}

    def _tenant_dir(self, tenant_id: str) -> Path:
        return self._base_dir / "tenants" / tenant_id

    def _jsonl_path(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "trajectories.jsonl"

    def _meta_path(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "trajectory_metadata.json"

    def _export_dir(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "trajectory_exports"

    def _freeze_dir(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "trajectory_freezes"

    def _training_approval_dir(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "trajectory_training_approvals"

    def _training_execution_request_dir(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "trajectory_training_execution_requests"

    def _training_audit_dir(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "trajectory_training_audits"

    def _reviewer_signoff_dir(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "trajectory_reviewer_signoffs"


def _review_content(feedback: dict[str, Any]) -> dict[str, Any]:
    content: dict[str, Any] = {
        "accepted": bool(feedback.get("accepted")),
        "reviewer": str(feedback.get("reviewer") or "").strip(),
        "notes": str(feedback.get("notes") or "").strip(),
    }
    if feedback.get("quality_score") is not None:
        content["quality_score"] = float(feedback["quality_score"])
    metadata = feedback.get("metadata")
    if isinstance(metadata, dict) and metadata:
        content["metadata"] = metadata
    return content


def _validate_review_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        raise ValueError("review metadata must be an object.")
    if any(not isinstance(key, str) or not key.strip() for key in metadata):
        raise ValueError("review metadata keys must be non-empty strings.")

    redacted = _redact_input(metadata)
    try:
        encoded = json.dumps(redacted, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("review metadata must contain JSON-compatible values.") from exc
    if len(encoded) > 16 * 1024:
        raise ValueError("review metadata must be 16 KiB or smaller.")
    return redacted
