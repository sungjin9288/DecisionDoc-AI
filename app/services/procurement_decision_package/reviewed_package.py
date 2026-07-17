"""Build and verify procurement packages after reviewer completion."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any, Mapping

from app.services.procurement_decision_package.constants import (
    EXCLUDED_ACTION_ORDER,
    EXPLICIT_AUTHORIZATION_BOUNDARY,
)
from app.services.procurement_decision_package.json_helpers import (
    load_json_object_content,
)
from app.services.procurement_decision_package.review_packet import (
    MAX_PACKET_SIZE_BYTES,
    PACKET_SCHEMA_VERSION,
    _write_zip_entry,
    verify_procurement_review_packet,
)
from app.services.procurement_decision_package.review_receipt import (
    REVIEW_RECEIPT_COMPLETED,
    REVIEW_RECEIPT_SCHEMA_VERSION,
    validate_procurement_review_receipt,
)


REVIEWED_PACKAGE_SCHEMA_VERSION = "decisiondoc.procurement_reviewed_package.v1"
REVIEWED_PACKAGE_STATUS = "review_completed"
REVIEWED_PACKAGE_PACKET_NAME = "procurement_review_packet.zip"
REVIEWED_PACKAGE_RECEIPT_NAME = "procurement_review_receipt.json"
REVIEWED_PACKAGE_MANIFEST_NAME = "reviewed_package_manifest.json"
REVIEWED_PACKAGE_ENTRY_ORDER = (
    REVIEWED_PACKAGE_PACKET_NAME,
    REVIEWED_PACKAGE_RECEIPT_NAME,
    REVIEWED_PACKAGE_MANIFEST_NAME,
)
REVIEWED_PACKAGE_MANIFEST_FIELD_ORDER = (
    "schema_version",
    "status",
    "package_id",
    "recommendation",
    "reviewer",
    "decision",
    "reviewed_at",
    "source",
    "excluded_actions",
    "authorization_boundary",
    "operational_approval",
)
REVIEWED_PACKAGE_SOURCE_FIELD_ORDER = (
    "packet_sha256",
    "packet_size_bytes",
    "packet_schema_version",
    "receipt_sha256",
    "receipt_size_bytes",
    "receipt_schema_version",
)
MAX_RECEIPT_SIZE_BYTES = 1024 * 1024
MAX_REVIEWED_PACKAGE_SIZE_BYTES = (
    MAX_PACKET_SIZE_BYTES + MAX_RECEIPT_SIZE_BYTES + 128 * 1024
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _load_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    return load_json_object_content(content, label=label)


def _review_context(
    packet_content: bytes,
    receipt: Mapping[str, Any],
    receipt_content: bytes,
) -> dict[str, Any]:
    if len(receipt_content) > MAX_RECEIPT_SIZE_BYTES:
        raise ValueError("procurement review receipt is too large")

    receipt_doc = dict(receipt)
    stored_receipt = _load_json_object(
        receipt_content,
        label="procurement review receipt",
    )
    if tuple(stored_receipt) != tuple(receipt_doc) or stored_receipt != receipt_doc:
        raise ValueError("procurement review receipt content does not match the receipt")

    packet = verify_procurement_review_packet(packet_content)
    review = validate_procurement_review_receipt(receipt_doc, packet_content)
    if review["review_status"] != REVIEW_RECEIPT_COMPLETED:
        raise ValueError("reviewed package requires a completed procurement review receipt")

    return {
        "packet": packet,
        "review": review,
    }


def _build_manifest(
    packet_content: bytes,
    receipt_content: bytes,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    packet = context["packet"]
    review = context["review"]
    return {
        "schema_version": REVIEWED_PACKAGE_SCHEMA_VERSION,
        "status": REVIEWED_PACKAGE_STATUS,
        "package_id": review["package_id"],
        "recommendation": review["recommendation"],
        "reviewer": review["reviewer"],
        "decision": review["decision"],
        "reviewed_at": review["reviewed_at"],
        "source": {
            "packet_sha256": _sha256(packet_content),
            "packet_size_bytes": len(packet_content),
            "packet_schema_version": packet["schema_version"],
            "receipt_sha256": _sha256(receipt_content),
            "receipt_size_bytes": len(receipt_content),
            "receipt_schema_version": REVIEW_RECEIPT_SCHEMA_VERSION,
        },
        "excluded_actions": list(EXCLUDED_ACTION_ORDER),
        "authorization_boundary": EXPLICIT_AUTHORIZATION_BOUNDARY,
        "operational_approval": False,
    }


def build_procurement_reviewed_package(
    packet_content: bytes,
    receipt: Mapping[str, Any],
    *,
    receipt_content: bytes,
) -> tuple[bytes, dict[str, Any]]:
    """Return a deterministic audit envelope for a completed review."""
    context = _review_context(packet_content, receipt, receipt_content)
    manifest = _build_manifest(packet_content, receipt_content, context)
    manifest_content = (
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        _write_zip_entry(
            archive,
            path=REVIEWED_PACKAGE_PACKET_NAME,
            content=packet_content,
        )
        _write_zip_entry(
            archive,
            path=REVIEWED_PACKAGE_RECEIPT_NAME,
            content=receipt_content,
        )
        _write_zip_entry(
            archive,
            path=REVIEWED_PACKAGE_MANIFEST_NAME,
            content=manifest_content,
        )
    return output.getvalue(), manifest


def _read_entries(content: bytes) -> dict[str, bytes]:
    if len(content) > MAX_REVIEWED_PACKAGE_SIZE_BYTES:
        raise ValueError("procurement reviewed package is too large")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if names != list(REVIEWED_PACKAGE_ENTRY_ORDER):
                raise ValueError(
                    "procurement reviewed package entries must match the expected order"
                )
            if any(info.is_dir() for info in infos):
                raise ValueError("procurement reviewed package must not contain directories")
            if infos[0].file_size > MAX_PACKET_SIZE_BYTES:
                raise ValueError("procurement reviewed package packet entry is too large")
            if infos[1].file_size > MAX_RECEIPT_SIZE_BYTES:
                raise ValueError("procurement reviewed package receipt entry is too large")
            return {name: archive.read(name) for name in names}
    except zipfile.BadZipFile as exc:
        raise ValueError(f"invalid procurement reviewed package: {exc}") from exc


def _validate_manifest(
    manifest: Any,
    *,
    packet_content: bytes,
    receipt_content: bytes,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("procurement reviewed package manifest must be an object")
    if tuple(manifest) != REVIEWED_PACKAGE_MANIFEST_FIELD_ORDER:
        raise ValueError("procurement reviewed package manifest fields are invalid")
    if manifest["schema_version"] != REVIEWED_PACKAGE_SCHEMA_VERSION:
        raise ValueError("procurement reviewed package schema_version is invalid")
    if manifest["status"] != REVIEWED_PACKAGE_STATUS:
        raise ValueError("procurement reviewed package status is invalid")

    source = manifest["source"]
    if not isinstance(source, dict) or tuple(source) != REVIEWED_PACKAGE_SOURCE_FIELD_ORDER:
        raise ValueError("procurement reviewed package source fields are invalid")
    packet = context["packet"]
    review = context["review"]
    expected_source = {
        "packet_sha256": _sha256(packet_content),
        "packet_size_bytes": len(packet_content),
        "packet_schema_version": PACKET_SCHEMA_VERSION,
        "receipt_sha256": _sha256(receipt_content),
        "receipt_size_bytes": len(receipt_content),
        "receipt_schema_version": REVIEW_RECEIPT_SCHEMA_VERSION,
    }
    for field, expected in expected_source.items():
        if source[field] != expected:
            raise ValueError(f"procurement reviewed package source.{field} is invalid")

    expected_review = {
        "package_id": review["package_id"],
        "recommendation": review["recommendation"],
        "reviewer": review["reviewer"],
        "decision": review["decision"],
        "reviewed_at": review["reviewed_at"],
    }
    for field, expected in expected_review.items():
        if manifest[field] != expected:
            raise ValueError(f"procurement reviewed package {field} is inconsistent")
    if packet["package_id"] != review["package_id"]:
        raise ValueError("procurement reviewed package packet identity is inconsistent")
    if manifest["excluded_actions"] != EXCLUDED_ACTION_ORDER:
        raise ValueError("procurement reviewed package excluded_actions are invalid")
    if manifest["authorization_boundary"] != EXPLICIT_AUTHORIZATION_BOUNDARY:
        raise ValueError("procurement reviewed package authorization boundary is invalid")
    if manifest["operational_approval"] is not False:
        raise ValueError("procurement reviewed package must not grant operational approval")
    return manifest


def verify_procurement_reviewed_package(content: bytes) -> dict[str, Any]:
    """Verify outer membership, source hashes, completed review, and authority."""
    entries = _read_entries(content)
    packet_content = entries[REVIEWED_PACKAGE_PACKET_NAME]
    receipt_content = entries[REVIEWED_PACKAGE_RECEIPT_NAME]
    receipt = _load_json_object(
        receipt_content,
        label="procurement review receipt",
    )
    context = _review_context(packet_content, receipt, receipt_content)
    manifest = _load_json_object(
        entries[REVIEWED_PACKAGE_MANIFEST_NAME],
        label="procurement reviewed package manifest",
    )
    manifest = _validate_manifest(
        manifest,
        packet_content=packet_content,
        receipt_content=receipt_content,
        context=context,
    )
    return {
        "schema_version": manifest["schema_version"],
        "reviewed_package_status": manifest["status"],
        "package_id": manifest["package_id"],
        "recommendation": manifest["recommendation"],
        "reviewer": manifest["reviewer"],
        "decision": manifest["decision"],
        "reviewed_at": manifest["reviewed_at"],
        "entry_count": len(entries),
        "authorization_boundary": manifest["authorization_boundary"],
        "operational_approval": manifest["operational_approval"],
        "package_verified": True,
    }
