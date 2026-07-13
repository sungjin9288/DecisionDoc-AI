"""Pre-execution audit checklist, audit export, and governance dashboard summary."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.storage.trajectory.redaction import _dedupe, _file_sha256, _is_safe_training_audit_filename, _now_iso


class TrajectoryTrainingAuditMixin:
    """Pre-execution audit checklist/export and governance dashboard summary."""

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
        request_record = self._load_training_execution_request_by_file(
            tenant_id,
            str((latest_request or {}).get("request_file") or ""),
        )
        request_plan = (
            request_record.get("plan_preview")
            if isinstance((request_record or {}).get("plan_preview"), dict)
            else {}
        )
        request_dataset = (
            request_plan.get("dataset")
            if isinstance(request_plan.get("dataset"), dict)
            else {}
        )
        request_gate = (
            request_record.get("request_gate")
            if isinstance((request_record or {}).get("request_gate"), dict)
            else {}
        )
        request_guard = (
            request_record.get("execution_guard")
            if isinstance((request_record or {}).get("execution_guard"), dict)
            else {}
        )
        request_two_person = (
            request_record.get("two_person_guard")
            if isinstance((request_record or {}).get("two_person_guard"), dict)
            else {}
        )
        request_guard_clean = bool(
            request_record
            and request_guard.get("training_execution_allowed", False) is False
            and request_guard.get("start_training_requested", False) is False
            and request_guard.get("provider_job_started", False) is False
            and request_guard.get("external_upload_started", False) is False
            and request_guard.get("provider_api_calls_allowed", False) is False
            and request_guard.get("model_promotion_allowed", False) is False
        )
        readiness_ready = readiness.get("ready_for_training_execution") is True
        plan_ready = plan_preview.get("status") == "ready_for_manual_execution_planning"
        two_person_ready = bool(
            request_record
            and request_two_person.get("satisfied") is True
            and request_two_person.get("required") is True
        )
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
        artifact_chain = readiness.get("artifact_chain") if isinstance(readiness.get("artifact_chain"), dict) else {}
        latest_approval = (
            readiness.get("latest_training_approval")
            if isinstance(readiness.get("latest_training_approval"), dict)
            else {}
        )
        request_chain_consistent = bool(
            latest_request
            and latest_request.get("integrity_verified") is True
            and request_record
            and request_record.get("request_id") == latest_request.get("request_id")
            and artifact_chain.get("consistent") is True
            and request_dataset.get("freeze_manifest_id") == dataset.get("freeze_manifest_id")
            and request_gate.get("prior_training_approval_id") == latest_approval.get("approval_id")
            and request_plan.get("provider") == job_spec.get("provider")
            and request_plan.get("base_model") == job_spec.get("base_model")
        )
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
                "passed": bool(latest_request and latest_request.get("exists") is True),
                "evidence": {
                    "request_id": (latest_request or {}).get("request_id"),
                    "exists": (latest_request or {}).get("exists", False),
                },
            },
            {
                "id": "artifact_chain_consistent",
                "severity": "required",
                "passed": request_chain_consistent,
                "evidence": {
                    "request_integrity_verified": (latest_request or {}).get("integrity_verified", False),
                    "current_manifest_id": dataset.get("freeze_manifest_id"),
                    "request_manifest_id": request_dataset.get("freeze_manifest_id"),
                    "current_approval_id": latest_approval.get("approval_id"),
                    "request_approval_id": request_gate.get("prior_training_approval_id"),
                    "current_provider": job_spec.get("provider"),
                    "request_provider": request_plan.get("provider"),
                    "current_base_model": job_spec.get("base_model"),
                    "request_base_model": request_plan.get("base_model"),
                },
            },
            {
                "id": "two_person_guard_satisfied",
                "severity": "required",
                "passed": two_person_ready,
                "evidence": {
                    "requester": request_two_person.get("execution_requester"),
                    "prior_training_approver": request_two_person.get("prior_training_approver"),
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
                    "request_provider_api_calls_allowed": request_guard.get("provider_api_calls_allowed"),
                    "request_model_promotion_allowed": request_guard.get("model_promotion_allowed"),
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
                "artifact_chain": artifact_chain,
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
            audit_sha256 = str(item.get("audit_sha256") or "")
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
                    "provider_api_calls_allowed": bool(item.get("provider_api_calls_allowed", False)),
                    "model_promotion_allowed": bool(item.get("model_promotion_allowed", False)),
                    "audit_sha256": audit_sha256 or None,
                    "integrity_verified": bool(
                        audit_path
                        and audit_sha256
                        and _file_sha256(audit_path) == audit_sha256
                    ),
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
        if checklist.get("status") != "ready_for_human_pre_execution_review":
            raise ValueError("Pre-execution audit export requires a ready checklist.")

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
        self._append_training_pre_execution_audit_meta(
            tenant_id,
            audit_file,
            audit_record,
            audit_sha256=_file_sha256(audit_path),
        )
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
        latest_audit = audits[0] if audits else None
        audit_chain = self._training_audit_chain_summary(
            tenant_id=tenant_id,
            latest_audit=latest_audit,
            current_checklist=audit_checklist,
        )
        guard_counts = {
            "training_allowed_count": sum(1 for item in freezes if item.get("training_allowed") is True),
            "training_started_count": sum(1 for item in freezes if item.get("training_started") is True),
            "approval_provider_job_started_count": sum(1 for item in approvals if item.get("provider_job_started") is True),
            "approval_model_promotion_allowed_count": sum(1 for item in approvals if item.get("model_promotion_allowed") is True),
            "approval_training_execution_allowed_count": sum(1 for item in approvals if item.get("training_execution_allowed") is True),
            "approval_external_upload_started_count": sum(1 for item in approvals if item.get("external_upload_started") is True),
            "approval_provider_api_calls_allowed_count": sum(1 for item in approvals if item.get("provider_api_calls_allowed") is True),
            "request_training_execution_allowed_count": sum(1 for item in execution_requests if item.get("training_execution_allowed") is True),
            "request_provider_job_started_count": sum(1 for item in execution_requests if item.get("provider_job_started") is True),
            "request_external_upload_started_count": sum(1 for item in execution_requests if item.get("external_upload_started") is True),
            "request_provider_api_calls_allowed_count": sum(1 for item in execution_requests if item.get("provider_api_calls_allowed") is True),
            "request_model_promotion_allowed_count": sum(1 for item in execution_requests if item.get("model_promotion_allowed") is True),
            "audit_training_execution_allowed_count": sum(1 for item in audits if item.get("training_execution_allowed") is True),
            "audit_provider_job_started_count": sum(1 for item in audits if item.get("provider_job_started") is True),
            "audit_external_upload_started_count": sum(1 for item in audits if item.get("external_upload_started") is True),
            "audit_provider_api_calls_allowed_count": sum(1 for item in audits if item.get("provider_api_calls_allowed") is True),
            "audit_model_promotion_allowed_count": sum(1 for item in audits if item.get("model_promotion_allowed") is True),
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
                *(
                    ["latest_training_audit_integrity_failed"]
                    if latest_audit and latest_audit.get("integrity_verified") is not True
                    else []
                ),
                *(
                    ["latest_training_audit_does_not_match_current_chain"]
                    if latest_audit and audit_chain.get("matches_current_chain") is not True
                    else []
                ),
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
            "artifact_chain": readiness.get("artifact_chain") or {},
            "audit_chain": audit_chain,
            "readiness_summary": readiness,
            "training_plan_preview": plan_preview,
            "audit_checklist": audit_checklist,
        }

    def _append_training_pre_execution_audit_meta(
        self,
        tenant_id: str,
        audit_file: str,
        audit_record: dict[str, Any],
        *,
        audit_sha256: str,
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
                    "audit_sha256": audit_sha256,
                    "status": gate.get("status"),
                    "auditor": gate.get("auditor"),
                    "request_id": packet.get("latest_request_id"),
                    "manifest_id": dataset.get("freeze_manifest_id"),
                    "provider": job_spec.get("provider"),
                    "base_model": job_spec.get("base_model"),
                    "training_execution_allowed": guard.get("training_execution_allowed", False),
                    "provider_job_started": guard.get("provider_job_started", False),
                    "external_upload_started": guard.get("external_upload_started", False),
                    "provider_api_calls_allowed": guard.get("provider_api_calls_allowed", False),
                    "model_promotion_allowed": guard.get("model_promotion_allowed", False),
                    "created_at": audit_record.get("created_at"),
                }
            )
            atomic_write_text(self._meta_path(tenant_id), json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True))

    def _training_audit_chain_summary(
        self,
        *,
        tenant_id: str,
        latest_audit: dict[str, Any] | None,
        current_checklist: dict[str, Any],
    ) -> dict[str, Any]:
        audit_record = self._load_training_audit_by_file(
            tenant_id,
            str((latest_audit or {}).get("audit_file") or ""),
        )
        audit_snapshot = (
            audit_record.get("checklist_snapshot")
            if isinstance((audit_record or {}).get("checklist_snapshot"), dict)
            else {}
        )
        audit_packet = (
            audit_snapshot.get("human_review_packet")
            if isinstance(audit_snapshot.get("human_review_packet"), dict)
            else {}
        )
        audit_dataset = (
            audit_packet.get("dataset")
            if isinstance(audit_packet.get("dataset"), dict)
            else {}
        )
        audit_plan = (
            audit_snapshot.get("training_plan_preview")
            if isinstance(audit_snapshot.get("training_plan_preview"), dict)
            else {}
        )
        audit_job_spec = (
            audit_plan.get("job_spec")
            if isinstance(audit_plan.get("job_spec"), dict)
            else {}
        )
        current_packet = (
            current_checklist.get("human_review_packet")
            if isinstance(current_checklist.get("human_review_packet"), dict)
            else {}
        )
        current_dataset = (
            current_packet.get("dataset")
            if isinstance(current_packet.get("dataset"), dict)
            else {}
        )
        current_plan = (
            current_checklist.get("training_plan_preview")
            if isinstance(current_checklist.get("training_plan_preview"), dict)
            else {}
        )
        current_job_spec = (
            current_plan.get("job_spec")
            if isinstance(current_plan.get("job_spec"), dict)
            else {}
        )
        matches_current_chain = bool(
            latest_audit
            and latest_audit.get("integrity_verified") is True
            and audit_record
            and audit_record.get("audit_id") == latest_audit.get("audit_id")
            and audit_packet.get("latest_request_id") == current_packet.get("latest_request_id")
            and audit_dataset.get("freeze_manifest_id") == current_dataset.get("freeze_manifest_id")
            and audit_job_spec.get("provider") == current_job_spec.get("provider")
            and audit_job_spec.get("base_model") == current_job_spec.get("base_model")
        )
        return {
            "audit_id": (latest_audit or {}).get("audit_id"),
            "audit_request_id": audit_packet.get("latest_request_id"),
            "current_request_id": current_packet.get("latest_request_id"),
            "audit_manifest_id": audit_dataset.get("freeze_manifest_id"),
            "current_manifest_id": current_dataset.get("freeze_manifest_id"),
            "integrity_verified": bool(
                latest_audit and latest_audit.get("integrity_verified") is True
            ),
            "matches_current_chain": matches_current_chain,
        }

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

    def _load_training_audit_by_file(self, tenant_id: str, filename: str) -> dict[str, Any] | None:
        audit_path = self._resolve_training_audit_path(tenant_id, filename)
        if audit_path is None:
            return None
        try:
            data = json.loads(audit_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        return data if isinstance(data, dict) else None
