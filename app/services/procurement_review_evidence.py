"""Semantic validation for persisted procurement review evidence."""
from __future__ import annotations

import io
import json
import zipfile
from typing import TYPE_CHECKING, Any

from app.services.procurement_decision_package.review_receipt import (
    validate_procurement_review_receipt,
)
from app.services.procurement_decision_package.reviewed_package import (
    REVIEWED_PACKAGE_RECEIPT_NAME,
    verify_procurement_reviewed_package,
)

if TYPE_CHECKING:
    from app.storage.procurement_review_store import ProcurementReviewRecord


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate persisted review evidence field: {key}")
        result[key] = value
    return result


def validate_persisted_procurement_review_packet(
    record: ProcurementReviewRecord,
    packet_content: bytes,
) -> None:
    """Require the persisted receipt and record to match the verified packet."""
    verification = validate_procurement_review_receipt(
        record.receipt,
        packet_content,
    )
    expected = {
        "review_status": record.review_status,
        "packet_sha256": record.packet_sha256,
        "package_id": record.package_id,
        "recommendation": record.recommendation,
        "reviewer": record.reviewer,
        "decision": record.decision,
        "reviewed_at": record.reviewed_at,
        "operational_approval": record.operational_approval,
    }
    if any(verification[field] != value for field, value in expected.items()):
        raise ValueError("persisted procurement review packet binding is inconsistent")


def validate_persisted_procurement_reviewed_package(
    record: ProcurementReviewRecord,
    reviewed_package_content: bytes,
) -> None:
    """Require package semantics and embedded receipt to match the record."""
    verification = verify_procurement_reviewed_package(
        reviewed_package_content,
    )
    expected = {
        "package_id": record.package_id,
        "recommendation": record.recommendation,
        "reviewer": record.reviewer,
        "decision": record.decision,
        "reviewed_at": record.reviewed_at,
        "operational_approval": record.operational_approval,
    }
    if any(verification[field] != value for field, value in expected.items()):
        raise ValueError("persisted procurement reviewed package binding is inconsistent")

    try:
        with zipfile.ZipFile(io.BytesIO(reviewed_package_content)) as archive:
            receipt_content = archive.read(REVIEWED_PACKAGE_RECEIPT_NAME)
        embedded_receipt = json.loads(
            receipt_content,
            object_pairs_hook=_unique_object,
        )
    except (
        KeyError,
        UnicodeError,
        json.JSONDecodeError,
        zipfile.BadZipFile,
    ) as exc:
        raise ValueError(
            "persisted procurement reviewed package receipt is invalid"
        ) from exc
    if (
        not isinstance(embedded_receipt, dict)
        or tuple(embedded_receipt) != tuple(record.receipt)
        or embedded_receipt != record.receipt
    ):
        raise ValueError(
            "persisted procurement reviewed package receipt is inconsistent"
        )
