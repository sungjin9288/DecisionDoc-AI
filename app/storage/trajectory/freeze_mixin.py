"""Dataset freeze manifest creation and lookup (no-training-by-default gate)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.trajectory.artifact_state_mixin import TrajectoryArtifact
from app.storage.trajectory.redaction import (
    _is_safe_freeze_filename,
    _json_sha256,
)


class TrajectoryFreezeMixin:
    """Dataset freeze manifest write path and listing."""

    def list_dataset_freezes(
        self,
        *,
        tenant_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Return newest dataset freeze manifest metadata."""
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_freezes = self._owned_meta_items(meta, "freezes", tenant_id)
        freezes: list[dict[str, Any]] = []
        seen_manifest_files: set[str] = set()
        for item in reversed(raw_freezes):
            if not isinstance(item, dict):
                continue
            manifest_file = str(item.get("manifest_file") or "")
            if manifest_file in seen_manifest_files:
                continue
            artifact = self._read_freeze_artifact(
                tenant_id,
                manifest_file,
            )
            if artifact and not self._json_artifact_belongs_to_tenant(
                artifact,
                tenant_id,
            ):
                continue
            manifest_sha256 = str(item.get("manifest_sha256") or "")
            manifest_size = item.get("manifest_size_bytes")
            size_matches = self._artifact_size_matches(
                artifact,
                manifest_size,
            )
            freezes.append(
                {
                    "manifest_id": item.get("manifest_id"),
                    "manifest_file": manifest_file,
                    "export_filename": item.get("export_filename"),
                    "export_sha256": item.get("export_sha256"),
                    "record_count": int(item.get("record_count") or 0),
                    "quality_report_sha256": item.get("quality_report_sha256"),
                    "manifest_sha256": manifest_sha256 or None,
                    "integrity_verified": bool(
                        artifact
                        and manifest_sha256
                        and size_matches
                        and artifact.sha256 == manifest_sha256
                    ),
                    "size_binding_verified": self._artifact_size_binding_verified(
                        artifact,
                        manifest_size,
                    ),
                    "training_allowed": bool(item.get("training_allowed", False)),
                    "training_started": bool(item.get("training_started", False)),
                    "reviewer": item.get("reviewer"),
                    "created_at": item.get("created_at"),
                    "exists": artifact is not None,
                    "size_bytes": artifact.size_bytes if artifact else 0,
                }
            )
            seen_manifest_files.add(manifest_file)
            if len(freezes) >= limit:
                break
        return freezes

    def freeze_sft_export(
        self,
        filename: str,
        *,
        tenant_id: str,
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
        export_artifact = self._get_sft_export_artifact(
            filename,
            tenant_id=tenant_id,
            reviewed_only=False,
            require_integrity=False,
        )
        if export_artifact is None:
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
        export_sha256 = export_artifact.sha256
        manifest = {
            "schema_version": "document_ops_dataset_freeze_v1",
            "manifest_id": manifest_id,
            "created_at": created_at,
            "tenant_id": tenant_id,
            "export": {
                "filename": export_artifact.filename,
                "size_bytes": export_artifact.size_bytes,
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
        export_stem = Path(export_artifact.filename).stem
        manifest_file = (
            f"freeze_{export_stem}_{manifest_ts}_{manifest_id[-8:]}.json"
        )
        raw = json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        artifact = self._publish_artifact(
            tenant_id=tenant_id,
            directory="trajectory_freezes",
            filename=manifest_file,
            raw=raw,
            content_type="application/json; charset=utf-8",
        )
        self._append_freeze_meta(
            tenant_id,
            manifest_file,
            manifest,
            manifest_size_bytes=artifact.size_bytes,
            manifest_sha256=artifact.sha256,
        )
        return manifest

    def _append_freeze_meta(
        self,
        tenant_id: str,
        manifest_file: str,
        manifest: dict[str, Any],
        *,
        manifest_size_bytes: int,
        manifest_sha256: str,
    ) -> None:
        item = {
            "tenant_id": tenant_id,
            "manifest_id": manifest.get("manifest_id"),
            "manifest_file": manifest_file,
            "manifest_size_bytes": manifest_size_bytes,
            "manifest_sha256": manifest_sha256,
            "export_filename": (manifest.get("export") or {}).get(
                "filename"
            ),
            "export_sha256": (manifest.get("export") or {}).get("sha256"),
            "record_count": (manifest.get("export") or {}).get(
                "record_count"
            ),
            "quality_report_sha256": (
                manifest.get("quality_report") or {}
            ).get("sha256"),
            "training_allowed": (manifest.get("training_guard") or {}).get(
                "training_allowed",
                False,
            ),
            "training_started": (manifest.get("training_guard") or {}).get(
                "training_started",
                False,
            ),
            "reviewer": (manifest.get("review_gate") or {}).get("reviewer"),
            "created_at": manifest.get("created_at"),
        }
        with self._lock:
            self._append_meta_item(
                tenant_id=tenant_id,
                collection="freezes",
                count_key="freeze_count",
                item=item,
                identity_keys=("manifest_id", "manifest_file"),
            )

    def _load_freeze_manifest_by_id(self, manifest_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            meta = self._load_meta_unlocked(tenant_id)
        raw_freezes = self._owned_meta_items(meta, "freezes", tenant_id)
        manifest_file = ""
        for item in raw_freezes:
            if isinstance(item, dict) and item.get("manifest_id") == manifest_id:
                manifest_file = str(item.get("manifest_file") or "")
                break
        if not manifest_file:
            return None
        artifact = self._read_freeze_artifact(tenant_id, manifest_file)
        if artifact is None:
            return None
        if not self._json_artifact_belongs_to_tenant(artifact, tenant_id):
            return None
        try:
            data = json.loads(artifact.text())
        except (json.JSONDecodeError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("tenant_id") not in (None, tenant_id):
            return None
        return data

    def _resolve_freeze_path(self, tenant_id: str, filename: str) -> Path | None:
        return self._local_artifact_path(
            self._read_freeze_artifact(tenant_id, filename)
        )

    def _read_freeze_artifact(
        self,
        tenant_id: str,
        filename: str,
    ) -> TrajectoryArtifact | None:
        if not _is_safe_freeze_filename(filename):
            return None
        return self._read_artifact(
            tenant_id=tenant_id,
            directory="trajectory_freezes",
            filename=filename,
        )
