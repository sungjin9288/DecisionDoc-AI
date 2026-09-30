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

from app.services.procurement_decision_package.applicability import (
    PACKAGE_SCHEMA_PURPOSE_V2, V3_ARTIFACT_ORDER, artifact_order, validate_applicability,
)

from app.schemas import ProcurementDecisionRecord
from app.schemas.procurement_binding import ProcurementSourceBinding
from app.services.procurement_source_binding import require_binding_matches_record
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
PACKET_SCHEMA_VERSION_V2 = "decisiondoc.procurement_review_packet.v2"
PACKET_SCHEMA_VERSION_V3 = "decisiondoc.procurement_review_packet.v3"
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
PACKET_V2_MANIFEST_FIELD_ORDER = (*PACKET_MANIFEST_FIELD_ORDER, "source_binding")
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

    for artifact_name in artifact_order(_load_package_document((root / DECISION_PACKAGE_NAME).read_bytes())):
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
            for path in artifact_order(package_doc)
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
    *, source_binding: ProcurementSourceBinding | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Return deterministic ZIP bytes and their embedded packet manifest."""
    artifacts = _read_source_artifacts(source_dir)
    package_doc = _load_package_document(artifacts[DECISION_PACKAGE_NAME])
    packet_manifest = _build_packet_manifest(artifacts, package_doc)
    has_applicability = package_doc["schema_purpose"] == PACKAGE_SCHEMA_PURPOSE_V2
    if has_applicability and source_binding is None:
        raise ValueError("requirement applicability requires source_binding")
    if source_binding is not None:
        source_binding = ProcurementSourceBinding.model_validate(source_binding.model_dump(mode="json"))
        _validate_binding_package(source_binding, package_doc)
        packet_manifest["schema_version"] = PACKET_SCHEMA_VERSION_V2
        packet_manifest["source_binding"] = source_binding.model_dump(mode="json")
        if has_applicability:
            validate_applicability(package_doc["package"]["requirement_applicability"], source_binding)
            packet_manifest["schema_version"] = PACKET_SCHEMA_VERSION_V3
    packet_manifest_content = (
        json.dumps(packet_manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for artifact_name in artifact_order(package_doc):
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
    source_binding: ProcurementSourceBinding | None = None,
    requirement_applicability: dict | None = None,
) -> ProjectProcurementReviewPacket:
    """Build and verify a portable packet from a tenant-resolved project record."""
    reviewer = reviewer_owner.strip()
    if not reviewer:
        raise ValueError("reviewer_owner must not be blank")
    if source_binding is not None:
        source_binding = require_binding_matches_record(source_binding, record)

    package_doc = build_decision_package_from_record(
        record,
        reviewer_owner=reviewer,
        source_binding=source_binding,
        requirement_applicability=requirement_applicability,
    )
    with tempfile.TemporaryDirectory(
        prefix="decisiondoc-project-procurement-packet-",
    ) as temp_dir:
        source_dir = Path(temp_dir)
        write_package_artifacts(package_doc, source_dir)
        content, manifest = build_procurement_review_packet(source_dir, source_binding=source_binding)

    verification = verify_procurement_review_packet(content)
    return ProjectProcurementReviewPacket(
        content=content,
        manifest=manifest,
        verification=verification,
        sha256=_sha256(content),
    )


def _require_packet_entry_names(archive: zipfile.ZipFile, *, version: str = PACKET_SCHEMA_VERSION) -> list[str]:
    names = [info.filename for info in archive.infolist()]
    if len(names) != len(set(names)):
        raise ValueError("procurement review packet contains duplicate entry names")

    expected_names = [*_packet_artifact_order(version), PACKET_MANIFEST_NAME]
    if names != expected_names:
        raise ValueError(
            "procurement review packet entries must match the expected order"
        )
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or len(path.parts) != 1 or ".." in path.parts:
            raise ValueError(f"procurement review packet entry path is invalid: {name}")
    return names


def _packet_artifact_order(version: str):
    if not isinstance(version, str):
        raise ValueError("procurement review packet schema_version is invalid")
    if version == PACKET_SCHEMA_VERSION_V3:
        return V3_ARTIFACT_ORDER
    if version in {PACKET_SCHEMA_VERSION, PACKET_SCHEMA_VERSION_V2}:
        return INCLUDED_ARTIFACT_ORDER
    raise ValueError("procurement review packet schema_version is invalid")


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
    version = packet_manifest.get("schema_version")
    order = _packet_artifact_order(version)
    fields = PACKET_MANIFEST_FIELD_ORDER if version == PACKET_SCHEMA_VERSION else PACKET_V2_MANIFEST_FIELD_ORDER
    if tuple(packet_manifest) != fields:
        raise ValueError("procurement review packet manifest fields are invalid")
    if version not in {PACKET_SCHEMA_VERSION, PACKET_SCHEMA_VERSION_V2, PACKET_SCHEMA_VERSION_V3}:
        raise ValueError("procurement review packet schema_version is invalid")
    if packet_manifest["status"] != PACKET_STATUS:
        raise ValueError("procurement review packet status must be review_ready")
    if type(packet_manifest["artifact_count"]) is not int or packet_manifest["artifact_count"] != len(order):
        raise ValueError("procurement review packet artifact_count is invalid")
    if packet_manifest["excluded_actions"] != EXCLUDED_ACTION_ORDER:
        raise ValueError("procurement review packet excluded_actions are invalid")
    if packet_manifest["authorization_boundary"] != EXPLICIT_AUTHORIZATION_BOUNDARY:
        raise ValueError("procurement review packet authorization boundary is invalid")
    if packet_manifest["operational_approval"] is not False:
        raise ValueError("procurement review packet must not grant operational approval")

    records = packet_manifest["artifacts"]
    if not isinstance(records, list) or len(records) != len(order):
        raise ValueError("procurement review packet artifact records are invalid")
    for artifact_name, record in zip(order, records, strict=True):
        if not isinstance(record, dict) or tuple(record) != PACKET_ARTIFACT_FIELD_ORDER:
            raise ValueError("procurement review packet artifact record fields are invalid")
        if record["path"] != artifact_name:
            raise ValueError("procurement review packet artifact record order is invalid")
        content = entries[artifact_name]
        if type(record["size_bytes"]) is not int or record["size_bytes"] != len(content):
            raise ValueError(f"procurement review packet artifact size is invalid: {artifact_name}")
        if record["sha256"] != _sha256(content):
            raise ValueError(f"procurement review packet artifact SHA256 is invalid: {artifact_name}")
    return packet_manifest


def _validate_packet_artifacts(entries: Mapping[str, bytes], *, version: str = PACKET_SCHEMA_VERSION) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="decisiondoc-procurement-packet-") as temp_dir:
        temp_path = Path(temp_dir)
        for artifact_name in _packet_artifact_order(version):
            (temp_path / artifact_name).write_bytes(entries[artifact_name])
        return validate_local_package_artifacts(temp_path)


def _validate_binding_package(binding: ProcurementSourceBinding, package_doc: Mapping[str, Any]) -> None:
    package = package_doc["package"]
    if package["package_id"] != f"{binding.decision_id}-package":
        raise ValueError("procurement packet decision identity mismatch")
    if package_doc["scenario_id"] != f"procurement-record-{binding.project_id}":
        raise ValueError("procurement packet project identity mismatch")
    if package_doc["updated_at"] != binding.source_updated_at:
        raise ValueError("procurement packet source timestamp mismatch")
    opportunity = package["opportunity_ref"]
    if (opportunity["opportunity_id"], opportunity["source_type"]) != (binding.source_id, binding.source_kind):
        raise ValueError("procurement packet source identity mismatch")


def verify_procurement_review_packet(
    content: bytes, *, expected_tenant_id: str | None = None, expected_project_id: str | None = None,
) -> dict[str, Any]:
    """Validate archive membership, fingerprints, package semantics, and boundary."""
    if len(content) > MAX_PACKET_SIZE_BYTES:
        raise ValueError("procurement review packet is too large")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if len(archive.namelist()) != len(set(archive.namelist())):
                raise ValueError("procurement review packet contains duplicate entry names")
            entries = _read_packet_entries(archive)
            if PACKET_MANIFEST_NAME not in entries:
                raise ValueError("procurement review packet manifest is missing")
            manifest = load_json_object_content(entries[PACKET_MANIFEST_NAME], label="packet manifest")
            names = _require_packet_entry_names(archive, version=manifest.get("schema_version"))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid procurement review packet: {exc}") from exc

    packet_manifest = load_json_object_content(
        entries[PACKET_MANIFEST_NAME],
        label="procurement review packet manifest",
    )
    packet_manifest = _validate_packet_manifest(packet_manifest, entries)
    package = _validate_packet_artifacts(entries, version=packet_manifest["schema_version"])

    if packet_manifest["package_id"] != package["package_id"]:
        raise ValueError("procurement review packet package_id is inconsistent")
    if packet_manifest["recommendation"] != package["recommendation"]:
        raise ValueError("procurement review packet recommendation is inconsistent")
    package_doc = _load_package_document(entries[DECISION_PACKAGE_NAME])
    if (packet_manifest["schema_version"] == PACKET_SCHEMA_VERSION_V3) != (
        package_doc["schema_purpose"] == PACKAGE_SCHEMA_PURPOSE_V2
    ):
        raise ValueError("procurement packet applicability version downgrade/mismatch")
    if packet_manifest["source_updated_at"] != package_doc["updated_at"]:
        raise ValueError("procurement review packet source_updated_at is inconsistent")

    result = {
        "schema_version": packet_manifest["schema_version"],
        "package_id": packet_manifest["package_id"],
        "recommendation": packet_manifest["recommendation"],
        "artifact_count": packet_manifest["artifact_count"],
        "entry_count": len(names),
        "authorization_boundary": packet_manifest["authorization_boundary"],
        "operational_approval": packet_manifest["operational_approval"],
        "packet_verified": True,
    }
    if packet_manifest["schema_version"] in {PACKET_SCHEMA_VERSION_V2, PACKET_SCHEMA_VERSION_V3}:
        binding = ProcurementSourceBinding.model_validate(packet_manifest["source_binding"])
        _validate_binding_package(binding, package_doc)
        if packet_manifest["schema_version"] == PACKET_SCHEMA_VERSION_V3:
            validate_applicability(package["requirement_applicability"], binding)
        if expected_tenant_id is not None and binding.tenant_id != expected_tenant_id:
            raise ValueError("procurement packet tenant mismatch")
        if expected_project_id is not None and binding.project_id != expected_project_id:
            raise ValueError("procurement packet project mismatch")
        result.update(source_binding=binding.model_dump(mode="json"), source_bytes_verified=False)
    return result


def verify_bound_procurement_packet(
    content: bytes, *, expected_tenant_id: str, expected_project_id: str,
) -> dict[str, Any] | None:
    """Enforce bound semantics and reject disguised downgrades in legacy packets."""
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return None
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if PACKET_MANIFEST_NAME not in archive.namelist():
            return None
        info = archive.getinfo(PACKET_MANIFEST_NAME)
        if info.file_size > MAX_ARTIFACT_SIZE_BYTES:
            raise ValueError("procurement packet manifest is too large")
        manifest = load_json_object_content(archive.read(info), label="procurement packet manifest")
    if manifest.get("schema_version") == PACKET_SCHEMA_VERSION and "source_binding" not in manifest:
        verify_procurement_review_packet(content)
        return None
    return verify_procurement_review_packet(content, expected_tenant_id=expected_tenant_id,
                                            expected_project_id=expected_project_id)


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
