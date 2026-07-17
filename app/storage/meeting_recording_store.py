"""Project-scoped meeting recording metadata and audio storage."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.storage.meeting_recording_models import (
    MeetingRecording,
    MeetingRecordingStoreError,
    recording_from_payload,
    require_multiline_text as _require_multiline_text,
    require_optional_text as _require_optional_text,
    require_segment as _require_segment,
    require_text as _require_text,
    unique_object as _unique_object,
)
from app.storage.state_backend import StateBackend, StateBackendError, get_state_backend
from app.tenant import require_tenant_id


_MAX_MUTATION_ATTEMPTS = 32
_MAX_TRACKED_MUTATIONS = 64
_MUTATION_IDS_FIELD = "_mutation_ids"

_recording_locks: dict[Path, threading.RLock] = {}
_recording_locks_guard = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lock_for_path(path: Path) -> threading.RLock:
    with _recording_locks_guard:
        return _recording_locks.setdefault(path.resolve(), threading.RLock())


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
        filename = payload.get("filename") if isinstance(payload, dict) else None
        expected_audio_path = self._audio_relative_path(
            tenant_id,
            project_id,
            recording_id,
            filename if isinstance(filename, str) else "",
        )
        return recording_from_payload(
            payload,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
            expected_audio_path=expected_audio_path,
        )

    def _load_recording(
        self,
        raw: str,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> tuple[MeetingRecording | None, list[str]]:
        try:
            payload = json.loads(raw, object_pairs_hook=_unique_object)
        except (json.JSONDecodeError, TypeError, MeetingRecordingStoreError) as exc:
            raise MeetingRecordingStoreError(
                "Invalid meeting recording metadata"
            ) from exc
        recording = self._recording_from_payload(
            payload,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )
        if recording is None:
            return None, []
        return recording, self._mutation_ids(payload)

    @staticmethod
    def _mutation_ids(payload: dict[str, Any]) -> list[str]:
        mutation_ids = payload.get(_MUTATION_IDS_FIELD, [])
        if (
            not isinstance(mutation_ids, list)
            or len(mutation_ids) > _MAX_TRACKED_MUTATIONS
            or any(
                not isinstance(mutation_id, str) or not mutation_id
                for mutation_id in mutation_ids
            )
            or len(mutation_ids) != len(set(mutation_ids))
        ):
            raise MeetingRecordingStoreError(
                "Invalid meeting recording mutation history"
            )
        return list(mutation_ids)

    def _read_state(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> tuple[str | None, MeetingRecording | None, list[str]]:
        relative_path = self._metadata_relative_path(
            tenant_id,
            project_id,
            recording_id,
        )
        try:
            raw = self._backend.read_text(relative_path)
        except (StateBackendError, UnicodeError) as exc:
            raise MeetingRecordingStoreError(
                "Failed to read meeting recording metadata"
            ) from exc
        if raw is None:
            return None, None, []
        recording, mutation_ids = self._load_recording(
            raw,
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )
        return raw, recording, mutation_ids

    def _get_unlocked(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
    ) -> MeetingRecording | None:
        return self._read_state(
            tenant_id=tenant_id,
            project_id=project_id,
            recording_id=recording_id,
        )[1]

    def _serialize(
        self,
        recording: MeetingRecording,
        mutation_ids: list[str],
    ) -> str:
        validated = self._recording_from_payload(
            asdict(recording),
            tenant_id=recording.tenant_id,
            project_id=recording.project_id,
            recording_id=recording.recording_id,
        )
        if validated is None:
            raise MeetingRecordingStoreError("Invalid meeting recording identity")
        payload = asdict(validated)
        payload[_MUTATION_IDS_FIELD] = mutation_ids[-_MAX_TRACKED_MUTATIONS:]
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _persist_if_current(
        self,
        *,
        expected: str | None,
        recording: MeetingRecording,
        mutation_ids: list[str],
        mutation_id: str,
    ) -> MeetingRecording | None:
        relative_path = self._metadata_relative_path(
            recording.tenant_id,
            recording.project_id,
            recording.recording_id,
        )
        replacement = self._serialize(recording, mutation_ids)
        try:
            if expected is None:
                written = self._backend.write_text_if_absent(
                    relative_path,
                    replacement,
                )
            else:
                written = self._backend.replace_text_if_equal(
                    relative_path,
                    expected=expected,
                    replacement=replacement,
                )
        except StateBackendError as exc:
            try:
                observed_raw = self._backend.read_text(relative_path)
            except (StateBackendError, UnicodeError):
                observed_raw = None
            if observed_raw == replacement:
                return recording
            if observed_raw is not None:
                try:
                    observed, observed_mutation_ids = self._load_recording(
                        observed_raw,
                        tenant_id=recording.tenant_id,
                        project_id=recording.project_id,
                        recording_id=recording.recording_id,
                    )
                except MeetingRecordingStoreError:
                    pass
                else:
                    if (
                        observed is not None
                        and mutation_id in observed_mutation_ids
                    ):
                        return observed
            raise MeetingRecordingStoreError(
                "Failed to persist meeting recording metadata"
            ) from exc
        return recording if written else None

    def _mutate(
        self,
        *,
        tenant_id: str,
        project_id: str,
        recording_id: str,
        change: Callable[[MeetingRecording], None],
    ) -> MeetingRecording:
        mutation_id = uuid.uuid4().hex
        for _ in range(_MAX_MUTATION_ATTEMPTS):
            expected, recording, mutation_ids = self._read_state(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
            if recording is None:
                raise KeyError(f"녹음 파일을 찾을 수 없습니다: {recording_id}")
            if mutation_id in mutation_ids:
                return recording
            change(recording)
            mutation_ids.append(mutation_id)
            persisted = self._persist_if_current(
                expected=expected,
                recording=recording,
                mutation_ids=mutation_ids,
                mutation_id=mutation_id,
            )
            if persisted is not None:
                return persisted
        raise MeetingRecordingStoreError(
            "Meeting recording metadata changed too many times to persist safely"
        )

    def _write_audio_if_absent(
        self,
        recording: MeetingRecording,
        raw: bytes,
    ) -> bool:
        try:
            written = self._backend.write_bytes_if_absent(
                recording.audio_relative_path,
                raw,
                content_type=recording.content_type,
            )
        except StateBackendError as exc:
            try:
                observed = self._backend.read_bytes(recording.audio_relative_path)
            except StateBackendError:
                observed = None
            if observed == raw:
                return False
            raise MeetingRecordingStoreError(
                "Failed to persist meeting recording audio"
            ) from exc
        if written:
            return True
        try:
            observed = self._backend.read_bytes(recording.audio_relative_path)
        except StateBackendError as exc:
            raise MeetingRecordingStoreError(
                "Failed to read meeting recording audio"
            ) from exc
        if observed != raw:
            raise MeetingRecordingStoreError("Duplicate meeting recording identity")
        return False

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
        mutation_id = uuid.uuid4().hex
        metadata_payload = self._serialize(recording, [mutation_id])

        with self._lock(tenant_id, project_id, recording_id):
            existing_raw, _, _ = self._read_state(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
            if existing_raw is not None:
                raise MeetingRecordingStoreError("Duplicate meeting recording identity")
            audio_created = self._write_audio_if_absent(recording, raw)
            metadata_path = self._metadata_relative_path(
                tenant_id,
                project_id,
                recording_id,
            )
            try:
                written = self._backend.write_text_if_absent(
                    metadata_path,
                    metadata_payload,
                )
            except StateBackendError as exc:
                written = False
                write_error: StateBackendError | None = exc
            else:
                write_error = None
            if written:
                return recording

            _, observed, observed_mutation_ids = self._read_state(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
            )
            if observed is not None and mutation_id in observed_mutation_ids:
                return observed
            if (
                audio_created
                and observed is not None
                and observed.audio_relative_path != audio_relative_path
            ):
                try:
                    self._backend.delete(audio_relative_path)
                except StateBackendError as exc:
                    raise MeetingRecordingStoreError(
                        "Failed to clean up unreferenced recording audio"
                    ) from exc
            if write_error is not None:
                raise MeetingRecordingStoreError(
                    "Failed to persist meeting recording metadata"
                ) from write_error
            raise MeetingRecordingStoreError("Duplicate meeting recording identity")

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
        try:
            paths = self._backend.list_prefix(prefix)
        except StateBackendError as exc:
            raise MeetingRecordingStoreError(
                "Failed to list meeting recording metadata"
            ) from exc
        for path in paths:
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
            try:
                raw = self._backend.read_bytes(recording.audio_relative_path)
            except StateBackendError as exc:
                raise MeetingRecordingStoreError(
                    "Failed to read meeting recording audio"
                ) from exc
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

        def change(recording: MeetingRecording) -> None:
            recording.transcription_status = "processing"
            recording.transcript_error = None
            recording.updated_at = _now_iso()

        with self._lock(tenant_id, project_id, recording_id):
            return self._mutate(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
                change=change,
            )

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

        def change(recording: MeetingRecording) -> None:
            recording.transcription_status = "completed"
            recording.transcript_text = transcript_text
            recording.transcript_language = transcript_language
            recording.transcript_model = transcript_model
            recording.transcript_error = None
            recording.updated_at = _now_iso()

        with self._lock(tenant_id, project_id, recording_id):
            return self._mutate(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
                change=change,
            )

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

        def change(recording: MeetingRecording) -> None:
            recording.transcription_status = "failed"
            recording.transcript_error = error_message
            recording.updated_at = _now_iso()

        with self._lock(tenant_id, project_id, recording_id):
            return self._mutate(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
                change=change,
            )

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

        def change(recording: MeetingRecording) -> None:
            recording.approval_status = "approved"
            recording.approved_at = _now_iso()
            recording.approved_by = approved_by
            recording.updated_at = recording.approved_at

        with self._lock(tenant_id, project_id, recording_id):
            return self._mutate(
                tenant_id=tenant_id,
                project_id=project_id,
                recording_id=recording_id,
                change=change,
            )
