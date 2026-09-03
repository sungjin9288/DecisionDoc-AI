"""Closed persisted contracts for generated-document review handoffs."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal, Mapping

from app.services.generation_export_packet import AUTHORITY_FALSE, FORMAT_ORDER
from app.tenant import require_tenant_id


RECORD_SCHEMA = "decisiondoc.generated_document_review_handoff.v1"
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class GeneratedDocumentReviewRecordError(ValueError):
    """Raised when a generated-document review record is not trustworthy."""


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
    review_status: Literal["pending"]
    review_only: bool
    packet_persisted: bool
    human_review_completed: bool
    operational_approval: bool
    authority: dict[str, bool]

    def to_public_dict(self) -> dict[str, Any]:
        return {
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


RECORD_FIELDS = set(GeneratedDocumentReviewRecord.__dataclass_fields__)


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


def validate_record(record: GeneratedDocumentReviewRecord) -> None:
    if record.schema_version != RECORD_SCHEMA:
        raise ValueError("generated document review schema is invalid")
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
    if record.review_status != "pending":
        raise ValueError("review_status is invalid")
    if record.review_only is not True or record.packet_persisted is not True:
        raise ValueError("review persistence boundary is invalid")
    if record.human_review_completed is not False or record.operational_approval is not False:
        raise ValueError("review authority state is invalid")
    if record.authority != AUTHORITY_FALSE or any(
        value is not False for value in record.authority.values()
    ):
        raise ValueError("authority is invalid")


def record_from_dict(payload: Mapping[str, Any]) -> GeneratedDocumentReviewRecord:
    if set(payload) != RECORD_FIELDS:
        raise ValueError("generated document review fields are invalid")
    record = GeneratedDocumentReviewRecord(**payload)
    validate_record(record)
    return record


def serialize_record(record: GeneratedDocumentReviewRecord) -> str:
    validate_record(record)
    return (
        json.dumps(asdict(record), ensure_ascii=False, separators=(",", ":"), sort_keys=True)
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
