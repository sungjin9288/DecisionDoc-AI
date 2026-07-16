"""Project-scoped meeting recording metadata and audio storage."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.storage.state_backend import StateBackend, get_state_backend
from app.tenant import require_tenant_id


_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_TRANSCRIPTION_STATUSES = {"uploaded", "processing", "completed", "failed"}
_APPROVAL_STATUSES = {"pending", "approved"}

_recording_locks: dict[Path, threading.RLock] = {}
_recording_locks_guard = threading.Lock()


class MeetingRecordingStoreError(RuntimeError):
    """Raised when recording metadata or audio cannot be trusted."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lock_for_path(path: Path) -> threading.RLock:
    with _recording_locks_guard:
        return _recording_locks.setdefault(path.resolve(), threading.RLock())


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MeetingRecordingStoreError(
                f"Duplicate key in meeting recording metadata: {key!r}"
            )
        result[key] = value
    return result


def _require_segment(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"Invalid {field}")
    return value


def _require_text(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise MeetingRecordingStoreError(f"Invalid {field}")
    return value


def _require_multiline_text(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(
            ord(character) < 32 and character not in {"\n", "\r", "\t"}
            for character in value
        )
        or "\x7f" in value
    ):
        raise MeetingRecordingStoreError(f"Invalid {field}")
    return value


def _require_optional_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise MeetingRecordingStoreError(f"Invalid {field}")
    return value


def _require_optional_multiline_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or any(
        ord(character) < 32
        and character not in {"\n", "\r", "\t"}
        or ord(character) == 127
        for character in value
    ):
        raise MeetingRecordingStoreError(f"Invalid {field}")
    return value


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
    """Persist recording metadata and audio under a caller-owned tenant/project path."""

    def __init__(
        self,
        base_dir: str | Path | None = None,
        *,
        backend: StateBackend | None = None,
    ) -> None:
        self._base = Path(base_dir or os.getenv("DATA_DIR", "data"))
        self._backend = backend or get_state_backend(data_dir=self._base)

    @staticmethod
    def _recording_prefix(
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> Path:
        return (
            Path("tenants")
            / tenant_id
            / "meeting_recordings"
            / project_id
            / recording_id
        )

    @staticmethod
    def _project_prefix(tenant_id: str, project_id: str) -> str:
        return str(Path("tenants") / tenant_id / "meeting_recordings" / project_id)

    def _metadata_relative_path(
        self,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> str:
        return str(
            self._recording_prefix(tenant_id, project_id, recording_id)
            / "metadata.json"
        )

    def _audio_relative_path(
        self,
        tenant_id: str,
        project_id: str,
        recording_id: str,
        filename: str,
    ) -> str:
        suffix = Path(filename).suffix.lower().strip() or ".bin"
        return str(
            self._recording_prefix(tenant_id, project_id, recording_id)
            / f"audio{suffix}"
        )

    def _lock(
        self,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> threading.RLock:
        metadata_path = self._base / self._metadata_relative_path(
            tenant_id,
            project_id,
            recording_id,
        )
        return _lock_for_path(metadata_path)

    def _recording_from_payload(
        self,
        payload: object,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> MeetingRecording | None:
        if not isinstance(payload, dict):
            raise MeetingRecordingStoreError("Invalid meeting recording metadata")

        stored_tenant_id = payload.get("tenant_id")
        stored_project_id = payload.get("project_id")
        stored_recording_id = payload.get("recording_id")
        if any(
            not isinstance(value, str) or not value
            for value in (
                stored_tenant_id,
                stored_project_id,
                stored_recording_id,
            )
        ):
            raise MeetingRecordingStoreError("Invalid meeting recording identity")
        if (
            stored_tenant_id != tenant_id
            or stored_project_id != project_id
            or stored_recording_id != recording_id
        ):
            return None

        filename = _require_text(payload.get("filename"), field="recording filename")
        content_type = _require_text(
            payload.get("content_type"),
            field="recording content type",
        )
        file_size_bytes = payload.get("file_size_bytes")
        if (
            isinstance(file_size_bytes, bool)
            or not isinstance(file_size_bytes, int)
            or file_size_bytes < 0
        ):
            raise MeetingRecordingStoreError("Invalid recording file size")

        audio_relative_path = payload.get("audio_relative_path")
        audio_sha256 = payload.get("audio_sha256")
        if not isinstance(audio_relative_path, str) or not audio_relative_path:
            raise MeetingRecordingStoreError("Invalid recording audio path")
        if not isinstance(audio_sha256, str) or not _SHA256_PATTERN.fullmatch(
            audio_sha256
        ):
            raise MeetingRecordingStoreError("Invalid recording audio digest")
        expected_audio_path = self._audio_relative_path(
            tenant_id,
            project_id,
            recording_id,
            filename,
        )
        if audio_relative_path != expected_audio_path:
            raise MeetingRecordingStoreError("Inconsistent recording audio path")

        uploaded_at = payload.get("uploaded_at")
        updated_at = payload.get("updated_at")
        if not isinstance(uploaded_at, str) or not isinstance(updated_at, str):
            raise MeetingRecordingStoreError("Invalid recording timestamp")
        try:
            datetime.fromisoformat(uploaded_at)
            datetime.fromisoformat(updated_at)
        except ValueError as exc:
            raise MeetingRecordingStoreError("Invalid recording timestamp") from exc

        transcription_status = payload.get("transcription_status")
        approval_status = payload.get("approval_status")
        if (
            not isinstance(transcription_status, str)
            or transcription_status not in _TRANSCRIPTION_STATUSES
        ):
            raise MeetingRecordingStoreError("Invalid transcription status")
        if (
            not isinstance(approval_status, str)
            or approval_status not in _APPROVAL_STATUSES
        ):
            raise MeetingRecordingStoreError("Invalid recording approval status")

        transcript_text = payload.get("transcript_text", "")
        if not isinstance(transcript_text, str):
            raise MeetingRecordingStoreError("Invalid recording transcript")
        if transcript_text:
            transcript_text = _require_multiline_text(
                transcript_text,
                field="recording transcript",
            )
        transcript_language = _require_optional_text(
            payload.get("transcript_language"),
            field="transcript language",
        )
        transcript_model = _require_optional_text(
            payload.get("transcript_model"),
            field="transcript model",
        )
        transcript_error = _require_optional_multiline_text(
            payload.get("transcript_error"),
            field="transcript error",
        )
        approved_at = _require_optional_text(
            payload.get("approved_at"),
            field="approval timestamp",
        )
        approved_by = _require_optional_text(
            payload.get("approved_by"),
            field="approval actor",
        )
        if approved_at:
            try:
                datetime.fromisoformat(approved_at)
            except ValueError as exc:
                raise MeetingRecordingStoreError(
                    "Invalid recording approval timestamp"
                ) from exc
        if approval_status == "approved" and (not approved_at or not approved_by):
            raise MeetingRecordingStoreError("Incomplete recording approval evidence")

        return MeetingRecording(
            recording_id=recording_id,
            tenant_id=tenant_id,
            project_id=project_id,
            filename=filename,
            content_type=content_type,
            file_size_bytes=file_size_bytes,
            audio_relative_path=audio_relative_path,
            audio_sha256=audio_sha256,
            uploaded_at=uploaded_at,
            updated_at=updated_at,
            transcription_status=transcription_status,
            approval_status=approval_status,
            transcript_text=transcript_text,
            transcript_language=transcript_language,
            transcript_model=transcript_model,
            transcript_error=transcript_error,
            approved_at=approved_at,
            approved_by=approved_by,
        )

    def _load_recording(
        self,
        raw: str,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> MeetingRecording | None:
        try:
            payload = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, MeetingRecordingStoreError) as exc:
            raise MeetingRecordingStoreError(
                "Invalid meeting recording metadata"
            ) from exc
        return self._recording_from_payload(
            payload,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )

    def _get_unlocked(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> MeetingRecording | None:
        raw = self._backend.read_text(
            self._metadata_relative_path(tenant_id, project_id, recording_id)
        )
        if raw is None:
            return None
        return self._load_recording(
            raw,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )

    def _save(self, recording: MeetingRecording) -> None:
        validated = self._recording_from_payload(
            asdict(recording),
            tenant_id=recording.tenant_id,
            project_id=recording.project_id,
            recording_id=recording.recording_id,
        )
        if validated is None:
            raise MeetingRecordingStoreError("Invalid meeting recording identity")
        self._backend.write_text(
            self._metadata_relative_path(
                recording.tenant_id,
                recording.project_id,
                recording.recording_id,
            ),
            json.dumps(asdict(validated), ensure_ascii=False, indent=2),
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
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_segment(project_id, field="project_id")
        filename = _require_text(filename, field="recording filename")
        if content_type is not None and not isinstance(content_type, str):
            raise MeetingRecordingStoreError("Invalid recording content type")
        if not isinstance(raw, bytes):
            raise MeetingRecordingStoreError("Invalid recording audio")

        guessed_content_type = (
            content_type
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        recording_id = _require_segment(str(uuid.uuid4()), field="recording_id")
        uploaded_at = _now_iso()
        audio_relative_path = self._audio_relative_path(
            tenant_id,
            project_id,
            recording_id,
            filename,
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
        self._recording_from_payload(
            asdict(recording),
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )

        with self._lock(tenant_id, project_id, recording_id):
            prefix = str(self._recording_prefix(tenant_id, project_id, recording_id))
            if self._backend.list_prefix(prefix):
                raise MeetingRecordingStoreError("Duplicate meeting recording identity")
            self._backend.write_bytes(
                audio_relative_path,
                raw,
                content_type=recording.content_type,
            )
            self._save(recording)
        return recording

    def get(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> MeetingRecording | None:
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_segment(project_id, field="project_id")
        recording_id = _require_segment(recording_id, field="recording_id")
        with self._lock(tenant_id, project_id, recording_id):
            return self._get_unlocked(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )

    def list_by_project(
        self,
        *,
        tenant_id: str,
        project_id: str,
    ) -> list[MeetingRecording]:
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_segment(project_id, field="project_id")
        prefix = self._project_prefix(tenant_id, project_id)
        records: list[MeetingRecording] = []
        for path in self._backend.list_prefix(prefix):
            try:
                recording_id, filename = Path(path).relative_to(prefix).parts
            except (TypeError, ValueError):
                continue
            if filename != "metadata.json":
                continue
            try:
                recording_id = _require_segment(
                    recording_id,
                    field="recording_id",
                )
            except ValueError:
                continue
            recording = self.get(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
            if recording is not None:
                records.append(recording)
        return sorted(
            records,
            key=lambda item: (item.uploaded_at, item.recording_id),
            reverse=True,
        )

    def read_audio_bytes(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> bytes:
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_segment(project_id, field="project_id")
        recording_id = _require_segment(recording_id, field="recording_id")
        with self._lock(tenant_id, project_id, recording_id):
            recording = self._get_unlocked(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
            if recording is None:
                raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
            raw = self._backend.read_bytes(recording.audio_relative_path)
            if raw is None:
                raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
            if (
                len(raw) != recording.file_size_bytes
                or hashlib.sha256(raw).hexdigest() != recording.audio_sha256
            ):
                raise MeetingRecordingStoreError(
                    "Recording audio integrity check failed"
                )
            return raw

    def mark_processing(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> MeetingRecording:
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_segment(project_id, field="project_id")
        recording_id = _require_segment(recording_id, field="recording_id")
        with self._lock(tenant_id, project_id, recording_id):
            recording = self._get_unlocked(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
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
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_segment(project_id, field="project_id")
        recording_id = _require_segment(recording_id, field="recording_id")
        transcript_text = _require_multiline_text(
            transcript_text,
            field="recording transcript",
        )
        transcript_language = _require_optional_text(
            transcript_language,
            field="transcript language",
        )
        transcript_model = _require_optional_text(
            transcript_model,
            field="transcript model",
        )
        with self._lock(tenant_id, project_id, recording_id):
            recording = self._get_unlocked(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
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
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_segment(project_id, field="project_id")
        recording_id = _require_segment(recording_id, field="recording_id")
        error_message = _require_multiline_text(
            error_message,
            field="transcription error",
        )
        with self._lock(tenant_id, project_id, recording_id):
            recording = self._get_unlocked(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
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
        tenant_id = require_tenant_id(tenant_id)
        project_id = _require_segment(project_id, field="project_id")
        recording_id = _require_segment(recording_id, field="recording_id")
        approved_by = _require_text(approved_by, field="approval actor")
        with self._lock(tenant_id, project_id, recording_id):
            recording = self._get_unlocked(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
            if recording is None:
                raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
            recording.approval_status = "approved"
            recording.approved_at = _now_iso()
            recording.approved_by = approved_by
            recording.updated_at = recording.approved_at
            self._save(recording)
            return recording
