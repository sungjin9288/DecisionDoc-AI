"""Closed persisted contracts for generated-document review handoffs."""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

from app.services.generation_export_packet import (
    AUTHORITY_FALSE,
    FORMAT_ORDER,
    MAX_PACKET_SIZE_BYTES,
    PERSISTED_PACKET_SCHEMA,
    PERSISTED_PACKET_SCHEMA_V2,
    _validate_zip_metadata,
    _write_zip_entry,
    verify_generation_export_packet,
)
from app.tenant import require_tenant_id


RECORD_SCHEMA = "decisiondoc.generated_document_review_handoff.v1"
COMPLETED_RECORD_SCHEMA = "decisiondoc.generated_document_review_handoff.v2"
REVIEW_RECEIPT_SCHEMA = "decisiondoc.generated_document_review_receipt.v1"
REVIEWED_PACKAGE_SCHEMA = "decisiondoc.generated_document_reviewed_package.v1"
REVIEWED_PACKAGE_PACKET_PATH = "generated_document_review_packet.zip"
REVIEWED_PACKAGE_RECEIPT_PATH = "generated_document_review_receipt.json"
REVIEWED_PACKAGE_MANIFEST_PATH = "reviewed_package_manifest.json"
REVIEWED_PACKAGE_ENTRY_ORDER = (
    REVIEWED_PACKAGE_PACKET_PATH,
    REVIEWED_PACKAGE_RECEIPT_PATH,
    REVIEWED_PACKAGE_MANIFEST_PATH,
)
MAX_REVIEW_RECEIPT_SIZE_BYTES = 1024 * 1024
MAX_REVIEWED_PACKAGE_MANIFEST_SIZE_BYTES = 1024 * 1024
MAX_REVIEWED_PACKAGE_SIZE_BYTES = MAX_PACKET_SIZE_BYTES + 2 * 1024 * 1024
REVIEW_DECISIONS = {"accepted", "changes_requested", "rejected"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class GeneratedDocumentReviewRecordError(ValueError):
    """Raised when a generated-document review record is not trustworthy."""


class GeneratedDocumentReviewedPackageError(ValueError):
    """Raised when a completed review package is not trustworthy."""


@dataclass(frozen=True)
class GeneratedDocumentReviewRecord:
    schema_version: str
    tenant_id: str
    project_id: str
    project_document_id: str
    request_id: str
    bundle_id: str
    title: str
    document_source_sha256: str
    packet_sha256: str
    packet_size_bytes: int
    manifest_sha256: str
    artifact_count: int
    formats: list[str]
    prepared_at: str
    creator_assignment: dict[str, str]
    reviewer_assignment: dict[str, str]
    review_status: Literal["pending", "completed"]
    review_only: bool
    packet_persisted: bool
    human_review_completed: bool
    operational_approval: bool
    authority: dict[str, bool]
    completion_operation_id: str | None = None
    review_decision: Literal["accepted", "changes_requested", "rejected"] | None = None
    review_rationale: str | None = None
    reviewed_at: str | None = None
    completion_assignment: dict[str, str] | None = None
    completion_receipt_sha256: str | None = None
    reviewed_package_sha256: str | None = None
    reviewed_package_size_bytes: int | None = None

    def to_public_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "project_document_id": self.project_document_id,
            "request_id": self.request_id,
            "bundle_id": self.bundle_id,
            "title": self.title,
            "document_source_sha256": self.document_source_sha256,
            "packet_sha256": self.packet_sha256,
            "packet_size_bytes": self.packet_size_bytes,
            "manifest_sha256": self.manifest_sha256,
            "artifact_count": self.artifact_count,
            "formats": list(self.formats),
            "prepared_at": self.prepared_at,
            "creator": {
                "username": self.creator_assignment["username"],
                "role": self.creator_assignment["role"],
            },
            "reviewer": {
                "username": self.reviewer_assignment["username"],
                "role": self.reviewer_assignment["role"],
            },
            "review_status": self.review_status,
            "review_only": self.review_only,
            "packet_persisted": self.packet_persisted,
            "human_review_completed": self.human_review_completed,
            "operational_approval": self.operational_approval,
            "authority": dict(self.authority),
        }
        if self.review_status == "completed":
            result.update(
                review_decision=self.review_decision,
                reviewed_at=self.reviewed_at,
                completion_receipt_sha256=self.completion_receipt_sha256,
                reviewed_package_sha256=self.reviewed_package_sha256,
                reviewed_package_size_bytes=self.reviewed_package_size_bytes,
            )
        return result


