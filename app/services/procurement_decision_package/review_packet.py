"""Build and verify portable procurement review packets."""
from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from uuid import uuid4

from app.schemas import ProcurementDecisionRecord
from app.services.procurement_decision_package.artifact_evidence import (
    validate_local_package_artifacts,
)
from app.services.procurement_decision_package.constants import (
    DECISION_PACKAGE_NAME,
    EXCLUDED_ACTION_ORDER,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
    INCLUDED_ARTIFACT_ORDER,
)
from app.services.procurement_decision_package.json_helpers import (
    load_json_object_content,
)
from app.services.procurement_decision_package.package_builder import (
    build_decision_package_from_record,
    write_package_artifacts,
)


PACKET_SCHEMA_VERSION = "decisiondoc.procurement_review_packet.v1"
PACKET_MANIFEST_NAME = "packet_manifest.json"
PACKET_STATUS = "review_ready"
PACKET_MANIFEST_FIELD_ORDER = (
    "schema_version",
    "status",
    "source_updated_at",
    "package_id",
    "recommendation",
    "artifact_count",
    "artifacts",
    "excluded_actions",
    "authorization_boundary",
    "operational_approval",
)
PACKET_ARTIFACT_FIELD_ORDER = ("path", "size_bytes", "sha256")
ZIP_ENTRY_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MAX_PACKET_SIZE_BYTES = 64 * 1024 * 1024
MAX_ARTIFACT_SIZE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class ProjectProcurementReviewPacket:
    content: bytes
    manifest: dict[str, Any]
    verification: dict[str, Any]
    sha256: str


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _artifact_record(path: str, content: bytes) -> dict[str, object]:
    return {
        "path": path,
        "size_bytes": len(content),
        "sha256": _sha256(content),
    }


def _read_source_artifacts(source_dir: Path) -> dict[str, bytes]:
    validate_local_package_artifacts(source_dir)
    root = source_dir.resolve()
    artifacts: dict[str, bytes] = {}

    for artifact_name in INCLUDED_ARTIFACT_ORDER:
        path = root / artifact_name
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"packet source artifact is missing: {artifact_name}") from exc
        if path.is_symlink() or not resolved.is_relative_to(root) or not resolved.is_file():
            raise ValueError(
                "packet source artifact must be a regular file inside the source directory: "
                f"{artifact_name}"
            )
        content = resolved.read_bytes()
        if len(content) > MAX_ARTIFACT_SIZE_BYTES:
            raise ValueError(f"packet source artifact is too large: {artifact_name}")
        artifacts[artifact_name] = content

    return artifacts


def _load_package_document(content: bytes) -> dict[str, Any]:
    return load_json_object_content(
        content,
        label="packet decision_package.json",
    )


def _build_packet_manifest(
    artifacts: Mapping[str, bytes],
    package_doc: Mapping[str, Any],
) -> dict[str, Any]:
    package = package_doc["package"]
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "status": PACKET_STATUS,
        "source_updated_at": package_doc["updated_at"],
        "package_id": package["package_id"],
        "recommendation": package["recommendation"],
        "artifact_count": len(artifacts),
        "artifacts": [
            _artifact_record(path, artifacts[path])
            for path in INCLUDED_ARTIFACT_ORDER
        ],
        "excluded_actions": list(EXCLUDED_ACTION_ORDER),
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        "operational_approval": False,
    }


