"""Dry-run training approval gate, readiness summary, and execution plan preview."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.storage.trajectory.redaction import (
    _is_safe_manifest_id,
    _is_safe_training_approval_filename,
    _now_iso,
    _redact_input,
)
from app.storage.trajectory.training_readiness import (
    _safe_provider_label,
    _training_readiness_recommendations,
)


class TrajectoryTrainingApprovalMixin:
    """Dry-run training approval, readiness summary, and execution plan preview."""

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
