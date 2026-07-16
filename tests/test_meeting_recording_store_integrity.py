from __future__ import annotations

import ast
import hashlib
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.storage.meeting_recording_store import (
    MeetingRecordingStore,
    MeetingRecordingStoreError,
)
from app.storage.state_backend import LocalStateBackend, S3StateBackend


class _SlowLocalBackend(LocalStateBackend):
    """Expose races when independent stores do not share a recording lock."""

    def read_text(self, relative_path: str) -> str | None:
        raw = super().read_text(relative_path)
        time.sleep(0.005)
        return raw

    def list_prefix(self, relative_prefix: str) -> list[str]:
        paths = super().list_prefix(relative_prefix)
        time.sleep(0.005)
        return paths


class _Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _MemoryS3Client:
    def __init__(self, *, read_delay: float = 0.0) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.read_delay = read_delay

    def put_object(
        self,
        *,
        Bucket: str,
        Key: str,
        Body: bytes,
        ContentType: str,
    ) -> None:
        _ = ContentType
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        time.sleep(self.read_delay)
        data = self.objects.get((Bucket, Key))
        if data is None:
            error = Exception("NoSuchKey")
            error.response = {"Error": {"Code": "NoSuchKey"}}
            raise error
        return {"Body": _Body(data)}

    def head_object(self, *, Bucket: str, Key: str) -> dict:
        if (Bucket, Key) not in self.objects:
            error = Exception("NotFound")
            error.response = {"Error": {"Code": "404"}}
            raise error
        return {}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, **kwargs) -> dict:
        _ = kwargs
        contents = [
            {"Key": key}
            for (bucket, key), _ in self.objects.items()
            if bucket == Bucket and key.startswith(Prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


def _s3_backend(
    *,
    read_delay: float = 0.0,
) -> tuple[S3StateBackend, _MemoryS3Client]:
    client = _MemoryS3Client(read_delay=read_delay)
    backend = S3StateBackend(
        bucket="unit-bucket",
        prefix="decisiondoc-ai/state/",
        s3_client=client,
    )
    return backend, client


def _metadata_path(
    root: Path,
    recording_id: str,
    *,
    tenant_id: str = "alpha",
    project_id: str = "project-1",
) -> Path:
    return (
        root
        / "tenants"
        / tenant_id
        / "meeting_recordings"
        / project_id
        / recording_id
        / "metadata.json"
    )


def _audio_path(
    root: Path,
    recording_id: str,
    *,
    tenant_id: str = "alpha",
    project_id: str = "project-1",
) -> Path:
    return (
        root
        / "tenants"
        / tenant_id
        / "meeting_recordings"
        / project_id
        / recording_id
        / "audio.wav"
    )


def _record(
    recording_id: str,
    *,
    tenant_id: str = "alpha",
    project_id: str = "project-1",
    raw: bytes = b"RIFF meeting audio",
) -> dict:
    return {
        "recording_id": recording_id,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "filename": "meeting.wav",
        "content_type": "audio/wav",
        "file_size_bytes": len(raw),
        "audio_relative_path": (
            f"tenants/{tenant_id}/meeting_recordings/{project_id}/"
            f"{recording_id}/audio.wav"
        ),
        "audio_sha256": hashlib.sha256(raw).hexdigest(),
        "uploaded_at": "2026-07-16T00:00:00+00:00",
        "updated_at": "2026-07-16T00:00:00+00:00",
        "transcription_status": "uploaded",
        "approval_status": "pending",
        "transcript_text": "",
        "transcript_language": None,
        "transcript_model": None,
        "transcript_error": None,
        "approved_at": None,
        "approved_by": None,
    }


def _write_recording(
    root: Path,
    recording_id: str,
    *,
    payload: dict | None = None,
    raw: bytes = b"RIFF meeting audio",
) -> tuple[Path, Path]:
    metadata_path = _metadata_path(root, recording_id)
    audio_path = _audio_path(root, recording_id)
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps(payload or _record(recording_id, raw=raw)),
        encoding="utf-8",
    )
    audio_path.write_bytes(raw)
    return metadata_path, audio_path


@pytest.mark.parametrize(
    "tenant_id",
    [" tenant", "tenant ", ".", "..", "tenant/a", "tenant\\a", "tenant\na"],
)
def test_meeting_recording_store_rejects_unsafe_tenant_before_state_access(
    tmp_path: Path,
    tenant_id: str,
) -> None:
    store = MeetingRecordingStore(base_dir=tmp_path)

    with pytest.raises(ValueError, match="Invalid tenant_id"):
        store.create(
            tenant_id=tenant_id,
            project_id="project-1",
            filename="meeting.wav",
            content_type="audio/wav",
            raw=b"audio",
        )

    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "unsafe_value",
    [" project", "project ", ".", "..", "project/a", "project\\a", "project\na"],
)
def test_meeting_recording_store_rejects_unsafe_project_and_recording_paths(
    tmp_path: Path,
    unsafe_value: str,
) -> None:
    store = MeetingRecordingStore(base_dir=tmp_path)

    with pytest.raises(ValueError):
        store.create(
            tenant_id="alpha",
            project_id=unsafe_value,
            filename="meeting.wav",
            content_type="audio/wav",
            raw=b"audio",
        )
    with pytest.raises(ValueError):
        store.get(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=unsafe_value,
        )

    assert not (tmp_path / "tenants").exists()


