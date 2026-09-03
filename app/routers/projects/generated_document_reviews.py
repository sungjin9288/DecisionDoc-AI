"""Session-bound generated-document review handoff endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.dependencies import (
    get_tenant_id,
    require_session_bound_generated_document_reviewer,
)
from app.schemas import CreateGeneratedDocumentReviewRequest
from app.services.generated_document_review_service import (
    GeneratedDocumentReviewConflictError,
    GeneratedDocumentReviewForbiddenError,
    GeneratedDocumentReviewNotFoundError,
    GeneratedDocumentReviewUnavailableError,
)
from app.services.generation_export_packet import (
    AUTHORITY_FALSE,
    ExportFormatInvalidError,
)


router = APIRouter()


def _service(request: Request):
    return request.app.state.generated_document_review_service


def _access(request: Request, *, tenant_id: str):
    return _service(request).resolve_access(
        tenant_id=tenant_id,
        user_id=str(request.state.user_id),
        username=str(request.state.username),
        role=str(request.state.user_role),
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "code": "generated_document_review_not_found",
            "message": "문서 검토 전달 항목을 찾을 수 없습니다.",
        },
    )


def _packet_headers(
    record,
    *,
    replay: bool,
    source_status: str | None = None,
) -> dict[str, str]:
    headers = {
        "Cache-Control": "no-store",
        "Content-Disposition": (
            f'attachment; filename="generated-document-review-{record.packet_sha256}.zip"'
        ),
        "X-Content-Type-Options": "nosniff",
        "X-DecisionDoc-Packet-SHA256": record.packet_sha256,
        "X-DecisionDoc-Manifest-SHA256": record.manifest_sha256,
        "X-DecisionDoc-Artifact-Count": str(record.artifact_count),
        "X-DecisionDoc-Review-Status": record.review_status,
        "X-DecisionDoc-Reviewer-Identity-Bound": "true",
        "X-DecisionDoc-Replay": str(replay).lower(),
        "X-DecisionDoc-Review-Only": "true",
        "X-DecisionDoc-Packet-Persisted": "true",
        "X-DecisionDoc-Human-Review-Completed": "false",
        "X-DecisionDoc-Operational-Approval": "false",
    }
    for key in AUTHORITY_FALSE:
        headers[f"X-DecisionDoc-Authority-{key.replace('_', '-')}"] = "false"
    if source_status is not None:
        headers["X-DecisionDoc-Source-Status"] = source_status
    return headers


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, GeneratedDocumentReviewForbiddenError):
        raise HTTPException(
            status_code=403,
            detail="멤버는 자신에게만 문서 검토를 지정할 수 있습니다.",
        ) from exc
    if isinstance(exc, GeneratedDocumentReviewNotFoundError):
        raise _not_found() from exc
    if isinstance(exc, GeneratedDocumentReviewConflictError):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "generated_document_review_conflict",
                "message": "현재 문서 상태로 검토 패킷을 만들 수 없습니다.",
            },
        ) from exc
    if isinstance(exc, GeneratedDocumentReviewUnavailableError):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "generated_document_review_unavailable",
                "message": "저장된 문서 검토 상태를 신뢰할 수 없습니다.",
            },
        ) from exc
    raise exc


def _parse_pagination(*, review_status: str, limit: str, offset: str) -> tuple[int, int]:
    if review_status != "pending":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "generated_document_review_query_invalid",
                "message": "pending 검토 상태만 조회할 수 있습니다.",
            },
        )
    try:
        parsed_limit = int(limit)
        parsed_offset = int(offset)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "generated_document_review_query_invalid",
                "message": "페이지 범위가 올바르지 않습니다.",
            },
        ) from exc
    if str(parsed_limit) != limit or str(parsed_offset) != offset:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "generated_document_review_query_invalid",
                "message": "페이지 범위가 올바르지 않습니다.",
            },
        )
    if not 1 <= parsed_limit <= 50 or parsed_offset < 0:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "generated_document_review_query_invalid",
                "message": "페이지 범위가 올바르지 않습니다.",
            },
        )
    return parsed_limit, parsed_offset


@router.post(
    "/projects/{project_id}/documents/{document_id}/generated-reviews",
    dependencies=[Depends(require_session_bound_generated_document_reviewer)],
)
async def create_generated_document_review(
    project_id: str,
    document_id: str,
    payload: CreateGeneratedDocumentReviewRequest,
    request: Request,
) -> Response:
    tenant_id = get_tenant_id(request)
    try:
        access = _access(request, tenant_id=tenant_id)
        record, content, created = await _service(request).prepare(
            tenant_id=tenant_id,
            project_id=project_id,
            project_document_id=document_id,
            reviewer_username=payload.reviewer,
            formats=payload.formats,
            access=access,
        )
    except ExportFormatInvalidError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "generated_document_review_format_invalid",
                "message": "지원하는 문서 형식을 하나 이상 선택해야 합니다.",
            },
        ) from exc
    except (
        GeneratedDocumentReviewForbiddenError,
        GeneratedDocumentReviewNotFoundError,
        GeneratedDocumentReviewConflictError,
        GeneratedDocumentReviewUnavailableError,
    ) as exc:
        _raise_service_error(exc)

    request.state.generated_document_review_action = "prepared"
    request.state.generated_document_review_project_id = project_id
    request.state.generated_document_review_document_id = document_id
    request.state.generated_document_review_packet_sha256 = record.packet_sha256
    request.state.generated_document_review_status = record.review_status
    request.state.generated_document_review_access_scope = access.scope
    request.state.generated_document_review_replay = not created
    request.state.generated_document_review_source_status = "current"
    request.state.generated_document_review_operational_approval = False
    return Response(
        content=content,
        media_type="application/zip",
        headers=_packet_headers(record, replay=not created),
    )


@router.get(
    "/generated-document-reviews",
    dependencies=[Depends(require_session_bound_generated_document_reviewer)],
)
def list_generated_document_reviews(
    request: Request,
    review_status: str = "pending",
    limit: str = "50",
    offset: str = "0",
) -> dict:
    parsed_limit, parsed_offset = _parse_pagination(
        review_status=review_status,
        limit=limit,
        offset=offset,
    )
    tenant_id = get_tenant_id(request)
    try:
        access = _access(request, tenant_id=tenant_id)
        records = _service(request).list_inbox(
            tenant_id=tenant_id,
            access=access,
        )
        summaries = [
            _service(request).summary(record, access=access)
            for record in records[parsed_offset : parsed_offset + parsed_limit]
        ]
    except (
        GeneratedDocumentReviewNotFoundError,
        GeneratedDocumentReviewUnavailableError,
    ) as exc:
        _raise_service_error(exc)
    request.state.generated_document_review_action = "listed"
    request.state.generated_document_review_access_scope = access.scope
    request.state.generated_document_review_status = "pending"
    request.state.generated_document_review_operational_approval = False
    return {
        "reviews": summaries,
        "total": len(records),
        "limit": parsed_limit,
        "offset": parsed_offset,
        "has_more": parsed_offset + parsed_limit < len(records),
        "access_scope": access.scope,
        "operational_approval": False,
    }


@router.get(
    "/projects/{project_id}/generated-document-reviews",
    dependencies=[Depends(require_session_bound_generated_document_reviewer)],
)
def list_project_generated_document_reviews(
    project_id: str,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    try:
        access = _access(request, tenant_id=tenant_id)
        records = _service(request).list_project(
            tenant_id=tenant_id,
            project_id=project_id,
            access=access,
        )
        summaries = [
            _service(request).summary(record, access=access) for record in records
        ]
    except (
        GeneratedDocumentReviewNotFoundError,
        GeneratedDocumentReviewUnavailableError,
    ) as exc:
        _raise_service_error(exc)
    request.state.generated_document_review_action = "project_listed"
    request.state.generated_document_review_project_id = project_id
    request.state.generated_document_review_access_scope = access.scope
    request.state.generated_document_review_status = "pending"
    request.state.generated_document_review_operational_approval = False
    return {
        "reviews": summaries,
        "total": len(summaries),
        "access_scope": access.scope,
        "operational_approval": False,
    }


@router.get(
    "/projects/{project_id}/generated-document-reviews/{packet_sha256}/packet",
    dependencies=[Depends(require_session_bound_generated_document_reviewer)],
)
def download_generated_document_review_packet(
    project_id: str,
    packet_sha256: str,
    request: Request,
) -> Response:
    tenant_id = get_tenant_id(request)
    try:
        access = _access(request, tenant_id=tenant_id)
        record, content, source_status = _service(request).download(
            tenant_id=tenant_id,
            project_id=project_id,
            packet_sha256=packet_sha256,
            access=access,
        )
    except (
        GeneratedDocumentReviewNotFoundError,
        GeneratedDocumentReviewUnavailableError,
    ) as exc:
        _raise_service_error(exc)
    request.state.generated_document_review_action = "downloaded"
    request.state.generated_document_review_project_id = project_id
    request.state.generated_document_review_document_id = record.project_document_id
    request.state.generated_document_review_packet_sha256 = record.packet_sha256
    request.state.generated_document_review_status = record.review_status
    request.state.generated_document_review_access_scope = access.scope
    request.state.generated_document_review_replay = True
    request.state.generated_document_review_source_status = source_status
    request.state.generated_document_review_operational_approval = False
    return Response(
        content=content,
        media_type="application/zip",
        headers=_packet_headers(
            record,
            replay=True,
            source_status=source_status,
        ),
    )