BASE_RECORD_FIELDS = {
    field
    for field in GeneratedDocumentReviewRecord.__dataclass_fields__
    if field
    not in {
        "completion_operation_id",
        "review_decision",
        "review_rationale",
        "reviewed_at",
        "completion_assignment",
        "completion_receipt_sha256",
        "reviewed_package_sha256",
        "reviewed_package_size_bytes",
    }
}
COMPLETED_RECORD_FIELDS = set(GeneratedDocumentReviewRecord.__dataclass_fields__)


def safe_segment(value: str, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{field} is invalid")
    return value


def require_sha256(value: str, *, field: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field} is invalid")
    return value


def _require_identity(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{field} is invalid")
    return value


def _require_assignment(value: object, *, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"user_id", "username", "role"}:
        raise ValueError(f"{field} is invalid")
    assignment = {
        key: _require_identity(value[key], field=f"{field}.{key}")
        for key in ("user_id", "username", "role")
    }
    if assignment["role"] not in {"admin", "member"}:
        raise ValueError(f"{field}.role is invalid")
    return assignment


def _require_rationale(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 4000
        or any(
            ord(character) < 32 and character not in {"\n", "\r", "\t"}
            for character in value
        )
        or any(ord(character) == 127 for character in value)
    ):
        raise ValueError("review_rationale is invalid")
    return value


def _require_uuid4(value: object, *, field: str) -> str:
    candidate = _require_identity(value, field=field)
    try:
        parsed = uuid.UUID(candidate)
    except ValueError as exc:
        raise ValueError(f"{field} is invalid") from exc
    if parsed.version != 4 or str(parsed) != candidate:
        raise ValueError(f"{field} is invalid")
    return candidate


def _validate_common_record(record: GeneratedDocumentReviewRecord) -> None:
    require_tenant_id(record.tenant_id)
    safe_segment(record.project_id, field="project_id")
    safe_segment(record.project_document_id, field="project_document_id")
    _require_identity(record.request_id, field="request_id")
    _require_identity(record.bundle_id, field="bundle_id")
    _require_identity(record.title, field="title")
    require_sha256(record.document_source_sha256, field="document_source_sha256")
    require_sha256(record.packet_sha256, field="packet_sha256")
    require_sha256(record.manifest_sha256, field="manifest_sha256")
    if (
        not isinstance(record.packet_size_bytes, int)
        or isinstance(record.packet_size_bytes, bool)
        or record.packet_size_bytes <= 0
    ):
        raise ValueError("packet_size_bytes is invalid")
    if (
        not isinstance(record.artifact_count, int)
        or isinstance(record.artifact_count, bool)
        or record.artifact_count <= 0
    ):
        raise ValueError("artifact_count is invalid")
    if (
        not isinstance(record.formats, list)
        or not record.formats
        or record.formats != [fmt for fmt in FORMAT_ORDER if fmt in record.formats]
        or len(record.formats) != len(set(record.formats))
        or len(record.formats) != record.artifact_count
    ):
        raise ValueError("formats are invalid")
    _require_identity(record.prepared_at, field="prepared_at")
    _require_assignment(record.creator_assignment, field="creator_assignment")
    _require_assignment(record.reviewer_assignment, field="reviewer_assignment")
    if record.review_only is not True or record.packet_persisted is not True:
        raise ValueError("review persistence boundary is invalid")
    if record.operational_approval is not False:
        raise ValueError("review authority state is invalid")
    if record.authority != AUTHORITY_FALSE or any(
        value is not False for value in record.authority.values()
    ):
        raise ValueError("authority is invalid")


def validate_record(record: GeneratedDocumentReviewRecord) -> None:
    _validate_common_record(record)
    completion_values = (
        record.completion_operation_id,
        record.review_decision,
        record.review_rationale,
        record.reviewed_at,
        record.completion_assignment,
        record.completion_receipt_sha256,
        record.reviewed_package_sha256,
        record.reviewed_package_size_bytes,
    )
    if record.schema_version == RECORD_SCHEMA:
        if (
            record.review_status != "pending"
            or record.human_review_completed is not False
        ):
            raise ValueError("review_status is invalid")
        if any(value is not None for value in completion_values):
            raise ValueError("pending review completion fields are invalid")
        return
    if record.schema_version != COMPLETED_RECORD_SCHEMA:
        raise ValueError("generated document review schema is invalid")
    if record.review_status != "completed" or record.human_review_completed is not True:
        raise ValueError("review_status is invalid")
    _require_uuid4(record.completion_operation_id, field="completion_operation_id")
    if record.review_decision not in REVIEW_DECISIONS:
        raise ValueError("review_decision is invalid")
    _require_rationale(record.review_rationale)
    _require_identity(record.reviewed_at, field="reviewed_at")
    completion_assignment = _require_assignment(
        record.completion_assignment,
        field="completion_assignment",
    )
    if completion_assignment != record.reviewer_assignment:
        raise ValueError("completion_assignment is invalid")
    require_sha256(
        record.completion_receipt_sha256,
        field="completion_receipt_sha256",
    )
    require_sha256(record.reviewed_package_sha256, field="reviewed_package_sha256")
    if (
        not isinstance(record.reviewed_package_size_bytes, int)
        or isinstance(record.reviewed_package_size_bytes, bool)
        or not 0 < record.reviewed_package_size_bytes <= MAX_REVIEWED_PACKAGE_SIZE_BYTES
    ):
        raise ValueError("reviewed_package_size_bytes is invalid")


def record_from_dict(payload: Mapping[str, Any]) -> GeneratedDocumentReviewRecord:
    schema_version = payload.get("schema_version")
    expected_fields = (
        BASE_RECORD_FIELDS
        if schema_version == RECORD_SCHEMA
        else COMPLETED_RECORD_FIELDS
        if schema_version == COMPLETED_RECORD_SCHEMA
        else set()
    )
    if set(payload) != expected_fields:
        raise ValueError("generated document review fields are invalid")
    record = GeneratedDocumentReviewRecord(**payload)
    validate_record(record)
    return record


def serialize_record(record: GeneratedDocumentReviewRecord) -> str:
    validate_record(record)
    payload = asdict(record)
    if record.schema_version == RECORD_SCHEMA:
        payload = {
            key: value for key, value in payload.items() if key in BASE_RECORD_FIELDS
        }
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    )


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GeneratedDocumentReviewRecordError(
                "duplicate key in generated document review record"
            )
        result[key] = value
    return result


def parse_record(raw: str) -> GeneratedDocumentReviewRecord:
    try:
        payload = json.loads(raw, object_pairs_hook=unique_object)
    except (json.JSONDecodeError, TypeError, GeneratedDocumentReviewRecordError) as exc:
        raise GeneratedDocumentReviewRecordError(
            "generated document review record is invalid"
        ) from exc
    if not isinstance(payload, dict):
        raise GeneratedDocumentReviewRecordError(
            "generated document review record is invalid"
        )
    try:
        record = record_from_dict(payload)
    except (TypeError, ValueError) as exc:
        raise GeneratedDocumentReviewRecordError(
            "generated document review record is invalid"
        ) from exc
    if serialize_record(record) != raw:
        raise GeneratedDocumentReviewRecordError(
            "generated document review record is not canonical"
        )
    return record


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(payload), ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        + "\n"
    ).encode("utf-8")