def test_missing_recording_reads_have_no_side_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    store = MeetingRecordingStore()

    assert (
        store.get(
            tenant_id="alpha",
            project_id="project-1",
            recording_id="missing",
        )
        is None
    )
    assert store.list_by_project(tenant_id="alpha", project_id="project-1") == []
    assert not (tmp_path / "tenants").exists()


@pytest.mark.parametrize(
    "raw_metadata",
    [
        "{not-json",
        "[]",
        '{"recording_id":"first","recording_id":"second"}',
        json.dumps({**_record("recording-1"), "filename": ["meeting.wav"]}),
        json.dumps({**_record("recording-1"), "filename": "meeting\u0000.wav"}),
        json.dumps({**_record("recording-1"), "file_size_bytes": True}),
        json.dumps({**_record("recording-1"), "file_size_bytes": -1}),
        json.dumps({**_record("recording-1"), "audio_sha256": "not-a-digest"}),
        json.dumps(
            {
                **_record("recording-1"),
                "audio_relative_path": "tenants/alpha/other/audio.wav",
            }
        ),
        json.dumps({**_record("recording-1"), "uploaded_at": "later"}),
        json.dumps({**_record("recording-1"), "transcription_status": "unknown"}),
        json.dumps({**_record("recording-1"), "transcription_status": []}),
        json.dumps({**_record("recording-1"), "approval_status": "approved"}),
        json.dumps({**_record("recording-1"), "transcript_text": []}),
        json.dumps({**_record("recording-1"), "transcript_text": "bad\u0000text"}),
    ],
)
def test_untrusted_recording_metadata_stops_reads_and_writes_without_replacement(
    tmp_path: Path,
    raw_metadata: str,
) -> None:
    metadata_path, audio_path = _write_recording(tmp_path, "recording-1")
    metadata_path.write_text(raw_metadata, encoding="utf-8")
    original_metadata = metadata_path.read_bytes()
    original_audio = audio_path.read_bytes()
    store = MeetingRecordingStore(base_dir=tmp_path)

    operations = (
        lambda: store.get(
            tenant_id="alpha",
            project_id="project-1",
            recording_id="recording-1",
        ),
        lambda: store.list_by_project(
            tenant_id="alpha",
            project_id="project-1",
        ),
        lambda: store.read_audio_bytes(
            tenant_id="alpha",
            project_id="project-1",
            recording_id="recording-1",
        ),
        lambda: store.mark_processing(
            tenant_id="alpha",
            project_id="project-1",
            recording_id="recording-1",
        ),
        lambda: store.save_transcript(
            tenant_id="alpha",
            project_id="project-1",
            recording_id="recording-1",
            transcript_text="회의 전사본",
            transcript_language="ko",
            transcript_model="test-model",
        ),
        lambda: store.mark_transcription_failed(
            tenant_id="alpha",
            project_id="project-1",
            recording_id="recording-1",
            error_message="transcription failed",
        ),
        lambda: store.approve(
            tenant_id="alpha",
            project_id="project-1",
            recording_id="recording-1",
            approved_by="reviewer",
        ),
    )
    for operation in operations:
        with pytest.raises(MeetingRecordingStoreError):
            operation()

    assert metadata_path.read_bytes() == original_metadata
    assert audio_path.read_bytes() == original_audio


