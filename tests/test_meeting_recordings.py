from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.meeting_recording_service import MeetingRecordingService


HEADERS = {"X-DecisionDoc-Api-Key": "test-key"}


def _build_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_API_KEY", "test-key")
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    return TestClient(create_app())


def _create_project(client: TestClient) -> str:
    response = client.post("/projects", json={"name": "회의 녹음 프로젝트", "fiscal_year": 2026}, headers=HEADERS)
    assert response.status_code == 200
    return response.json()["project_id"]


def _install_transcription_transport(client: TestClient, *, transcript_text: str = "회의 전사본 본문", language: str = "ko") -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/audio/transcriptions")
        return httpx.Response(200, json={"text": transcript_text, "language": language})

    client.app.state.meeting_recording_service = MeetingRecordingService(
        recording_store=client.app.state.meeting_recording_store,
        project_store=client.app.state.project_store,
        generation_service=client.app.state.service,
        transport=httpx.MockTransport(handler),
    )


def _install_transcription_failure_transport(
    client: TestClient,
    *,
    status_code: int = 500,
    error_message: str = "upstream transcription failed",
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/audio/transcriptions")
        return httpx.Response(status_code, json={"error": {"message": error_message}})

    client.app.state.meeting_recording_service = MeetingRecordingService(
        recording_store=client.app.state.meeting_recording_store,
        project_store=client.app.state.project_store,
        generation_service=client.app.state.service,
        transport=httpx.MockTransport(handler),
    )


def test_upload_recording_endpoint_persists_recording_and_exposes_project_detail(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recording"]["filename"] == "meeting.wav"
    assert payload["recording"]["transcription_status"] == "uploaded"
    project = client.get(f"/projects/{project_id}", headers=HEADERS).json()
    assert len(project["meeting_recordings"]) == 1
    assert project["meeting_recordings"][0]["filename"] == "meeting.wav"


def test_list_and_get_recording_endpoints_return_persisted_metadata(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    upload = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]

    listing = client.get(f"/projects/{project_id}/recordings", headers=HEADERS)
    assert listing.status_code == 200
    recordings = listing.json()["recordings"]
    assert len(recordings) == 1
    assert recordings[0]["recording_id"] == recording_id
    assert recordings[0]["filename"] == "meeting.wav"
    assert recordings[0]["transcription_status"] == "uploaded"

    detail = client.get(
        f"/projects/{project_id}/recordings/{recording_id}",
        headers=HEADERS,
    )
    assert detail.status_code == 200
    payload = detail.json()["recording"]
    assert payload["recording_id"] == recording_id
    assert payload["filename"] == "meeting.wav"
    assert payload["file_size_bytes"] == len(b"RIFF....fakewav")
    assert payload["transcription_status"] == "uploaded"
    assert payload["approval_status"] == "pending"


def test_upload_recording_endpoint_rejects_unsupported_extension(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("notes.txt", b"not-audio", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "meeting_recording_upload_invalid"


def test_upload_recording_endpoint_rejects_files_over_size_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("MEETING_RECORDING_MAX_UPLOAD_BYTES", "4")
    client = _build_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("meeting.wav", b"12345", "audio/wav")},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "meeting_recording_upload_invalid"


def test_upload_recording_endpoint_returns_404_for_missing_project(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.post(
        "/projects/missing-project/recordings",
        headers=HEADERS,
        files={"file": ("meeting.wav", b"1234", "audio/wav")},
    )

    assert response.status_code == 404


def test_list_recordings_endpoint_returns_404_for_missing_project(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.get("/projects/missing-project/recordings", headers=HEADERS)

    assert response.status_code == 404


def test_transcribe_endpoint_returns_503_without_openai_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    client = _build_client(tmp_path, monkeypatch)
    project_id = _create_project(client)
    upload = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    recording_id = upload.json()["recording"]["recording_id"]

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        headers=HEADERS,
        json={},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "meeting_recording_transcription_not_configured"


def test_recording_can_be_transcribed_approved_and_generate_documents(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _build_client(tmp_path, monkeypatch)
    _install_transcription_transport(
        client,
        transcript_text="참석자: PM, 개발, 운영\n논의: 일정 조정과 위험 항목 점검\n액션: API 안정화, 회의록 배포",
    )
    project_id = _create_project(client)
    upload = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("weekly-sync.m4a", b"FAKEAUDIO", "audio/m4a")},
    )
    recording_id = upload.json()["recording"]["recording_id"]

    transcribe = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        headers=HEADERS,
        json={"language": "ko"},
    )
    assert transcribe.status_code == 200
    assert transcribe.json()["recording"]["transcription_status"] == "completed"
    assert "일정 조정" in transcribe.json()["recording"]["transcript_text"]

    approve = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/approve",
        headers=HEADERS,
    )
    assert approve.status_code == 200
    assert approve.json()["recording"]["approval_status"] == "approved"

    generate = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/generate-documents",
        headers=HEADERS,
        json={"bundle_types": ["meeting_minutes_kr", "project_report_kr"]},
    )
    assert generate.status_code == 200
    generated_documents = generate.json()["generated_documents"]
    assert [item["bundle_type"] for item in generated_documents] == ["meeting_minutes_kr", "project_report_kr"]

    project = client.get(f"/projects/{project_id}", headers=HEADERS).json()
    assert len(project["documents"]) == 2
    assert {doc["bundle_id"] for doc in project["documents"]} == {"meeting_minutes_kr", "project_report_kr"}
    assert all(doc["source_kind"] == "meeting_recording" for doc in project["documents"])
    assert all(doc["source_recording_id"] == recording_id for doc in project["documents"])


def test_generate_documents_defaults_bundle_types_when_not_provided(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _build_client(tmp_path, monkeypatch)
    _install_transcription_transport(client, transcript_text="기본 번들 테스트")
    project_id = _create_project(client)
    upload = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("weekly-sync.m4a", b"FAKEAUDIO", "audio/m4a")},
    )
    recording_id = upload.json()["recording"]["recording_id"]

    transcribe = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        headers=HEADERS,
        json={},
    )
    assert transcribe.status_code == 200

    approve = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/approve",
        headers=HEADERS,
    )
    assert approve.status_code == 200

    generate = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/generate-documents",
        headers=HEADERS,
        json={},
    )
    assert generate.status_code == 200
    generated_documents = generate.json()["generated_documents"]
    assert [item["bundle_type"] for item in generated_documents] == [
        "meeting_minutes_kr",
        "project_report_kr",
    ]


