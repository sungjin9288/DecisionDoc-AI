import logging
import json
import sys
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from app.observability.logging import JsonLineFormatter
from app.services.meeting_recording_service import MeetingRecordingService


def _create_client(tmp_path, monkeypatch, provider="mock", procurement_enabled=False):
    monkeypatch.setenv("DECISIONDOC_PROVIDER", provider)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv(
        "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED",
        "1" if procurement_enabled else "0",
    )
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)
    from app.main import create_app

    return TestClient(create_app())


def _captured_events(caplog, capsys) -> list[dict]:
    events = []
    for record in caplog.records:
        if isinstance(record.msg, dict):
            events.append(record.msg)
            continue
        text = record.getMessage()
        if isinstance(text, str) and text.startswith("{"):
            try:
                parsed = json.loads(text)
            except ValueError:
                continue
            if isinstance(parsed, dict):
                events.append(parsed)
    if events:
        return events

    stderr_output = capsys.readouterr().err
    for line in stderr_output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _create_project(client: TestClient) -> str:
    response = client.post("/projects", json={"name": "observability project", "fiscal_year": 2026})
    assert response.status_code == 200
    return response.json()["project_id"]


def _install_transcription_transport(
    client: TestClient,
    *,
    transcript_text: str = "회의 전사본 본문",
    language: str = "ko",
) -> None:
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


def test_logs_emitted_for_generate(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)

    response = client.post("/generate", json={"title": "obs", "goal": "capture logs"})
    assert response.status_code == 200

    events = _captured_events(caplog, capsys)
    assert any(e.get("event") == "request.completed" for e in events)
    generate_events = [e for e in events if e.get("event") == "generate.completed"]
    assert generate_events

    evt = generate_events[-1]
    assert isinstance(evt.get("request_id"), str)
    assert evt.get("status_code") == 200
    for key in ["provider_ms", "render_ms", "lints_ms", "validator_ms"]:
        assert isinstance(evt.get(key), int)
        assert evt.get(key) >= 0


def test_logs_do_not_contain_sensitive_tokens(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)

    sentinel = "SUPER_SECRET_DO_NOT_LOG"
    response = client.post(
        "/generate",
        json={
            "title": "sensitive",
            "goal": "sensitive",
            "context": sentinel,
            "constraints": sentinel,
            "assumptions": [sentinel],
        },
    )
    assert response.status_code == 200

    all_logs = "\n".join([caplog.text] + [str(r.msg) for r in caplog.records])
    assert sentinel not in all_logs
    assert "OPENAI_API_KEY" not in all_logs
    assert "GEMINI_API_KEY" not in all_logs


def test_json_formatter_includes_traceback_for_exception_records():
    formatter = JsonLineFormatter()
    try:
        raise RuntimeError("formatter boom")
    except RuntimeError:
        record = logging.getLogger("decisiondoc.test").makeRecord(
            name="decisiondoc.test",
            level=logging.ERROR,
            fn=__file__,
            lno=0,
            msg="Unhandled error during test",
            args=(),
            exc_info=sys.exc_info(),
        )

    payload = json.loads(formatter.format(record))
    assert payload["message"] == "Unhandled error during test"
    assert "traceback" in payload
    assert "RuntimeError: formatter boom" in payload["traceback"]