def test_foreign_recording_metadata_remains_hidden_and_preserved(
    tmp_path: Path,
) -> None:
    store = MeetingRecordingStore(base_dir=tmp_path)
    recording = store.create(
        tenant_id="alpha",
        project_id="project-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"owned audio",
    )
    metadata_path = _metadata_path(tmp_path, recording.recording_id)
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["tenant_id"] = "beta"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")
    original_bytes = metadata_path.read_bytes()

    assert (
        store.get(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
        )
        is None
    )
    assert store.list_by_project(tenant_id="alpha", project_id="project-1") == []
    with pytest.raises(KeyError):
        store.mark_processing(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
        )

    assert metadata_path.read_bytes() == original_bytes


@pytest.mark.parametrize("tampered_audio", [b"short", b"RIFF modified audio"])
def test_audio_integrity_mismatch_is_rejected_without_repair(
    tmp_path: Path,
    tampered_audio: bytes,
) -> None:
    store = MeetingRecordingStore(base_dir=tmp_path)
    recording = store.create(
        tenant_id="alpha",
        project_id="project-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"RIFF original audio",
    )
    metadata_path = _metadata_path(tmp_path, recording.recording_id)
    audio_path = _audio_path(tmp_path, recording.recording_id)
    audio_path.write_bytes(tampered_audio)
    original_metadata = metadata_path.read_bytes()

    with pytest.raises(
        MeetingRecordingStoreError,
        match="audio integrity check failed",
    ):
        store.read_audio_bytes(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
        )

    assert audio_path.read_bytes() == tampered_audio
    assert metadata_path.read_bytes() == original_metadata


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("filename", "", "Invalid recording filename"),
        ("filename", "meeting\n.wav", "Invalid recording filename"),
        ("content_type", [], "Invalid recording content type"),
        ("raw", bytearray(b"audio"), "Invalid recording audio"),
    ],
)
def test_invalid_recording_input_is_rejected_before_write(
    tmp_path: Path,
    field: str,
    value: object,
    error: str,
) -> None:
    arguments = {
        "tenant_id": "alpha",
        "project_id": "project-1",
        "filename": "meeting.wav",
        "content_type": "audio/wav",
        "raw": b"audio",
        field: value,
    }
    store = MeetingRecordingStore(base_dir=tmp_path)

    with pytest.raises(MeetingRecordingStoreError, match=error):
        store.create(**arguments)

    assert not (tmp_path / "tenants").exists()


def test_invalid_recording_mutation_input_does_not_rewrite_metadata(
    tmp_path: Path,
) -> None:
    store = MeetingRecordingStore(base_dir=tmp_path)
    recording = store.create(
        tenant_id="alpha",
        project_id="project-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"audio",
    )
    metadata_path = _metadata_path(tmp_path, recording.recording_id)
    original_bytes = metadata_path.read_bytes()

    operations = (
        lambda: store.save_transcript(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
            transcript_text="",
            transcript_language="ko",
            transcript_model="test-model",
        ),
        lambda: store.save_transcript(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
            transcript_text="transcript",
            transcript_language=[],
            transcript_model="test-model",
        ),
        lambda: store.mark_transcription_failed(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
            error_message="",
        ),
        lambda: store.approve(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
            approved_by="",
        ),
    )
    for operation in operations:
        with pytest.raises(MeetingRecordingStoreError):
            operation()

    assert metadata_path.read_bytes() == original_bytes


