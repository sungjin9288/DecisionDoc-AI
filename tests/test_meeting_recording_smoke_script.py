from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx


def _load_meeting_recording_smoke_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "meeting_recording_smoke.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_meeting_recording_smoke_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _install_mock_runtime(monkeypatch, module, tmp_path, handler) -> Path:
    fixture_path = tmp_path / "meeting_recording_smoke.wav"
    fixture_path.write_bytes(b"RIFF....fakewav")
    real_client = httpx.Client

    monkeypatch.setenv("SMOKE_BASE_URL", "https://example.com")
    monkeypatch.setenv("SMOKE_API_KEY", "smoke-key")
    monkeypatch.setenv("MEETING_RECORDING_SMOKE_LANGUAGE", "ko")
    monkeypatch.setattr(module, "FIXTURE_AUDIO_PATH", fixture_path)
    monkeypatch.setattr(
        module.httpx,
        "Client",
        lambda *args, **kwargs: real_client(
            transport=httpx.MockTransport(handler),
            timeout=kwargs.get("timeout"),
        ),
    )
    return fixture_path


def test_meeting_recording_smoke_completes_happy_path(tmp_path, monkeypatch, capsys):
    smoke = _load_meeting_recording_smoke_module()
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        if request.method == "POST" and request.url.path == "/projects/project-123/recordings":
            return httpx.Response(200, json={"recording": {"recording_id": "rec-123"}})
        if request.method == "POST" and request.url.path == "/projects/project-123/recordings/rec-123/transcribe":
            return httpx.Response(200, json={"recording": {"transcript_text": "회의 전사본 본문"}})
        if request.method == "POST" and request.url.path == "/projects/project-123/recordings/rec-123/approve":
            return httpx.Response(200, json={"recording": {"approval_status": "approved"}})
        if request.method == "POST" and request.url.path == "/projects/project-123/recordings/rec-123/generate-documents":
            return httpx.Response(
                200,
                json={
                    "generated_documents": [
                        {"bundle_type": "meeting_minutes_kr"},
                        {"bundle_type": "project_report_kr"},
                    ]
                },
            )
        if request.method == "GET" and request.url.path == "/projects/project-123":
            return httpx.Response(
                200,
                json={
                    "documents": [
                        {"source_kind": "meeting_recording", "source_recording_id": "rec-123"},
                        {"source_kind": "meeting_recording", "source_recording_id": "rec-123"},
                    ]
                },
            )
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    _install_mock_runtime(monkeypatch, smoke, tmp_path, handler)

    assert smoke.main() == 0
    captured = capsys.readouterr().out
    assert "Meeting recording smoke completed." in captured
    assert calls == [
        ("POST", "/projects"),
        ("POST", "/projects/project-123/recordings"),
        ("POST", "/projects/project-123/recordings/rec-123/transcribe"),
        ("POST", "/projects/project-123/recordings/rec-123/approve"),
        ("POST", "/projects/project-123/recordings/rec-123/generate-documents"),
        ("GET", "/projects/project-123"),
    ]


def test_meeting_recording_smoke_fails_when_project_detail_loses_source_links(tmp_path, monkeypatch):
    smoke = _load_meeting_recording_smoke_module()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/projects":
            return httpx.Response(200, json={"project_id": "project-123"})
        if request.method == "POST" and request.url.path == "/projects/project-123/recordings":
            return httpx.Response(200, json={"recording": {"recording_id": "rec-123"}})
        if request.method == "POST" and request.url.path == "/projects/project-123/recordings/rec-123/transcribe":
            return httpx.Response(200, json={"recording": {"transcript_text": "회의 전사본 본문"}})
        if request.method == "POST" and request.url.path == "/projects/project-123/recordings/rec-123/approve":
            return httpx.Response(200, json={"recording": {"approval_status": "approved"}})
        if request.method == "POST" and request.url.path == "/projects/project-123/recordings/rec-123/generate-documents":
            return httpx.Response(
                200,
                json={
                    "generated_documents": [
                        {"bundle_type": "meeting_minutes_kr"},
                        {"bundle_type": "project_report_kr"},
                    ]
                },
            )
        if request.method == "GET" and request.url.path == "/projects/project-123":
            return httpx.Response(
                200,
                json={
                    "documents": [
                        {"source_kind": "meeting_recording", "source_recording_id": "other-rec"},
                        {"source_kind": "meeting_recording", "source_recording_id": "other-rec"},
                    ]
                },
            )
        raise AssertionError(f"Unhandled request: {request.method} {request.url}")

    _install_mock_runtime(monkeypatch, smoke, tmp_path, handler)

    try:
        smoke.main()
    except SystemExit as exc:
        assert str(exc) == "Project detail missing source-linked meeting recording documents"
    else:
        raise AssertionError("meeting recording smoke should fail when source-linked docs are missing")
