"""Two-person training execution request records (no execution side effects)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.trajectory.artifact_state_mixin import TrajectoryArtifact
from app.storage.trajectory.redaction import (
    _is_safe_training_execution_request_filename,
    _json_sha256,
)


class TrajectoryTrainingExecutionMixin:
    """Two-person training execution request write path and listing."""

    def list_training_execution_requests(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return newest no-side-effect training execution request records."""
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_requests = self._owned_meta_items(
            meta,
            "training_execution_requests",
            tenant_id,
        )
        requests: list[dict[str, Any]] = []
        seen_files: set[str] = set()
        for item in reversed(raw_requests):
            if not isinstance(item, dict):
                continue
            request_file = str(item.get("request_file") or "")
            if request_file in seen_files:
                continue
            artifact = self._read_training_execution_request_artifact(
                tenant_id,
                request_file,
            )
            if artifact and not self._json_artifact_belongs_to_tenant(
                artifact,
                tenant_id,
            ):
                continue
            request_sha256 = str(item.get("request_sha256") or "")
            request_size = item.get("request_size_bytes")
            size_matches = self._artifact_size_matches(
                artifact,
                request_size,
            )
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
                    "provider_api_calls_allowed": bool(item.get("provider_api_calls_allowed", False)),
                    "model_promotion_allowed": bool(item.get("model_promotion_allowed", False)),
                    "request_sha256": request_sha256 or None,
                    "integrity_verified": bool(
                        artifact
                        and request_sha256
                        and size_matches
                        and artifact.sha256 == request_sha256
                    ),
                    "size_binding_verified": self._artifact_size_binding_verified(
                        artifact,
                        request_size,
                    ),
                    "created_at": item.get("created_at"),
                    "exists": artifact is not None,
                    "size_bytes": artifact.size_bytes if artifact else 0,
                }
            )
            seen_files.add(request_file)
            if len(requests) >= limit:
                break
        return requests

    def request_training_execution_from_plan(
        self,
        *,
        tenant_id: str,
        requester: str,
        provider: str = "provider_agnostic",
        base_model: str | None = None,
        notes: str = "",
        limit: int = 50,
        start_training: bool = False,
        upload_dataset: bool = False,
        call_provider_api: bool = False,
        operation_id: str | None = None,
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

        operation_payload_hash = (
            _json_sha256(
                {
                    "action": "request_training_execution_from_plan",
                    "base_model": base_model,
                    "call_provider_api": call_provider_api,
                    "limit": limit,
                    "notes": notes,
                    "provider": provider,
                    "requester": requester,
                    "start_training": start_training,
                    "upload_dataset": upload_dataset,
                }
            )
            if operation_id is not None
            else None
        )
        existing_operation = self._find_meta_operation_item(
            tenant_id=tenant_id,
            collection="training_execution_requests",
            operation_id=operation_id,
            operation_payload_hash=operation_payload_hash,
        )
        if existing_operation is not None:
            return self._load_bound_operation_artifact(
                artifact=self._read_training_execution_request_artifact(
                    tenant_id,
                    str(existing_operation.get("request_file") or ""),
                ),
                metadata=existing_operation,
                tenant_id=tenant_id,
                size_key="request_size_bytes",
                sha256_key="request_sha256",
                identity_key="request_id",
            )

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
        artifact = self._publish_artifact(
            tenant_id=tenant_id,
            directory="trajectory_training_execution_requests",
            filename=request_file,
            raw=json.dumps(
                request_record,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )
        selected = self._append_training_execution_request_meta(
            tenant_id,
            request_file,
            request_record,
            request_size_bytes=artifact.size_bytes,
            request_sha256=artifact.sha256,
            operation_id=operation_id,
            operation_payload_hash=operation_payload_hash,
        )
        if selected.get("request_id") != request_id:
            return self._load_bound_operation_artifact(
                artifact=self._read_training_execution_request_artifact(
                    tenant_id,
                    str(selected.get("request_file") or ""),
                ),
                metadata=selected,
                tenant_id=tenant_id,
                size_key="request_size_bytes",
                sha256_key="request_sha256",
                identity_key="request_id",
            )
        return request_record

    def _append_training_execution_request_meta(
        self,
        tenant_id: str,
        request_file: str,
        request_record: dict[str, Any],
        *,
        request_size_bytes: int,
        request_sha256: str,
        operation_id: str | None = None,
        operation_payload_hash: str | None = None,
    ) -> dict[str, Any]:
        plan = (
            request_record.get("plan_preview")
            if isinstance(request_record.get("plan_preview"), dict)
            else {}
        )
        dataset = (
            plan.get("dataset")
            if isinstance(plan.get("dataset"), dict)
            else {}
        )
        gate = (
            request_record.get("request_gate")
            if isinstance(request_record.get("request_gate"), dict)
            else {}
        )
        guard = (
            request_record.get("execution_guard")
            if isinstance(request_record.get("execution_guard"), dict)
            else {}
        )
        two_person = (
            request_record.get("two_person_guard")
            if isinstance(request_record.get("two_person_guard"), dict)
            else {}
        )
        item = {
            "tenant_id": tenant_id,
            "request_id": request_record.get("request_id"),
            "request_file": request_file,
            "request_size_bytes": request_size_bytes,
            "request_sha256": request_sha256,
            "manifest_id": dataset.get("freeze_manifest_id"),
            "approval_id": gate.get("prior_training_approval_id"),
            "provider": plan.get("provider"),
            "base_model": plan.get("base_model"),
            "requester": gate.get("requester"),
            "prior_training_approver": gate.get(
                "prior_training_approver"
            ),
            "two_person_guard_satisfied": two_person.get(
                "satisfied",
                False,
            ),
            "training_execution_allowed": guard.get(
                "training_execution_allowed",
                False,
            ),
            "provider_job_started": guard.get(
                "provider_job_started",
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
            "model_promotion_allowed": guard.get(
                "model_promotion_allowed",
                False,
            ),
            "created_at": request_record.get("created_at"),
        }
        with self._lock:
            return self._append_meta_item(
                tenant_id=tenant_id,
                collection="training_execution_requests",
                count_key="training_execution_request_count",
                item=item,
                identity_keys=("request_id", "request_file"),
                operation_id=operation_id,
                operation_payload_hash=operation_payload_hash,
            )

    def _resolve_training_execution_request_path(self, tenant_id: str, filename: str) -> Path | None:
        return self._local_artifact_path(
            self._read_training_execution_request_artifact(
                tenant_id,
                filename,
            )
        )

    def _read_training_execution_request_artifact(
        self,
        tenant_id: str,
        filename: str,
    ) -> TrajectoryArtifact | None:
        if not _is_safe_training_execution_request_filename(filename):
            return None
        return self._read_artifact(
            tenant_id=tenant_id,
            directory="trajectory_training_execution_requests",
            filename=filename,
        )

    def _load_training_execution_request_by_file(
        self,
        tenant_id: str,
        filename: str,
    ) -> dict[str, Any] | None:
        artifact = self._read_training_execution_request_artifact(
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