def test_recording_store_rejects_uuid_collision_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = MeetingRecordingStore(base_dir=tmp_path)
    first = store.create(
        tenant_id="alpha",
        project_id="project-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"first audio",
    )
    metadata_path = _metadata_path(tmp_path, first.recording_id)
    audio_path = _audio_path(tmp_path, first.recording_id)
    original_metadata = metadata_path.read_bytes()
    original_audio = audio_path.read_bytes()
    monkeypatch.setattr(
        "app.storage.meeting_recording_store.uuid.uuid4",
        lambda: uuid.UUID(first.recording_id),
    )

    with pytest.raises(
        MeetingRecordingStoreError,
        match="Duplicate meeting recording identity",
    ):
        store.create(
            tenant_id="alpha",
            project_id="project-1",
            filename="meeting.wav",
            content_type="audio/wav",
            raw=b"replacement audio",
        )

    assert metadata_path.read_bytes() == original_metadata
    assert audio_path.read_bytes() == original_audio


def test_independent_local_stores_allow_one_concurrent_create_per_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording_uuid = uuid.uuid4()
    monkeypatch.setattr(
        "app.storage.meeting_recording_store.uuid.uuid4",
        lambda: recording_uuid,
    )
    stores = [
        MeetingRecordingStore(
            base_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    def create(index: int) -> bool:
        try:
            stores[index].create(
                tenant_id="alpha",
                project_id="project-1",
                filename="meeting.wav",
                content_type="audio/wav",
                raw=f"audio-{index}".encode(),
            )
        except MeetingRecordingStoreError:
            return False
        return True

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(create, range(20)))

    assert results.count(True) == 1
    reloaded = MeetingRecordingStore(base_dir=tmp_path).get(
        tenant_id="alpha",
        project_id="project-1",
        recording_id=str(recording_uuid),
    )
    assert reloaded is not None
    assert (
        len(
            MeetingRecordingStore(base_dir=tmp_path).read_audio_bytes(
                tenant_id="alpha",
                project_id="project-1",
                recording_id=str(recording_uuid),
            )
        )
        == reloaded.file_size_bytes
    )


def test_independent_local_stores_preserve_concurrent_transcript_and_approval(
    tmp_path: Path,
) -> None:
    creator = MeetingRecordingStore(base_dir=tmp_path)
    recording = creator.create(
        tenant_id="alpha",
        project_id="project-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"audio",
    )
    creator.save_transcript(
        tenant_id="alpha",
        project_id="project-1",
        recording_id=recording.recording_id,
        transcript_text="initial transcript",
        transcript_language="ko",
        transcript_model="test-model",
    )
    stores = [
        MeetingRecordingStore(
            base_dir=tmp_path,
            backend=_SlowLocalBackend(tmp_path),
        )
        for _ in range(20)
    ]

    def mutate(index: int) -> None:
        if index % 2:
            stores[index].approve(
                tenant_id="alpha",
                project_id="project-1",
                recording_id=recording.recording_id,
                approved_by=f"reviewer-{index}",
            )
            return
        stores[index].save_transcript(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
            transcript_text=f"transcript-{index}",
            transcript_language="ko",
            transcript_model="test-model",
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(mutate, range(20)))

    reloaded = creator.get(
        tenant_id="alpha",
        project_id="project-1",
        recording_id=recording.recording_id,
    )
    assert reloaded is not None
    assert reloaded.approval_status == "approved"
    assert reloaded.approved_by is not None
    assert reloaded.transcript_text.startswith("transcript-")


def test_meeting_recording_round_trip_through_fake_s3() -> None:
    backend, client = _s3_backend()
    store = MeetingRecordingStore(base_dir="/virtual/data", backend=backend)
    recording = store.create(
        tenant_id="alpha",
        project_id="project-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"RIFF fake audio",
    )
    metadata_key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/meeting_recordings/"
        f"project-1/{recording.recording_id}/metadata.json",
    )

    assert metadata_key in client.objects
    reloaded = MeetingRecordingStore(
        base_dir="/virtual/data",
        backend=backend,
    )
    assert (
        reloaded.read_audio_bytes(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
        )
        == b"RIFF fake audio"
    )