def test_procurement_logs_include_action_state_and_recommendation(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch, procurement_enabled=True)

    create_project = client.post("/projects", json={"name": "obs procurement", "fiscal_year": 2026})
    assert create_project.status_code == 200
    project_id = create_project.json()["project_id"]

    from app.services.g2b_collector import G2BAnnouncement
    fake = G2BAnnouncement(
        bid_number="OBS-2026-001",
        title="AI 기반 민원 서비스 고도화 사업",
        issuer="행정안전부",
        budget="5억원",
        announcement_date="2026-03-25",
        deadline="2026-05-30 17:00",
        bid_type="일반경쟁",
        category="용역",
        detail_url="https://www.g2b.go.kr/notice/OBS-2026-001",
        attachments=[],
        raw_text="입찰참가자격: 소프트웨어사업자, ISMS 보유. 유사사업 수행실적 필요.",
        source="scrape",
    )

    with patch(
        "app.services.g2b_collector.fetch_announcement_detail",
        new=AsyncMock(return_value=fake),
    ):
        imported = client.post(
            f"/projects/{project_id}/imports/g2b-opportunity",
            json={"url_or_number": "OBS-2026-001"},
        )
    assert imported.status_code == 200

    from app.storage.knowledge_store import KnowledgeStore
    KnowledgeStore(project_id, data_dir=str(tmp_path)).add_document(
        "capability.txt",
        (
            "공공 AI 서비스 구축 레퍼런스 2건, 클라우드 전환 경험, "
            "소프트웨어사업자 등록, ISMS 인증, PM/개발자/컨설턴트 인력 보유."
        ),
    )

    recommended = client.post(f"/projects/{project_id}/procurement/recommend")
    assert recommended.status_code == 200

    events = _captured_events(caplog, capsys)
    import_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/imports/g2b-opportunity"
    ]
    assert import_events
    assert import_events[-1]["procurement_action"] == "import"
    assert import_events[-1]["procurement_project_id"] == project_id
    assert import_events[-1]["procurement_operation"] == "created"
    assert import_events[-1]["procurement_source_kind"] == "g2b"
    assert import_events[-1]["procurement_source_id"] == "OBS-2026-001"

    recommend_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/procurement/recommend"
    ]
    assert recommend_events
    assert recommend_events[-1]["procurement_action"] == "recommend"
    assert recommend_events[-1]["procurement_project_id"] == project_id
    assert recommend_events[-1]["procurement_recommendation"] in {"GO", "CONDITIONAL_GO", "NO_GO"}
    assert recommend_events[-1]["procurement_checklist_action_count"] >= 0


def test_generate_logs_procurement_handoff_usage(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch, procurement_enabled=True)

    create_project = client.post("/projects", json={"name": "handoff obs", "fiscal_year": 2026})
    assert create_project.status_code == 200
    project_id = create_project.json()["project_id"]

    from app.schemas import (
        NormalizedProcurementOpportunity,
        ProcurementDecisionUpsert,
        ProcurementRecommendation,
        ProcurementRecommendationValue,
    )
    store = client.app.state.procurement_store
    snapshot = store.save_source_snapshot(
        tenant_id="system",
        project_id=project_id,
        source_kind="g2b_import",
        source_label="obs handoff",
        external_id="OBS-HANDOFF-001",
        payload={
            "announcement": {"title": "AI 기반 민원 서비스 고도화 사업"},
            "extracted_fields": {"issuer": "행정안전부"},
            "structured_context": "행정안전부 / CONDITIONAL_GO / 최신 파트너 확약서 필요",
        },
    )
    store.upsert(
        ProcurementDecisionUpsert(
            project_id=project_id,
            tenant_id="system",
            opportunity=NormalizedProcurementOpportunity(
                source_kind="g2b",
                source_id="OBS-HANDOFF-001",
                source_url="https://www.g2b.go.kr/notice/OBS-HANDOFF-001",
                title="AI 기반 민원 서비스 고도화 사업",
                issuer="행정안전부",
                budget="5억원",
                deadline="2026-05-30 17:00",
                bid_type="일반경쟁",
                category="용역",
                region="전국",
                raw_text_preview="행정안전부 / CONDITIONAL_GO",
            ),
            recommendation=ProcurementRecommendation(
                value=ProcurementRecommendationValue.CONDITIONAL_GO,
                summary="조건부 진행",
                evidence=["레퍼런스는 충분하지만 파트너 확약이 필요합니다."],
            ),
            source_snapshots=[snapshot],
        )
    )

    response = client.post(
        "/generate",
        json={
            "title": "AI 기반 민원 서비스 고도화 사업",
            "goal": "입찰 참여 여부를 판단한다",
            "bundle_type": "bid_decision_kr",
            "project_id": project_id,
        },
    )
    assert response.status_code == 200

    events = _captured_events(caplog, capsys)
    generate_events = [e for e in events if e.get("event") == "generate.completed"]
    assert generate_events
    assert generate_events[-1]["bundle_type"] == "bid_decision_kr"
    assert generate_events[-1]["procurement_handoff_used"] is True

    request_events = [
        e for e in events
        if e.get("event") == "request.completed" and e.get("path") == "/generate"
    ]
    assert request_events
    assert request_events[-1]["procurement_handoff_used"] is True


