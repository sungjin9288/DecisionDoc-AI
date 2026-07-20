"""Selected-backend authority for DocumentOps governance metadata and artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from app.storage.conditional_state import mutate_with_retry, persist_text_if_current
from app.storage.state_backend import StateBackendError
from app.storage.trajectory.state_mixin import TrajectoryStoreError
from app.tenant import require_tenant_id

_MAX_METADATA_MUTATION_ATTEMPTS = 32
_MutationResult = TypeVar("_MutationResult")
_METADATA_COLLECTIONS = {
    "exports": (
        "export_count",
        ("filename", "export_fingerprint"),
        "size_bytes",
        "content_sha256",
    ),
    "freezes": (
        "freeze_count",
        ("manifest_id", "manifest_file"),
        "manifest_size_bytes",
        "manifest_sha256",
    ),
    "training_approvals": (
        "training_approval_count",
        ("approval_id", "approval_file"),
        "approval_size_bytes",
        "approval_sha256",
    ),
    "training_execution_requests": (
        "training_execution_request_count",
        ("request_id", "request_file"),
        "request_size_bytes",
        "request_sha256",
    ),
    "training_pre_execution_audits": (
        "training_pre_execution_audit_count",
        ("audit_id", "audit_file"),
        "audit_size_bytes",
        "audit_sha256",
    ),
}


@dataclass(frozen=True)
class TrajectoryArtifact:
    filename: str
    relative_path: str
    raw: bytes

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()

    @property
    def size_bytes(self) -> int:
        return len(self.raw)

    def text(self) -> str:
        try:
            return self.raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TrajectoryStoreError("Trajectory artifact is not valid UTF-8") from exc


def _unique_metadata_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TrajectoryStoreError(
                f"Duplicate key in trajectory metadata: {key!r}"
            )
        result[key] = value
    return result


def _reject_nonfinite_metadata(value: str) -> None:
    raise TrajectoryStoreError(
        f"Invalid numeric value in trajectory metadata: {value}"
    )


class TrajectoryArtifactStateMixin:
    """Persist the governance index with CAS and artifacts as immutable objects."""

    def _empty_meta(self, tenant_id: str) -> dict[str, Any]:
        return {
            "tenant_id": tenant_id,
            "export_count": 0,
            "exports": [],
        }

    def _decode_meta(
        self,
        raw: str,
        *,
        tenant_id: str,
        for_update: bool,
    ) -> dict[str, Any]:
        if not raw:
            raise TrajectoryStoreError("Trajectory metadata is blank")
        try:
            meta = json.loads(
                raw,
                object_pairs_hook=_unique_metadata_object,
                parse_constant=_reject_nonfinite_metadata,
            )
        except (
            json.JSONDecodeError,
            TypeError,
            TrajectoryStoreError,
        ) as exc:
            raise TrajectoryStoreError(
                "Trajectory metadata document is invalid"
            ) from exc
        if not isinstance(meta, dict):
            raise TrajectoryStoreError(
                "Trajectory metadata document must be an object"
            )

        stored_tenant = meta.get("tenant_id")
        if stored_tenant not in (None, tenant_id):
            if for_update:
                raise ValueError(
                    "trajectory metadata tenant_id does not match the requested tenant"
                )
            return self._empty_meta(tenant_id)

        result = dict(meta)
        result["tenant_id"] = tenant_id
        for key, value in result.items():
            if key.endswith("_count") and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise TrajectoryStoreError(
                    f"Invalid trajectory metadata count: {key}"
                )
        for collection, (
            count_key,
            identity_keys,
            size_key,
            sha256_key,
        ) in _METADATA_COLLECTIONS.items():
            entries = result.get(collection)
            if entries is None:
                if count_key in result and result[count_key] != 0:
                    raise TrajectoryStoreError(
                        f"Trajectory metadata count mismatch: {count_key}"
                    )
                continue
            if not isinstance(entries, list) or any(
                not isinstance(entry, dict)
                for entry in entries
            ):
                raise TrajectoryStoreError(
                    f"Invalid trajectory metadata collection: {collection}"
                )
            owned = [
                entry
                for entry in entries
                if entry.get("tenant_id") in (None, tenant_id)
            ]
            for identity_key in identity_keys:
                identities = [
                    entry.get(identity_key)
                    for entry in owned
                ]
                if any(
                    not isinstance(identity, str) or not identity
                    for identity in identities
                ):
                    raise TrajectoryStoreError(
                        f"Invalid trajectory metadata identity: {collection}"
                    )
                if len(identities) != len(set(identities)):
                    raise TrajectoryStoreError(
                        f"Duplicate trajectory metadata identity: {collection}"
                    )
            for entry in owned:
                size = entry.get(size_key)
                if size is not None and (
                    isinstance(size, bool)
                    or not isinstance(size, int)
                    or size <= 0
                ):
                    raise TrajectoryStoreError(
                        f"Invalid trajectory artifact size: {collection}"
                    )
                sha256 = entry.get(sha256_key)
                if (
                    not isinstance(sha256, str)
                    or len(sha256) != 64
                    or any(character not in "0123456789abcdef" for character in sha256)
                ):
                    raise TrajectoryStoreError(
                        f"Invalid trajectory artifact checksum: {collection}"
                    )
            if count_key in result and result[count_key] != len(owned):
                raise TrajectoryStoreError(
                    f"Trajectory metadata count mismatch: {count_key}"
                )
        return result

    def _read_meta_state(
        self,
        tenant_id: str,
        *,
        for_update: bool,
    ) -> tuple[str | None, dict[str, Any]]:
        relative_path = self._meta_relative_path(tenant_id)
        try:
            raw = self._backend.read_text(relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise TrajectoryStoreError(
                "Trajectory metadata could not be read"
            ) from exc
        if raw is None:
            return None, self._empty_meta(tenant_id)
        return raw, self._decode_meta(
            raw,
            tenant_id=tenant_id,
            for_update=for_update,
        )

    def _load_meta_unlocked(
        self,
        tenant_id: str,
        *,
        for_update: bool = False,
    ) -> dict[str, Any]:
        return self._read_meta_state(
            tenant_id,
            for_update=for_update,
        )[1]

    def _serialize_meta(
        self,
        tenant_id: str,
        meta: dict[str, Any],
    ) -> str:
        if meta.get("tenant_id") != tenant_id:
            raise ValueError(
                "trajectory metadata tenant_id does not match the requested tenant"
            )
        try:
            serialized = json.dumps(
                meta,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise TrajectoryStoreError(
                "Trajectory metadata could not be serialized"
            ) from exc
        self._decode_meta(
            serialized,
            tenant_id=tenant_id,
            for_update=True,
        )
        return serialized

    def _persist_meta_if_current(
        self,
        *,
        tenant_id: str,
        expected: str | None,
        meta: dict[str, Any],
        committed: Callable[[dict[str, Any]], bool],
    ) -> bool:
        replacement = self._serialize_meta(tenant_id, meta)
        try:
            return persist_text_if_current(
                backend=self._backend,
                relative_path=self._meta_relative_path(tenant_id),
                expected=expected,
                replacement=replacement,
                decode=lambda raw: self._decode_meta(
                    raw,
                    tenant_id=tenant_id,
                    for_update=True,
                ),
                committed=committed,
                decode_errors=(TrajectoryStoreError,),
            )
        except StateBackendError as exc:
            raise TrajectoryStoreError(
                "Trajectory metadata could not be persisted"
            ) from exc

    def _mutate_meta(
        self,
        *,
        tenant_id: str,
        change: Callable[
            [dict[str, Any]],
            tuple[_MutationResult, bool],
        ],
        committed: Callable[[dict[str, Any]], bool],
    ) -> _MutationResult:
        return mutate_with_retry(
            read=lambda: self._read_meta_state(
                tenant_id,
                for_update=True,
            ),
            change=change,
            persist=lambda expected, meta, was_committed: (
                self._persist_meta_if_current(
                    tenant_id=tenant_id,
                    expected=expected,
                    meta=meta,
                    committed=was_committed,
                )
            ),
            committed=committed,
            max_attempts=_MAX_METADATA_MUTATION_ATTEMPTS,
            conflict_error=lambda: TrajectoryStoreError(
                "Trajectory metadata changed too many times to persist safely"
            ),
        )

    def _append_meta_item(
        self,
        *,
        tenant_id: str,
        collection: str,
        count_key: str,
        item: dict[str, Any],
        identity_keys: tuple[str, ...],
    ) -> None:
        def same_identity(candidate: dict[str, Any]) -> bool:
            return any(
                candidate.get(key) == item.get(key)
                for key in identity_keys
            )

        def append(meta: dict[str, Any]) -> tuple[None, bool]:
            entries = meta.setdefault(collection, [])
            if not isinstance(entries, list):
                raise TrajectoryStoreError(
                    f"Invalid trajectory metadata collection: {collection}"
                )
            owned = [
                entry
                for entry in entries
                if isinstance(entry, dict)
                and entry.get("tenant_id") in (None, tenant_id)
            ]
            existing = next(
                (entry for entry in owned if same_identity(entry)),
                None,
            )
            if existing is not None:
                if existing != item:
                    raise TrajectoryStoreError(
                        f"Trajectory metadata identity collision: {collection}"
                    )
                return None, False
            entries.append(item)
            meta[count_key] = len(owned) + 1
            return None, True

        def was_committed(meta: dict[str, Any]) -> bool:
            entries = meta.get(collection)
            return isinstance(entries, list) and any(
                entry == item
                for entry in entries
                if isinstance(entry, dict)
            )

        self._mutate_meta(
            tenant_id=tenant_id,
            change=append,
            committed=was_committed,
        )

    def _read_artifact(
        self,
        *,
        tenant_id: str,
        directory: str,
        filename: str,
    ) -> TrajectoryArtifact | None:
        relative_path = self._artifact_relative_path(
            tenant_id,
            directory,
            filename,
        )
        try:
            raw = self._backend.read_bytes(relative_path)
        except StateBackendError as exc:
            raise TrajectoryStoreError(
                "Trajectory artifact could not be read"
            ) from exc
        if raw is None:
            return None
        return TrajectoryArtifact(
            filename=filename,
            relative_path=relative_path,
            raw=raw,
        )

    def _publish_artifact(
        self,
        *,
        tenant_id: str,
        directory: str,
        filename: str,
        raw: bytes,
        content_type: str,
    ) -> TrajectoryArtifact:
        relative_path = self._artifact_relative_path(
            tenant_id,
            directory,
            filename,
        )
        try:
            created = self._backend.write_bytes_if_absent(
                relative_path,
                raw,
                content_type=content_type,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_bytes(relative_path)
            except StateBackendError:
                observed = None
            if observed != raw:
                raise TrajectoryStoreError(
                    "Trajectory artifact could not be published"
                ) from exc
            created = False

        if not created:
            try:
                observed = self._backend.read_bytes(relative_path)
            except StateBackendError as exc:
                raise TrajectoryStoreError(
                    "Trajectory artifact could not be verified"
                ) from exc
            if observed != raw:
                raise TrajectoryStoreError(
                    "Trajectory artifact identity collision"
                )

        return TrajectoryArtifact(
            filename=filename,
            relative_path=relative_path,
            raw=raw,
        )

    def _local_artifact_path(
        self,
        artifact: TrajectoryArtifact | None,
    ) -> Path | None:
        if artifact is None or self._backend.kind != "local":
            return None
        root = getattr(self._backend, "root", None)
        if root is None:
            return None
        candidate = Path(root) / artifact.relative_path
        try:
            resolved = candidate.resolve(strict=True)
            resolved_root = Path(root).resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_file() or not resolved.is_relative_to(resolved_root):
            return None
        return resolved

    def _artifact_reference(self, artifact: TrajectoryArtifact) -> str:
        local_path = self._local_artifact_path(artifact)
        return str(local_path or artifact.relative_path)

    @staticmethod
    def _artifact_size_matches(
        artifact: TrajectoryArtifact | None,
        expected_size: Any,
    ) -> bool:
        return expected_size is None or bool(
            artifact
            and isinstance(expected_size, int)
            and not isinstance(expected_size, bool)
            and artifact.size_bytes == expected_size
        )

    @staticmethod
    def _artifact_size_binding_verified(
        artifact: TrajectoryArtifact | None,
        expected_size: Any,
    ) -> bool:
        return bool(
            artifact
            and isinstance(expected_size, int)
            and not isinstance(expected_size, bool)
            and artifact.size_bytes == expected_size
        )

    @staticmethod
    def _json_artifact_belongs_to_tenant(
        artifact: TrajectoryArtifact,
        tenant_id: str,
    ) -> bool:
        try:
            data = json.loads(artifact.text())
        except (json.JSONDecodeError, TrajectoryStoreError):
            return True
        if not isinstance(data, dict):
            return True
        return data.get("tenant_id") in (None, tenant_id)

    @staticmethod
    def _jsonl_export_belongs_to_tenant(
        artifact: TrajectoryArtifact,
        tenant_id: str,
    ) -> bool:
        for line in artifact.text().splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            metadata = data.get("metadata")
            if (
                isinstance(metadata, dict)
                and metadata.get("tenant_id") not in (None, tenant_id)
            ):
                return False
        return True

    def _meta_relative_path(self, tenant_id: str) -> str:
        tenant = require_tenant_id(tenant_id)
        return f"tenants/{tenant}/trajectory_metadata.json"

    def _artifact_relative_path(
        self,
        tenant_id: str,
        directory: str,
        filename: str,
    ) -> str:
        tenant = require_tenant_id(tenant_id)
        return f"tenants/{tenant}/{directory}/{filename}"

    def _artifact_directory_path(
        self,
        tenant_id: str,
        directory: str,
    ) -> Path:
        tenant = require_tenant_id(tenant_id)
        root = (
            Path(self._backend.root)
            if self._backend.kind == "local"
            and getattr(self._backend, "root", None) is not None
            else self._base_dir
        )
        return root / "tenants" / tenant / directory

    def _list_artifact_paths(
        self,
        *,
        tenant_id: str,
        directory: str,
    ) -> list[str]:
        tenant = require_tenant_id(tenant_id)
        prefix = f"tenants/{tenant}/{directory}"
        try:
            paths = self._backend.list_prefix(prefix)
        except StateBackendError as exc:
            raise TrajectoryStoreError(
                "Trajectory artifacts could not be listed"
            ) from exc
        return sorted(paths, reverse=True)