def test_untrusted_fake_s3_metadata_is_preserved() -> None:
    backend, client = _s3_backend()
    store = MeetingRecordingStore(base_dir="/virtual/data", backend=backend)
    recording = store.create(
        tenant_id="alpha",
        project_id="project-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"audio",
    )
    key = (
        "unit-bucket",
        "decisiondoc-ai/state/tenants/alpha/meeting_recordings/"
        f"project-1/{recording.recording_id}/metadata.json",
    )
    client.objects[key] = b"{not-json"

    with pytest.raises(MeetingRecordingStoreError):
        store.mark_processing(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
        )

    assert client.objects[key] == b"{not-json"


def test_independent_fake_s3_stores_preserve_concurrent_mutations() -> None:
    backend, _ = _s3_backend(read_delay=0.005)
    creator = MeetingRecordingStore(base_dir="/virtual/data", backend=backend)
    recording = creator.create(
        tenant_id="alpha",
        project_id="project-1",
        filename="meeting.wav",
        content_type="audio/wav",
        raw=b"audio",
    )
    creator.save_transcript(
        tenant_id="alpha",
        project_id="project-1",
        recording_id=recording.recording_id,
        transcript_text="initial transcript",
        transcript_language="ko",
        transcript_model="test-model",
    )
    stores = [
        MeetingRecordingStore(base_dir="/virtual/data", backend=backend)
        for _ in range(20)
    ]

    def mutate(index: int) -> None:
        if index % 2:
            stores[index].approve(
                tenant_id="alpha",
                project_id="project-1",
                recording_id=recording.recording_id,
                approved_by=f"reviewer-{index}",
            )
            return
        stores[index].save_transcript(
            tenant_id="alpha",
            project_id="project-1",
            recording_id=recording.recording_id,
            transcript_text=f"transcript-{index}",
            transcript_language="ko",
            transcript_model="test-model",
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        list(executor.map(mutate, range(20)))

    reloaded = creator.get(
        tenant_id="alpha",
        project_id="project-1",
        recording_id=recording.recording_id,
    )
    assert reloaded is not None
    assert reloaded.approval_status == "approved"
    assert reloaded.transcript_text.startswith("transcript-")


def test_application_constructs_recording_store_with_shared_backend() -> None:
    source_path = Path("app/main.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "MeetingRecordingStore"
    ]

    assert len(calls) == 1
    keywords = {keyword.arg for keyword in calls[0].keywords}
    assert {"base_dir", "backend"} <= keywords


def test_meeting_recording_api_reports_corrupt_metadata_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    project_id = _create_project(client)
    recording_id = "corrupt-recording"
    metadata_path = _metadata_path(
        tmp_path,
        recording_id,
        tenant_id="system",
        project_id=project_id,
    )
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text("{not-json", encoding="utf-8")

    responses = (
        client.get(f"/projects/{project_id}"),
        client.get(f"/projects/{project_id}/recordings"),
        client.get(f"/projects/{project_id}/recordings/{recording_id}"),
        client.post(
            f"/projects/{project_id}/recordings/{recording_id}/transcribe", json={}
        ),
        client.post(f"/projects/{project_id}/recordings/{recording_id}/approve"),
        client.post(
            f"/projects/{project_id}/recordings/{recording_id}/generate-documents",
            json={"bundle_types": ["meeting_minutes_kr"]},
        ),
    )

    assert all(response.status_code == 500 for response in responses)
    assert all(response.json()["code"] == "INTERNAL_ERROR" for response in responses)
    assert metadata_path.read_bytes() == b"{not-json"


def test_transcription_api_rejects_tampered_audio_before_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(tmp_path, monkeypatch)
    project_id = _create_project(client)
    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"RIFF original", "audio/wav")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]
    audio_path = _audio_path(
        tmp_path,
        recording_id,
        tenant_id="system",
        project_id=project_id,
    )
    audio_path.write_bytes(b"tampered")

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        json={},
    )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert audio_path.read_bytes() == b"tampered"


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_STATE_STORAGE", "local")
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(
        create_app(),
        headers={"X-DecisionDoc-Api-Key": "test-key"},
        raise_server_exceptions=False,
    )


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/projects",
        json={"name": "Recording integrity", "fiscal_year": 2026},
    )
    assert response.status_code == 200
    return response.json()["project_id"]
