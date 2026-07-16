"""app/routers/projects/meeting_recordings.py — Voice-brief import and meeting-recording endpoints.

Extracted from app/routers/projects.py (moved verbatim; no behavior changes).
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.auth.api_key import require_api_key
from app.dependencies import get_tenant_id, get_username
from app.schemas import (
    GenerateMeetingRecordingDocumentsRequest,
    ImportVoiceBriefDocumentRequest,
    TranscribeMeetingRecordingRequest,
)
from app.services.meeting_recording_service import (
    MeetingRecordingConfigError,
    MeetingRecordingStateError,
    MeetingRecordingTranscriptionError,
    MeetingRecordingUploadError,
    TRANSCRIPTION_FAILED_MESSAGE,
)
from app.services.generation.context_store import record_named_provider_usage
from app.services.voice_brief_import_service import (
    VoiceBriefImportBlockedError,
    VoiceBriefRemoteError,
)

from app.routers.projects._shared import (
    _serialize_meeting_recording,
    _serialize_meeting_recording_summary,
)

router = APIRouter()


def _set_error_code(request: Request, code: str) -> None:
    request.state.error_code = code


def _apply_meeting_recording_observability(
    request: Request,
    *,
    action: str,
    project_id: str,
    recording_id: str | None = None,
    file_size_bytes: int | None = None,
    recording=None,
    generated_documents: list[dict] | None = None,
) -> None:
    request.state.meeting_recording_action = action
    request.state.meeting_recording_project_id = project_id

    resolved_recording_id = recording_id
    if recording is not None:
        resolved_recording_id = recording.recording_id
    request.state.meeting_recording_recording_id = resolved_recording_id

    if file_size_bytes is not None:
        request.state.meeting_recording_file_size_bytes = file_size_bytes
    elif recording is not None:
        request.state.meeting_recording_file_size_bytes = recording.file_size_bytes

    if recording is not None:
        request.state.meeting_recording_transcription_status = recording.transcription_status
        request.state.meeting_recording_approval_status = recording.approval_status
        request.state.meeting_recording_transcript_language = recording.transcript_language
        request.state.meeting_recording_transcript_model = recording.transcript_model
        request.state.meeting_recording_transcript_error = (
            TRANSCRIPTION_FAILED_MESSAGE if recording.transcript_error else None
        )

    if generated_documents is not None:
        bundle_types = [
            str(item.get("bundle_type"))
            for item in generated_documents
            if item.get("bundle_type")
        ]
        request.state.meeting_recording_generated_bundle_count = len(bundle_types)
        request.state.meeting_recording_generated_bundle_types = bundle_types


def _apply_meeting_recording_error_observability(
    request: Request,
    *,
    service,
    tenant_id: str,
    project_id: str,
    recording_id: str,
    action: str,
) -> None:
    try:
        recording = service.get_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )
    except KeyError:
        return
    _apply_meeting_recording_observability(
        request,
        action=action,
        project_id=project_id,
        recording=recording,
    )


def _ensure_project_exists_for_meeting_recording(
    request: Request,
    *,
    project_id: str,
    tenant_id: str,
) -> None:
    project = request.app.state.project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        _set_error_code(request, "project_not_found")
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")


@router.post(
    "/projects/{project_id}/imports/voice-brief",
    dependencies=[Depends(require_api_key)],
)
def import_voice_brief_document_endpoint(
    project_id: str,
    payload: ImportVoiceBriefDocumentRequest,
    request: Request,
) -> dict:
    """Import an approved Voice Brief document package into an existing project."""
    tenant_id = get_tenant_id(request)
    project_store = request.app.state.project_store
    project = project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")

    import_service = getattr(request.app.state, "voice_brief_import_service", None)
    if import_service is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "voice_brief_not_configured",
                "message": "VOICE_BRIEF_API_BASE_URL is not configured.",
            },
        )

    try:
        result = import_service.import_into_project(
            project_store=project_store,
            project_id=project_id,
            tenant_id=tenant_id,
            recording_id=payload.recording_id,
            revision_id=payload.revision_id,
        )
    except VoiceBriefImportBlockedError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": exc.code,
                "message": str(exc),
            },
        ) from exc
    except VoiceBriefRemoteError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "voice_brief_not_found",
                    "message": str(exc),
                },
            ) from exc
        raise HTTPException(
            status_code=502,
            detail={
                "code": "voice_brief_upstream_error",
                "message": str(exc),
            },
        ) from exc

    return {
        "project_id": project_id,
        "operation": result.operation,
        "import_outcome": result.outcome,
        "source_key": result.source_key,
        "document_id": result.document_id,
        "source_recording_id": result.source_recording_id,
        "source_summary_revision_id": result.source_summary_revision_id,
        "document": asdict(result.document),
        "voice_brief": {
            "recording_id": result.source_recording_id,
            "summary_revision_id": result.source_summary_revision_id,
            "summary_review_status": result.voice_brief_document.get("summaryReviewStatus"),
            "summary_sync_status": result.voice_brief_document.get("summarySyncStatus"),
        },
    }


@router.post(
    "/projects/{project_id}/recordings",
    dependencies=[Depends(require_api_key)],
)
async def upload_project_meeting_recording_endpoint(
    project_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    """Upload a native meeting recording for later transcription and document generation."""
    tenant_id = get_tenant_id(request)
    service = request.app.state.meeting_recording_service
    raw = await file.read()
    _apply_meeting_recording_observability(
        request,
        action="upload",
        project_id=project_id,
        file_size_bytes=len(raw),
    )
    try:
        recording = service.upload_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            filename=file.filename or "recording",
            content_type=file.content_type,
            raw=raw,
        )
    except KeyError as exc:
        _set_error_code(request, "project_not_found")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeetingRecordingUploadError as exc:
        _set_error_code(request, "meeting_recording_upload_invalid")
        raise HTTPException(
            status_code=422,
            detail={"code": "meeting_recording_upload_invalid", "message": str(exc)},
        ) from exc
    _apply_meeting_recording_observability(
        request,
        action="upload",
        project_id=project_id,
        recording=recording,
    )
    return {
        "project_id": project_id,
        "recording": _serialize_meeting_recording_summary(recording),
    }


@router.get(
    "/projects/{project_id}/recordings",
    dependencies=[Depends(require_api_key)],
)
def list_project_meeting_recordings_endpoint(project_id: str, request: Request) -> dict:
    tenant_id = get_tenant_id(request)
    service = request.app.state.meeting_recording_service
    _apply_meeting_recording_observability(
        request,
        action="list",
        project_id=project_id,
    )
    project = request.app.state.project_store.get(project_id, tenant_id=tenant_id)
    if project is None:
        _set_error_code(request, "project_not_found")
        raise HTTPException(status_code=404, detail=f"프로젝트를 찾을 수 없습니다: {project_id}")
    recordings = service.list_recordings(tenant_id=tenant_id, project_id=project_id)
    return {
        "project_id": project_id,
        "recordings": [_serialize_meeting_recording_summary(recording) for recording in recordings],
    }


@router.get(
    "/projects/{project_id}/recordings/{recording_id}",
    dependencies=[Depends(require_api_key)],
)
def get_project_meeting_recording_endpoint(
    project_id: str,
    recording_id: str,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    service = request.app.state.meeting_recording_service
    _apply_meeting_recording_observability(
        request,
        action="get",
        project_id=project_id,
        recording_id=recording_id,
    )
    _ensure_project_exists_for_meeting_recording(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
    )
    try:
        recording = service.get_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )
    except KeyError as exc:
        _set_error_code(request, "meeting_recording_not_found")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _apply_meeting_recording_observability(
        request,
        action="get",
        project_id=project_id,
        recording=recording,
    )
    return {
        "project_id": project_id,
        "recording": _serialize_meeting_recording(recording),
    }


@router.post(
    "/projects/{project_id}/recordings/{recording_id}/transcribe",
    dependencies=[Depends(require_api_key)],
)
def transcribe_project_meeting_recording_endpoint(
    project_id: str,
    recording_id: str,
    payload: TranscribeMeetingRecordingRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    service = request.app.state.meeting_recording_service
    _apply_meeting_recording_observability(
        request,
        action="transcribe",
        project_id=project_id,
        recording_id=recording_id,
    )
    _ensure_project_exists_for_meeting_recording(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
    )
    try:
        recording = service.transcribe_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            language=payload.language,
            record_provider_usage=lambda model: record_named_provider_usage(
                request,
                model=model,
                bundle_id="meeting-recording.transcription",
            ),
        )
    except KeyError as exc:
        _set_error_code(request, "meeting_recording_not_found")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeetingRecordingConfigError as exc:
        _apply_meeting_recording_error_observability(
            request,
            service=service,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            action="transcribe",
        )
        _set_error_code(request, "meeting_recording_transcription_not_configured")
        raise HTTPException(
            status_code=503,
            detail={"code": "meeting_recording_transcription_not_configured", "message": str(exc)},
        ) from exc
    except MeetingRecordingTranscriptionError as exc:
        _apply_meeting_recording_error_observability(
            request,
            service=service,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            action="transcribe",
        )
        _set_error_code(request, "meeting_recording_transcription_failed")
        raise HTTPException(
            status_code=502,
            detail={
                "code": "meeting_recording_transcription_failed",
                "message": TRANSCRIPTION_FAILED_MESSAGE,
            },
        ) from exc
    _apply_meeting_recording_observability(
        request,
        action="transcribe",
        project_id=project_id,
        recording=recording,
    )
    return {
        "project_id": project_id,
        "recording": _serialize_meeting_recording(recording),
    }


@router.post(
    "/projects/{project_id}/recordings/{recording_id}/approve",
    dependencies=[Depends(require_api_key)],
)
def approve_project_meeting_recording_endpoint(
    project_id: str,
    recording_id: str,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    service = request.app.state.meeting_recording_service
    _apply_meeting_recording_observability(
        request,
        action="approve",
        project_id=project_id,
        recording_id=recording_id,
    )
    _ensure_project_exists_for_meeting_recording(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
    )
    try:
        recording = service.approve_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            approved_by=get_username(request),
        )
    except KeyError as exc:
        _set_error_code(request, "meeting_recording_not_found")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MeetingRecordingStateError as exc:
        _apply_meeting_recording_error_observability(
            request,
            service=service,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            action="approve",
        )
        _set_error_code(request, "meeting_recording_not_ready_for_approval")
        raise HTTPException(
            status_code=409,
            detail={"code": "meeting_recording_not_ready_for_approval", "message": str(exc)},
        ) from exc
    _apply_meeting_recording_observability(
        request,
        action="approve",
        project_id=project_id,
        recording=recording,
    )
    return {
        "project_id": project_id,
        "recording": _serialize_meeting_recording(recording),
    }


@router.post(
    "/projects/{project_id}/recordings/{recording_id}/generate-documents",
    dependencies=[Depends(require_api_key)],
)
def generate_project_docs_from_meeting_recording_endpoint(
    project_id: str,
    recording_id: str,
    payload: GenerateMeetingRecordingDocumentsRequest,
    request: Request,
) -> dict:
    tenant_id = get_tenant_id(request)
    service = request.app.state.meeting_recording_service
    _apply_meeting_recording_observability(
        request,
        action="generate_documents",
        project_id=project_id,
        recording_id=recording_id,
    )
    _ensure_project_exists_for_meeting_recording(
        request,
        project_id=project_id,
        tenant_id=tenant_id,
    )
    try:
        result = service.generate_documents_from_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            request_id=request.state.request_id,
            bundle_types=payload.bundle_types,
            context_note=payload.context_note,
        )
    except KeyError as exc:
        _set_error_code(request, "meeting_recording_not_found")
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        _apply_meeting_recording_error_observability(
            request,
            service=service,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            action="generate_documents",
        )
        _set_error_code(request, "meeting_recording_bundle_invalid")
        raise HTTPException(
            status_code=422,
            detail={"code": "meeting_recording_bundle_invalid", "message": str(exc)},
        ) from exc
    except MeetingRecordingStateError as exc:
        _apply_meeting_recording_error_observability(
            request,
            service=service,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            action="generate_documents",
        )
        _set_error_code(request, "meeting_recording_not_ready_for_generation")
        raise HTTPException(
            status_code=409,
            detail={"code": "meeting_recording_not_ready_for_generation", "message": str(exc)},
        ) from exc
    recording = service.get_recording(
        tenant_id=tenant_id,
        project_id=project_id,
        recording_id=recording_id,
    )
    _apply_meeting_recording_observability(
        request,
        action="generate_documents",
        project_id=project_id,
        recording=recording,
        generated_documents=result["generated_documents"],
    )
    return result
