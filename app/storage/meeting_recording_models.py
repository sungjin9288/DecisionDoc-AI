"""Meeting recording metadata model and validation rules."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal


_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_TRANSCRIPTION_STATUSES = {"uploaded", "processing", "completed", "failed"}
_APPROVAL_STATUSES = {"pending", "approved"}


class MeetingRecordingStoreError(RuntimeError):
    """Raised when recording metadata or audio cannot be trusted."""


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MeetingRecordingStoreError(
                f"Duplicate key in meeting recording metadata: {key!r}"
            )
        result[key] = value
    return result


def require_segment(value: object, *, field: str) -> str:
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


def require_text(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise MeetingRecordingStoreError(f"Invalid {field}")
    return value


def require_multiline_text(value: object, *, field: str) -> str:
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


def require_optional_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or any(
        ord(character) < 32 or ord(character) == 127 for character in value
    ):
        raise MeetingRecordingStoreError(f"Invalid {field}")
    return value


def require_optional_multiline_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or any(
        (
            ord(character) < 32
            and character not in {"\n", "\r", "\t"}
        )
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


def recording_from_payload(
    payload: object,
    *,
    tenant_id: str,
    project_id: str,
    recording_id: str,
    expected_audio_path: str,
) -> MeetingRecording | None:
    if not isinstance(payload, dict):
        raise MeetingRecordingStoreError("Invalid meeting recording metadata")

    stored_identity = (
        payload.get("tenant_id"),
        payload.get("project_id"),
        payload.get("recording_id"),
    )
    if any(not isinstance(value, str) or not value for value in stored_identity):
        raise MeetingRecordingStoreError("Invalid meeting recording identity")
    if stored_identity != (tenant_id, project_id, recording_id):
        return None

    filename = require_text(payload.get("filename"), field="recording filename")
    content_type = require_text(
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
    if (
        not isinstance(audio_sha256, str)
        or not _SHA256_PATTERN.fullmatch(audio_sha256)
    ):
        raise MeetingRecordingStoreError("Invalid recording audio digest")
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
        transcript_text = require_multiline_text(
            transcript_text,
            field="recording transcript",
        )
    transcript_language = require_optional_text(
        payload.get("transcript_language"),
        field="transcript language",
    )
    transcript_model = require_optional_text(
        payload.get("transcript_model"),
        field="transcript model",
    )
    transcript_error = require_optional_multiline_text(
        payload.get("transcript_error"),
        field="transcript error",
    )
    approved_at = require_optional_text(
        payload.get("approved_at"),
        field="approval timestamp",
    )
    approved_by = require_optional_text(
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
