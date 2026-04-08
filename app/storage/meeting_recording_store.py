"""app/storage/meeting_recording_store.py — Project-scoped meeting recording storage."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from app.storage.state_backend import StateBackend, get_state_backend


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MeetingRecording:
    recording_id: str
    tenant_id: str
    project_id: str
    filename: str
    content_type: str
    file_size_bytes: int
    audio_relative_path: str
    audio_sha256: str
    uploaded_at: str
    updated_at: str
    transcription_status: Literal["uploaded", "processing", "completed", "failed"]
    approval_status: Literal["pending", "approved"]
    transcript_text: str = ""
    transcript_language: str | None = None
    transcript_model: str | None = None
    transcript_error: str | None = None
    approved_at: str | None = None
    approved_by: str | None = None


class MeetingRecordingStore:
    """Persist meeting recordings as per-recording metadata + audio blobs."""

    def __init__(self, base_dir: str = "data", *, backend: StateBackend | None = None) -> None:
        self._base = Path(base_dir)
        self._backend = backend or get_state_backend(data_dir=self._base)
        self._lock = threading.Lock()

    def _recording_prefix(self, tenant_id: str, project_id: str, recording_id: str) -> Path:
        return Path("tenants") / tenant_id / "meeting_recordings" / project_id / recording_id

    def _project_prefix(self, tenant_id: str, project_id: str) -> str:
        return str(Path("tenants") / tenant_id / "meeting_recordings" / project_id)

    def _metadata_relative_path(self, tenant_id: str, project_id: str, recording_id: str) -> str:
        return str(self._recording_prefix(tenant_id, project_id, recording_id) / "metadata.json")

    def _audio_relative_path(self, tenant_id: str, project_id: str, recording_id: str, filename: str) -> str:
        suffix = Path(filename).suffix.lower().strip()
        if not suffix:
            suffix = ".bin"
        return str(self._recording_prefix(tenant_id, project_id, recording_id) / f"audio{suffix}")

    @staticmethod
    def _from_dict(payload: dict) -> MeetingRecording:
        return MeetingRecording(
            recording_id=payload["recording_id"],
            tenant_id=payload["tenant_id"],
            project_id=payload["project_id"],
            filename=payload.get("filename", ""),
            content_type=payload.get("content_type", "application/octet-stream"),
            file_size_bytes=int(payload.get("file_size_bytes", 0)),
            audio_relative_path=payload.get("audio_relative_path", ""),
            audio_sha256=payload.get("audio_sha256", ""),
            uploaded_at=payload.get("uploaded_at", ""),
            updated_at=payload.get("updated_at", payload.get("uploaded_at", "")),
            transcription_status=payload.get("transcription_status", "uploaded"),
            approval_status=payload.get("approval_status", "pending"),
            transcript_text=payload.get("transcript_text", ""),
            transcript_language=payload.get("transcript_language"),
            transcript_model=payload.get("transcript_model"),
            transcript_error=payload.get("transcript_error"),
            approved_at=payload.get("approved_at"),
            approved_by=payload.get("approved_by"),
        )

    def _save(self, recording: MeetingRecording) -> None:
        self._backend.write_text(
            self._metadata_relative_path(
                recording.tenant_id,
                recording.project_id,
                recording.recording_id,
            ),
            json.dumps(asdict(recording), ensure_ascii=False, indent=2),
        )

    def create(
        self,
        *,
        tenant_id: str,
        project_id: str,
        filename: str,
        content_type: str | None,
        raw: bytes,
    ) -> MeetingRecording:
        guessed_content_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        recording_id = str(uuid.uuid4())
        uploaded_at = _now_iso()
        audio_relative_path = self._audio_relative_path(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            filename=filename,
        )
        recording = MeetingRecording(
            recording_id=recording_id,
            tenant_id=tenant_id,
            project_id=project_id,
            filename=filename,
            content_type=guessed_content_type,
            file_size_bytes=len(raw),
            audio_relative_path=audio_relative_path,
            audio_sha256=hashlib.sha256(raw).hexdigest(),
            uploaded_at=uploaded_at,
            updated_at=uploaded_at,
            transcription_status="uploaded",
            approval_status="pending",
        )
        with self._lock:
            self._backend.write_bytes(audio_relative_path, raw, content_type=recording.content_type)
            self._save(recording)
        return recording

    def get(self, *, tenant_id: str, project_id: str, recording_id: str) -> MeetingRecording | None:
        raw = self._backend.read_text(self._metadata_relative_path(tenant_id, project_id, recording_id))
        if raw is None:
            return None
        try:
            return self._from_dict(json.loads(raw))
        except (json.JSONDecodeError, ValueError, KeyError):
            return None

    def list_by_project(self, *, tenant_id: str, project_id: str) -> list[MeetingRecording]:
        prefix = self._project_prefix(tenant_id, project_id)
        records: list[MeetingRecording] = []
        for path in sorted(self._backend.list_prefix(prefix)):
            if not path.endswith("/metadata.json"):
                continue
            raw = self._backend.read_text(path)
            if raw is None:
                continue
            try:
                records.append(self._from_dict(json.loads(raw)))
            except (json.JSONDecodeError, ValueError, KeyError):
                continue
        return sorted(records, key=lambda item: item.uploaded_at, reverse=True)

    def read_audio_bytes(self, recording: MeetingRecording) -> bytes:
        raw = self._backend.read_bytes(recording.audio_relative_path)
        if raw is None:
            raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording.recording_id}")
        return raw

    def mark_processing(self, *, tenant_id: str, project_id: str, recording_id: str) -> MeetingRecording:
        with self._lock:
            recording = self.get(tenant_id=tenant_id, project_id=project_id, recording_id=recording_id)
            if recording is None:
                raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
            recording.transcription_status = "processing"
            recording.transcript_error = None
            recording.updated_at = _now_iso()
            self._save(recording)
            return recording

    def save_transcript(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
        transcript_text: str,
        transcript_language: str | None,
        transcript_model: str | None,
    ) -> MeetingRecording:
        with self._lock:
            recording = self.get(tenant_id=tenant_id, project_id=project_id, recording_id=recording_id)
            if recording is None:
                raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
            recording.transcription_status = "completed"
            recording.transcript_text = transcript_text
            recording.transcript_language = transcript_language
            recording.transcript_model = transcript_model
            recording.transcript_error = None
            recording.updated_at = _now_iso()
            self._save(recording)
            return recording

    def mark_transcription_failed(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
        error_message: str,
    ) -> MeetingRecording:
        with self._lock:
            recording = self.get(tenant_id=tenant_id, project_id=project_id, recording_id=recording_id)
            if recording is None:
                raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
            recording.transcription_status = "failed"
            recording.transcript_error = error_message
            recording.updated_at = _now_iso()
            self._save(recording)
            return recording

    def approve(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
        approved_by: str,
    ) -> MeetingRecording:
        with self._lock:
            recording = self.get(tenant_id=tenant_id, project_id=project_id, recording_id=recording_id)
            if recording is None:
                raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
            recording.approval_status = "approved"
            recording.approved_at = _now_iso()
            recording.approved_by = approved_by
            recording.updated_at = recording.approved_at
            self._save(recording)
            return recording
