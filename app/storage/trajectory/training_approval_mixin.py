"""Dry-run training approval gate, readiness summary, and execution plan preview."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.trajectory.artifact_state_mixin import TrajectoryArtifact
from app.storage.trajectory.redaction import (
    _is_safe_manifest_id,
    _is_safe_training_approval_filename,
    _json_sha256,
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
        tenant_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return newest dry-run training approval gate metadata."""
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_approvals = self._owned_meta_items(meta, "training_approvals", tenant_id)
        approvals: list[dict[str, Any]] = []
        seen_files: set[str] = set()
        for item in reversed(raw_approvals):
            if not isinstance(item, dict):
                continue
            approval_file = str(item.get("approval_file") or "")
            if approval_file in seen_files:
                continue
            artifact = self._read_training_approval_artifact(
                tenant_id,
                approval_file,
            )
            if artifact and not self._json_artifact_belongs_to_tenant(
                artifact,
                tenant_id,
            ):
                continue
            approval_sha256 = str(item.get("approval_sha256") or "")
            approval_size = item.get("approval_size_bytes")
            size_matches = self._artifact_size_matches(
                artifact,
                approval_size,
            )
            approvals.append(
                {
                    "approval_id": item.get("approval_id"),
                    "approval_file": approval_file,
                    "manifest_id": item.get("manifest_id"),
                    "export_filename": item.get("export_filename"),
                    "export_sha256": item.get("export_sha256"),
                    "quality_report_sha256": item.get("quality_report_sha256"),
                    "approver": item.get("approver"),
                    "dry_run": bool(item.get("dry_run", True)),
                    "training_execution_allowed": bool(item.get("training_execution_allowed", False)),
                    "external_upload_started": bool(item.get("external_upload_started", False)),
                    "provider_api_calls_allowed": bool(item.get("provider_api_calls_allowed", False)),
                    "provider_job_started": bool(item.get("provider_job_started", False)),
                    "model_promotion_allowed": bool(item.get("model_promotion_allowed", False)),
                    "approval_sha256": approval_sha256 or None,
                    "integrity_verified": bool(
                        artifact
                        and approval_sha256
                        and size_matches
                        and artifact.sha256 == approval_sha256
                    ),
                    "size_binding_verified": self._artifact_size_binding_verified(
                        artifact,
                        approval_size,
                    ),
                    "created_at": item.get("created_at"),
                    "exists": artifact is not None,
                    "size_bytes": artifact.size_bytes if artifact else 0,
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
        tenant_id: str,
        approver: str,
        eval_plan: dict[str, Any],
        notes: str = "",
        dry_run: bool = True,
        start_training: bool = False,
        operation_id: str | None = None,
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
        redacted_eval_plan = _redact_input(eval_plan)
        operation_payload_hash = (
            _json_sha256(
                {
                    "action": "approve_training_from_freeze",
                    "approver": approver,
                    "dry_run": dry_run,
                    "eval_plan": eval_plan,
                    "manifest_id": manifest_id,
                    "notes": notes,
                    "start_training": start_training,
                }
            )
            if operation_id is not None
            else None
        )
        existing_operation = self._find_meta_operation_item(
            tenant_id=tenant_id,
            collection="training_approvals",
            operation_id=operation_id,
            operation_payload_hash=operation_payload_hash,
        )
        if existing_operation is not None:
            return self._load_bound_operation_artifact(
                artifact=self._read_training_approval_artifact(
                    tenant_id,
                    str(existing_operation.get("approval_file") or ""),
                ),
                metadata=existing_operation,
                tenant_id=tenant_id,
                size_key="approval_size_bytes",
                sha256_key="approval_sha256",
                identity_key="approval_id",
            )
        manifest = self._load_freeze_manifest_by_id(manifest_id, tenant_id=tenant_id)
        if manifest is None:
            return None
        freeze_meta = next(
            (
                item
                for item in self.list_dataset_freezes(tenant_id=tenant_id, limit=10_000)
                if item.get("manifest_id") == manifest_id
            ),
            None,
        )
        if freeze_meta is None or freeze_meta.get("integrity_verified") is not True:
            raise ValueError("dataset freeze manifest integrity check failed.")
        freeze_reviewer = str((manifest.get("review_gate") or {}).get("reviewer") or "").strip()
        if freeze_reviewer and freeze_reviewer == approver:
            raise ValueError("training approver must be different from dataset freeze reviewer.")
        training_guard = manifest.get("training_guard") if isinstance(manifest.get("training_guard"), dict) else {}
        if training_guard.get("training_allowed") is not False:
            raise ValueError("dataset manifest must keep training_allowed=false.")
        if training_guard.get("training_started") is not False:
            raise ValueError("dataset manifest must keep training_started=false.")
        if (manifest.get("quality_report") or {}).get("ready_for_training") is not True:
            raise ValueError("dataset manifest quality report is not ready for training approval.")
        export = manifest.get("export") if isinstance(manifest.get("export"), dict) else {}
        export_filename = str(export.get("filename") or "")
        current_quality = self.inspect_sft_export_quality(
            export_filename,
            tenant_id=tenant_id,
            sample_limit=0,
        )
        if current_quality is None or current_quality.get("ready_for_training") is not True:
            raise ValueError("dataset export integrity or quality check failed.")
        if current_quality.get("content_sha256") != export.get("sha256"):
            raise ValueError("dataset export checksum does not match the freeze manifest.")

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
            "eval_plan": redacted_eval_plan,
            "execution_guard": {
                "dry_run": True,
                "training_execution_allowed": False,
                "start_training_requested": False,
                "external_upload_started": False,
                "provider_api_calls_allowed": False,
                "provider_job_started": False,
                "model_promotion_allowed": False,
                "reason": "Training approval recorded only. Provider job execution and model promotion require a separate explicit workflow.",
            },
        }
        approval_file = f"training_approval_{manifest_id}_{approval_ts}_{approval_id[-8:]}.json"
        artifact = self._publish_artifact(
            tenant_id=tenant_id,
            directory="trajectory_training_approvals",
            filename=approval_file,
            raw=json.dumps(
                approval,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )
        selected = self._append_training_approval_meta(
            tenant_id,
            approval_file,
            approval,
            approval_size_bytes=artifact.size_bytes,
            approval_sha256=artifact.sha256,
            operation_id=operation_id,
            operation_payload_hash=operation_payload_hash,
        )
        if selected.get("approval_id") != approval_id:
            return self._load_bound_operation_artifact(
                artifact=self._read_training_approval_artifact(
                    tenant_id,
                    str(selected.get("approval_file") or ""),
                ),
                metadata=selected,
                tenant_id=tenant_id,
                size_key="approval_size_bytes",
                sha256_key="approval_sha256",
                identity_key="approval_id",
            )
        return approval

    def training_readiness_summary(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Summarize readiness gates without starting training or uploads."""
        reviewed_exports = self.list_reviewed_sft_exports(tenant_id=tenant_id, limit=limit)
        freezes = self.list_dataset_freezes(tenant_id=tenant_id, limit=limit)
        approvals = self.list_training_approvals(tenant_id=tenant_id, limit=limit)

        latest_export = reviewed_exports[0] if reviewed_exports else None
        latest_freeze = freezes[0] if freezes else None
        latest_approval = approvals[0] if approvals else None
        artifact_chain = self._training_artifact_chain_summary(
            tenant_id=tenant_id,
            latest_export=latest_export,
            latest_freeze=latest_freeze,
            latest_approval=latest_approval,
        )

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
        training_execution_allowed_count = sum(
            1 for item in approvals if item.get("training_execution_allowed") is True
        )
        external_upload_started_count = sum(
            1 for item in approvals if item.get("external_upload_started") is True
        )
        provider_api_calls_allowed_count = sum(
            1 for item in approvals if item.get("provider_api_calls_allowed") is True
        )
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
        elif artifact_chain["freeze_integrity_verified"] is not True:
            blockers.append("latest_dataset_freeze_integrity_failed")
        if latest_approval is None:
            blockers.append("no_dry_run_training_approval")
        elif latest_approval.get("exists") is not True:
            blockers.append("latest_training_approval_file_missing")
        elif artifact_chain["approval_integrity_verified"] is not True:
            blockers.append("latest_training_approval_integrity_failed")
        if artifact_chain["freeze_matches_latest_export"] is False:
            blockers.append("latest_dataset_freeze_does_not_match_latest_export")
        if artifact_chain["approval_matches_latest_freeze"] is False:
            blockers.append("latest_training_approval_does_not_match_latest_freeze")
        if artifact_chain["approval_guard_clean"] is False:
            blockers.append("latest_training_approval_guard_not_clean")
        if latest_eval_summary is None or latest_eval_summary["has_eval_plan"] is not True:
            blockers.append("latest_training_approval_missing_eval_plan")
        elif latest_eval_summary["has_required_metrics"] is not True:
            blockers.append("latest_training_approval_missing_required_metrics")
        if provider_job_started_count:
            blockers.append("provider_job_started_detected")
        if model_promotion_allowed_count:
            blockers.append("model_promotion_allowed_detected")
        if training_execution_allowed_count:
            blockers.append("training_execution_allowed_detected")
        if external_upload_started_count:
            blockers.append("external_upload_started_detected")
        if provider_api_calls_allowed_count:
            blockers.append("provider_api_calls_allowed_detected")
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
            "artifact_chain": artifact_chain,
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
                "training_execution_allowed_count": training_execution_allowed_count,
                "external_upload_started_count": external_upload_started_count,
                "external_upload_started": external_upload_started_count > 0,
                "provider_api_calls_allowed_count": provider_api_calls_allowed_count,
                "no_training_started": (
                    training_started_count == 0
                    and training_execution_allowed_count == 0
                    and external_upload_started_count == 0
                    and provider_api_calls_allowed_count == 0
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
        tenant_id: str,
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
        *,
        approval_size_bytes: int,
        approval_sha256: str,
        operation_id: str | None = None,
        operation_payload_hash: str | None = None,
    ) -> dict[str, Any]:
        manifest = (
            approval.get("manifest")
            if isinstance(approval.get("manifest"), dict)
            else {}
        )
        guard = (
            approval.get("execution_guard")
            if isinstance(approval.get("execution_guard"), dict)
            else {}
        )
        gate = (
            approval.get("approval_gate")
            if isinstance(approval.get("approval_gate"), dict)
            else {}
        )
        item = {
            "tenant_id": tenant_id,
            "approval_id": approval.get("approval_id"),
            "approval_file": approval_file,
            "approval_size_bytes": approval_size_bytes,
            "approval_sha256": approval_sha256,
            "manifest_id": manifest.get("manifest_id"),
            "export_filename": manifest.get("export_filename"),
            "export_sha256": manifest.get("export_sha256"),
            "quality_report_sha256": manifest.get(
                "quality_report_sha256"
            ),
            "approver": gate.get("approver"),
            "dry_run": guard.get("dry_run", True),
            "training_execution_allowed": guard.get(
                "training_execution_allowed",
                False,
            ),
            "external_upload_started": guard.get(
                "external_upload_started",
                False,
            ),
            "provider_api_calls_allowed": guard.get(
                "provider_api_calls_allowed",
                False,
            ),
            "provider_job_started": guard.get(
                "provider_job_started",
                False,
            ),
            "model_promotion_allowed": guard.get(
                "model_promotion_allowed",
                False,
            ),
            "created_at": approval.get("created_at"),
        }
        with self._lock:
            return self._append_meta_item(
                tenant_id=tenant_id,
                collection="training_approvals",
                count_key="training_approval_count",
                item=item,
                identity_keys=("approval_id", "approval_file"),
                operation_id=operation_id,
                operation_payload_hash=operation_payload_hash,
            )

    def _training_artifact_chain_summary(
        self,
        *,
        tenant_id: str,
        latest_export: dict[str, Any] | None,
        latest_freeze: dict[str, Any] | None,
        latest_approval: dict[str, Any] | None,
    ) -> dict[str, Any]:
        manifest_id = str((latest_freeze or {}).get("manifest_id") or "")
        manifest = self._load_freeze_manifest_by_id(manifest_id, tenant_id=tenant_id) if manifest_id else None
        approval = self._load_training_approval_by_file(
            tenant_id,
            str((latest_approval or {}).get("approval_file") or ""),
        )
        export = manifest.get("export") if isinstance((manifest or {}).get("export"), dict) else {}
        quality_report = (
            manifest.get("quality_report")
            if isinstance((manifest or {}).get("quality_report"), dict)
            else {}
        )
        approval_manifest = (
            approval.get("manifest")
            if isinstance((approval or {}).get("manifest"), dict)
            else {}
        )
        approval_guard = (
            approval.get("execution_guard")
            if isinstance((approval or {}).get("execution_guard"), dict)
            else {}
        )

        freeze_matches_latest_export: bool | None = None
        if latest_export is not None and latest_freeze is not None:
            freeze_matches_latest_export = bool(
                manifest
                and export.get("filename") == latest_export.get("filename")
                and export.get("sha256") == latest_export.get("content_sha256")
                and int(export.get("record_count") or 0) == int(latest_export.get("record_count") or 0)
            )

        approval_matches_latest_freeze: bool | None = None
        approval_guard_clean: bool | None = None
        if latest_freeze is not None and latest_approval is not None:
            approval_matches_latest_freeze = bool(
                manifest
                and approval
                and approval_manifest.get("manifest_id") == manifest.get("manifest_id")
                and approval_manifest.get("export_filename") == export.get("filename")
                and approval_manifest.get("export_sha256") == export.get("sha256")
                and approval_manifest.get("quality_report_sha256") == quality_report.get("sha256")
                and int(approval_manifest.get("record_count") or 0) == int(export.get("record_count") or 0)
            )
            approval_guard_clean = bool(
                approval
                and approval_guard.get("dry_run") is True
                and approval_guard.get("training_execution_allowed", False) is False
                and approval_guard.get("start_training_requested", False) is False
                and approval_guard.get("external_upload_started", False) is False
                and approval_guard.get("provider_api_calls_allowed", False) is False
                and approval_guard.get("provider_job_started", False) is False
                and approval_guard.get("model_promotion_allowed", False) is False
            )

        freeze_integrity_verified = bool(
            latest_freeze and latest_freeze.get("integrity_verified") is True
        )
        approval_integrity_verified = bool(
            latest_approval and latest_approval.get("integrity_verified") is True
        )
        return {
            "latest_export_filename": (latest_export or {}).get("filename"),
            "freeze_manifest_id": (latest_freeze or {}).get("manifest_id"),
            "approval_id": (latest_approval or {}).get("approval_id"),
            "freeze_integrity_verified": freeze_integrity_verified,
            "approval_integrity_verified": approval_integrity_verified,
            "freeze_matches_latest_export": freeze_matches_latest_export,
            "approval_matches_latest_freeze": approval_matches_latest_freeze,
            "approval_guard_clean": approval_guard_clean,
            "consistent": bool(
                freeze_integrity_verified
                and approval_integrity_verified
                and freeze_matches_latest_export is True
                and approval_matches_latest_freeze is True
                and approval_guard_clean is True
            ),
        }

    def _resolve_training_approval_path(self, tenant_id: str, filename: str) -> Path | None:
        return self._local_artifact_path(
            self._read_training_approval_artifact(tenant_id, filename)
        )

    def _read_training_approval_artifact(
        self,
        tenant_id: str,
        filename: str,
    ) -> TrajectoryArtifact | None:
        if not _is_safe_training_approval_filename(filename):
            return None
        return self._read_artifact(
            tenant_id=tenant_id,
            directory="trajectory_training_approvals",
            filename=filename,
        )

    def _load_training_approval_by_file(self, tenant_id: str, filename: str) -> dict[str, Any] | None:
        artifact = self._read_training_approval_artifact(
            tenant_id,
            filename,
        )
        if artifact is None:
            return None
        if not self._json_artifact_belongs_to_tenant(artifact, tenant_id):
            return None
        try:
            data = json.loads(artifact.text())
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or data.get("tenant_id") not in (None, tenant_id):
            return None
        return data

    def _training_approval_eval_summary(self, tenant_id: str, approval: dict[str, Any]) -> dict[str, Any]:
        approval_file = str(approval.get("approval_file") or "")
        artifact = self._read_training_approval_artifact(
            tenant_id,
            approval_file,
        )
        data = self._load_training_approval_by_file(tenant_id, approval_file) or {}
        eval_plan = data.get("eval_plan") if isinstance(data.get("eval_plan"), dict) else {}
        required_metrics = eval_plan.get("required_metrics") if isinstance(eval_plan.get("required_metrics"), dict) else {}
        return {
            "approval_id": approval.get("approval_id"),
            "approval_file": approval_file,
            "exists": artifact is not None,
            "has_eval_plan": bool(eval_plan),
            "suite": eval_plan.get("suite"),
            "has_required_metrics": bool(required_metrics),
            "required_metric_count": len(required_metrics),
            "required_metric_names": sorted(str(key) for key in required_metrics.keys()),
        }
