"""Session-bound access and HTTP projections for procurement reviews."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from fastapi import HTTPException, Request

from app.storage.procurement_review_models import ProcurementReviewRecord


@dataclass(frozen=True)
class ProcurementReviewAccess:
    user_id: str
    username: str
    role: str

    @property
    def scope(self) -> str:
        return "tenant" if self.role == "admin" else "assigned"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def get_procurement_review_access(request: Request) -> ProcurementReviewAccess:
    """Read the session principal already checked by the route dependency."""
    return ProcurementReviewAccess(
        user_id=str(request.state.user_id),
        username=str(request.state.username),
        role=str(request.state.user_role),
    )


def require_assignment_request_access(
    access: ProcurementReviewAccess,
    reviewer_username: str,
) -> None:
    """Members may prepare a packet only for their own current account."""
    if access.is_admin:
        return
    if reviewer_username.casefold() != access.username.casefold():
        raise HTTPException(
            status_code=403,
            detail="멤버는 자신에게만 procurement 검토를 지정할 수 있습니다.",
        )


def require_assignment_access(
    access: ProcurementReviewAccess,
    assignment: dict[str, str],
) -> None:
    """Keep the username request and resolved stable identity aligned."""
    if access.is_admin:
        return
    if assignment["user_id"] != access.user_id:
        raise HTTPException(
            status_code=403,
            detail="멤버는 자신에게만 procurement 검토를 지정할 수 있습니다.",
        )


def require_reviewer_filter_access(
    access: ProcurementReviewAccess,
    reviewer_username: str | None,
) -> None:
    """A member cannot use the tenant inbox to inspect another reviewer."""
    if not reviewer_username or access.is_admin:
        return
    if reviewer_username.casefold() != access.username.casefold():
        raise HTTPException(
            status_code=403,
            detail="멤버는 자신의 procurement 검토함만 조회할 수 있습니다.",
        )


def authorized_review_records(
    records: Iterable[ProcurementReviewRecord],
    access: ProcurementReviewAccess,
) -> list[ProcurementReviewRecord]:
    """Return the tenant-wide admin view or the member's assigned v2 records."""
    records = list(records)
    if access.is_admin:
        return records
    return [
        record
        for record in records
        if record.reviewer_identity_bound
        and record.reviewer_assignment is not None
        and record.reviewer_assignment["user_id"] == access.user_id
    ]


def require_project_review_access(
    *,
    has_records: bool,
    authorized: Iterable[ProcurementReviewRecord],
    access: ProcurementReviewAccess,
) -> None:
    """Do not expose a project review history that belongs only to another user."""
    authorized = list(authorized)
    if access.is_admin:
        return
    if has_records and not authorized:
        raise HTTPException(
            status_code=403,
            detail="이 프로젝트의 procurement 검토 이력에 접근할 수 없습니다.",
        )


def require_reviewed_package_access(
    record: ProcurementReviewRecord,
    access: ProcurementReviewAccess,
) -> None:
    """Authorize package access before any artifact read or verification."""
    if access.is_admin:
        return
    assignment = record.reviewer_assignment
    if (
        record.reviewer_identity_bound
        and assignment is not None
        and assignment["user_id"] == access.user_id
    ):
        return
    raise HTTPException(
        status_code=403,
        detail="지정된 검토 담당자 또는 관리자만 완료 패키지를 내려받을 수 있습니다.",
    )


def review_summary(
    record: ProcurementReviewRecord,
    access: ProcurementReviewAccess,
) -> dict[str, object]:
    """Expose only workflow fields needed by the procurement review UI."""
    assignment = record.reviewer_assignment or {}
    attestation = record.reviewer_attestation or {}
    attested_reviewer = attestation.get("reviewer", {})
    completed_by = (
        attested_reviewer.get("username")
        if isinstance(attested_reviewer, dict)
        else None
    )
    assigned_to_current_user = (
        record.reviewer_identity_bound
        and assignment.get("user_id") == access.user_id
    )
    return {
        "project_id": record.project_id,
        "packet_sha256": record.packet_sha256,
        "packet_size_bytes": record.packet_size_bytes,
        "package_id": record.package_id,
        "recommendation": record.recommendation,
        "review_status": record.review_status,
        "decision": record.decision,
        "prepared_at": record.prepared_at,
        "reviewed_at": record.reviewed_at,
        "reviewed_package_sha256": record.reviewed_package_sha256,
        "reviewed_package_size_bytes": record.reviewed_package_size_bytes,
        "operational_approval": False,
        "assigned_reviewer": assignment.get("username") or record.reviewer,
        "assigned_to_current_user": assigned_to_current_user,
        "completed_by": completed_by,
        "reviewer_identity_bound": record.reviewer_identity_bound,
        "reviewer_session_bound": record.reviewer_session_bound,
        "access_scope": access.scope,
    }
