"""app/services/meeting_recording_service.py — Native meeting recording workflow."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

import httpx

from app.bundle_catalog.registry import get_bundle_spec
from app.config import (
    get_meeting_recording_context_char_limit,
    get_meeting_recording_max_upload_bytes,
    get_meeting_recording_transcription_model,
    get_openai_api_base_url,
)
from app.schemas import GenerateRequest
from app.storage.meeting_recording_store import MeetingRecording, MeetingRecordingStore
from app.storage.project_store import ProjectStore


ALLOWED_RECORDING_EXTENSIONS = {
    ".mp3",
    ".mp4",
    ".mpeg",
    ".mpga",
    ".m4a",
    ".wav",
    ".webm",
}
DEFAULT_GENERATION_BUNDLES = ["meeting_minutes_kr", "project_report_kr"]


class MeetingRecordingError(Exception):
    """Base error for native meeting recording workflow."""


class MeetingRecordingConfigError(MeetingRecordingError):
    """Raised when transcription is not configured."""


class MeetingRecordingStateError(MeetingRecordingError):
    """Raised when an operation is invalid for the recording's current state."""


class MeetingRecordingTranscriptionError(MeetingRecordingError):
    """Raised when OpenAI transcription fails."""


class MeetingRecordingUploadError(MeetingRecordingError):
    """Raised when an uploaded recording is invalid."""