def test_meeting_recording_logs_include_operational_context(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _create_client(tmp_path, monkeypatch)
    _install_transcription_transport(
        client,
        transcript_text="참석자: PM, 개발, 운영\n논의: 일정 조정과 위험 항목 점검\n액션: API 안정화, 회의록 배포",
        language="ko",
    )
    project_id = _create_project(client)

    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("weekly-sync.m4a", b"FAKEAUDIO", "audio/m4a")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]

    transcribe = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        json={"language": "ko"},
    )
    assert transcribe.status_code == 200

    approve = client.post(f"/projects/{project_id}/recordings/{recording_id}/approve")
    assert approve.status_code == 200

    generate = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/generate-documents",
        json={"bundle_types": ["meeting_minutes_kr", "project_report_kr"]},
    )
    assert generate.status_code == 200

    events = _captured_events(caplog, capsys)

    upload_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings"
        and event.get("meeting_recording_action") == "upload"
    ]
    assert upload_events
    assert upload_events[-1]["meeting_recording_project_id"] == project_id
    assert upload_events[-1]["meeting_recording_recording_id"] == recording_id
    assert upload_events[-1]["meeting_recording_file_size_bytes"] == len(b"FAKEAUDIO")
    assert upload_events[-1]["meeting_recording_transcription_status"] == "uploaded"
    assert upload_events[-1]["meeting_recording_approval_status"] == "pending"

    transcribe_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}/transcribe"
    ]
    assert transcribe_events
    assert transcribe_events[-1]["meeting_recording_action"] == "transcribe"
    assert transcribe_events[-1]["meeting_recording_project_id"] == project_id
    assert transcribe_events[-1]["meeting_recording_recording_id"] == recording_id
    assert transcribe_events[-1]["meeting_recording_transcription_status"] == "completed"
    assert transcribe_events[-1]["meeting_recording_transcript_language"] == "ko"
    assert transcribe_events[-1]["meeting_recording_transcript_model"]

    approve_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}/approve"
    ]
    assert approve_events
    assert approve_events[-1]["meeting_recording_action"] == "approve"
    assert approve_events[-1]["meeting_recording_approval_status"] == "approved"

    generate_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}/generate-documents"
    ]
    assert generate_events
    assert generate_events[-1]["meeting_recording_action"] == "generate_documents"
    assert generate_events[-1]["meeting_recording_generated_bundle_count"] == 2
    assert generate_events[-1]["meeting_recording_generated_bundle_types"] == [
        "meeting_minutes_kr",
        "project_report_kr",
    ]
    assert generate_events[-1]["meeting_recording_transcription_status"] == "completed"
    assert generate_events[-1]["meeting_recording_approval_status"] == "approved"


def test_meeting_recording_logs_capture_upload_validation_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("notes.txt", b"not-audio", "text/plain")},
    )
    assert response.status_code == 422

    events = _captured_events(caplog, capsys)
    upload_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings"
        and event.get("meeting_recording_action") == "upload"
    ]
    assert upload_events
    assert upload_events[-1]["status_code"] == 422
    assert upload_events[-1]["error_code"] == "meeting_recording_upload_invalid"
    assert upload_events[-1]["meeting_recording_project_id"] == project_id
    assert upload_events[-1]["meeting_recording_file_size_bytes"] == len(b"not-audio")


