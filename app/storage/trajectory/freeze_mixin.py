"""Dataset freeze manifest creation and lookup (no-training-by-default gate)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.storage.base import atomic_write_text
from app.storage.trajectory.redaction import _file_sha256, _is_safe_freeze_filename, _json_sha256


class TrajectoryFreezeMixin:
    """Dataset freeze manifest write path and listing."""

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
