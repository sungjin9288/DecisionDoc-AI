"""Load the current human-review evidence for a Report Quality pilot pack."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.create_report_quality_review_sheet import (
    REVIEW_MANIFEST_REPORT_TYPE,
    REVIEW_MANIFEST_SCHEMA,
    build_report_quality_review_state,
)
from scripts.report_quality_pilot_pack_provenance import PilotPackSnapshot
from scripts.validate_report_quality_review_decision_receipt import (
    validate_review_decision_receipt,
)


REVIEW_MANIFEST_NAME = "human_review_manifest.json"
DECISION_RECEIPT_REPORT_TYPE = "report_quality_review_decision_application_receipt"
DECISION_RECEIPT_PREFIX = "review_decision_application_receipt"


class UnsafeReviewEvidenceError(ValueError):
    """Raised when review evidence crosses a local path safety boundary."""


@dataclass(frozen=True)
class ReviewEvidence:
    path: Path
    content: bytes
    payload: dict[str, Any]
    sha256: str

    def summary(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class DecisionReceiptEvidence(ReviewEvidence):
    validation: dict[str, Any]

    def summary(self) -> dict[str, Any]:
        return {
            **super().summary(),
            "artifact_count": self.validation["artifact_count"],
        }


def _read_json_object(path: Path, *, label: str) -> tuple[bytes, dict[str, Any]]:
    content = path.read_bytes()
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must contain valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} root must be an object")
    return content, payload


def load_current_review_manifest(snapshot: PilotPackSnapshot) -> ReviewEvidence:
    manifest_path = snapshot.pack_dir / REVIEW_MANIFEST_NAME
    if manifest_path.is_symlink():
        raise UnsafeReviewEvidenceError("symlink human review manifests are not allowed")
    if not manifest_path.is_file():
        raise ValueError("current human review manifest is required for --require-ready")

    content, payload = _read_json_object(manifest_path, label="human review manifest")
    if payload.get("report_type") != REVIEW_MANIFEST_REPORT_TYPE:
        raise ValueError("human review manifest report_type is invalid")
    if payload.get("schema_version") != REVIEW_MANIFEST_SCHEMA:
        raise ValueError("human review manifest schema_version is invalid")
    if payload.get("pack_binding") != snapshot.binding():
        raise ValueError("human review manifest does not match the current pack binding")

    expected_rows, expected_counts = build_report_quality_review_state(snapshot)
    manifest_rows = payload.get("artifacts")
    if not isinstance(manifest_rows, list) or len(manifest_rows) != len(expected_rows):
        raise ValueError("human review manifest artifact membership is invalid")
    for manifest_row, expected_row in zip(manifest_rows, expected_rows, strict=True):
        if not isinstance(manifest_row, dict) or any(
            manifest_row.get(key) != value
            for key, value in expected_row.items()
        ):
            raise ValueError("human review manifest artifact state does not match current drafts")

    counts = payload.get("counts")
    if not isinstance(counts, dict) or any(
        counts.get(key) != value
        for key, value in expected_counts.items()
    ):
        raise ValueError("human review manifest counts do not match current drafts")

    return ReviewEvidence(
        path=manifest_path,
        content=content,
        payload=payload,
        sha256=hashlib.sha256(content).hexdigest(),
    )


def load_current_decision_receipt(snapshot: PilotPackSnapshot) -> DecisionReceiptEvidence:
    candidates: list[tuple[str, str, DecisionReceiptEvidence]] = []
    for receipt_path in sorted(snapshot.pack_dir.glob("*.json")):
        if receipt_path.is_symlink():
            if receipt_path.name.startswith(DECISION_RECEIPT_PREFIX):
                raise UnsafeReviewEvidenceError(
                    "symlink review decision receipts are not allowed"
                )
            continue
        try:
            content, payload = _read_json_object(
                receipt_path,
                label="review decision receipt",
            )
            if payload.get("report_type") != DECISION_RECEIPT_REPORT_TYPE:
                continue
            validation = validate_review_decision_receipt(receipt_path)
        except (OSError, ValueError):
            continue

        sha256 = hashlib.sha256(content).hexdigest()
        if sha256 != validation["receipt_sha256"]:
            continue
        operation = payload.get("operation")
        transitions = payload.get("artifacts")
        if not isinstance(operation, dict) or operation.get("require_ready") is not True:
            continue
        if not isinstance(transitions, list) or not transitions:
            continue
        if any(
            not isinstance(item, dict)
            or item.get("decision") != "accepted"
            or item.get("ready_for_learning") is not True
            for item in transitions
        ):
            continue

        evidence = DecisionReceiptEvidence(
            path=receipt_path,
            content=content,
            payload=payload,
            sha256=sha256,
            validation=validation,
        )
        candidates.append(
            (
                str(payload.get("created_at") or ""),
                receipt_path.name,
                evidence,
            )
        )

    if not candidates:
        raise ValueError(
            "current accepted review decision receipt is required for --require-ready"
        )
    return max(candidates, key=lambda item: (item[0], item[1]))[2]