def test_meeting_recording_logs_capture_upload_size_validation_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("MEETING_RECORDING_MAX_UPLOAD_BYTES", "4")
    client = _create_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    response = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"12345", "audio/wav")},
    )
    assert response.status_code == 422

    events = _captured_events(caplog, capsys)
    upload_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings"
        and event.get("meeting_recording_action") == "upload"
    ]
    assert upload_events
    assert upload_events[-1]["status_code"] == 422
    assert upload_events[-1]["error_code"] == "meeting_recording_upload_invalid"
    assert upload_events[-1]["meeting_recording_project_id"] == project_id
    assert upload_events[-1]["meeting_recording_file_size_bytes"] == len(b"12345")


def test_meeting_recording_logs_capture_upload_missing_project_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/projects/missing-project/recordings",
        files={"file": ("meeting.wav", b"1234", "audio/wav")},
    )
    assert response.status_code == 404

    events = _captured_events(caplog, capsys)
    upload_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == "/projects/missing-project/recordings"
        and event.get("meeting_recording_action") == "upload"
    ]
    assert upload_events
    assert upload_events[-1]["status_code"] == 404
    assert upload_events[-1]["error_code"] == "project_not_found"
    assert upload_events[-1]["meeting_recording_project_id"] == "missing-project"
    assert upload_events[-1]["meeting_recording_file_size_bytes"] == len(b"1234")


def test_meeting_recording_logs_capture_list_and_get_success(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]

    listing = client.get(f"/projects/{project_id}/recordings")
    assert listing.status_code == 200

    detail = client.get(f"/projects/{project_id}/recordings/{recording_id}")
    assert detail.status_code == 200

    events = _captured_events(caplog, capsys)
    list_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings"
        and event.get("meeting_recording_action") == "list"
    ]
    assert list_events
    assert list_events[-1]["status_code"] == 200
    assert list_events[-1]["meeting_recording_project_id"] == project_id

    get_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}"
        and event.get("meeting_recording_action") == "get"
    ]
    assert get_events
    assert get_events[-1]["status_code"] == 200
    assert get_events[-1]["meeting_recording_project_id"] == project_id
    assert get_events[-1]["meeting_recording_recording_id"] == recording_id
    assert get_events[-1]["meeting_recording_transcription_status"] == "uploaded"
    assert get_events[-1]["meeting_recording_approval_status"] == "pending"


def test_meeting_recording_logs_capture_list_missing_project_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)

    response = client.get("/projects/missing-project/recordings")
    assert response.status_code == 404

    events = _captured_events(caplog, capsys)
    list_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == "/projects/missing-project/recordings"
        and event.get("meeting_recording_action") == "list"
    ]
    assert list_events
    assert list_events[-1]["status_code"] == 404
    assert list_events[-1]["error_code"] == "project_not_found"
    assert list_events[-1]["meeting_recording_project_id"] == "missing-project"


def test_meeting_recording_logs_capture_transcription_config_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    client = _create_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        json={},
    )
    assert response.status_code == 503

    events = _captured_events(caplog, capsys)
    transcribe_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}/transcribe"
    ]
    assert transcribe_events
    assert transcribe_events[-1]["status_code"] == 503
    assert transcribe_events[-1]["error_code"] == "meeting_recording_transcription_not_configured"
    assert transcribe_events[-1]["meeting_recording_action"] == "transcribe"
    assert transcribe_events[-1]["meeting_recording_project_id"] == project_id
    assert transcribe_events[-1]["meeting_recording_recording_id"] == recording_id
    assert transcribe_events[-1]["meeting_recording_transcription_status"] == "uploaded"
    assert transcribe_events[-1]["meeting_recording_approval_status"] == "pending"


