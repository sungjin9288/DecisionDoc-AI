"""Read and bind a Report Quality pilot pack to its current local files."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_pilot_receipt import (  # noqa: E402
    RECEIPT_SCHEMA_VERSION,
    parse_pilot_export_receipt,
    pilot_export_receipt_sha256,
    validate_pilot_export_receipt,
)
from app.services.report_quality_pilot_package import (  # noqa: E402
    NO_EXTERNAL_ACTION_KEYS as PACKAGE_NO_EXTERNAL_ACTION_KEYS,
    PACKAGE_REPORT_TYPE,
    PACKAGE_SCHEMA_VERSION,
)


SOURCE_MANIFEST_NAME = "SOURCE_MANIFEST.json"
SOURCE_RECEIPT_NAME = "SOURCE_EXPORT_RECEIPT.json"
SOURCE_PACKAGE_MANIFEST_NAME = "SOURCE_PACKAGE_MANIFEST.json"
SOURCE_MANIFEST_REPORT_TYPE = "report_quality_pilot_source_manifest"
SOURCE_MANIFEST_SCHEMA = "decisiondoc_report_quality_pilot_source_manifest.v3"
PREVIOUS_SOURCE_MANIFEST_SCHEMA = "decisiondoc_report_quality_pilot_source_manifest.v2"
LEGACY_SOURCE_MANIFEST_SCHEMA = "decisiondoc_report_quality_pilot_source_manifest.v1"
PACK_BINDING_SCHEMA = "decisiondoc_report_quality_pilot_pack_binding.v1"
ARTIFACT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
NO_EXTERNAL_ACTION_KEYS = (
    "external_dataset_upload_started",
    "provider_fine_tune_api_called",
    "provider_job_created",
    "training_execution_started",
    "model_promotion_started",
)


@dataclass(frozen=True)
class DraftSnapshot:
    artifact_id: str
    path: Path
    sha256: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class PilotPackSnapshot:
    pack_dir: Path
    drafts: tuple[DraftSnapshot, ...]
    source_manifest_path: Path | None = None
    source_jsonl_path: Path | None = None
    source_manifest_sha256: str | None = None
    source_jsonl_sha256: str | None = None
    tenant_id: str | None = None

    @property
    def source_order_applied(self) -> bool:
        return self.source_manifest_path is not None

    def binding(self) -> dict[str, Any]:
        source_manifest = None
        if self.source_manifest_path is not None:
            source_manifest = {
                "path": str(self.source_manifest_path),
                "sha256": self.source_manifest_sha256,
                "source_jsonl_sha256": self.source_jsonl_sha256,
                "tenant_id": self.tenant_id,
            }
        return {
            "schema_version": PACK_BINDING_SCHEMA,
            "pack_dir": str(self.pack_dir),
            "source_manifest": source_manifest,
            "artifacts": [
                {
                    "artifact_id": draft.artifact_id,
                    "draft_sha256": draft.sha256,
                }
                for draft in self.drafts
            ],
        }


def _read_json_snapshot(path: Path) -> tuple[dict[str, Any], str]:
    content = path.read_bytes()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: JSON file must be UTF-8") from exc
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return payload, hashlib.sha256(content).hexdigest()


def _artifact_id(payload: dict[str, Any], path: Path) -> str:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    if not ARTIFACT_ID_PATTERN.fullmatch(artifact_id):
        raise ValueError(f"{path}: artifact_id must be safe for a local filename")
    expected_name = f"{artifact_id}.json"
    if path.name != expected_name:
        raise ValueError(f"{path}: filename must match artifact_id ({expected_name})")
    return artifact_id


def _load_drafts(drafts_dir: Path) -> dict[str, DraftSnapshot]:
    draft_paths = sorted(drafts_dir.glob("*.json"))
    if not draft_paths:
        raise ValueError(f"no draft JSON files found: {drafts_dir}")

    drafts: dict[str, DraftSnapshot] = {}
    for path in draft_paths:
        if path.is_symlink():
            raise ValueError(f"{path}: symlink drafts are not allowed")
        payload, sha256 = _read_json_snapshot(path)
        artifact_id = _artifact_id(payload, path)
        if artifact_id in drafts:
            raise ValueError(f"duplicate artifact_id found: {artifact_id}")
        drafts[artifact_id] = DraftSnapshot(
            artifact_id=artifact_id,
            path=path,
            sha256=sha256,
            payload=payload,
        )
    return drafts


def _source_artifact_ids(
    pack_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> list[str]:
    if manifest.get("report_type") != SOURCE_MANIFEST_REPORT_TYPE:
        raise ValueError(f"{manifest_path}: unsupported report_type")
    schema_version = manifest.get("schema_version")
    supported_schemas = {
        SOURCE_MANIFEST_SCHEMA,
        PREVIOUS_SOURCE_MANIFEST_SCHEMA,
        LEGACY_SOURCE_MANIFEST_SCHEMA,
    }
    if schema_version not in supported_schemas:
        raise ValueError(f"{manifest_path}: unsupported source manifest schema_version")
    if manifest.get("batch_id") != pack_dir.name:
        raise ValueError(f"{manifest_path}: batch_id does not match the pilot pack directory")
    source = manifest.get("source")
    if not isinstance(source, dict):
        raise ValueError(f"{manifest_path}: source must be an object")
    artifact_ids = source.get("artifact_ids")
    if not isinstance(artifact_ids, list) or not artifact_ids:
        raise ValueError(f"{manifest_path}: source.artifact_ids must be a non-empty list")
    if any(not isinstance(value, str) or not ARTIFACT_ID_PATTERN.fullmatch(value) for value in artifact_ids):
        raise ValueError(f"{manifest_path}: source.artifact_ids contains an unsafe artifact_id")
    if len(set(artifact_ids)) != len(artifact_ids):
        raise ValueError(f"{manifest_path}: source.artifact_ids must be unique")
    if source.get("artifact_count") != len(artifact_ids):
        raise ValueError(f"{manifest_path}: source.artifact_count does not match artifact_ids")
    if schema_version == SOURCE_MANIFEST_SCHEMA:
        if not isinstance(source.get("size_bytes"), int) or source["size_bytes"] < 1:
            raise ValueError(f"{manifest_path}: source.size_bytes must be a positive integer")
    if source.get("format") != "jsonl" or source.get("order_preserved") is not True:
        raise ValueError(f"{manifest_path}: source format and order_preserved contract are invalid")
    package = source.get("package")
    if package is not None:
        if not isinstance(package, dict):
            raise ValueError(f"{manifest_path}: source.package must be an object")
        if package.get("path") != source.get("path"):
            raise ValueError(f"{manifest_path}: source.package.path must match source.path")
        if package.get("schema_version") != PACKAGE_SCHEMA_VERSION:
            raise ValueError(f"{manifest_path}: source.package.schema_version is unsupported")
        for field in ("sha256", "manifest_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(package.get(field) or "")):
                raise ValueError(f"{manifest_path}: source.package.{field} must be a lowercase SHA-256 digest")
        source_sha256 = str(source.get("sha256") or "")
        expected_prefix = source_sha256[:12]
        if package.get("jsonl_entry") != f"report_quality_pilot_artifacts_{expected_prefix}.jsonl":
            raise ValueError(f"{manifest_path}: source.package.jsonl_entry is invalid")
        if package.get("receipt_entry") != f"report_quality_pilot_receipt_{expected_prefix}.json":
            raise ValueError(f"{manifest_path}: source.package.receipt_entry is invalid")
    validation = manifest.get("validation")
    required_validation = [
        "all_valid",
        "all_ready_for_learning",
        "unique_artifact_ids",
        "single_tenant",
    ]
    if schema_version in {SOURCE_MANIFEST_SCHEMA, PREVIOUS_SOURCE_MANIFEST_SCHEMA}:
        required_validation.append("server_preview_verified")
    if not isinstance(validation, dict) or any(validation.get(key) is not True for key in required_validation):
        raise ValueError(f"{manifest_path}: source validation contract is incomplete")
    boundary = manifest.get("side_effect_boundary")
    if not isinstance(boundary, dict) or any(boundary.get(key) is not False for key in NO_EXTERNAL_ACTION_KEYS):
        raise ValueError(f"{manifest_path}: no-training side-effect boundary is invalid")
    if schema_version in {SOURCE_MANIFEST_SCHEMA, PREVIOUS_SOURCE_MANIFEST_SCHEMA}:
        receipt = manifest.get("receipt")
        if not isinstance(receipt, dict):
            raise ValueError(f"{manifest_path}: receipt must be an object")
        if receipt.get("path") != SOURCE_RECEIPT_NAME:
            raise ValueError(f"{manifest_path}: receipt.path must be {SOURCE_RECEIPT_NAME}")
        if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"{manifest_path}: receipt.schema_version is unsupported")
        if receipt.get("preview_verified") is not True:
            raise ValueError(f"{manifest_path}: receipt must prove server preview verification")
        if not re.fullmatch(r"[0-9a-f]{64}", str(receipt.get("sha256") or "")):
            raise ValueError(f"{manifest_path}: receipt.sha256 must be a lowercase SHA-256 digest")
        if schema_version == SOURCE_MANIFEST_SCHEMA and (
            not isinstance(receipt.get("size_bytes"), int) or receipt["size_bytes"] < 1
        ):
            raise ValueError(f"{manifest_path}: receipt.size_bytes must be a positive integer")
        if isinstance(package, dict) and package.get("request_id") != receipt.get("request_id"):
            raise ValueError(f"{manifest_path}: source.package.request_id must match receipt.request_id")
        if schema_version == SOURCE_MANIFEST_SCHEMA and isinstance(package, dict):
            if package.get("manifest_path") != SOURCE_PACKAGE_MANIFEST_NAME:
                raise ValueError(
                    f"{manifest_path}: source.package.manifest_path must be "
                    f"{SOURCE_PACKAGE_MANIFEST_NAME}"
                )
    return artifact_ids


def _validate_source_package_manifest(
    *,
    pack_dir: Path,
    source_manifest: dict[str, Any],
    receipt_size_bytes: int,
) -> None:
    if source_manifest.get("schema_version") != SOURCE_MANIFEST_SCHEMA:
        return
    source = source_manifest["source"]
    package = source.get("package")
    if not isinstance(package, dict):
        return

    package_manifest_path = pack_dir / SOURCE_PACKAGE_MANIFEST_NAME
    if package_manifest_path.is_symlink() or not package_manifest_path.is_file():
        raise ValueError(
            f"{package_manifest_path}: source package manifest must be a regular file"
        )
    package_manifest, manifest_sha256 = _read_json_snapshot(package_manifest_path)
    if manifest_sha256 != package["manifest_sha256"]:
        raise ValueError(
            f"{package_manifest_path}: SHA-256 does not match source manifest"
        )

    receipt = source_manifest["receipt"]
    expected_fields = {
        "report_type": PACKAGE_REPORT_TYPE,
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "tenant_id": source["tenant_id"],
        "request_id": receipt["request_id"],
        "artifact_count": source["artifact_count"],
        "ordered_artifact_ids": source["artifact_ids"],
        "export_sha256": source["sha256"],
        "external_action_boundary": {
            key: False for key in PACKAGE_NO_EXTERNAL_ACTION_KEYS
        },
    }
    for field, expected in expected_fields.items():
        if package_manifest.get(field) != expected:
            raise ValueError(
                f"{package_manifest_path}: {field} does not match source provenance"
            )

    expected_entries = [
        {
            "path": package["jsonl_entry"],
            "sha256": source["sha256"],
            "size_bytes": source["size_bytes"],
            "media_type": "application/x-ndjson",
        },
        {
            "path": package["receipt_entry"],
            "sha256": receipt["sha256"],
            "size_bytes": receipt_size_bytes,
            "media_type": "application/json",
        },
    ]
    if package_manifest.get("entries") != expected_entries:
        raise ValueError(
            f"{package_manifest_path}: entries do not match source provenance"
        )


def _ordered_source_drafts(
    *,
    manifest_path: Path,
    manifest: dict[str, Any],
    drafts: dict[str, DraftSnapshot],
) -> tuple[DraftSnapshot, ...]:
    artifact_ids = _source_artifact_ids(manifest_path.parent, manifest_path, manifest)
    missing = [artifact_id for artifact_id in artifact_ids if artifact_id not in drafts]
    untracked = sorted(set(drafts) - set(artifact_ids))
    if missing or untracked:
        details: list[str] = []
        if missing:
            details.append(f"missing drafts: {', '.join(missing)}")
        if untracked:
            details.append(f"untracked drafts: {', '.join(untracked)}")
        raise ValueError(f"{manifest_path}: source order does not match drafts ({'; '.join(details)})")
    return tuple(drafts[artifact_id] for artifact_id in artifact_ids)


def load_pilot_pack(pack_dir: Path) -> PilotPackSnapshot:
    resolved_pack_dir = pack_dir.expanduser().resolve()
    drafts_dir = resolved_pack_dir / "drafts"
    if not drafts_dir.is_dir():
        raise ValueError(f"drafts directory not found: {drafts_dir}")
    drafts = _load_drafts(drafts_dir)

    manifest_path = resolved_pack_dir / SOURCE_MANIFEST_NAME
    if manifest_path.is_symlink():
        raise ValueError(f"{manifest_path}: symlink source manifests are not allowed")
    if not manifest_path.is_file():
        return PilotPackSnapshot(
            pack_dir=resolved_pack_dir,
            drafts=tuple(drafts[artifact_id] for artifact_id in sorted(drafts)),
        )

    manifest, manifest_sha256 = _read_json_snapshot(manifest_path)
    ordered_drafts = _ordered_source_drafts(
        manifest_path=manifest_path,
        manifest=manifest,
        drafts=drafts,
    )
    source = manifest["source"]
    source_path_value = source.get("path")
    source_jsonl_path: Path | None = None
    if isinstance(source_path_value, str) and source_path_value.strip():
        source_jsonl_path = Path(source_path_value.strip()).expanduser()
        if not source_jsonl_path.is_absolute():
            source_jsonl_path = manifest_path.parent / source_jsonl_path
        source_jsonl_path = source_jsonl_path.resolve()
    tenant_id = str(source.get("tenant_id") or "").strip()
    source_jsonl_sha256 = str(source.get("sha256") or "").strip()
    if not tenant_id:
        raise ValueError(f"{manifest_path}: source.tenant_id must be non-empty")
    if not re.fullmatch(r"[0-9a-f]{64}", source_jsonl_sha256):
        raise ValueError(f"{manifest_path}: source.sha256 must be a lowercase SHA-256 digest")
    if manifest.get("schema_version") in {
        SOURCE_MANIFEST_SCHEMA,
        PREVIOUS_SOURCE_MANIFEST_SCHEMA,
    }:
        receipt_info = manifest["receipt"]
        receipt_path = resolved_pack_dir / SOURCE_RECEIPT_NAME
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise ValueError(f"{receipt_path}: source export receipt must be a regular file")
        receipt_bytes = receipt_path.read_bytes()
        if pilot_export_receipt_sha256(receipt_bytes) != receipt_info["sha256"]:
            raise ValueError(f"{receipt_path}: SHA-256 does not match source manifest")
        if (
            manifest.get("schema_version") == SOURCE_MANIFEST_SCHEMA
            and len(receipt_bytes) != receipt_info["size_bytes"]
        ):
            raise ValueError(f"{receipt_path}: size does not match source manifest")
        receipt = parse_pilot_export_receipt(receipt_bytes)
        validate_pilot_export_receipt(
            receipt,
            export_sha256=source_jsonl_sha256,
            artifact_ids=source["artifact_ids"],
            tenant_id=tenant_id,
        )
        if receipt.get("request_id") != receipt_info.get("request_id"):
            raise ValueError(f"{receipt_path}: request_id does not match source manifest")
        if receipt.get("issued_at") != receipt_info.get("issued_at"):
            raise ValueError(f"{receipt_path}: issued_at does not match source manifest")
        _validate_source_package_manifest(
            pack_dir=resolved_pack_dir,
            source_manifest=manifest,
            receipt_size_bytes=len(receipt_bytes),
        )
    for draft in ordered_drafts:
        workflow = draft.payload.get("workflow_reference")
        draft_tenant_id = str(workflow.get("tenant_id") or "").strip() if isinstance(workflow, dict) else ""
        if draft_tenant_id != tenant_id:
            raise ValueError(f"{draft.path}: tenant_id does not match source manifest")

    return PilotPackSnapshot(
        pack_dir=resolved_pack_dir,
        drafts=ordered_drafts,
        source_manifest_path=manifest_path,
        source_jsonl_path=source_jsonl_path,
        source_manifest_sha256=manifest_sha256,
        source_jsonl_sha256=source_jsonl_sha256,
        tenant_id=tenant_id,
    )


def require_current_pack_binding(snapshot: PilotPackSnapshot, binding: Any) -> None:
    if not isinstance(binding, dict):
        raise ValueError("source-bound pilot pack requires a pack_binding object")
    expected = snapshot.binding()
    if binding.get("schema_version") != PACK_BINDING_SCHEMA:
        raise ValueError("pack_binding.schema_version is unsupported")
    if binding.get("pack_dir") != expected["pack_dir"]:
        raise ValueError("pack_binding.pack_dir does not match the current pilot pack")
    if binding.get("source_manifest") != expected["source_manifest"]:
        raise ValueError("pack_binding.source_manifest is stale or does not match")

    artifacts = binding.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("pack_binding.artifacts must be a list")
    expected_artifacts = expected["artifacts"]
    if [item.get("artifact_id") for item in artifacts if isinstance(item, dict)] != [
        item["artifact_id"] for item in expected_artifacts
    ]:
        raise ValueError("pack_binding artifact order or membership does not match")
    if artifacts != expected_artifacts:
        raise ValueError("pack_binding draft SHA-256 values are stale or do not match")
