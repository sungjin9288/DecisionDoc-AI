"""TrajectoryStore — reviewed DocumentOps trajectory persistence.

This store complements FineTuneStore. It keeps rich internal trajectories in a
tenant-scoped JSONL file, then exports reviewed/accepted examples into
SFT-compatible message records only when explicitly requested.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text

_log = logging.getLogger("decisiondoc.storage.trajectory")


class TrajectoryStore:
    """Thread-safe JSONL store for DocumentOps trajectories."""

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
        with self._lock:
            records = self._read_records_unlocked(tenant_id)
        if task_type:
            records = [item for item in records if item.get("task_type") == task_type]
        if human_review_status:
            records = [item for item in records if item.get("human_review_status") == human_review_status]
        if accepted_only:
            records = [item for item in records if _is_accepted(item)]
        return records[-limit:]

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
        with self._lock:
            records = self._read_records_unlocked(tenant_id)
            updated: dict[str, Any] | None = None
            for record in records:
                if str(record.get("trajectory_id")) != trajectory_id:
                    continue
                feedback = {
                    "accepted": bool(accepted),
                    "reviewer": reviewer,
                    "notes": notes,
                    "reviewed_at": _now_iso(),
                }
                if quality_score is not None:
                    feedback["quality_score"] = float(quality_score)
                if metadata:
                    feedback["metadata"] = _redact_input(metadata)
                record["human_feedback"] = feedback
                record["human_review_status"] = "accepted" if accepted else "rejected"
                updated = record
                break
            if updated is None:
                return None
            self._write_records_unlocked(tenant_id, records)
        return updated

    def export_sft_messages(
        self,
        *,
        tenant_id: str = "system",
        task_type: str | None = None,
        min_records: int = 1,
        accepted_only: bool = True,
        include_metadata: bool = True,
    ) -> str | None:
        """Export trajectories as JSONL SFT messages.

        Returns the export path, or None when fewer than ``min_records`` match.
        """
        records = self._select_sft_export_records(
            tenant_id=tenant_id,
            task_type=task_type,
            accepted_only=accepted_only,
        )
        if len(records) < min_records:
            return None
        export_records = [self._to_sft_record(record, include_metadata=include_metadata) for record in records]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        suffix = f"_{_safe_label(task_type)}" if task_type else ""
        export_dir = self._tenant_dir(tenant_id) / "trajectory_exports"
        export_path = export_dir / f"sft{suffix}_{ts}.jsonl"
        atomic_write_text(
            export_path,
            "\n".join(json.dumps(item, ensure_ascii=False, sort_keys=True) for item in export_records) + "\n",
        )
        self._append_export_meta(tenant_id, export_path.name, records, task_type=task_type, accepted_only=accepted_only)
        return str(export_path)

    def list_sft_exports(
        self,
        *,
        tenant_id: str = "system",
        task_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return newest metadata for generated SFT JSONL exports.

        Only metadata-recorded export files are exposed. This keeps the
        download surface constrained to files generated by this store.
        """
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_exports = meta.get("exports") if isinstance(meta.get("exports"), list) else []
        exports: list[dict[str, Any]] = []
        seen_filenames: set[str] = set()
        for item in reversed(raw_exports):
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename") or "")
            if filename in seen_filenames:
                continue
            if task_type is not None and item.get("task_type") != task_type:
                continue
            path = self._resolve_export_path(tenant_id, filename)
            exports.append(
                {
                    "filename": filename,
                    "record_count": int(item.get("record_count") or 0),
                    "task_type": item.get("task_type"),
                    "accepted_only": bool(item.get("accepted_only", True)),
                    "exported_at": item.get("exported_at"),
                    "exists": path is not None,
                    "size_bytes": path.stat().st_size if path else 0,
                }
            )
            seen_filenames.add(filename)
            if len(exports) >= limit:
                break
        return exports

    def list_reviewed_sft_exports(
        self,
        *,
        tenant_id: str = "system",
        task_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return metadata for reviewed-only SFT JSONL exports.

        Reviewed SFT exports are files generated from accepted trajectories
        only. This list intentionally excludes historical exports created with
        ``accepted_only=false`` so the download surface cannot accidentally
        expose unreviewed examples.
        """
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_exports = meta.get("exports") if isinstance(meta.get("exports"), list) else []
        exports: list[dict[str, Any]] = []
        seen_filenames: set[str] = set()
        for item in reversed(raw_exports):
            if not isinstance(item, dict):
                continue
            if item.get("accepted_only") is not True:
                continue
            filename = str(item.get("filename") or "")
            if filename in seen_filenames:
                continue
            if task_type is not None and item.get("task_type") != task_type:
                continue
            path = self._resolve_export_path(tenant_id, filename)
            exports.append(
                {
                    "filename": filename,
                    "record_count": int(item.get("record_count") or 0),
                    "task_type": item.get("task_type"),
                    "accepted_only": True,
                    "exported_at": item.get("exported_at"),
                    "exists": path is not None,
                    "size_bytes": path.stat().st_size if path else 0,
                }
            )
            seen_filenames.add(filename)
            if len(exports) >= limit:
                break
        return exports

    def list_dataset_freezes(
        self,
        *,
        tenant_id: str = "system",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return newest dataset freeze manifest metadata."""
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_freezes = meta.get("freezes") if isinstance(meta.get("freezes"), list) else []
        freezes: list[dict[str, Any]] = []
        seen_manifest_files: set[str] = set()
        for item in reversed(raw_freezes):
            if not isinstance(item, dict):
                continue
            manifest_file = str(item.get("manifest_file") or "")
            if manifest_file in seen_manifest_files:
                continue
            manifest_path = self._resolve_freeze_path(tenant_id, manifest_file)
            freezes.append(
                {
                    "manifest_id": item.get("manifest_id"),
                    "manifest_file": manifest_file,
                    "export_filename": item.get("export_filename"),
                    "record_count": int(item.get("record_count") or 0),
                    "quality_report_sha256": item.get("quality_report_sha256"),
                    "training_allowed": bool(item.get("training_allowed", False)),
                    "training_started": bool(item.get("training_started", False)),
                    "reviewer": item.get("reviewer"),
                    "created_at": item.get("created_at"),
                    "exists": manifest_path is not None,
                    "size_bytes": manifest_path.stat().st_size if manifest_path else 0,
                }
            )
            seen_manifest_files.add(manifest_file)
            if len(freezes) >= limit:
                break
        return freezes

    def list_training_approvals(
        self,
        *,
        tenant_id: str = "system",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return newest dry-run training approval gate metadata."""
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_approvals = meta.get("training_approvals") if isinstance(meta.get("training_approvals"), list) else []
        approvals: list[dict[str, Any]] = []
        seen_files: set[str] = set()
        for item in reversed(raw_approvals):
            if not isinstance(item, dict):
                continue
            approval_file = str(item.get("approval_file") or "")
            if approval_file in seen_files:
                continue
            approval_path = self._resolve_training_approval_path(tenant_id, approval_file)
            approvals.append(
                {
                    "approval_id": item.get("approval_id"),
                    "approval_file": approval_file,
                    "manifest_id": item.get("manifest_id"),
                    "export_filename": item.get("export_filename"),
                    "approver": item.get("approver"),
                    "dry_run": bool(item.get("dry_run", True)),
                    "provider_job_started": bool(item.get("provider_job_started", False)),
                    "model_promotion_allowed": bool(item.get("model_promotion_allowed", False)),
                    "created_at": item.get("created_at"),
                    "exists": approval_path is not None,
                    "size_bytes": approval_path.stat().st_size if approval_path else 0,
                }
            )
            seen_files.add(approval_file)
            if len(approvals) >= limit:
                break
        return approvals

    def get_sft_export_path(self, filename: str, *, tenant_id: str = "system") -> Path | None:
        """Resolve a metadata-recorded SFT export filename to a safe path."""
        if not _is_safe_export_filename(filename):
            raise ValueError("Invalid export filename.")
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_exports = meta.get("exports") if isinstance(meta.get("exports"), list) else []
        known = {
            str(item.get("filename") or "")
            for item in raw_exports
            if isinstance(item, dict)
        }
        if filename not in known:
            return None
        return self._resolve_export_path(tenant_id, filename)

    def get_reviewed_sft_export_path(self, filename: str, *, tenant_id: str = "system") -> Path | None:
        """Resolve a reviewed-only SFT export filename to a safe path."""
        if not _is_safe_export_filename(filename):
            raise ValueError("Invalid export filename.")
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_exports = meta.get("exports") if isinstance(meta.get("exports"), list) else []
        reviewed_known = {
            str(item.get("filename") or "")
            for item in raw_exports
            if isinstance(item, dict) and item.get("accepted_only") is True
        }
        if filename not in reviewed_known:
            return None
        return self._resolve_export_path(tenant_id, filename)

    def freeze_sft_export(
        self,
        filename: str,
        *,
        tenant_id: str = "system",
        reviewer: str,
        notes: str = "",
        sample_limit: int = 5,
        training_allowed: bool = False,
    ) -> dict[str, Any] | None:
        """Freeze a reviewed SFT export manifest without starting training."""
        if training_allowed:
            raise ValueError("Dataset freeze is no-training-by-default; model training requires a separate workflow.")
        reviewer = reviewer.strip()
        if not reviewer:
            raise ValueError("reviewer is required.")
        export_path = self.get_sft_export_path(filename, tenant_id=tenant_id)
        if export_path is None:
            return None
        quality_report = self.inspect_sft_export_quality(filename, tenant_id=tenant_id, sample_limit=sample_limit)
        if quality_report is None:
            return None
        if not quality_report.get("ready_for_training"):
            raise ValueError("SFT export quality report is not ready for dataset freeze.")
        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        manifest_ts = now.strftime("%Y%m%dT%H%M%S")
        manifest_id = f"dsf_{uuid.uuid4().hex}"
        quality_report_sha256 = _json_sha256(quality_report)
        export_sha256 = _file_sha256(export_path)
        manifest = {
            "schema_version": "document_ops_dataset_freeze_v1",
            "manifest_id": manifest_id,
            "created_at": created_at,
            "tenant_id": tenant_id,
            "export": {
                "filename": export_path.name,
                "size_bytes": export_path.stat().st_size,
                "sha256": export_sha256,
                "record_count": int(quality_report.get("jsonl_record_count") or 0),
            },
            "quality_report": {
                "sha256": quality_report_sha256,
                "schema_valid_count": int(quality_report.get("schema_valid_count") or 0),
                "schema_invalid_count": int(quality_report.get("schema_invalid_count") or 0),
                "role_sequence_summary": quality_report.get("role_sequence_summary") or {},
                "qa_summary": quality_report.get("qa_summary") or {},
                "evidence_coverage": quality_report.get("evidence_coverage") or {},
                "ready_for_training": bool(quality_report.get("ready_for_training")),
            },
            "review_gate": {
                "status": "approved_for_dataset_freeze",
                "reviewer": reviewer,
                "notes": notes,
                "reviewed_at": created_at,
            },
            "training_guard": {
                "training_allowed": False,
                "training_started": False,
                "reason": "Dataset freeze only. Model training or promotion requires a separate explicit approval workflow.",
            },
        }
        manifest_file = f"freeze_{export_path.stem}_{manifest_ts}_{manifest_id[-8:]}.json"
        manifest_path = self._freeze_dir(tenant_id) / manifest_file
        atomic_write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
        self._append_freeze_meta(
            tenant_id,
            manifest_file,
            manifest,
        )
        return manifest

    def approve_training_from_freeze(
        self,
        manifest_id: str,
        *,
        tenant_id: str = "system",
        approver: str,
        eval_plan: dict[str, Any],
        notes: str = "",
        dry_run: bool = True,
        start_training: bool = False,
    ) -> dict[str, Any] | None:
        """Record a manual training approval gate without starting a provider job."""
        if not _is_safe_manifest_id(manifest_id):
            raise ValueError("Invalid manifest_id.")
        approver = approver.strip()
        if not approver:
            raise ValueError("approver is required.")
        if not isinstance(eval_plan, dict) or not eval_plan:
            raise ValueError("eval_plan is required.")
        if start_training:
            raise ValueError("Phase 10 is no-provider-job mode; start_training requires a separate execution workflow.")
        if not dry_run:
            raise ValueError("Phase 10 only supports dry_run=true.")
        manifest = self._load_freeze_manifest_by_id(manifest_id, tenant_id=tenant_id)
        if manifest is None:
            return None
        freeze_reviewer = str((manifest.get("review_gate") or {}).get("reviewer") or "").strip()
        if freeze_reviewer and freeze_reviewer == approver:
            raise ValueError("training approver must be different from dataset freeze reviewer.")
        if (manifest.get("training_guard") or {}).get("training_started") is True:
            raise ValueError("dataset manifest already has training_started=true.")
        if (manifest.get("quality_report") or {}).get("ready_for_training") is not True:
            raise ValueError("dataset manifest quality report is not ready for training approval.")

        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        approval_ts = now.strftime("%Y%m%dT%H%M%S")
        approval_id = f"tap_{uuid.uuid4().hex}"
        approval = {
            "schema_version": "document_ops_training_approval_v1",
            "approval_id": approval_id,
            "created_at": created_at,
            "tenant_id": tenant_id,
            "manifest": {
                "manifest_id": manifest.get("manifest_id"),
                "export_filename": (manifest.get("export") or {}).get("filename"),
                "export_sha256": (manifest.get("export") or {}).get("sha256"),
                "quality_report_sha256": (manifest.get("quality_report") or {}).get("sha256"),
                "record_count": (manifest.get("export") or {}).get("record_count"),
            },
            "approval_gate": {
                "status": "approved_for_training_dry_run",
                "approver": approver,
                "notes": notes,
                "approved_at": created_at,
                "freeze_reviewer": freeze_reviewer,
            },
            "eval_plan": _redact_input(eval_plan),
            "execution_guard": {
                "dry_run": True,
                "start_training_requested": False,
                "provider_job_started": False,
                "model_promotion_allowed": False,
                "reason": "Training approval recorded only. Provider job execution and model promotion require a separate explicit workflow.",
            },
        }
        approval_file = f"training_approval_{manifest_id}_{approval_ts}_{approval_id[-8:]}.json"
        approval_path = self._training_approval_dir(tenant_id) / approval_file
        atomic_write_text(approval_path, json.dumps(approval, ensure_ascii=False, indent=2, sort_keys=True))
        self._append_training_approval_meta(tenant_id, approval_file, approval)
        return approval

    def preview_sft_export(
        self,
        *,
        tenant_id: str = "system",
        task_type: str | None = None,
        min_records: int = 1,
        accepted_only: bool = True,
        include_metadata: bool = True,
        sample_limit: int = 5,
    ) -> dict[str, Any]:
        """Dry-run SFT export selection without writing files."""
        all_records = self.get_records(
            tenant_id=tenant_id,
            task_type=task_type,
            limit=100_000,
        )
        candidate_records = [
            record
            for record in all_records
            if not accepted_only or _is_accepted(record)
        ]
        blocked: list[dict[str, Any]] = []
        eligible: list[dict[str, Any]] = []
        for record in candidate_records:
            blockers = _sft_export_blockers(record, accepted_only=accepted_only)
            if blockers:
                blocked.append(_record_preview(record, blockers=blockers))
            else:
                eligible.append(record)

        blocker_summary: dict[str, int] = {}
        for item in blocked:
            for blocker in item["blockers"]:
                blocker_summary[blocker] = blocker_summary.get(blocker, 0) + 1
        quality_scores = [
            score
            for score in (_quality_score(record) for record in eligible)
            if score is not None
        ]
        export_ready = len(eligible) >= min_records
        warnings: list[str] = []
        if len(eligible) < min_records:
            warnings.append("min_records_not_met")
        if blocked:
            warnings.append("blocked_records_present")
        return {
            "dry_run": True,
            "would_export": export_ready,
            "tenant_id": tenant_id,
            "task_type": task_type,
            "accepted_only": accepted_only,
            "include_metadata": include_metadata,
            "min_records": min_records,
            "candidate_count": len(candidate_records),
            "eligible_count": len(eligible),
            "blocked_count": len(blocked),
            "estimated_jsonl_lines": len(eligible),
            "blocker_summary": blocker_summary,
            "quality_score_summary": _score_summary(quality_scores),
            "task_counts": _count_by(eligible, "task_type"),
            "skill_counts": _skill_counts(eligible),
            "sample_records": [
                _record_preview(record, blockers=[])
                for record in eligible[: max(0, sample_limit)]
            ],
            "blocked_samples": blocked[: max(0, sample_limit)],
            "warnings": warnings,
        }

    def report_sft_export_quality(
        self,
        *,
        tenant_id: str = "system",
        task_type: str | None = None,
        min_records: int = 1,
        accepted_only: bool = True,
        include_metadata: bool = True,
        sample_limit: int = 5,
    ) -> dict[str, Any]:
        """Build an offline quality report for the next reviewed SFT export."""
        all_records = self.get_records(
            tenant_id=tenant_id,
            task_type=task_type,
            limit=100_000,
        )
        candidate_records = [
            record
            for record in all_records
            if not accepted_only or _is_accepted(record)
        ]
        blocked: list[dict[str, Any]] = []
        eligible: list[dict[str, Any]] = []
        for record in candidate_records:
            blockers = _sft_export_blockers(record, accepted_only=accepted_only)
            if blockers:
                blocked.append(_record_preview(record, blockers=blockers))
            else:
                eligible.append(record)
        sft_records = [self._to_sft_record(record, include_metadata=include_metadata) for record in eligible]
        report = _build_sft_quality_report(
            sft_records,
            blocked_samples=blocked,
            sample_limit=sample_limit,
        )
        report.update(
            {
                "report_type": "sft_export_candidate_quality",
                "dry_run": True,
                "tenant_id": tenant_id,
                "task_type": task_type,
                "accepted_only": accepted_only,
                "include_metadata": include_metadata,
                "min_records": min_records,
                "candidate_count": len(candidate_records),
                "eligible_count": len(eligible),
                "blocked_count": len(blocked),
                "rejection_reason_summary": _blocker_summary(blocked),
                "ready_for_export": len(eligible) >= min_records and report["schema_invalid_count"] == 0,
                "ready_for_training": (
                    len(eligible) >= min_records
                    and report["schema_invalid_count"] == 0
                    and not blocked
                ),
            }
        )
        report["recommendations"] = _quality_recommendations(report)
        return report

    def inspect_sft_export_quality(
        self,
        filename: str,
        *,
        tenant_id: str = "system",
        sample_limit: int = 5,
    ) -> dict[str, Any] | None:
        """Inspect a metadata-recorded SFT JSONL export without modifying it."""
        path = self.get_sft_export_path(filename, tenant_id=tenant_id)
        if path is None:
            return None
        records: list[dict[str, Any]] = []
        parse_errors: list[dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                item = json.loads(stripped)
            except json.JSONDecodeError as exc:
                parse_errors.append(
                    {
                        "line": line_number,
                        "issues": ["invalid_jsonl"],
                        "detail": str(exc),
                    }
                )
                continue
            if isinstance(item, dict):
                records.append(item)
            else:
                parse_errors.append(
                    {
                        "line": line_number,
                        "issues": ["jsonl_root_not_object"],
                    }
                )
        report = _build_sft_quality_report(
            records,
            blocked_samples=[],
            jsonl_parse_errors=parse_errors,
            sample_limit=sample_limit,
        )
        report.update(
            {
                "report_type": "sft_export_file_quality",
                "dry_run": False,
                "tenant_id": tenant_id,
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "jsonl_line_count": len(records) + len(parse_errors),
                "ready_for_training": report["schema_invalid_count"] == 0 and bool(records),
                "rejection_reason_summary": {},
            }
        )
        report["recommendations"] = _quality_recommendations(report)
        return report

    def training_readiness_summary(
        self,
        *,
        tenant_id: str = "system",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Summarize readiness gates without starting training or uploads."""
        reviewed_exports = self.list_reviewed_sft_exports(tenant_id=tenant_id, limit=limit)
        freezes = self.list_dataset_freezes(tenant_id=tenant_id, limit=limit)
        approvals = self.list_training_approvals(tenant_id=tenant_id, limit=limit)

        latest_export = reviewed_exports[0] if reviewed_exports else None
        latest_freeze = freezes[0] if freezes else None
        latest_approval = approvals[0] if approvals else None

        latest_quality_report: dict[str, Any] | None = None
        if latest_export and latest_export.get("exists") is True:
            latest_quality_report = self.inspect_sft_export_quality(
                str(latest_export.get("filename") or ""),
                tenant_id=tenant_id,
                sample_limit=0,
            )

        approval_eval_summaries = [
            self._training_approval_eval_summary(tenant_id, approval)
            for approval in approvals
        ]
        approvals_with_eval_plan = sum(1 for item in approval_eval_summaries if item["has_eval_plan"])
        approvals_with_required_metrics = sum(1 for item in approval_eval_summaries if item["has_required_metrics"])
        latest_eval_summary = approval_eval_summaries[0] if approval_eval_summaries else None

        provider_job_started_count = sum(1 for item in approvals if item.get("provider_job_started") is True)
        model_promotion_allowed_count = sum(1 for item in approvals if item.get("model_promotion_allowed") is True)
        training_allowed_count = sum(1 for item in freezes if item.get("training_allowed") is True)
        training_started_count = sum(1 for item in freezes if item.get("training_started") is True)

        blockers: list[str] = []
        if latest_export is None:
            blockers.append("no_reviewed_sft_export")
        elif latest_export.get("exists") is not True:
            blockers.append("latest_reviewed_sft_export_missing")
        if latest_quality_report is None:
            blockers.append("latest_export_quality_report_unavailable")
        elif latest_quality_report.get("ready_for_training") is not True:
            blockers.append("latest_export_quality_not_ready")
        if latest_freeze is None:
            blockers.append("no_dataset_freeze_manifest")
        elif latest_freeze.get("exists") is not True:
            blockers.append("latest_dataset_freeze_manifest_missing")
        if latest_approval is None:
            blockers.append("no_dry_run_training_approval")
        elif latest_approval.get("exists") is not True:
            blockers.append("latest_training_approval_file_missing")
        if latest_eval_summary is None or latest_eval_summary["has_eval_plan"] is not True:
            blockers.append("latest_training_approval_missing_eval_plan")
        elif latest_eval_summary["has_required_metrics"] is not True:
            blockers.append("latest_training_approval_missing_required_metrics")
        if provider_job_started_count:
            blockers.append("provider_job_started_detected")
        if model_promotion_allowed_count:
            blockers.append("model_promotion_allowed_detected")
        if training_allowed_count:
            blockers.append("dataset_training_allowed_flag_detected")
        if training_started_count:
            blockers.append("dataset_training_started_flag_detected")

        ready_for_training_execution = not blockers
        status = "ready_for_training_decision" if ready_for_training_execution else "needs_attention"
        return {
            "report_type": "document_ops_training_readiness",
            "read_only": True,
            "tenant_id": tenant_id,
            "generated_at": _now_iso(),
            "status": status,
            "ready_for_training_execution": ready_for_training_execution,
            "training_execution_allowed": False,
            "reviewed_export_count": len(reviewed_exports),
            "freeze_count": len(freezes),
            "dry_run_training_approval_count": len(approvals),
            "counts": {
                "reviewed_sft_exports": len(reviewed_exports),
                "dataset_freezes": len(freezes),
                "dry_run_training_approvals": len(approvals),
            },
            "latest_reviewed_export": latest_export,
            "latest_dataset_freeze": latest_freeze,
            "latest_training_approval": latest_approval,
            "latest_export_quality": {
                "ready_for_training": bool((latest_quality_report or {}).get("ready_for_training")),
                "schema_valid_count": int((latest_quality_report or {}).get("schema_valid_count") or 0),
                "schema_invalid_count": int((latest_quality_report or {}).get("schema_invalid_count") or 0),
                "jsonl_record_count": int((latest_quality_report or {}).get("jsonl_record_count") or 0),
                "evidence_coverage": (latest_quality_report or {}).get("evidence_coverage") or {},
                "qa_summary": (latest_quality_report or {}).get("qa_summary") or {},
                "recommendations": (latest_quality_report or {}).get("recommendations") or [],
            },
            "eval_plan_coverage": {
                "approval_count": len(approvals),
                "approvals_with_eval_plan": approvals_with_eval_plan,
                "approvals_with_required_metrics": approvals_with_required_metrics,
                "latest": latest_eval_summary,
            },
            "training_guard": {
                "training_started_count": training_started_count,
                "training_allowed_count": training_allowed_count,
                "provider_job_started_count": provider_job_started_count,
                "model_promotion_allowed_count": model_promotion_allowed_count,
                "external_upload_started": False,
                "no_training_started": (
                    training_started_count == 0
                    and provider_job_started_count == 0
                    and model_promotion_allowed_count == 0
                ),
            },
            "blockers": blockers,
            "recommendations": _training_readiness_recommendations(blockers),
        }

    def training_execution_plan_preview(
        self,
        *,
        tenant_id: str = "system",
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Build a provider-agnostic dry-run training job spec without side effects."""
        readiness = self.training_readiness_summary(tenant_id=tenant_id, limit=limit)
        latest_freeze = readiness.get("latest_dataset_freeze") if isinstance(readiness.get("latest_dataset_freeze"), dict) else {}
        latest_approval = (
            readiness.get("latest_training_approval")
            if isinstance(readiness.get("latest_training_approval"), dict)
            else {}
        )
        manifest_id = str(latest_freeze.get("manifest_id") or "")
        manifest = self._load_freeze_manifest_by_id(manifest_id, tenant_id=tenant_id) if manifest_id else None
        approval = self._load_training_approval_by_file(
            tenant_id,
            str(latest_approval.get("approval_file") or ""),
        )
        export = manifest.get("export") if isinstance((manifest or {}).get("export"), dict) else {}
        quality_report = (
            manifest.get("quality_report")
            if isinstance((manifest or {}).get("quality_report"), dict)
            else {}
        )
        eval_plan = approval.get("eval_plan") if isinstance((approval or {}).get("eval_plan"), dict) else {}
        blocked = readiness.get("ready_for_training_execution") is not True
        provider_label = _safe_provider_label(provider)
        job_spec = {
            "provider": provider_label,
            "objective": "supervised_fine_tuning",
            "base_model": (base_model or "").strip() or "to_be_selected",
            "dataset": {
                "tenant_id": tenant_id,
                "freeze_manifest_id": manifest_id or None,
                "export_filename": export.get("filename"),
                "export_sha256": export.get("sha256"),
                "record_count": int(export.get("record_count") or 0),
                "quality_report_sha256": quality_report.get("sha256"),
            },
            "evaluation": {
                "suite": eval_plan.get("suite") or eval_plan.get("eval_suite"),
                "required_metrics": eval_plan.get("required_metrics") or eval_plan.get("metrics") or {},
            },
            "training_parameters": {
                "epochs": "to_be_selected",
                "batch_size": "to_be_selected",
                "learning_rate_multiplier": "to_be_selected",
            },
            "execution_steps": [
                {"step": "validate_readiness", "status": "preview_only"},
                {"step": "upload_dataset", "status": "not_started"},
                {"step": "create_provider_fine_tune_job", "status": "not_started"},
                {"step": "monitor_training", "status": "not_started"},
                {"step": "run_required_evals", "status": "not_started"},
                {"step": "promote_model_candidate", "status": "not_started"},
            ],
        }
        return {
            "report_type": "document_ops_training_execution_plan_preview",
            "tenant_id": tenant_id,
            "generated_at": _now_iso(),
            "dry_run": True,
            "preview_only": True,
            "read_only": True,
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
            "status": "blocked" if blocked else "ready_for_manual_execution_planning",
            "readiness_status": readiness.get("status"),
            "blockers": readiness.get("blockers") or [],
            "job_spec": job_spec,
            "required_manual_actions": [
                "select_provider_and_base_model",
                "confirm_dataset_freeze_manifest",
                "confirm_eval_plan_thresholds",
                "create_separate_training_execution_approval",
            ],
        }

    def list_training_execution_requests(
        self,
        *,
        tenant_id: str = "system",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return newest no-side-effect training execution request records."""
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_requests = meta.get("training_execution_requests") if isinstance(meta.get("training_execution_requests"), list) else []
        requests: list[dict[str, Any]] = []
        seen_files: set[str] = set()
        for item in reversed(raw_requests):
            if not isinstance(item, dict):
                continue
            request_file = str(item.get("request_file") or "")
            if request_file in seen_files:
                continue
            request_path = self._resolve_training_execution_request_path(tenant_id, request_file)
            requests.append(
                {
                    "request_id": item.get("request_id"),
                    "request_file": request_file,
                    "manifest_id": item.get("manifest_id"),
                    "approval_id": item.get("approval_id"),
                    "provider": item.get("provider"),
                    "base_model": item.get("base_model"),
                    "requester": item.get("requester"),
                    "prior_training_approver": item.get("prior_training_approver"),
                    "two_person_guard_satisfied": bool(item.get("two_person_guard_satisfied", False)),
                    "training_execution_allowed": bool(item.get("training_execution_allowed", False)),
                    "provider_job_started": bool(item.get("provider_job_started", False)),
                    "external_upload_started": bool(item.get("external_upload_started", False)),
                    "created_at": item.get("created_at"),
                    "exists": request_path is not None,
                    "size_bytes": request_path.stat().st_size if request_path else 0,
                }
            )
            seen_files.add(request_file)
            if len(requests) >= limit:
                break
        return requests

    def request_training_execution_from_plan(
        self,
        *,
        tenant_id: str = "system",
        requester: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        notes: str = "",
        limit: int = 50,
        start_training: bool = False,
        upload_dataset: bool = False,
        call_provider_api: bool = False,
    ) -> dict[str, Any]:
        """Record a two-person training execution request without execution side effects."""
        requester = requester.strip()
        if not requester:
            raise ValueError("requester is required.")
        if start_training:
            raise ValueError("Training execution requests are record-only; start_training requires a separate execution workflow.")
        if upload_dataset:
            raise ValueError("Training execution requests are no-upload; dataset upload requires a separate execution workflow.")
        if call_provider_api:
            raise ValueError("Training execution requests cannot call provider APIs.")

        plan_preview = self.training_execution_plan_preview(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )
        if plan_preview.get("status") != "ready_for_manual_execution_planning":
            raise ValueError("Training execution request requires a ready dry-run plan preview.")
        job_spec = plan_preview.get("job_spec") if isinstance(plan_preview.get("job_spec"), dict) else {}
        dataset = job_spec.get("dataset") if isinstance(job_spec.get("dataset"), dict) else {}
        latest_approval = self.training_readiness_summary(tenant_id=tenant_id, limit=limit).get("latest_training_approval")
        approval_meta = latest_approval if isinstance(latest_approval, dict) else {}
        prior_approver = str(approval_meta.get("approver") or "").strip()
        if prior_approver and prior_approver == requester:
            raise ValueError("execution requester must be different from dry-run training approver.")

        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        request_ts = now.strftime("%Y%m%dT%H%M%S")
        request_id = f"ter_{uuid.uuid4().hex}"
        request_record = {
            "schema_version": "document_ops_training_execution_request_v1",
            "request_id": request_id,
            "created_at": created_at,
            "tenant_id": tenant_id,
            "plan_preview": {
                "report_type": plan_preview.get("report_type"),
                "generated_at": plan_preview.get("generated_at"),
                "provider": job_spec.get("provider"),
                "base_model": job_spec.get("base_model"),
                "dataset": dataset,
                "evaluation": job_spec.get("evaluation") if isinstance(job_spec.get("evaluation"), dict) else {},
            },
            "request_gate": {
                "status": "requested_for_separate_training_execution_review",
                "requester": requester,
                "notes": notes,
                "requested_at": created_at,
                "prior_training_approver": prior_approver,
                "prior_training_approval_id": approval_meta.get("approval_id"),
            },
            "two_person_guard": {
                "required": True,
                "prior_training_approver": prior_approver,
                "execution_requester": requester,
                "satisfied": bool(prior_approver and prior_approver != requester),
            },
            "execution_guard": {
                "training_execution_allowed": False,
                "start_training_requested": False,
                "external_upload_started": False,
                "provider_api_calls_allowed": False,
                "provider_job_started": False,
                "model_promotion_allowed": False,
                "reason": "Execution request recorded only. Training, upload, provider jobs, and promotion require a separate explicit workflow.",
            },
        }
        if request_record["two_person_guard"]["satisfied"] is not True:
            raise ValueError("two-person guard is not satisfied.")

        request_file = f"training_execution_request_{request_id}_{request_ts}.json"
        request_path = self._training_execution_request_dir(tenant_id) / request_file
        atomic_write_text(request_path, json.dumps(request_record, ensure_ascii=False, indent=2, sort_keys=True))
        self._append_training_execution_request_meta(tenant_id, request_file, request_record)
        return request_record

    def training_pre_execution_audit_checklist(
        self,
        *,
        tenant_id: str = "system",
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Bundle readiness, plan preview, and request records for human audit."""
        readiness = self.training_readiness_summary(tenant_id=tenant_id, limit=limit)
        plan_preview = self.training_execution_plan_preview(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )
        requests = self.list_training_execution_requests(tenant_id=tenant_id, limit=limit)
        latest_request = requests[0] if requests else None
        request_guard_clean = bool(
            latest_request
            and latest_request.get("training_execution_allowed") is False
            and latest_request.get("provider_job_started") is False
            and latest_request.get("external_upload_started") is False
        )
        readiness_ready = readiness.get("ready_for_training_execution") is True
        plan_ready = plan_preview.get("status") == "ready_for_manual_execution_planning"
        two_person_ready = bool(latest_request and latest_request.get("two_person_guard_satisfied") is True)
        no_side_effects = bool(
            plan_preview.get("training_execution_allowed") is False
            and plan_preview.get("provider_api_calls_allowed") is False
            and plan_preview.get("external_upload_allowed") is False
            and plan_preview.get("provider_job_started") is False
            and plan_preview.get("model_promotion_allowed") is False
            and request_guard_clean
        )
        job_spec = plan_preview.get("job_spec") if isinstance(plan_preview.get("job_spec"), dict) else {}
        dataset = job_spec.get("dataset") if isinstance(job_spec.get("dataset"), dict) else {}
        evaluation = job_spec.get("evaluation") if isinstance(job_spec.get("evaluation"), dict) else {}
        checklist = [
            {
                "id": "readiness_summary_ready",
                "severity": "required",
                "passed": readiness_ready,
                "evidence": {
                    "status": readiness.get("status"),
                    "blockers": readiness.get("blockers") or [],
                },
            },
            {
                "id": "dry_run_plan_preview_ready",
                "severity": "required",
                "passed": plan_ready,
                "evidence": {
                    "status": plan_preview.get("status"),
                    "provider": job_spec.get("provider"),
                    "base_model": job_spec.get("base_model"),
                    "freeze_manifest_id": dataset.get("freeze_manifest_id"),
                },
            },
            {
                "id": "execution_request_recorded",
                "severity": "required",
                "passed": latest_request is not None,
                "evidence": {
                    "request_id": (latest_request or {}).get("request_id"),
                    "exists": (latest_request or {}).get("exists", False),
                },
            },
            {
                "id": "two_person_guard_satisfied",
                "severity": "required",
                "passed": two_person_ready,
                "evidence": {
                    "requester": (latest_request or {}).get("requester"),
                    "prior_training_approver": (latest_request or {}).get("prior_training_approver"),
                },
            },
            {
                "id": "no_training_side_effects_detected",
                "severity": "required",
                "passed": no_side_effects,
                "evidence": {
                    "training_execution_allowed": plan_preview.get("training_execution_allowed"),
                    "provider_api_calls_allowed": plan_preview.get("provider_api_calls_allowed"),
                    "external_upload_allowed": plan_preview.get("external_upload_allowed"),
                    "request_guard_clean": request_guard_clean,
                },
            },
            {
                "id": "eval_metrics_attached",
                "severity": "required",
                "passed": bool(evaluation.get("required_metrics")),
                "evidence": {
                    "suite": evaluation.get("suite"),
                    "required_metrics": sorted(str(key) for key in (evaluation.get("required_metrics") or {}).keys()),
                },
            },
            {
                "id": "provider_and_base_model_pending_manual_selection",
                "severity": "advisory",
                "passed": not (
                    str(job_spec.get("provider") or "") == "provider_agnostic"
                    or str(job_spec.get("base_model") or "") == "to_be_selected"
                ),
                "evidence": {
                    "provider": job_spec.get("provider"),
                    "base_model": job_spec.get("base_model"),
                    "note": "Advisory only; final provider/model selection remains a separate manual execution workflow.",
                },
            },
        ]
        required_failures = [
            str(item["id"])
            for item in checklist
            if item.get("severity") == "required" and item.get("passed") is not True
        ]
        blockers = _dedupe(
            [
                *[str(item) for item in readiness.get("blockers") or []],
                *[str(item) for item in plan_preview.get("blockers") or []],
                *required_failures,
            ]
        )
        status = "ready_for_human_pre_execution_review" if not blockers else "blocked"
        return {
            "report_type": "document_ops_training_pre_execution_audit_checklist",
            "tenant_id": tenant_id,
            "generated_at": _now_iso(),
            "read_only": True,
            "preview_only": True,
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
            "status": status,
            "blockers": blockers,
            "checklist": checklist,
            "latest_training_execution_request": latest_request,
            "training_execution_requests": requests,
            "readiness_summary": readiness,
            "training_plan_preview": plan_preview,
            "human_review_packet": {
                "dataset": dataset,
                "evaluation": evaluation,
                "latest_request_id": (latest_request or {}).get("request_id"),
                "request_count": len(requests),
            },
        }

    def list_training_pre_execution_audits(
        self,
        *,
        tenant_id: str = "system",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return newest exported pre-execution audit artifacts."""
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_audits = meta.get("training_pre_execution_audits") if isinstance(meta.get("training_pre_execution_audits"), list) else []
        audits: list[dict[str, Any]] = []
        seen_files: set[str] = set()
        for item in reversed(raw_audits):
            if not isinstance(item, dict):
                continue
            audit_file = str(item.get("audit_file") or "")
            if audit_file in seen_files:
                continue
            audit_path = self._resolve_training_audit_path(tenant_id, audit_file)
            audits.append(
                {
                    "audit_id": item.get("audit_id"),
                    "audit_file": audit_file,
                    "status": item.get("status"),
                    "auditor": item.get("auditor"),
                    "request_id": item.get("request_id"),
                    "manifest_id": item.get("manifest_id"),
                    "provider": item.get("provider"),
                    "base_model": item.get("base_model"),
                    "training_execution_allowed": bool(item.get("training_execution_allowed", False)),
                    "provider_job_started": bool(item.get("provider_job_started", False)),
                    "external_upload_started": bool(item.get("external_upload_started", False)),
                    "created_at": item.get("created_at"),
                    "exists": audit_path is not None,
                    "size_bytes": audit_path.stat().st_size if audit_path else 0,
                }
            )
            seen_files.add(audit_file)
            if len(audits) >= limit:
                break
        return audits

    def export_training_pre_execution_audit(
        self,
        *,
        tenant_id: str = "system",
        auditor: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        notes: str = "",
        limit: int = 50,
        start_training: bool = False,
        upload_dataset: bool = False,
        call_provider_api: bool = False,
    ) -> dict[str, Any]:
        """Write a final human-review audit packet without execution side effects."""
        auditor = auditor.strip()
        if not auditor:
            raise ValueError("auditor is required.")
        if start_training:
            raise ValueError("Pre-execution audit export is no-execution; start_training requires a separate workflow.")
        if upload_dataset:
            raise ValueError("Pre-execution audit export is no-upload; dataset upload requires a separate workflow.")
        if call_provider_api:
            raise ValueError("Pre-execution audit export cannot call provider APIs.")

        checklist = self.training_pre_execution_audit_checklist(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )
        if checklist.get("status") != "ready_for_human_pre_execution_review":
            raise ValueError("Pre-execution audit export requires a ready checklist.")
        latest_request = (
            checklist.get("latest_training_execution_request")
            if isinstance(checklist.get("latest_training_execution_request"), dict)
            else {}
        )
        requester = str(latest_request.get("requester") or "").strip()
        prior_approver = str(latest_request.get("prior_training_approver") or "").strip()
        if requester and auditor == requester:
            raise ValueError("auditor must be different from training execution requester.")
        if prior_approver and auditor == prior_approver:
            raise ValueError("auditor must be different from dry-run training approver.")

        now = datetime.now(timezone.utc)
        created_at = now.isoformat()
        audit_ts = now.strftime("%Y%m%dT%H%M%S")
        audit_id = f"tea_{uuid.uuid4().hex}"
        audit_record = {
            "schema_version": "document_ops_training_pre_execution_audit_v1",
            "audit_id": audit_id,
            "created_at": created_at,
            "tenant_id": tenant_id,
            "audit_gate": {
                "status": "exported_for_final_human_pre_execution_review",
                "auditor": auditor,
                "notes": notes,
                "audited_at": created_at,
                "requester": requester,
                "prior_training_approver": prior_approver,
                "separation_of_duties_satisfied": bool(
                    auditor and auditor not in {requester, prior_approver}
                ),
            },
            "checklist_snapshot": checklist,
            "execution_guard": {
                "training_execution_allowed": False,
                "start_training_requested": False,
                "external_upload_started": False,
                "provider_api_calls_allowed": False,
                "provider_job_started": False,
                "model_promotion_allowed": False,
                "reason": "Audit export only. Training, upload, provider jobs, and model promotion require a separate explicit execution workflow.",
            },
        }
        audit_file = f"training_pre_execution_audit_{audit_id}_{audit_ts}.json"
        audit_path = self._training_audit_dir(tenant_id) / audit_file
        audit_record["audit_file"] = audit_file
        atomic_write_text(audit_path, json.dumps(audit_record, ensure_ascii=False, indent=2, sort_keys=True))
        self._append_training_pre_execution_audit_meta(tenant_id, audit_file, audit_record)
        return audit_record

    def get_training_pre_execution_audit_path(self, filename: str, *, tenant_id: str = "system") -> Path | None:
        """Resolve a metadata-safe pre-execution audit artifact path."""
        return self._resolve_training_audit_path(tenant_id, filename)

    def training_governance_dashboard_summary(
        self,
        *,
        tenant_id: str = "system",
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Aggregate all pre-training governance gates without side effects."""
        reviewed_exports = self.list_reviewed_sft_exports(tenant_id=tenant_id, limit=limit)
        freezes = self.list_dataset_freezes(tenant_id=tenant_id, limit=limit)
        approvals = self.list_training_approvals(tenant_id=tenant_id, limit=limit)
        execution_requests = self.list_training_execution_requests(tenant_id=tenant_id, limit=limit)
        audits = self.list_training_pre_execution_audits(tenant_id=tenant_id, limit=limit)
        readiness = self.training_readiness_summary(tenant_id=tenant_id, limit=limit)
        plan_preview = self.training_execution_plan_preview(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )
        audit_checklist = self.training_pre_execution_audit_checklist(
            tenant_id=tenant_id,
            provider=provider,
            base_model=base_model,
            limit=limit,
        )
        guard_counts = {
            "training_allowed_count": sum(1 for item in freezes if item.get("training_allowed") is True),
            "training_started_count": sum(1 for item in freezes if item.get("training_started") is True),
            "approval_provider_job_started_count": sum(1 for item in approvals if item.get("provider_job_started") is True),
            "approval_model_promotion_allowed_count": sum(1 for item in approvals if item.get("model_promotion_allowed") is True),
            "request_training_execution_allowed_count": sum(1 for item in execution_requests if item.get("training_execution_allowed") is True),
            "request_provider_job_started_count": sum(1 for item in execution_requests if item.get("provider_job_started") is True),
            "request_external_upload_started_count": sum(1 for item in execution_requests if item.get("external_upload_started") is True),
            "audit_training_execution_allowed_count": sum(1 for item in audits if item.get("training_execution_allowed") is True),
            "audit_provider_job_started_count": sum(1 for item in audits if item.get("provider_job_started") is True),
            "audit_external_upload_started_count": sum(1 for item in audits if item.get("external_upload_started") is True),
        }
        no_side_effects = all(value == 0 for value in guard_counts.values())
        required_audit_failures = [
            str(item.get("id"))
            for item in audit_checklist.get("checklist", [])
            if isinstance(item, dict)
            and item.get("severity") == "required"
            and item.get("passed") is not True
        ]
        blockers = _dedupe(
            [
                *[str(item) for item in readiness.get("blockers") or []],
                *[str(item) for item in plan_preview.get("blockers") or []],
                *[str(item) for item in audit_checklist.get("blockers") or []],
                *required_audit_failures,
                *(["training_side_effect_detected"] if not no_side_effects else []),
            ]
        )
        status = "governance_ready_for_human_review" if not blockers and audits else "needs_attention"
        return {
            "report_type": "document_ops_training_governance_dashboard_summary",
            "tenant_id": tenant_id,
            "generated_at": _now_iso(),
            "read_only": True,
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
            "status": status,
            "counts": {
                "reviewed_sft_exports": len(reviewed_exports),
                "dataset_freezes": len(freezes),
                "dry_run_training_approvals": len(approvals),
                "training_execution_requests": len(execution_requests),
                "pre_execution_audit_exports": len(audits),
            },
            "latest": {
                "reviewed_sft_export": reviewed_exports[0] if reviewed_exports else None,
                "dataset_freeze": freezes[0] if freezes else None,
                "dry_run_training_approval": approvals[0] if approvals else None,
                "training_execution_request": execution_requests[0] if execution_requests else None,
                "pre_execution_audit": audits[0] if audits else None,
            },
            "guard_counts": guard_counts,
            "no_side_effects": no_side_effects,
            "blockers": blockers,
            "readiness_status": readiness.get("status"),
            "plan_preview_status": plan_preview.get("status"),
            "audit_checklist_status": audit_checklist.get("status"),
            "readiness_summary": readiness,
            "training_plan_preview": plan_preview,
            "audit_checklist": audit_checklist,
        }

    def reviewer_signoff_summary(
        self,
        *,
        tenant_id: str = "system",
        limit: int = 50,
    ) -> dict[str, Any]:
        """Summarize tenant-local reviewer sign-off JSON records without side effects."""
        signoff_dir = self._reviewer_signoff_dir(tenant_id)
        paths = _list_reviewer_signoff_record_paths(signoff_dir, limit=limit)
        records: list[dict[str, Any]] = []
        load_errors: list[dict[str, str]] = []
        for path in paths:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("sign-off record must be a JSON object")
                records.append(_summarize_reviewer_signoff_record(path.name, data))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                load_errors.append({"filename": path.name, "error": str(exc)})

        completed_count = sum(1 for item in records if item["completed_validation"]["valid"])
        pending_count = sum(
            1
            for item in records
            if item["record_status"] == "pending_manual_signoff_no_training_authorization"
        )
        follow_up_count = sum(
            1
            for item in records
            if item["record_status"] == "manual_follow_up_required_no_training_authorization"
        )
        boundary_violation_count = sum(
            1
            for item in records
            if item["record_status"] == "attention_required_boundary_violation"
        )
        all_protected_false = all(
            item["boundary"]["protected_training_flags_false"]
            and item["boundary"]["generation_side_effect_flags_false"]
            for item in records
        )
        if load_errors:
            overall_status = "attention_required_load_errors"
        elif not records:
            overall_status = "no_signoff_records_found"
        elif boundary_violation_count:
            overall_status = "attention_required_boundary_violation"
        elif completed_count == len(records):
            overall_status = "manual_signoff_complete_no_training_authorization"
        elif follow_up_count:
            overall_status = "manual_follow_up_required_no_training_authorization"
        else:
            overall_status = "pending_manual_signoff_no_training_authorization"

        return {
            "report_type": "document_ops_phase25_signoff_summary_endpoint",
            "tenant_id": tenant_id,
            "generated_at": _now_iso(),
            "read_only": True,
            "summary_source": "tenant_local_reviewer_signoff_records",
            "record_directory_exists": signoff_dir.is_dir(),
            "record_count": len(records),
            "load_error_count": len(load_errors),
            "overall_status": overall_status,
            "status": overall_status,
            "training_execution_allowed": False,
            "provider_api_calls_allowed": False,
            "external_upload_allowed": False,
            "provider_job_started": False,
            "model_promotion_allowed": False,
            "records": records,
            "load_errors": load_errors,
            "aggregate": {
                "completed_record_count": completed_count,
                "pending_record_count": pending_count,
                "manual_follow_up_record_count": follow_up_count,
                "boundary_violation_count": boundary_violation_count,
                "load_error_count": len(load_errors),
                "all_protected_training_flags_false": all_protected_false,
                "training_execution_authorized": False,
                "external_dataset_upload_authorized": False,
                "provider_fine_tune_api_call_authorized": False,
                "provider_job_creation_authorized": False,
                "model_promotion_authorized": False,
            },
            "side_effect_boundary": {
                "actual_reviewer_approval_recorded_by_summary": False,
                "training_execution_started": False,
                "external_dataset_uploaded": False,
                "provider_fine_tune_api_called": False,
                "provider_job_created": False,
                "model_promoted": False,
            },
            "blockers": _reviewer_signoff_summary_blockers(
                records=records,
                load_errors=load_errors,
                overall_status=overall_status,
            ),
        }

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
        skill_name = str(skill.get("name") or "unknown")
        skill_version = str(skill.get("version") or "unknown")
        assistant_payload = {
            "plan": record.get("plan") or [],
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
                "quality_score": (record.get("human_feedback") or {}).get("quality_score"),
            }
        return sft

    def _append_export_meta(
        self,
        tenant_id: str,
        filename: str,
        records: list[dict[str, Any]],
        *,
        task_type: str | None,
        accepted_only: bool,
    ) -> None:
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
            meta["export_count"] = int(meta.get("export_count") or 0) + 1
            meta.setdefault("exports", []).append(
                {
                    "filename": filename,
                    "record_count": len(records),
                    "task_type": task_type,
                    "accepted_only": accepted_only,
                    "exported_at": _now_iso(),
                }
            )
            atomic_write_text(self._meta_path(tenant_id), json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True))

    def _append_freeze_meta(
        self,
        tenant_id: str,
        manifest_file: str,
        manifest: dict[str, Any],
    ) -> None:
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
            meta["freeze_count"] = int(meta.get("freeze_count") or 0) + 1
            meta.setdefault("freezes", []).append(
                {
                    "manifest_id": manifest.get("manifest_id"),
                    "manifest_file": manifest_file,
                    "export_filename": (manifest.get("export") or {}).get("filename"),
                    "record_count": (manifest.get("export") or {}).get("record_count"),
                    "quality_report_sha256": (manifest.get("quality_report") or {}).get("sha256"),
                    "training_allowed": (manifest.get("training_guard") or {}).get("training_allowed", False),
                    "training_started": (manifest.get("training_guard") or {}).get("training_started", False),
                    "reviewer": (manifest.get("review_gate") or {}).get("reviewer"),
                    "created_at": manifest.get("created_at"),
                }
            )
            atomic_write_text(self._meta_path(tenant_id), json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True))

    def _append_training_approval_meta(
        self,
        tenant_id: str,
        approval_file: str,
        approval: dict[str, Any],
    ) -> None:
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
            meta["training_approval_count"] = int(meta.get("training_approval_count") or 0) + 1
            manifest = approval.get("manifest") if isinstance(approval.get("manifest"), dict) else {}
            guard = approval.get("execution_guard") if isinstance(approval.get("execution_guard"), dict) else {}
            gate = approval.get("approval_gate") if isinstance(approval.get("approval_gate"), dict) else {}
            meta.setdefault("training_approvals", []).append(
                {
                    "approval_id": approval.get("approval_id"),
                    "approval_file": approval_file,
                    "manifest_id": manifest.get("manifest_id"),
                    "export_filename": manifest.get("export_filename"),
                    "approver": gate.get("approver"),
                    "dry_run": guard.get("dry_run", True),
                    "provider_job_started": guard.get("provider_job_started", False),
                    "model_promotion_allowed": guard.get("model_promotion_allowed", False),
                    "created_at": approval.get("created_at"),
                }
            )
            atomic_write_text(self._meta_path(tenant_id), json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True))

    def _append_training_execution_request_meta(
        self,
        tenant_id: str,
        request_file: str,
        request_record: dict[str, Any],
    ) -> None:
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
            meta["training_execution_request_count"] = int(meta.get("training_execution_request_count") or 0) + 1
            plan = request_record.get("plan_preview") if isinstance(request_record.get("plan_preview"), dict) else {}
            dataset = plan.get("dataset") if isinstance(plan.get("dataset"), dict) else {}
            gate = request_record.get("request_gate") if isinstance(request_record.get("request_gate"), dict) else {}
            guard = request_record.get("execution_guard") if isinstance(request_record.get("execution_guard"), dict) else {}
            two_person = request_record.get("two_person_guard") if isinstance(request_record.get("two_person_guard"), dict) else {}
            meta.setdefault("training_execution_requests", []).append(
                {
                    "request_id": request_record.get("request_id"),
                    "request_file": request_file,
                    "manifest_id": dataset.get("freeze_manifest_id"),
                    "approval_id": gate.get("prior_training_approval_id"),
                    "provider": plan.get("provider"),
                    "base_model": plan.get("base_model"),
                    "requester": gate.get("requester"),
                    "prior_training_approver": gate.get("prior_training_approver"),
                    "two_person_guard_satisfied": two_person.get("satisfied", False),
                    "training_execution_allowed": guard.get("training_execution_allowed", False),
                    "provider_job_started": guard.get("provider_job_started", False),
                    "external_upload_started": guard.get("external_upload_started", False),
                    "created_at": request_record.get("created_at"),
                }
            )
            atomic_write_text(self._meta_path(tenant_id), json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True))

    def _append_training_pre_execution_audit_meta(
        self,
        tenant_id: str,
        audit_file: str,
        audit_record: dict[str, Any],
    ) -> None:
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
            meta["training_pre_execution_audit_count"] = int(meta.get("training_pre_execution_audit_count") or 0) + 1
            gate = audit_record.get("audit_gate") if isinstance(audit_record.get("audit_gate"), dict) else {}
            guard = audit_record.get("execution_guard") if isinstance(audit_record.get("execution_guard"), dict) else {}
            checklist = (
                audit_record.get("checklist_snapshot")
                if isinstance(audit_record.get("checklist_snapshot"), dict)
                else {}
            )
            packet = (
                checklist.get("human_review_packet")
                if isinstance(checklist.get("human_review_packet"), dict)
                else {}
            )
            dataset = packet.get("dataset") if isinstance(packet.get("dataset"), dict) else {}
            plan = (
                checklist.get("training_plan_preview")
                if isinstance(checklist.get("training_plan_preview"), dict)
                else {}
            )
            job_spec = plan.get("job_spec") if isinstance(plan.get("job_spec"), dict) else {}
            meta.setdefault("training_pre_execution_audits", []).append(
                {
                    "audit_id": audit_record.get("audit_id"),
                    "audit_file": audit_file,
                    "status": gate.get("status"),
                    "auditor": gate.get("auditor"),
                    "request_id": packet.get("latest_request_id"),
                    "manifest_id": dataset.get("freeze_manifest_id"),
                    "provider": job_spec.get("provider"),
                    "base_model": job_spec.get("base_model"),
                    "training_execution_allowed": guard.get("training_execution_allowed", False),
                    "provider_job_started": guard.get("provider_job_started", False),
                    "external_upload_started": guard.get("external_upload_started", False),
                    "created_at": audit_record.get("created_at"),
                }
            )
            atomic_write_text(self._meta_path(tenant_id), json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True))

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

    def _load_freeze_manifest_by_id(self, manifest_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_freezes = meta.get("freezes") if isinstance(meta.get("freezes"), list) else []
        manifest_file = ""
        for item in raw_freezes:
            if isinstance(item, dict) and item.get("manifest_id") == manifest_id:
                manifest_file = str(item.get("manifest_file") or "")
                break
        if not manifest_file:
            return None
        manifest_path = self._resolve_freeze_path(tenant_id, manifest_file)
        if manifest_path is None:
            return None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _resolve_export_path(self, tenant_id: str, filename: str) -> Path | None:
        if not _is_safe_export_filename(filename):
            return None
        export_dir = self._export_dir(tenant_id)
        candidate = export_dir / filename
        try:
            base = export_dir.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_file() or not resolved.is_relative_to(base):
            return None
        return resolved

    def _resolve_freeze_path(self, tenant_id: str, filename: str) -> Path | None:
        if not _is_safe_freeze_filename(filename):
            return None
        freeze_dir = self._freeze_dir(tenant_id)
        candidate = freeze_dir / filename
        try:
            base = freeze_dir.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_file() or not resolved.is_relative_to(base):
            return None
        return resolved

    def _resolve_training_approval_path(self, tenant_id: str, filename: str) -> Path | None:
        if not _is_safe_training_approval_filename(filename):
            return None
        approval_dir = self._training_approval_dir(tenant_id)
        candidate = approval_dir / filename
        try:
            base = approval_dir.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_file() or not resolved.is_relative_to(base):
            return None
        return resolved

    def _resolve_training_execution_request_path(self, tenant_id: str, filename: str) -> Path | None:
        if not _is_safe_training_execution_request_filename(filename):
            return None
        request_dir = self._training_execution_request_dir(tenant_id)
        candidate = request_dir / filename
        try:
            base = request_dir.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_file() or not resolved.is_relative_to(base):
            return None
        return resolved

    def _resolve_training_audit_path(self, tenant_id: str, filename: str) -> Path | None:
        if not _is_safe_training_audit_filename(filename):
            return None
        audit_dir = self._training_audit_dir(tenant_id)
        candidate = audit_dir / filename
        try:
            base = audit_dir.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_file() or not resolved.is_relative_to(base):
            return None
        return resolved

    def _load_training_approval_by_file(self, tenant_id: str, filename: str) -> dict[str, Any] | None:
        approval_path = self._resolve_training_approval_path(tenant_id, filename)
        if approval_path is None:
            return None
        try:
            data = json.loads(approval_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _training_approval_eval_summary(self, tenant_id: str, approval: dict[str, Any]) -> dict[str, Any]:
        approval_file = str(approval.get("approval_file") or "")
        path = self._resolve_training_approval_path(tenant_id, approval_file)
        data = self._load_training_approval_by_file(tenant_id, approval_file) or {}
        eval_plan = data.get("eval_plan") if isinstance(data.get("eval_plan"), dict) else {}
        required_metrics = eval_plan.get("required_metrics") if isinstance(eval_plan.get("required_metrics"), dict) else {}
        return {
            "approval_id": approval.get("approval_id"),
            "approval_file": approval_file,
            "exists": path is not None,
            "has_eval_plan": bool(eval_plan),
            "suite": eval_plan.get("suite"),
            "has_required_metrics": bool(required_metrics),
            "required_metric_count": len(required_metrics),
            "required_metric_names": sorted(str(key) for key in required_metrics.keys()),
        }


def _is_accepted(record: dict[str, Any]) -> bool:
    feedback = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
    return bool(feedback.get("accepted")) or record.get("human_review_status") in {"accepted", "approved"}


def _sft_export_blockers(record: dict[str, Any], *, accepted_only: bool) -> list[str]:
    blockers: list[str] = []
    if accepted_only and not _is_accepted(record):
        blockers.append("not_accepted")
    if not str(record.get("task_type") or "").strip():
        blockers.append("missing_task_type")
    skill = record.get("skill") if isinstance(record.get("skill"), dict) else {}
    if not str(skill.get("name") or "").strip() or str(skill.get("name")) == "unknown":
        blockers.append("missing_skill")
    if not record.get("plan"):
        blockers.append("missing_plan")
    if not (record.get("final_output") or record.get("draft_output") or record.get("draft")):
        blockers.append("missing_assistant_output")
    qa = record.get("qa") if isinstance(record.get("qa"), dict) else {}
    if qa.get("hard_gate_pass") is False:
        blockers.append("qa_hard_gate_failed")
    return blockers


def _record_preview(record: dict[str, Any], *, blockers: list[str]) -> dict[str, Any]:
    skill = record.get("skill") if isinstance(record.get("skill"), dict) else {}
    feedback = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
    qa = record.get("qa") if isinstance(record.get("qa"), dict) else {}
    return {
        "trajectory_id": record.get("trajectory_id"),
        "task_type": record.get("task_type"),
        "skill": skill.get("name"),
        "skill_version": skill.get("version"),
        "human_review_status": record.get("human_review_status"),
        "accepted": _is_accepted(record),
        "quality_score": feedback.get("quality_score"),
        "qa_hard_gate_pass": qa.get("hard_gate_pass"),
        "blockers": blockers,
    }


def _build_sft_quality_report(
    sft_records: list[dict[str, Any]],
    *,
    blocked_samples: list[dict[str, Any]],
    jsonl_parse_errors: list[dict[str, Any]] | None = None,
    sample_limit: int = 5,
) -> dict[str, Any]:
    parse_errors = jsonl_parse_errors or []
    invalid_samples: list[dict[str, Any]] = list(parse_errors[: max(0, sample_limit)])
    valid_count = 0
    role_sequences: dict[str, int] = {}
    qa_hard_pass = 0
    qa_hard_fail = 0
    qa_warning_count = 0
    qa_gate_issue_count = 0
    quality_scores: list[float] = []
    evidence = {
        "records_with_confirmed": 0,
        "records_with_assumptions": 0,
        "records_with_gaps": 0,
        "records_with_source_references": 0,
        "unsupported_confirmed_records": 0,
    }
    sample_records: list[dict[str, Any]] = []

    for index, record in enumerate(sft_records):
        validation = _validate_sft_record(record)
        role_key = ",".join(validation["roles"]) if validation["roles"] else "missing"
        role_sequences[role_key] = role_sequences.get(role_key, 0) + 1
        if validation["issues"]:
            if len(invalid_samples) < sample_limit:
                invalid_samples.append(
                    {
                        "index": index,
                        "issues": validation["issues"],
                        "metadata": record.get("metadata") if isinstance(record.get("metadata"), dict) else {},
                    }
                )
            continue

        valid_count += 1
        assistant_payload = validation["assistant_payload"]
        qa = assistant_payload.get("qa") if isinstance(assistant_payload.get("qa"), dict) else {}
        if qa.get("hard_gate_pass") is False:
            qa_hard_fail += 1
        else:
            qa_hard_pass += 1
        qa_warning_count += len(_string_list(qa.get("warnings")))
        gate_issues = qa.get("gate_issues")
        if isinstance(gate_issues, list):
            qa_gate_issue_count += len(gate_issues)
        score = _metadata_quality_score(record.get("metadata"))
        if score is not None:
            quality_scores.append(score)

        evidence_status = assistant_payload.get("evidence_status")
        evidence_status = evidence_status if isinstance(evidence_status, dict) else {}
        confirmed = _string_list(evidence_status.get("confirmed"))
        assumptions = _string_list(evidence_status.get("assumptions") or evidence_status.get("assumed"))
        gaps = _string_list(evidence_status.get("gaps") or evidence_status.get("todo") or evidence_status.get("open_questions"))
        sources = _string_list(evidence_status.get("source_references") or evidence_status.get("sources"))
        if confirmed:
            evidence["records_with_confirmed"] += 1
        if assumptions:
            evidence["records_with_assumptions"] += 1
        if gaps:
            evidence["records_with_gaps"] += 1
        if sources:
            evidence["records_with_source_references"] += 1
        if confirmed and not sources:
            evidence["unsupported_confirmed_records"] += 1
        if len(sample_records) < sample_limit:
            sample_records.append(
                {
                    "index": index,
                    "trajectory_id": (record.get("metadata") or {}).get("trajectory_id") if isinstance(record.get("metadata"), dict) else None,
                    "task_type": (record.get("metadata") or {}).get("task_type") if isinstance(record.get("metadata"), dict) else None,
                    "roles": validation["roles"],
                    "assistant_keys": sorted(assistant_payload.keys()),
                    "has_source_references": bool(sources),
                    "qa_hard_gate_pass": qa.get("hard_gate_pass"),
                }
            )

    invalid_count = len(sft_records) - valid_count + len(parse_errors)
    return {
        "jsonl_record_count": len(sft_records),
        "schema_valid_count": valid_count,
        "schema_invalid_count": invalid_count,
        "role_sequence_summary": role_sequences,
        "qa_summary": {
            "hard_gate_pass_count": qa_hard_pass,
            "hard_gate_fail_count": qa_hard_fail,
            "warning_count": qa_warning_count,
            "gate_issue_count": qa_gate_issue_count,
            "quality_score_summary": _score_summary(quality_scores),
        },
        "evidence_coverage": {
            **evidence,
            "source_reference_coverage": _coverage_ratio(evidence["records_with_source_references"], valid_count),
            "confirmed_coverage": _coverage_ratio(evidence["records_with_confirmed"], valid_count),
        },
        "invalid_samples": invalid_samples,
        "blocked_samples": blocked_samples[: max(0, sample_limit)],
        "sample_records": sample_records,
    }


def _validate_sft_record(record: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    messages = record.get("messages")
    roles: list[str] = []
    assistant_payload: dict[str, Any] = {}
    if not isinstance(messages, list):
        return {"issues": ["missing_messages"], "roles": roles, "assistant_payload": assistant_payload}
    for message in messages:
        role = message.get("role") if isinstance(message, dict) else None
        roles.append(str(role or "missing"))
    if roles != ["system", "user", "assistant"]:
        issues.append("invalid_role_sequence")
    if len(messages) != 3:
        issues.append("invalid_message_count")
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            issues.append(f"message_{index}_not_object")
            continue
        if not str(message.get("content") or "").strip():
            issues.append(f"message_{index}_missing_content")
    assistant = messages[2] if len(messages) >= 3 and isinstance(messages[2], dict) else {}
    try:
        parsed = json.loads(str(assistant.get("content") or ""))
    except json.JSONDecodeError:
        issues.append("assistant_content_not_json")
        parsed = {}
    if isinstance(parsed, dict):
        assistant_payload = parsed
    else:
        issues.append("assistant_content_not_object")
    if not _string_list(assistant_payload.get("plan")):
        issues.append("assistant_missing_plan")
    if not str(assistant_payload.get("draft") or "").strip():
        issues.append("assistant_missing_draft")
    if not isinstance(assistant_payload.get("evidence_status"), dict):
        issues.append("assistant_missing_evidence_status")
    if not isinstance(assistant_payload.get("qa"), dict):
        issues.append("assistant_missing_qa")
    return {"issues": issues, "roles": roles, "assistant_payload": assistant_payload}


def _metadata_quality_score(metadata: Any) -> float | None:
    if not isinstance(metadata, dict):
        return None
    raw = metadata.get("quality_score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _blocker_summary(blocked: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in blocked:
        for blocker in item.get("blockers", []):
            label = str(blocker)
            summary[label] = summary.get(label, 0) + 1
    return summary


def _coverage_ratio(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 3)


def _quality_recommendations(report: dict[str, Any]) -> list[str]:
    recommendations: list[str] = []
    if report.get("schema_invalid_count"):
        recommendations.append("fix_invalid_sft_schema_before_training")
    if report.get("blocked_count"):
        recommendations.append("review_or_reject_blocked_trajectories_before_dataset_freeze")
    evidence = report.get("evidence_coverage") if isinstance(report.get("evidence_coverage"), dict) else {}
    if evidence.get("unsupported_confirmed_records"):
        recommendations.append("add_source_references_for_confirmed_claims")
    if report.get("eligible_count") == 0 or report.get("jsonl_record_count") == 0:
        recommendations.append("collect_reviewed_accepted_trajectories")
    return recommendations


def _training_readiness_recommendations(blockers: list[str]) -> list[str]:
    if not blockers:
        return ["review_latest_freeze_and_approval_before_explicit_training_execution"]
    recommendations: list[str] = []
    if "no_dataset_freeze_manifest" in blockers or "latest_dataset_freeze_manifest_missing" in blockers:
        recommendations.append("create_dataset_freeze_manifest_from_reviewed_sft_export")
    if "no_dry_run_training_approval" in blockers:
        recommendations.append("record_dry_run_training_approval_with_separate_approver")
    if "latest_training_approval_missing_eval_plan" in blockers or "latest_training_approval_missing_required_metrics" in blockers:
        recommendations.append("complete_eval_plan_suite_and_required_metrics")
    if "provider_job_started_detected" in blockers or "dataset_training_started_flag_detected" in blockers:
        recommendations.append("investigate_existing_training_state_before_new_execution")
    if "latest_reviewed_sft_export_missing" in blockers or "latest_training_approval_file_missing" in blockers:
        recommendations.append("restore_or_recreate_missing_manifest_artifact")
    return _dedupe(recommendations)


def _safe_provider_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())[:80].strip("._-")
    return label or "provider_agnostic"


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _json_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_references(record: dict[str, Any]) -> list[Any]:
    direct = record.get("source_references")
    if isinstance(direct, list):
        return direct
    input_payload = record.get("input") if isinstance(record.get("input"), dict) else {}
    nested = input_payload.get("source_references")
    return nested if isinstance(nested, list) else []


def _quality_score(record: dict[str, Any]) -> float | None:
    feedback = record.get("human_feedback") if isinstance(record.get("human_feedback"), dict) else {}
    raw = feedback.get("quality_score")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _score_summary(scores: list[float]) -> dict[str, Any]:
    if not scores:
        return {"count": 0, "min": None, "max": None, "avg": None}
    return {
        "count": len(scores),
        "min": round(min(scores), 3),
        "max": round(max(scores), 3),
        "avg": round(sum(scores) / len(scores), 3),
    }


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        label = str(record.get(key) or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


def _skill_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        skill = record.get("skill") if isinstance(record.get("skill"), dict) else {}
        label = str(skill.get("name") or "unknown")
        counts[label] = counts.get(label, 0) + 1
    return counts


_SIGNOFF_REQUIRED_REVIEWER_ROLES = {
    "product_pm_reviewer",
    "ml_ai_owner",
    "compliance_security_reviewer",
    "release_owner",
}
_SIGNOFF_DEFAULT_ALLOWED_DECISIONS = {
    "pending",
    "sign_off_ready_for_human_review",
    "changes_requested",
    "blocked",
}
_SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS = {
    "reviewed_phase20_handoff_for_role",
    "does_not_authorize_model_training",
    "does_not_authorize_dataset_upload",
    "does_not_authorize_provider_fine_tune_api_calls",
    "does_not_authorize_provider_job_creation_or_polling",
    "does_not_authorize_model_promotion",
    "blocking_issues_recorded_in_notes",
}
_SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS = {
    "training_execution_authorized",
    "external_dataset_upload_authorized",
    "provider_fine_tune_api_call_authorized",
    "provider_job_creation_authorized",
    "provider_job_polling_authorized",
    "model_candidate_emission_authorized",
    "model_promotion_authorized",
}
_SIGNOFF_PROTECTED_FALSE_GENERATION_KEYS = {
    "training_execution_started",
    "external_dataset_uploaded",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "model_promoted",
}


def _list_reviewer_signoff_record_paths(directory: Path, *, limit: int) -> list[Path]:
    if not directory.is_dir():
        return []
    paths = [
        path
        for path in directory.glob("*.json")
        if path.is_file() and Path(path.name).name == path.name
    ]
    paths.sort(key=lambda path: (path.stat().st_mtime, path.name), reverse=True)
    return paths[:limit]


def _load_json_file(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("sign-off record must be a JSON object")
    return data


def _as_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_iso_datetime(value: str) -> bool:
    if not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _signoff_acknowledgement_summary(value: Any) -> dict[str, Any]:
    acknowledgements = value if isinstance(value, dict) else {}
    checked = sum(1 for key in _SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS if acknowledgements.get(key) is True)
    total = len(_SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS)
    return {
        "checked": checked,
        "total": total,
        "complete": checked == total,
        "unchecked": sorted(
            key
            for key in _SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS
            if acknowledgements.get(key) is not True
        ),
    }


def _summarize_signoff_reviewer(reviewer: dict[str, Any]) -> dict[str, Any]:
    role = _as_text(reviewer.get("reviewer_role"))
    decision = _as_text(reviewer.get("decision")) or "missing"
    reviewed_at = _as_text(reviewer.get("reviewed_at"))
    evidence = reviewer.get("evidence_reviewed")
    evidence_count = len(evidence) if isinstance(evidence, list) else 0
    acknowledgements = _signoff_acknowledgement_summary(reviewer.get("required_acknowledgements"))
    notes = _as_text(reviewer.get("notes"))
    complete = all(
        [
            role in _SIGNOFF_REQUIRED_REVIEWER_ROLES,
            bool(_as_text(reviewer.get("reviewer_name"))),
            bool(_as_text(reviewer.get("reviewer_title_or_team"))),
            _is_iso_datetime(reviewed_at),
            decision in _SIGNOFF_DEFAULT_ALLOWED_DECISIONS,
            decision != "pending",
            evidence_count > 0,
            acknowledgements["complete"],
            bool(notes) if decision in {"changes_requested", "blocked"} else True,
        ]
    )
    return {
        "reviewer_role": role,
        "reviewer_name_present": bool(_as_text(reviewer.get("reviewer_name"))),
        "reviewer_title_or_team_present": bool(_as_text(reviewer.get("reviewer_title_or_team"))),
        "reviewed_at_present": bool(reviewed_at),
        "reviewed_at_valid": _is_iso_datetime(reviewed_at),
        "decision": decision,
        "evidence_reviewed_count": evidence_count,
        "acknowledgements": acknowledgements,
        "notes_present": bool(notes),
        "complete": complete,
    }


def _signoff_boundary_summary(record: dict[str, Any]) -> dict[str, Any]:
    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        boundary = {}
    generation_boundary = record.get("generation_boundary")
    if not isinstance(generation_boundary, dict):
        generation_boundary = {}
    protected = {key: boundary.get(key) for key in sorted(_SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS)}
    generation_side_effects = {
        key: generation_boundary.get(key, False)
        for key in sorted(_SIGNOFF_PROTECTED_FALSE_GENERATION_KEYS)
    }
    return {
        "actual_reviewer_approval_recorded": boundary.get("actual_reviewer_approval_recorded") is True,
        "protected_training_flags": protected,
        "generation_side_effect_flags": generation_side_effects,
        "training_execution_authorized": False,
        "external_dataset_upload_authorized": False,
        "provider_fine_tune_api_call_authorized": False,
        "provider_job_creation_authorized": False,
        "provider_job_polling_authorized": False,
        "model_candidate_emission_authorized": False,
        "model_promotion_authorized": False,
        "protected_training_flags_false": all(value is False for value in protected.values()),
        "generation_side_effect_flags_false": all(value is False for value in generation_side_effects.values()),
    }


def _validate_reviewer_signoff_record(record: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    reviewers = record.get("required_reviewers")
    if not isinstance(reviewers, list):
        errors.append("required_reviewers must be a list")
        reviewers = []
    allowed_decisions = record.get("allowed_decisions") or sorted(_SIGNOFF_DEFAULT_ALLOWED_DECISIONS)
    if not isinstance(allowed_decisions, list) or not all(isinstance(item, str) for item in allowed_decisions):
        errors.append("allowed_decisions must be a list of strings")
        allowed_decisions = sorted(_SIGNOFF_DEFAULT_ALLOWED_DECISIONS)
    allowed_decision_set = set(allowed_decisions)
    reviewer_roles = {
        reviewer.get("reviewer_role")
        for reviewer in reviewers
        if isinstance(reviewer, dict) and isinstance(reviewer.get("reviewer_role"), str)
    }
    missing_roles = sorted(_SIGNOFF_REQUIRED_REVIEWER_ROLES - reviewer_roles)
    if missing_roles:
        errors.append(f"missing required reviewer roles: {', '.join(missing_roles)}")
    for role in sorted(reviewer_roles - _SIGNOFF_REQUIRED_REVIEWER_ROLES):
        warnings.append(f"unexpected reviewer role present: {role}")
    for index, reviewer in enumerate(reviewers, start=1):
        if not isinstance(reviewer, dict):
            errors.append(f"reviewer[{index}] must be an object")
            continue
        role = _as_text(reviewer.get("reviewer_role")) or f"reviewer[{index}]"
        if role not in _SIGNOFF_REQUIRED_REVIEWER_ROLES:
            continue
        if not _as_text(reviewer.get("reviewer_name")):
            errors.append(f"{role}: reviewer_name is required")
        if not _as_text(reviewer.get("reviewer_title_or_team")):
            errors.append(f"{role}: reviewer_title_or_team is required")
        reviewed_at = _as_text(reviewer.get("reviewed_at"))
        if not _is_iso_datetime(reviewed_at):
            errors.append(f"{role}: reviewed_at must be an ISO 8601 datetime")
        decision = _as_text(reviewer.get("decision"))
        if decision not in allowed_decision_set:
            errors.append(f"{role}: decision must be one of {', '.join(sorted(allowed_decision_set))}")
        elif decision == "pending":
            errors.append(f"{role}: decision must not be pending for completed sign-off validation")
        evidence_reviewed = reviewer.get("evidence_reviewed")
        if not isinstance(evidence_reviewed, list) or not evidence_reviewed:
            errors.append(f"{role}: evidence_reviewed must be a non-empty list")
        elif not all(_as_text(item) for item in evidence_reviewed):
            errors.append(f"{role}: evidence_reviewed entries must be non-empty strings")
        acknowledgements = reviewer.get("required_acknowledgements")
        if not isinstance(acknowledgements, dict):
            errors.append(f"{role}: required_acknowledgements must be an object")
            acknowledgements = {}
        missing_acknowledgements = sorted(_SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS - set(acknowledgements))
        if missing_acknowledgements:
            errors.append(f"{role}: missing acknowledgements: {', '.join(missing_acknowledgements)}")
        unchecked = sorted(
            key
            for key in _SIGNOFF_REQUIRED_ACKNOWLEDGEMENTS
            if acknowledgements.get(key) is not True
        )
        if unchecked:
            errors.append(f"{role}: unchecked acknowledgements: {', '.join(unchecked)}")
        notes = _as_text(reviewer.get("notes"))
        if decision in {"changes_requested", "blocked"} and not notes:
            errors.append(f"{role}: notes are required when decision is {decision}")

    boundary = record.get("signoff_boundary")
    if not isinstance(boundary, dict):
        errors.append("signoff_boundary must be an object")
        boundary = {}
    missing_boundary = sorted(_SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS - set(boundary))
    if missing_boundary:
        errors.append(f"missing signoff_boundary keys: {', '.join(missing_boundary)}")
    for key in sorted(_SIGNOFF_PROTECTED_FALSE_BOUNDARY_KEYS):
        if boundary.get(key) is not False:
            errors.append(f"signoff_boundary.{key} must remain false")
    completion_rule = record.get("completion_rule")
    if isinstance(completion_rule, dict):
        for key in (
            "all_required_reviewers_have_non_empty_name",
            "all_required_reviewers_have_timestamp",
            "all_required_reviewers_decided",
            "all_required_acknowledgements_checked",
            "changes_requested_or_blocked_records_have_notes",
            "manual_signoff_complete",
        ):
            if completion_rule.get(key) is not True:
                errors.append(f"completion_rule.{key} must be true for completed sign-off validation")
    else:
        warnings.append("completion_rule missing; reviewer fields and boundary flags were validated directly")
    return {
        "valid": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "reviewer_roles": sorted(role for role in reviewer_roles if isinstance(role, str)),
    }


def _signoff_record_status(
    validation: dict[str, Any],
    boundary: dict[str, Any],
    decision_counts: dict[str, int],
) -> str:
    if not boundary["protected_training_flags_false"] or not boundary["generation_side_effect_flags_false"]:
        return "attention_required_boundary_violation"
    if validation["valid"]:
        return "manual_signoff_complete_no_training_authorization"
    if decision_counts.get("blocked") or decision_counts.get("changes_requested"):
        return "manual_follow_up_required_no_training_authorization"
    return "pending_manual_signoff_no_training_authorization"


def _summarize_reviewer_signoff_record(filename: str, record: dict[str, Any]) -> dict[str, Any]:
    validation = _validate_reviewer_signoff_record(record)
    reviewers_raw = record.get("required_reviewers")
    reviewers = (
        [_summarize_signoff_reviewer(item) for item in reviewers_raw if isinstance(item, dict)]
        if isinstance(reviewers_raw, list)
        else []
    )
    boundary = _signoff_boundary_summary(record)
    completed_roles = sorted(item["reviewer_role"] for item in reviewers if item["complete"])
    pending_roles = sorted(
        {
            item["reviewer_role"] or "unknown"
            for item in reviewers
            if item["decision"] == "pending" or not item["complete"]
        }
    )
    decision_counts: dict[str, int] = {}
    for reviewer in reviewers:
        decision = reviewer["decision"] or "missing"
        decision_counts[decision] = decision_counts.get(decision, 0) + 1
    return {
        "filename": filename,
        "report_type": record.get("report_type", ""),
        "signoff_record_id": record.get("signoff_record_id", ""),
        "created_at": record.get("created_at", ""),
        "record_status": _signoff_record_status(validation, boundary, decision_counts),
        "reviewers": reviewers,
        "reviewers_complete_count": len(completed_roles),
        "pending_reviewer_count": len(pending_roles),
        "changes_requested_count": int(decision_counts.get("changes_requested") or 0),
        "blocked_count": int(decision_counts.get("blocked") or 0),
        "completed_reviewer_roles": completed_roles,
        "pending_reviewer_roles": pending_roles,
        "decision_counts": decision_counts,
        "completion_rule": record.get("completion_rule", {}),
        "boundary": boundary,
        "completed_validation": {
            "valid": validation["valid"],
            "error_count": validation["error_count"],
            "warning_count": validation["warning_count"],
            "errors": validation["errors"],
            "warnings": validation["warnings"],
        },
    }


def _reviewer_signoff_summary_blockers(
    *,
    records: list[dict[str, Any]],
    load_errors: list[dict[str, str]],
    overall_status: str,
) -> list[str]:
    blockers: list[str] = []
    if overall_status == "no_signoff_records_found":
        blockers.append("no_reviewer_signoff_records_found")
    if load_errors:
        blockers.append("reviewer_signoff_record_load_errors")
    for record in records:
        status = str(record.get("record_status") or "")
        if status == "attention_required_boundary_violation":
            blockers.append(f"{record.get('filename')}: boundary_violation")
        elif status == "manual_follow_up_required_no_training_authorization":
            blockers.append(f"{record.get('filename')}: reviewer_follow_up_required")
        elif status == "pending_manual_signoff_no_training_authorization":
            blockers.append(f"{record.get('filename')}: pending_manual_signoff")
    return _dedupe(blockers)


_SENSITIVE_KEY_PARTS = (
    "raw",
    "attachment",
    "file_bytes",
    "base64",
    "document_text",
    "source_document",
)


def _redact_input(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact_input(item)
        return redacted
    if isinstance(value, list):
        return [_redact_input(item) for item in value]
    if isinstance(value, str) and len(value) > 2000:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return f"{value[:300]}...[redacted_long_text sha256={digest}]"
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_label(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in raw).strip("-") or "all"


_EXPORT_FILENAME_RE = re.compile(r"^sft(?:_[A-Za-z0-9_-]+)?_[0-9]{8}T[0-9]{6}\.jsonl$")
_FREEZE_FILENAME_RE = re.compile(r"^freeze_sft(?:_[A-Za-z0-9_-]+)?_[0-9]{8}T[0-9]{6}_[0-9]{8}T[0-9]{6}_[a-f0-9]{8}\.json$")
_MANIFEST_ID_RE = re.compile(r"^dsf_[a-f0-9]{32}$")
_TRAINING_APPROVAL_FILENAME_RE = re.compile(r"^training_approval_dsf_[a-f0-9]{32}_[0-9]{8}T[0-9]{6}_[a-f0-9]{8}\.json$")
_TRAINING_EXECUTION_REQUEST_FILENAME_RE = re.compile(r"^training_execution_request_ter_[a-f0-9]{32}_[0-9]{8}T[0-9]{6}\.json$")
_TRAINING_AUDIT_FILENAME_RE = re.compile(r"^training_pre_execution_audit_tea_[a-f0-9]{32}_[0-9]{8}T[0-9]{6}\.json$")


def _is_safe_export_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_EXPORT_FILENAME_RE.fullmatch(filename))


def _is_safe_freeze_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_FREEZE_FILENAME_RE.fullmatch(filename))


def _is_safe_manifest_id(manifest_id: str) -> bool:
    return bool(_MANIFEST_ID_RE.fullmatch(str(manifest_id or "")))


def _is_safe_training_approval_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_TRAINING_APPROVAL_FILENAME_RE.fullmatch(filename))


def _is_safe_training_execution_request_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_TRAINING_EXECUTION_REQUEST_FILENAME_RE.fullmatch(filename))


def _is_safe_training_audit_filename(filename: str) -> bool:
    if Path(filename).name != filename:
        return False
    return bool(_TRAINING_AUDIT_FILENAME_RE.fullmatch(filename))