def test_meeting_recording_logs_capture_transcription_failures(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _create_client(tmp_path, monkeypatch)
    _install_transcription_failure_transport(client, error_message="upstream transcription failed")
    project_id = _create_project(client)

    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        json={},
    )
    assert response.status_code == 502

    events = _captured_events(caplog, capsys)
    transcribe_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}/transcribe"
    ]
    assert transcribe_events
    assert transcribe_events[-1]["status_code"] == 502
    assert transcribe_events[-1]["error_code"] == "meeting_recording_transcription_failed"
    assert transcribe_events[-1]["meeting_recording_transcription_status"] == "failed"
    assert transcribe_events[-1]["meeting_recording_approval_status"] == "pending"
    assert transcribe_events[-1]["meeting_recording_transcript_error"] == "upstream transcription failed"


def test_meeting_recording_logs_capture_approval_state_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/approve",
    )
    assert response.status_code == 409

    events = _captured_events(caplog, capsys)
    approve_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}/approve"
    ]
    assert approve_events
    assert approve_events[-1]["status_code"] == 409
    assert approve_events[-1]["error_code"] == "meeting_recording_not_ready_for_approval"
    assert approve_events[-1]["meeting_recording_transcription_status"] == "uploaded"
    assert approve_events[-1]["meeting_recording_approval_status"] == "pending"


def test_meeting_recording_logs_capture_generation_state_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _create_client(tmp_path, monkeypatch)
    _install_transcription_transport(client, transcript_text="간단한 전사")
    project_id = _create_project(client)

    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]

    transcribe = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        json={},
    )
    assert transcribe.status_code == 200

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/generate-documents",
        json={},
    )
    assert response.status_code == 409

    events = _captured_events(caplog, capsys)
    generate_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}/generate-documents"
    ]
    assert generate_events
    assert generate_events[-1]["status_code"] == 409
    assert generate_events[-1]["error_code"] == "meeting_recording_not_ready_for_generation"
    assert generate_events[-1]["meeting_recording_transcription_status"] == "completed"
    assert generate_events[-1]["meeting_recording_approval_status"] == "pending"


def test_meeting_recording_logs_capture_bundle_validation_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    client = _create_client(tmp_path, monkeypatch)
    _install_transcription_transport(client, transcript_text="간단한 전사")
    project_id = _create_project(client)

    upload = client.post(
        f"/projects/{project_id}/recordings",
        files={"file": ("meeting.wav", b"RIFF....fakewav", "audio/wav")},
    )
    assert upload.status_code == 200
    recording_id = upload.json()["recording"]["recording_id"]

    transcribe = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/transcribe",
        json={},
    )
    assert transcribe.status_code == 200

    approve = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/approve",
    )
    assert approve.status_code == 200

    response = client.post(
        f"/projects/{project_id}/recordings/{recording_id}/generate-documents",
        json={"bundle_types": ["unknown_bundle"]},
    )
    assert response.status_code == 422

    events = _captured_events(caplog, capsys)
    generate_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/{recording_id}/generate-documents"
    ]
    assert generate_events
    assert generate_events[-1]["status_code"] == 422
    assert generate_events[-1]["error_code"] == "meeting_recording_bundle_invalid"
    assert generate_events[-1]["meeting_recording_transcription_status"] == "completed"
    assert generate_events[-1]["meeting_recording_approval_status"] == "approved"


def test_meeting_recording_logs_capture_get_missing_recording_errors(tmp_path, monkeypatch, caplog, capsys):
    caplog.set_level(logging.INFO)
    client = _create_client(tmp_path, monkeypatch)
    project_id = _create_project(client)

    response = client.get(
        f"/projects/{project_id}/recordings/missing-recording",
    )
    assert response.status_code == 404

    events = _captured_events(caplog, capsys)
    get_events = [
        event for event in events
        if event.get("event") == "request.completed"
        and event.get("path") == f"/projects/{project_id}/recordings/missing-recording"
        and event.get("meeting_recording_action") == "get"
    ]
    assert get_events
    assert get_events[-1]["status_code"] == 404
    assert get_events[-1]["error_code"] == "meeting_recording_not_found"
    assert get_events[-1]["meeting_recording_project_id"] == project_id
    assert get_events[-1]["meeting_recording_recording_id"] == "missing-recording"
