"""Tenant-scoped persistence for packet-bound procurement reviews."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from app.storage.state_backend import StateBackend, get_state_backend


REVIEW_RECORD_SCHEMA_VERSION = "decisiondoc.procurement_project_review_record.v1"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProcurementReviewRecord:
    schema_version: str
    tenant_id: str
    project_id: str
    packet_sha256: str
    packet_size_bytes: int
    package_id: str
    recommendation: str
    reviewer: str
    review_status: Literal["pending", "completed"]
    decision: Literal["accepted", "changes_requested", "rejected"] | None
    prepared_at: str
    reviewed_at: str | None
    reviewed_package_sha256: str | None
    reviewed_package_size_bytes: int | None
    operational_approval: bool
    receipt: dict[str, Any]

    def to_public_dict(self) -> dict[str, Any]:
        """Return reviewer-facing state without exposing storage paths."""
        return {
            key: value
            for key, value in asdict(self).items()
            if key not in {"tenant_id", "receipt"}
        }


class ProcurementReviewStore:
    """Persist original packets, review state, and completed review packages."""

    def __init__(
        self,
        base_dir: str = "data",
        *,
        backend: StateBackend | None = None,
    ) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._lock = threading.Lock()

    @staticmethod
    def _safe_segment(value: str, *, field: str) -> str:
        if not value or value in {".", ".."} or Path(value).name != value or "\\" in value:
            raise ValueError(f"{field} is invalid")
        return value

    @staticmethod
    def _require_sha256(value: str, *, field: str = "packet_sha256") -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError(f"{field} is invalid")
        return value

    def _review_prefix(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str | None = None,
    ) -> Path:
        project = self._safe_segment(project_id, field="project_id")
        prefix = self._tenant_review_prefix(tenant_id=tenant_id) / project
        if packet_sha256 is not None:
            prefix /= self._require_sha256(packet_sha256)
        return prefix

    def _tenant_review_prefix(self, *, tenant_id: str) -> Path:
        tenant = self._safe_segment(tenant_id, field="tenant_id")
        return Path("tenants") / tenant / "procurement_reviews"

    def _relative_path(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
        filename: str,
    ) -> str:
        return str(
            self._review_prefix(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            / filename
        )

    @staticmethod
    def _sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _from_dict(payload: Mapping[str, Any]) -> ProcurementReviewRecord:
        record = ProcurementReviewRecord(
            schema_version=payload["schema_version"],
            tenant_id=payload["tenant_id"],
            project_id=payload["project_id"],
            packet_sha256=payload["packet_sha256"],
            packet_size_bytes=payload["packet_size_bytes"],
            package_id=payload["package_id"],
            recommendation=payload["recommendation"],
            reviewer=payload["reviewer"],
            review_status=payload["review_status"],
            decision=payload["decision"],
            prepared_at=payload["prepared_at"],
            reviewed_at=payload["reviewed_at"],
            reviewed_package_sha256=payload["reviewed_package_sha256"],
            reviewed_package_size_bytes=payload["reviewed_package_size_bytes"],
            operational_approval=payload["operational_approval"],
            receipt=dict(payload["receipt"]),
        )
        ProcurementReviewStore._validate_record(record)
        return record

    @staticmethod
    def _validate_record(record: ProcurementReviewRecord) -> None:
        if record.schema_version != REVIEW_RECORD_SCHEMA_VERSION:
            raise ValueError("procurement review record schema_version is invalid")
        ProcurementReviewStore._require_sha256(record.packet_sha256)
        if record.packet_size_bytes <= 0:
            raise ValueError("procurement review record packet_size_bytes is invalid")
        if not record.project_id or not record.tenant_id or not record.prepared_at:
            raise ValueError("procurement review record identity is invalid")
        if not record.package_id or not record.recommendation or not record.reviewer:
            raise ValueError("procurement review record review context is invalid")
        if record.operational_approval is not False:
            raise ValueError("procurement review record must not grant operational approval")

        receipt = record.receipt
        expected_receipt_values = {
            "packet_sha256": record.packet_sha256,
            "packet_size_bytes": record.packet_size_bytes,
            "package_id": record.package_id,
            "recommendation": record.recommendation,
            "reviewer": record.reviewer,
            "status": record.review_status,
            "decision": record.decision,
            "reviewed_at": record.reviewed_at,
            "operational_approval": False,
        }
        if any(receipt.get(field) != expected for field, expected in expected_receipt_values.items()):
            raise ValueError("procurement review record receipt is inconsistent")

        if record.review_status == "pending":
            if any(
                value is not None
                for value in (
                    record.decision,
                    record.reviewed_at,
                    record.reviewed_package_sha256,
                    record.reviewed_package_size_bytes,
                )
            ):
                raise ValueError("pending procurement review record contains completion evidence")
            return

        if record.review_status != "completed":
            raise ValueError("procurement review record status is invalid")
        if record.decision not in {"accepted", "changes_requested", "rejected"}:
            raise ValueError("procurement review record decision is invalid")
        if not record.reviewed_at or record.reviewed_package_size_bytes is None:
            raise ValueError("completed procurement review record is incomplete")
        if record.reviewed_package_size_bytes <= 0:
            raise ValueError("procurement review record package size is invalid")
        ProcurementReviewStore._require_sha256(
            record.reviewed_package_sha256 or "",
            field="reviewed_package_sha256",
        )

    def _save_record(self, record: ProcurementReviewRecord) -> None:
        self._validate_record(record)
        self._backend.write_text(
            self._relative_path(
                tenant_id=record.tenant_id,
                project_id=record.project_id,
                packet_sha256=record.packet_sha256,
                filename="record.json",
            ),
            json.dumps(asdict(record), ensure_ascii=False, indent=2),
        )

    def prepare(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_content: bytes,
        receipt: Mapping[str, Any],
        prepared_at: str,
    ) -> tuple[ProcurementReviewRecord, bool]:
        """Create an idempotent pending review bound to exact packet bytes."""
        packet_sha256 = self._sha256(packet_content)
        pending_receipt = dict(receipt)
        record = ProcurementReviewRecord(
            schema_version=REVIEW_RECORD_SCHEMA_VERSION,
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
            packet_size_bytes=len(packet_content),
            package_id=pending_receipt.get("package_id", ""),
            recommendation=pending_receipt.get("recommendation", ""),
            reviewer=pending_receipt.get("reviewer", ""),
            review_status=pending_receipt.get("status", ""),
            decision=pending_receipt.get("decision"),
            prepared_at=prepared_at,
            reviewed_at=pending_receipt.get("reviewed_at"),
            reviewed_package_sha256=None,
            reviewed_package_size_bytes=None,
            operational_approval=False,
            receipt=pending_receipt,
        )
        self._validate_record(record)

        with self._lock:
            existing = self.get(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if existing is not None:
                stored_packet = self.read_packet(existing)
                if stored_packet != packet_content:
                    raise ValueError("stored procurement review packet content is inconsistent")
                return existing, False

            self._backend.write_bytes(
                self._relative_path(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    packet_sha256=packet_sha256,
                    filename="packet.zip",
                ),
                packet_content,
                content_type="application/zip",
            )
            self._save_record(record)
        return record, True

    def get(
        self,
        *,
        tenant_id: str,
        project_id: str,
        packet_sha256: str,
    ) -> ProcurementReviewRecord | None:
        raw = self._backend.read_text(
            self._relative_path(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
                filename="record.json",
            )
        )
        if raw is None:
            return None
        try:
            record = self._from_dict(json.loads(raw))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("stored procurement review record is invalid") from exc
        if record.tenant_id != tenant_id or record.project_id != project_id:
            raise ValueError("stored procurement review record identity is inconsistent")
        return record

    def list_by_project(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> list[ProcurementReviewRecord]:
        prefix = str(self._review_prefix(tenant_id=tenant_id, project_id=project_id))
        records: list[ProcurementReviewRecord] = []
        for path in self._backend.list_prefix(prefix):
            if not path.endswith("/record.json"):
                continue
            packet_sha256 = Path(path).parent.name
            record = self.get(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if record is not None:
                records.append(record)
        return sorted(
            records,
            key=lambda item: (item.prepared_at, item.packet_sha256),
            reverse=True,
        )

    def list_by_tenant(self, *, tenant_id: str) -> list[ProcurementReviewRecord]:
        """List every packet-bound review owned by one tenant."""
        prefix = self._tenant_review_prefix(tenant_id=tenant_id)
        records: list[ProcurementReviewRecord] = []
        for path in self._backend.list_prefix(str(prefix)):
            try:
                project_id, packet_sha256, filename = Path(path).relative_to(prefix).parts
            except (ValueError, TypeError):
                continue
            if filename != "record.json" or not _SHA256_PATTERN.fullmatch(packet_sha256):
                continue
            record = self.get(
                tenant_id=tenant_id,
                project_id=project_id,
                packet_sha256=packet_sha256,
            )
            if record is not None:
                records.append(record)
        return sorted(
            records,
            key=lambda item: (item.prepared_at, item.packet_sha256),
            reverse=True,
        )

    def read_packet(self, record: ProcurementReviewRecord) -> bytes:
        content = self._backend.read_bytes(
            self._relative_path(
                tenant_id=record.tenant_id,
                project_id=record.project_id,
                packet_sha256=record.packet_sha256,
                filename="packet.zip",
            )
        )
        if content is None:
            raise KeyError("procurement review packet is missing")
        if len(content) != record.packet_size_bytes or self._sha256(content) != record.packet_sha256:
            raise ValueError("stored procurement review packet evidence is inconsistent")
        return content

    def complete(
        self,
        *,
        current: ProcurementReviewRecord,
        completed_receipt: Mapping[str, Any],
        reviewed_package_content: bytes,
    ) -> ProcurementReviewRecord:
        """Persist one completed decision after its reviewed package is built."""
        completed = ProcurementReviewRecord(
            **{
                **asdict(current),
                "review_status": completed_receipt.get("status"),
                "decision": completed_receipt.get("decision"),
                "reviewed_at": completed_receipt.get("reviewed_at"),
                "reviewed_package_sha256": self._sha256(reviewed_package_content),
                "reviewed_package_size_bytes": len(reviewed_package_content),
                "receipt": dict(completed_receipt),
            }
        )
        self._validate_record(completed)

        with self._lock:
            stored = self.get(
                tenant_id=current.tenant_id,
                project_id=current.project_id,
                packet_sha256=current.packet_sha256,
            )
            if stored is None:
                raise KeyError("procurement review record is missing")
            if stored != current:
                raise ValueError("procurement review record changed before completion")
            if stored.review_status != "pending":
                raise ValueError("procurement review record is already completed")

            self._backend.write_bytes(
                self._relative_path(
                    tenant_id=current.tenant_id,
                    project_id=current.project_id,
                    packet_sha256=current.packet_sha256,
                    filename="reviewed_package.zip",
                ),
                reviewed_package_content,
                content_type="application/zip",
            )
            self._save_record(completed)
        return completed

    def read_reviewed_package(self, record: ProcurementReviewRecord) -> bytes:
        if record.review_status != "completed":
            raise ValueError("procurement review is not completed")
        content = self._backend.read_bytes(
            self._relative_path(
                tenant_id=record.tenant_id,
                project_id=record.project_id,
                packet_sha256=record.packet_sha256,
                filename="reviewed_package.zip",
            )
        )
        if content is None:
            raise KeyError("procurement reviewed package is missing")
        if (
            len(content) != record.reviewed_package_size_bytes
            or self._sha256(content) != record.reviewed_package_sha256
        ):
            raise ValueError("stored procurement reviewed package evidence is inconsistent")
        return content