def _load_canonical_json(content: bytes, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8"), object_pairs_hook=unique_object)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        GeneratedDocumentReviewRecordError,
    ) as exc:
        raise GeneratedDocumentReviewedPackageError(f"{label} is invalid") from exc
    if not isinstance(payload, dict) or _canonical_json_bytes(payload) != content:
        raise GeneratedDocumentReviewedPackageError(f"{label} is not canonical")
    return payload


def _build_reviewed_zip(
    packet_content: bytes,
    receipt_content: bytes,
    manifest_content: bytes,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_zip_entry(archive, REVIEWED_PACKAGE_PACKET_PATH, packet_content)
        _write_zip_entry(archive, REVIEWED_PACKAGE_RECEIPT_PATH, receipt_content)
        _write_zip_entry(archive, REVIEWED_PACKAGE_MANIFEST_PATH, manifest_content)
    return output.getvalue()


def _completion_receipt(
    record: GeneratedDocumentReviewRecord,
    *,
    completion_assignment: Mapping[str, str],
    operation_id: str,
    decision: str,
    rationale: str,
    reviewed_at: str,
    source_procurement_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document = {
        "bundle_id": record.bundle_id,
        "document_source_sha256": record.document_source_sha256,
        "project_document_id": record.project_document_id,
        "project_id": record.project_id,
        "request_id": record.request_id,
        "tenant_id": record.tenant_id,
        "title": record.title,
    }
    if source_procurement_binding is not None:
        document["source_procurement_binding"] = source_procurement_binding
    return {
        "authority": dict(AUTHORITY_FALSE),
        "completion_operation_id": operation_id,
        "document": document,
        "human_review_completed": True,
        "operational_approval": False,
        "packet_sha256": record.packet_sha256,
        "packet": {
            "artifact_count": record.artifact_count,
            "formats": list(record.formats),
            "manifest_sha256": record.manifest_sha256,
            "packet_sha256": record.packet_sha256,
            "packet_size_bytes": record.packet_size_bytes,
        },
        "prepared_at": record.prepared_at,
        "review_decision": decision,
        "review_rationale": rationale,
        "reviewed_at": reviewed_at,
        "reviewer_assignment": dict(completion_assignment),
        "schema_version": REVIEW_RECEIPT_SCHEMA,
    }


def build_generated_document_reviewed_package(
    record: GeneratedDocumentReviewRecord,
    packet_content: bytes,
    *,
    completion_assignment: Mapping[str, str],
    operation_id: str,
    decision: str,
    rationale: str,
    reviewed_at: str,
) -> tuple[bytes, dict[str, Any], str]:
    """Build one deterministic, self-contained package for a completed review."""
    if record.review_status != "pending" or record.schema_version != RECORD_SCHEMA:
        raise ValueError("generated document review is not pending")
    assignment = _require_assignment(
        completion_assignment, field="completion_assignment"
    )
    if assignment != record.reviewer_assignment:
        raise ValueError("completion_assignment is invalid")
    _require_uuid4(operation_id, field="completion_operation_id")
    if decision not in REVIEW_DECISIONS:
        raise ValueError("review_decision is invalid")
    _require_rationale(rationale)
    _require_identity(reviewed_at, field="reviewed_at")
    if (
        len(packet_content) != record.packet_size_bytes
        or _sha256(packet_content) != record.packet_sha256
    ):
        raise ValueError("generated document review packet binding is invalid")
    packet_verification = verify_generation_export_packet(packet_content)
    if packet_verification["schema"] not in {
        PERSISTED_PACKET_SCHEMA,
        PERSISTED_PACKET_SCHEMA_V2,
    }:
        raise ValueError("generated document review packet schema is invalid")

    receipt = _completion_receipt(
        record,
        completion_assignment=assignment,
        operation_id=operation_id,
        decision=decision,
        rationale=rationale,
        reviewed_at=reviewed_at,
        source_procurement_binding=packet_verification.get(
            "source_procurement_binding"
        ),
    )
    receipt_content = _canonical_json_bytes(receipt)
    if len(receipt_content) > MAX_REVIEW_RECEIPT_SIZE_BYTES:
        raise ValueError("generated document review receipt is too large")
    receipt_sha256 = _sha256(receipt_content)
    manifest = {
        "authority": dict(AUTHORITY_FALSE),
        "entries": [
            {
                "path": REVIEWED_PACKAGE_PACKET_PATH,
                "sha256": record.packet_sha256,
                "size_bytes": len(packet_content),
            },
            {
                "path": REVIEWED_PACKAGE_RECEIPT_PATH,
                "sha256": receipt_sha256,
                "size_bytes": len(receipt_content),
            },
        ],
        "human_review_completed": True,
        "operational_approval": False,
        "review_status": "completed",
        "schema_version": REVIEWED_PACKAGE_SCHEMA,
    }
    manifest_content = _canonical_json_bytes(manifest)
    content = _build_reviewed_zip(packet_content, receipt_content, manifest_content)
    if len(content) > MAX_REVIEWED_PACKAGE_SIZE_BYTES:
        raise ValueError("generated document reviewed package is too large")
    return content, receipt, receipt_sha256


def verify_generated_document_reviewed_package(
    content: bytes,
    *,
    expected_record: GeneratedDocumentReviewRecord | None = None,
    expected_packet_content: bytes | None = None,
) -> dict[str, Any]:
    """Verify a completed review package from bytes alone, with optional store bindings."""
    if (
        not isinstance(content, bytes)
        or not content
        or len(content) > MAX_REVIEWED_PACKAGE_SIZE_BYTES
    ):
        raise GeneratedDocumentReviewedPackageError("reviewed package size is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as archive:
            if archive.comment:
                raise GeneratedDocumentReviewedPackageError(
                    "reviewed package ZIP comment is invalid"
                )
            members = archive.infolist()
            names = [member.filename for member in members]
            if names != list(REVIEWED_PACKAGE_ENTRY_ORDER):
                raise GeneratedDocumentReviewedPackageError(
                    "reviewed package entries are invalid"
                )
            for member in members:
                _validate_zip_metadata(member)
            if members[0].file_size > MAX_PACKET_SIZE_BYTES:
                raise GeneratedDocumentReviewedPackageError(
                    "reviewed package packet is too large"
                )
            if members[1].file_size > MAX_REVIEW_RECEIPT_SIZE_BYTES:
                raise GeneratedDocumentReviewedPackageError(
                    "reviewed package receipt is too large"
                )
            if members[2].file_size > MAX_REVIEWED_PACKAGE_MANIFEST_SIZE_BYTES:
                raise GeneratedDocumentReviewedPackageError(
                    "reviewed package manifest is too large"
                )
            if sum(member.file_size for member in members) > MAX_REVIEWED_PACKAGE_SIZE_BYTES:
                raise GeneratedDocumentReviewedPackageError(
                    "reviewed package uncompressed size is invalid"
                )
            entries = {name: archive.read(name) for name in names}
    except GeneratedDocumentReviewedPackageError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError, ValueError) as exc:
        raise GeneratedDocumentReviewedPackageError(
            "reviewed package ZIP cannot be read"
        ) from exc

    packet_content = entries[REVIEWED_PACKAGE_PACKET_PATH]
    receipt_content = entries[REVIEWED_PACKAGE_RECEIPT_PATH]
    manifest_content = entries[REVIEWED_PACKAGE_MANIFEST_PATH]
    try:
        packet = verify_generation_export_packet(packet_content)
    except ValueError as exc:
        raise GeneratedDocumentReviewedPackageError(
            "reviewed package packet is invalid"
        ) from exc
    if packet["schema"] not in {
        PERSISTED_PACKET_SCHEMA,
        PERSISTED_PACKET_SCHEMA_V2,
    }:
        raise GeneratedDocumentReviewedPackageError(
            "reviewed package packet schema is invalid"
        )
    receipt = _load_canonical_json(receipt_content, label="review receipt")
    manifest = _load_canonical_json(manifest_content, label="reviewed package manifest")
    expected_receipt_fields = {
        "authority",
        "completion_operation_id",
        "document",
        "human_review_completed",
        "operational_approval",
        "packet_sha256",
        "packet",
        "prepared_at",
        "review_decision",
        "review_rationale",
        "reviewed_at",
        "reviewer_assignment",
        "schema_version",
    }
    if (
        set(receipt) != expected_receipt_fields
        or receipt.get("schema_version") != REVIEW_RECEIPT_SCHEMA
    ):
        raise GeneratedDocumentReviewedPackageError("review receipt fields are invalid")
    try:
        _require_uuid4(
            receipt.get("completion_operation_id"), field="completion_operation_id"
        )
        _require_identity(receipt.get("prepared_at"), field="prepared_at")
        _require_identity(receipt.get("reviewed_at"), field="reviewed_at")
        _require_rationale(receipt.get("review_rationale"))
        reviewer_assignment = _require_assignment(
            receipt.get("reviewer_assignment"), field="reviewer_assignment"
        )
    except ValueError as exc:
        raise GeneratedDocumentReviewedPackageError(
            "review receipt values are invalid"
        ) from exc
    if (
        not isinstance(receipt.get("review_decision"), str)
        or receipt["review_decision"] not in REVIEW_DECISIONS
    ):
        raise GeneratedDocumentReviewedPackageError(
            "review receipt decision is invalid"
        )
    if (
        receipt.get("human_review_completed") is not True
        or receipt.get("operational_approval") is not False
        or receipt.get("authority") != AUTHORITY_FALSE
        or any(value is not False for value in receipt["authority"].values())
    ):
        raise GeneratedDocumentReviewedPackageError(
            "review receipt authority is invalid"
        )
    source = packet["source"]
    expected_document = {
        "bundle_id": source["bundle_id"],
        "document_source_sha256": source["document_source_sha256"],
        "project_document_id": source["project_document_id"],
        "project_id": source["project_id"],
        "request_id": source["request_id"],
        "tenant_id": source["tenant_id"],
        "title": source["title"],
    }
    if packet.get("source_procurement_binding") is not None:
        expected_document["source_procurement_binding"] = packet[
            "source_procurement_binding"
        ]
    expected_packet = {
        "artifact_count": packet["artifact_count"],
        "formats": packet["formats"],
        "manifest_sha256": packet["manifest_sha256"],
        "packet_sha256": packet["packet_sha256"],
        "packet_size_bytes": len(packet_content),
    }
    if (
        receipt.get("packet_sha256") != packet["packet_sha256"]
        or receipt.get("document") != expected_document
        or not isinstance(receipt.get("packet"), dict)
        or _canonical_json_bytes(receipt["packet"])
        != _canonical_json_bytes(expected_packet)
    ):
        raise GeneratedDocumentReviewedPackageError(
            "review receipt source binding is invalid"
        )
    receipt_sha256 = _sha256(receipt_content)
    expected_manifest = {
        "authority": dict(AUTHORITY_FALSE),
        "entries": [
            {
                "path": REVIEWED_PACKAGE_PACKET_PATH,
                "sha256": packet["packet_sha256"],
                "size_bytes": len(packet_content),
            },
            {
                "path": REVIEWED_PACKAGE_RECEIPT_PATH,
                "sha256": receipt_sha256,
                "size_bytes": len(receipt_content),
            },
        ],
        "human_review_completed": True,
        "operational_approval": False,
        "review_status": "completed",
        "schema_version": REVIEWED_PACKAGE_SCHEMA,
    }
    if manifest_content != _canonical_json_bytes(expected_manifest):
        raise GeneratedDocumentReviewedPackageError(
            "reviewed package manifest is invalid"
        )

    rebuilt = _build_reviewed_zip(packet_content, receipt_content, manifest_content)
    if rebuilt != content:
        raise GeneratedDocumentReviewedPackageError(
            "reviewed package bytes are not canonical"
        )
    if (
        expected_packet_content is not None
        and packet_content != expected_packet_content
    ):
        raise GeneratedDocumentReviewedPackageError(
            "reviewed package packet does not match expected bytes"
        )
    package_sha256 = _sha256(content)
    if expected_record is not None:
        validate_record(expected_record)
        if (
            expected_record.review_status != "completed"
            or expected_record.tenant_id != source["tenant_id"]
            or expected_record.project_id != source["project_id"]
            or expected_record.project_document_id != source["project_document_id"]
            or expected_record.request_id != source["request_id"]
            or expected_record.bundle_id != source["bundle_id"]
            or expected_record.title != source["title"]
            or expected_record.document_source_sha256
            != source["document_source_sha256"]
            or expected_record.packet_sha256 != packet["packet_sha256"]
            or expected_record.packet_size_bytes != len(packet_content)
            or expected_record.manifest_sha256 != packet["manifest_sha256"]
            or expected_record.artifact_count != packet["artifact_count"]
            or expected_record.formats != packet["formats"]
            or expected_record.prepared_at != receipt["prepared_at"]
            or expected_record.completion_operation_id
            != receipt["completion_operation_id"]
            or expected_record.review_decision != receipt["review_decision"]
            or expected_record.review_rationale != receipt["review_rationale"]
            or expected_record.reviewed_at != receipt["reviewed_at"]
            or expected_record.completion_assignment != reviewer_assignment
            or expected_record.completion_receipt_sha256 != receipt_sha256
            or expected_record.reviewed_package_sha256 != package_sha256
            or expected_record.reviewed_package_size_bytes != len(content)
        ):
            raise GeneratedDocumentReviewedPackageError(
                "reviewed package record binding is invalid"
            )
    return {
        "manifest": manifest,
        "packet": packet,
        "receipt": receipt,
        "completion_receipt_sha256": receipt_sha256,
        "reviewed_package_sha256": package_sha256,
        "reviewed_package_size_bytes": len(content),
        "verified": True,
    }