def test_generate_documents_requires_approved_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _build_client(tmp_path, monkeypatch)
    _install_transcription_transport(client, transcript_text="간단한 전사")
    project_id = _create_project(client)
    upload = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("meeting.webm", b"FAKEAUDIO", "audio/webm")},
    )
    recording_id = upload.json()["recording"]["recording_id"]
    client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        headers=HEADERS,
        json={},
    )

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/generate-documents",
        headers=HEADERS,
        json={},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "meeting_recording_not_ready_for_generation"


def test_generate_documents_rejects_unknown_bundle_type(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _build_client(tmp_path, monkeypatch)
    _install_transcription_transport(client, transcript_text="간단한 전사")
    project_id = _create_project(client)
    upload = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("meeting.webm", b"FAKEAUDIO", "audio/webm")},
    )
    recording_id = upload.json()["recording"]["recording_id"]
    transcribe = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        headers=HEADERS,
        json={},
    )
    assert transcribe.status_code == 200
    approve = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/approve",
        headers=HEADERS,
    )
    assert approve.status_code == 200

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/generate-documents",
        headers=HEADERS,
        json={"bundle_types": ["unknown_bundle"]},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "meeting_recording_bundle_invalid"


def test_transcribe_failure_marks_recording_failed_and_exposes_error(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _build_client(tmp_path, monkeypatch)
    _install_transcription_failure_transport(client, error_message="upstream transcription failed")
    project_id = _create_project(client)
    upload = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    recording_id = upload.json()["recording"]["recording_id"]

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        headers=HEADERS,
        json={},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "meeting_recording_transcription_failed"

    detail = client.get(
        f"/projects/{project_id}/recordings/{recording_id}",
        headers=HEADERS,
    )
    assert detail.status_code == 200
    payload = detail.json()["recording"]
    assert payload["transcription_status"] == "failed"
    assert payload["approval_status"] == "pending"
    assert payload["transcript_error"] == "upstream transcription failed"


def test_transcribe_rejects_empty_transcript(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _build_client(tmp_path, monkeypatch)
    _install_transcription_transport(client, transcript_text="")
    project_id = _create_project(client)
    upload = client.post(
        f"/projects/{project_id}/recordings",
        headers=HEADERS,
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    recording_id = upload.json()["recording"]["recording_id"]

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        headers=HEADERS,
        json={},
    )

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "meeting_recording_transcription_failed"

    detail = client.get(
        f"/projects/{project_id}/recordings/{recording_id}",
        headers=HEADERS,
    )
    payload = detail.json()["recording"]
    assert payload["transcription_status"] == "failed"
    assert payload["approval_status"] == "pending"
    assert payload["transcript_error"] == "OpenAI transcription response did not include transcript text."


def test_get_recording_endpoint_returns_404_for_missing_recording(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    response = client.get(
        f"/projects/{project_id}/recordings/missing-recording",
        headers=HEADERS,
    )

    assert response.status_code == 404


def test_get_recording_endpoint_returns_404_for_missing_project(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.get(
        "/projects/missing-project/recordings/missing-recording",
        headers=HEADERS,
    )

    assert response.status_code == 404
    assert "프로젝트를 찾을 수 없습니다: missing-project" in response.json()["detail"]


def test_recording_state_endpoints_return_404_for_missing_recording(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _build_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    transcribe = client.post(
        f"/projects/{project_id}/recordings/missing-recording/transcribe",
        headers=HEADERS,
        json={},
    )
    assert transcribe.status_code == 404

    approve = client.post(
        f"/projects/{project_id}/recordings/missing-recording/approve",
        headers=HEADERS,
    )
    assert approve.status_code == 404

    generate = client.post(
        f"/projects/{project_id}/recordings/missing-recording/generate-documents",
        headers=HEADERS,
        json={},
    )
    assert generate.status_code == 404


def test_recording_state_endpoints_return_404_for_missing_project(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _build_client(tmp_path, monkeypatch)

    transcribe = client.post(
        "/projects/missing-project/recordings/missing-recording/transcribe",
        headers=HEADERS,
        json={},
    )
    assert transcribe.status_code == 404
    assert "프로젝트를 찾을 수 없습니다: missing-project" in transcribe.json()["detail"]

    approve = client.post(
        "/projects/missing-project/recordings/missing-recording/approve",
        headers=HEADERS,
    )
    assert approve.status_code == 404
    assert "프로젝트를 찾을 수 없습니다: missing-project" in approve.json()["detail"]

    generate = client.post(
        "/projects/missing-project/recordings/missing-recording/generate-documents",
        headers=HEADERS,
        json={},
    )
    assert generate.status_code == 404
    assert "프로젝트를 찾을 수 없습니다: missing-project" in generate.json()["detail"]


def test_root_page_contains_meeting_recording_controls(tmp_path, monkeypatch):
    client = _build_client(tmp_path, monkeypatch)

    response = client.get("/")

    assert response.status_code == 200
    assert "회의 녹음 업로드" in response.text
    assert "meeting-recording-file" in response.text
    assert "submitMeetingRecordingUpload" in response.text