def _write_zip_entry(
    archive: zipfile.ZipFile,
    *,
    path: str,
    content: bytes,
) -> None:
    info = zipfile.ZipInfo(path, date_time=ZIP_ENTRY_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(
        info,
        content,
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def build_procurement_review_packet(
    source_dir: Path,
) -> tuple[bytes, dict[str, Any]]:
    """Return deterministic ZIP bytes and their embedded packet manifest."""
    artifacts = _read_source_artifacts(source_dir)
    package_doc = _load_package_document(artifacts[DECISION_PACKAGE_NAME])
    packet_manifest = _build_packet_manifest(artifacts, package_doc)
    packet_manifest_content = (
        json.dumps(packet_manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for artifact_name in INCLUDED_ARTIFACT_ORDER:
            _write_zip_entry(
                archive,
                path=artifact_name,
                content=artifacts[artifact_name],
            )
        _write_zip_entry(
            archive,
            path=PACKET_MANIFEST_NAME,
            content=packet_manifest_content,
        )
    return output.getvalue(), packet_manifest


def build_project_procurement_review_packet(
    record: ProcurementDecisionRecord,
    *,
    reviewer_owner: str,
) -> ProjectProcurementReviewPacket:
    """Build and verify a portable packet from a tenant-resolved project record."""
    reviewer = reviewer_owner.strip()
    if not reviewer:
        raise ValueError("reviewer_owner must not be blank")

    package_doc = build_decision_package_from_record(
        record,
        reviewer_owner=reviewer,
    )
    with tempfile.TemporaryDirectory(
        prefix="decisiondoc-project-procurement-packet-",
    ) as temp_dir:
        source_dir = Path(temp_dir)
        write_package_artifacts(package_doc, source_dir)
        content, manifest = build_procurement_review_packet(source_dir)

    verification = verify_procurement_review_packet(content)
    return ProjectProcurementReviewPacket(
        content=content,
        manifest=manifest,
        verification=verification,
        sha256=_sha256(content),
    )


def _require_packet_entry_names(archive: zipfile.ZipFile) -> list[str]:
    names = [info.filename for info in archive.infolist()]
    if len(names) != len(set(names)):
        raise ValueError("procurement review packet contains duplicate entry names")

    expected_names = [*INCLUDED_ARTIFACT_ORDER, PACKET_MANIFEST_NAME]
    if names != expected_names:
        raise ValueError(
            "procurement review packet entries must match the expected order"
        )
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or len(path.parts) != 1 or ".." in path.parts:
            raise ValueError(f"procurement review packet entry path is invalid: {name}")
    return names


def _read_packet_entries(archive: zipfile.ZipFile) -> dict[str, bytes]:
    total_size = 0
    entries: dict[str, bytes] = {}
    for info in archive.infolist():
        if info.is_dir():
            raise ValueError("procurement review packet must not contain directories")
        if info.file_size > MAX_ARTIFACT_SIZE_BYTES:
            raise ValueError(f"procurement review packet entry is too large: {info.filename}")
        total_size += info.file_size
        if total_size > MAX_PACKET_SIZE_BYTES:
            raise ValueError("procurement review packet expanded size is too large")
        entries[info.filename] = archive.read(info.filename)
    return entries


def _validate_packet_manifest(
    packet_manifest: Any,
    entries: Mapping[str, bytes],
) -> dict[str, Any]:
    if not isinstance(packet_manifest, dict):
        raise ValueError("procurement review packet manifest must be an object")
    if tuple(packet_manifest) != PACKET_MANIFEST_FIELD_ORDER:
        raise ValueError("procurement review packet manifest fields are invalid")
    if packet_manifest["schema_version"] != PACKET_SCHEMA_VERSION:
        raise ValueError("procurement review packet schema_version is invalid")
    if packet_manifest["status"] != PACKET_STATUS:
        raise ValueError("procurement review packet status must be review_ready")
    if packet_manifest["artifact_count"] != len(INCLUDED_ARTIFACT_ORDER):
        raise ValueError("procurement review packet artifact_count is invalid")
    if packet_manifest["excluded_actions"] != EXCLUDED_ACTION_ORDER:
        raise ValueError("procurement review packet excluded_actions are invalid")
    if packet_manifest["authorization_boundary"] != EXPLICIT_AUTHORIZATION_BOUNDARY:
        raise ValueError("procurement review packet authorization boundary is invalid")
    if packet_manifest["operational_approval"] is not False:
        raise ValueError("procurement review packet must not grant operational approval")

    records = packet_manifest["artifacts"]
    if not isinstance(records, list) or len(records) != len(INCLUDED_ARTIFACT_ORDER):
        raise ValueError("procurement review packet artifact records are invalid")
    for artifact_name, record in zip(INCLUDED_ARTIFACT_ORDER, records, strict=True):
        if not isinstance(record, dict) or tuple(record) != PACKET_ARTIFACT_FIELD_ORDER:
            raise ValueError("procurement review packet artifact record fields are invalid")
        if record["path"] != artifact_name:
            raise ValueError("procurement review packet artifact record order is invalid")
        content = entries[artifact_name]
        if record["size_bytes"] != len(content):
            raise ValueError(f"procurement review packet artifact size is invalid: {artifact_name}")
        if record["sha256"] != _sha256(content):
            raise ValueError(f"procurement review packet artifact SHA256 is invalid: {artifact_name}")
    return packet_manifest


def _validate_packet_artifacts(entries: Mapping[str, bytes]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="decisiondoc-procurement-packet-") as temp_dir:
        temp_path = Path(temp_dir)
        for artifact_name in INCLUDED_ARTIFACT_ORDER:
            (temp_path / artifact_name).write_bytes(entries[artifact_name])
        return validate_local_package_artifacts(temp_path)


def verify_procurement_review_packet(content: bytes) -> dict[str, Any]:
    """Validate archive membership, fingerprints, package semantics, and boundary."""
    if len(content) > MAX_PACKET_SIZE_BYTES:
        raise ValueError("procurement review packet is too large")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = _require_packet_entry_names(archive)
            entries = _read_packet_entries(archive)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid procurement review packet: {exc}") from exc

    packet_manifest = load_json_object_content(
        entries[PACKET_MANIFEST_NAME],
        label="procurement review packet manifest",
    )
    packet_manifest = _validate_packet_manifest(packet_manifest, entries)
    package = _validate_packet_artifacts(entries)

    if packet_manifest["package_id"] != package["package_id"]:
        raise ValueError("procurement review packet package_id is inconsistent")
    if packet_manifest["recommendation"] != package["recommendation"]:
        raise ValueError("procurement review packet recommendation is inconsistent")
    package_doc = _load_package_document(entries[DECISION_PACKAGE_NAME])
    if packet_manifest["source_updated_at"] != package_doc["updated_at"]:
        raise ValueError("procurement review packet source_updated_at is inconsistent")

    return {
        "schema_version": packet_manifest["schema_version"],
        "package_id": packet_manifest["package_id"],
        "recommendation": packet_manifest["recommendation"],
        "artifact_count": packet_manifest["artifact_count"],
        "entry_count": len(names),
        "authorization_boundary": packet_manifest["authorization_boundary"],
        "operational_approval": packet_manifest["operational_approval"],
        "packet_verified": True,
    }


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    try:
        with temp_path.open("wb") as file_obj:
            file_obj.write(content)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