class MeetingRecordingService:
    def __init__(
        self,
        *,
        recording_store: MeetingRecordingStore,
        project_store: ProjectStore,
        generation_service: Any,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._recording_store = recording_store
        self._project_store = project_store
        self._generation_service = generation_service
        self._transport = transport

    def upload_recording(
        self,
        *,
        tenant_id: str,
        project_id: str,
        filename: str,
        content_type: str | None,
        raw: bytes,
    ) -> MeetingRecording:
        if self._project_store.get(project_id, tenant_id=tenant_id) is None:
            raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

        suffix = os.path.splitext(filename)[1].lower()
        if suffix not in ALLOWED_RECORDING_EXTENSIONS:
            supported = ", ".join(sorted(ALLOWED_RECORDING_EXTENSIONS))
            raise MeetingRecordingUploadError(
                f"지원하지 않는 녹음 파일 형식입니다: {suffix or '(no extension)'} (지원: {supported})"
            )

        max_bytes = get_meeting_recording_max_upload_bytes()
        if len(raw) > max_bytes:
            raise MeetingRecordingUploadError(
                f"녹음 파일 크기가 제한을 초과했습니다. 최대 {max_bytes // (1024 * 1024)}MB까지 업로드할 수 있습니다."
            )

        return self._recording_store.create(
            tenant_id=tenant_id,
            project_id=project_id,
            filename=filename,
            content_type=content_type,
            raw=raw,
        )

    def list_recordings(self, *, tenant_id: str, project_id: str) -> list[MeetingRecording]:
        return self._recording_store.list_by_project(tenant_id=tenant_id, project_id=project_id)

    def get_recording(self, *, tenant_id: str, project_id: str, recording_id: str) -> MeetingRecording:
        recording = self._recording_store.get(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )
        if recording is None:
            raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
        return recording

    def transcribe_recording(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
        language: str | None = None,
    ) -> MeetingRecording:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise MeetingRecordingConfigError("OPENAI_API_KEY is not configured for meeting transcription.")

        recording = self.get_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )
        raw = self._recording_store.read_audio_bytes(recording)
        model = get_meeting_recording_transcription_model()
        self._recording_store.mark_processing(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )

        try:
            with self._create_client() as client:
                response = client.post(
                    f"{get_openai_api_base_url()}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    data={
                        "model": model,
                        **({"language": language} if language else {}),
                    },
                    files={
                        "file": (
                            recording.filename,
                            raw,
                            recording.content_type or "application/octet-stream",
                        )
                    },
                )
            if response.status_code >= 400:
                raise MeetingRecordingTranscriptionError(self._extract_openai_error(response))

            payload = response.json()
            transcript_text = str(payload.get("text") or "").strip()
            if not transcript_text:
                raise MeetingRecordingTranscriptionError("OpenAI transcription response did not include transcript text.")
            return self._recording_store.save_transcript(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
                transcript_text=transcript_text,
                transcript_language=(payload.get("language") or language or "").strip() or None,
                transcript_model=model,
            )
        except (httpx.HTTPError, json.JSONDecodeError, MeetingRecordingTranscriptionError) as exc:
            message = str(exc) or "OpenAI transcription request failed."
            self._recording_store.mark_transcription_failed(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
                error_message=message,
            )
            if isinstance(exc, MeetingRecordingTranscriptionError):
                raise
            raise MeetingRecordingTranscriptionError(message) from exc

    def approve_recording(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
        approved_by: str,
    ) -> MeetingRecording:
        recording = self.get_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )
        if recording.transcription_status != "completed" or not recording.transcript_text.strip():
            raise MeetingRecordingStateError("전사가 완료된 녹음만 승인할 수 있습니다.")
        return self._recording_store.approve(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            approved_by=approved_by,
        )

    def generate_documents_from_recording(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
        request_id: str,
        bundle_types: list[str] | None = None,
        context_note: str = "",
    ) -> dict[str, Any]:
        project = self._project_store.get(project_id, tenant_id=tenant_id)
        if project is None:
            raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

        recording = self.get_recording(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )
        if recording.approval_status != "approved":
            raise MeetingRecordingStateError("승인된 전사본만 문서 생성에 사용할 수 있습니다.")
        if not recording.transcript_text.strip():
            raise MeetingRecordingStateError("전사 텍스트가 비어 있습니다.")

        selected_bundle_types = bundle_types or list(DEFAULT_GENERATION_BUNDLES)
        results: list[dict[str, Any]] = []
        for index, bundle_type in enumerate(selected_bundle_types, start=1):
            get_bundle_spec(bundle_type)
            generate_request = GenerateRequest(
                title=self._build_document_title(project.name, recording.filename, bundle_type),
                goal=self._build_generation_goal(bundle_type),
                context=self._build_generation_context(recording, context_note=context_note),
                bundle_type=bundle_type,
                project_id=project_id,
            )
            generate_request_id = f"{request_id}:{bundle_type}:{index}"
            generated = self._generation_service.generate_documents(
                generate_request,
                request_id=generate_request_id,
                tenant_id=tenant_id,
            )
            metadata = generated["metadata"]
            document = self._project_store.add_document(
                project_id=project_id,
                request_id=generate_request_id,
                bundle_id=bundle_type,
                title=generate_request.title,
                docs=generated["docs"],
                tenant_id=tenant_id,
                source_kind="meeting_recording",
                source_recording_id=recording.recording_id,
                source_review_status=recording.approval_status,
                source_sync_status=recording.transcription_status,
                source_use_case="meeting_recording",
            )
            results.append(
                {
                    "bundle_type": bundle_type,
                    "request_id": generate_request_id,
                    "document": asdict(document),
                    "metadata": metadata,
                    "docs": generated["docs"],
                }
            )

        return {
            "project_id": project_id,
            "recording_id": recording.recording_id,
            "generated_documents": results,
        }

    def _create_client(self) -> httpx.Client:
        return httpx.Client(timeout=120, transport=self._transport)

    @staticmethod
    def _build_document_title(project_name: str, filename: str, bundle_type: str) -> str:
        if bundle_type == "meeting_minutes_kr":
            return f"{project_name} 회의록"
        if bundle_type == "project_report_kr":
            return f"{project_name} 프로젝트 보고서"
        stem = os.path.splitext(filename)[0] or project_name
        return f"{project_name} {stem}"

    @staticmethod
    def _build_generation_goal(bundle_type: str) -> str:
        if bundle_type == "meeting_minutes_kr":
            return "회의 녹음 전사본을 바탕으로 의사결정, 참석자 논의, 액션 아이템이 정리된 회의록을 작성한다."
        if bundle_type == "project_report_kr":
            return "회의 녹음 전사본을 바탕으로 경영진 또는 발주처 공유용 프로젝트 보고서를 작성한다."
        return "회의 녹음 전사본을 바탕으로 프로젝트 문서를 작성한다."

    @staticmethod
    def _extract_openai_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return f"OpenAI transcription request failed with status {response.status_code}."
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return message
        return f"OpenAI transcription request failed with status {response.status_code}."

    def _build_generation_context(self, recording: MeetingRecording, *, context_note: str = "") -> str:
        transcript_text = recording.transcript_text.strip()
        max_chars = get_meeting_recording_context_char_limit()
        clipped = transcript_text[:max_chars]
        truncated = len(transcript_text) > len(clipped)
        parts = [
            "아래는 승인된 회의 녹음 전사본입니다. 회의록/보고서 작성의 primary source로 사용하세요.",
            f"- 파일명: {recording.filename}",
        ]
        if recording.transcript_language:
            parts.append(f"- 언어: {recording.transcript_language}")
        if truncated:
            parts.append(
                f"- 참고: 전사본 길이가 길어 앞 {max_chars}자만 context에 포함했습니다. 핵심 논의와 action item을 우선 요약하세요."
            )
        if context_note.strip():
            parts.append(f"- 추가 지시: {context_note.strip()}")
        parts.extend(["", "[회의 전사본]", clipped])
        return "\n".join(parts)
