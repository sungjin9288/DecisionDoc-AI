"""Read-only inventory for DocumentOps governance artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.storage.trajectory.redaction import (
    _is_safe_export_filename,
    _is_safe_freeze_filename,
    _is_safe_training_approval_filename,
    _is_safe_training_audit_filename,
    _is_safe_training_execution_request_filename,
)
from app.storage.trajectory.state_mixin import TrajectoryStoreError
from app.tenant import require_tenant_id


@dataclass(frozen=True)
class _ArtifactCollection:
    directory: str
    filename_key: str
    size_key: str
    sha256_key: str
    safe_filename: Callable[[str], bool]


_ARTIFACT_COLLECTIONS = {
    "exports": _ArtifactCollection(
        "trajectory_exports",
        "filename",
        "size_bytes",
        "content_sha256",
        _is_safe_export_filename,
    ),
    "freezes": _ArtifactCollection(
        "trajectory_freezes",
        "manifest_file",
        "manifest_size_bytes",
        "manifest_sha256",
        _is_safe_freeze_filename,
    ),
    "training_approvals": _ArtifactCollection(
        "trajectory_training_approvals",
        "approval_file",
        "approval_size_bytes",
        "approval_sha256",
        _is_safe_training_approval_filename,
    ),
    "training_execution_requests": _ArtifactCollection(
        "trajectory_training_execution_requests",
        "request_file",
        "request_size_bytes",
        "request_sha256",
        _is_safe_training_execution_request_filename,
    ),
    "training_pre_execution_audits": _ArtifactCollection(
        "trajectory_training_audits",
        "audit_file",
        "audit_size_bytes",
        "audit_sha256",
        _is_safe_training_audit_filename,
    ),
}

_ISSUE_STATUSES = {
    "invalid_reference",
    "referenced_missing",
    "referenced_tampered",
    "unreferenced",
}


class TrajectoryArtifactInventoryMixin:
    """Compare governance metadata authority with selected-backend objects."""

    def inspect_governance_artifacts(
        self,
        *,
        tenant_id: str,
        limit: int = 200,
    ) -> dict[str, Any]:
        tenant_id = require_tenant_id(tenant_id)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")

        with self._lock:
            metadata_raw, metadata = self._read_meta_state(
                tenant_id,
                for_update=False,
            )

        totals = self._empty_inventory_counts()
        collection_reports: dict[str, dict[str, Any]] = {}
        for collection_name, collection in _ARTIFACT_COLLECTIONS.items():
            report = self._inspect_artifact_collection(
                tenant_id=tenant_id,
                metadata=metadata,
                collection_name=collection_name,
                collection=collection,
                limit=limit,
            )
            collection_reports[collection_name] = report
            for key in totals:
                totals[key] += report["counts"][key]

        issue_count = sum(totals[key] for key in _ISSUE_STATUSES)
        return {
            "report_type": "document_ops_governance_artifact_inventory",
            "tenant_id": tenant_id,
            "backend": self._backend.kind,
            "status": "attention_required" if issue_count else "clean",
            "read_only": True,
            "metadata": {
                "relative_path": self._meta_relative_path(tenant_id),
                "exists": metadata_raw is not None,
            },
            "counts": totals,
            "collections": collection_reports,
            "observation_boundary": {
                "metadata_snapshot_atomic": True,
                "multi_object_snapshot_atomic": False,
                "concurrent_writes_may_require_recheck": True,
            },
            "cleanup_boundary": {
                "automatic_cleanup_allowed": False,
                "objects_deleted": False,
                "manual_recheck_required": True,
            },
        }

    def _inspect_artifact_collection(
        self,
        *,
        tenant_id: str,
        metadata: dict[str, Any],
        collection_name: str,
        collection: _ArtifactCollection,
        limit: int,
    ) -> dict[str, Any]:
        counts = self._empty_inventory_counts()
        entries: list[dict[str, Any]] = []
        referenced_paths: set[str] = set()
        references = self._owned_meta_items(
            metadata,
            collection_name,
            tenant_id,
        )

        for reference in references:
            counts["authoritative_references"] += 1
            entry = self._inspect_artifact_reference(
                tenant_id=tenant_id,
                collection_name=collection_name,
                collection=collection,
                reference=reference,
            )
            entries.append(entry)
            counts[entry["status"]] += 1
            relative_path = entry.get("relative_path")
            if isinstance(relative_path, str):
                referenced_paths.add(relative_path)

        observed_paths = set(
            self._list_artifact_paths(
                tenant_id=tenant_id,
                directory=collection.directory,
            )
        )
        counts["observed_objects"] = len(observed_paths)
        for relative_path in sorted(observed_paths - referenced_paths):
            counts["unreferenced"] += 1
            entries.append(
                {
                    "filename": relative_path.rsplit("/", 1)[-1],
                    "relative_path": relative_path,
                    "status": "unreferenced",
                    "content_inspected": False,
                }
            )

        entries.sort(
            key=lambda entry: (
                entry["status"] == "referenced_verified",
                str(entry.get("relative_path") or entry.get("filename") or ""),
            )
        )
        return {
            "directory": collection.directory,
            "counts": counts,
            "artifacts": entries[:limit],
            "returned": min(len(entries), limit),
            "truncated": len(entries) > limit,
        }

    def _inspect_artifact_reference(
        self,
        *,
        tenant_id: str,
        collection_name: str,
        collection: _ArtifactCollection,
        reference: dict[str, Any],
    ) -> dict[str, Any]:
        filename = str(reference.get(collection.filename_key) or "")
        expected_size = reference.get(collection.size_key)
        expected_sha256 = str(reference.get(collection.sha256_key) or "")
        if not collection.safe_filename(filename):
            return {
                "filename": filename,
                "relative_path": None,
                "status": "invalid_reference",
                "expected_size_bytes": expected_size,
                "expected_sha256": expected_sha256,
                "content_inspected": False,
            }

        artifact = self._read_artifact(
            tenant_id=tenant_id,
            directory=collection.directory,
            filename=filename,
        )
        relative_path = self._artifact_relative_path(
            tenant_id,
            collection.directory,
            filename,
        )
        if artifact is None:
            return {
                "filename": filename,
                "relative_path": relative_path,
                "status": "referenced_missing",
                "expected_size_bytes": expected_size,
                "expected_sha256": expected_sha256,
                "content_inspected": False,
            }

        size_matches = self._artifact_size_matches(artifact, expected_size)
        checksum_matches = artifact.sha256 == expected_sha256
        ownership_verified = self._artifact_ownership_matches(
            collection_name,
            artifact,
            tenant_id,
        )
        integrity_verified = size_matches and checksum_matches and ownership_verified
        return {
            "filename": filename,
            "relative_path": relative_path,
            "status": (
                "referenced_verified"
                if integrity_verified
                else "referenced_tampered"
            ),
            "expected_size_bytes": expected_size,
            "observed_size_bytes": artifact.size_bytes,
            "expected_sha256": expected_sha256,
            "observed_sha256": artifact.sha256,
            "checksum_verified": checksum_matches,
            "size_binding_verified": self._artifact_size_binding_verified(
                artifact,
                expected_size,
            ),
            "ownership_verified": ownership_verified,
            "integrity_verified": integrity_verified,
            "content_inspected": True,
        }

    def _artifact_ownership_matches(
        self,
        collection_name: str,
        artifact: Any,
        tenant_id: str,
    ) -> bool:
        try:
            if collection_name == "exports":
                return self._jsonl_export_belongs_to_tenant(
                    artifact,
                    tenant_id,
                )
            return self._json_artifact_belongs_to_tenant(
                artifact,
                tenant_id,
            )
        except TrajectoryStoreError:
            return False

    @staticmethod
    def _empty_inventory_counts() -> dict[str, int]:
        return {
            "authoritative_references": 0,
            "observed_objects": 0,
            "referenced_verified": 0,
            "referenced_missing": 0,
            "referenced_tampered": 0,
            "invalid_reference": 0,
            "unreferenced": 0,
        }
