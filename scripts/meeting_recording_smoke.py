#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


FIXTURE_AUDIO_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "meeting_recording_smoke.wav"
)


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _json_body(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _assert_status(endpoint: str, response: httpx.Response, expected: int) -> dict[str, Any]:
    body = _json_body(response)
    if response.status_code != expected:
        detail = body.get("detail") or body.get("message") or body.get("error") or response.text
        raise SystemExit(
            f"{endpoint} expected {expected}, got {response.status_code} "
            f"(detail={detail})"
        )
    return body


def _print_result(
    endpoint: str,
    status_code: int,
    *,
    project_id: str = "",
    recording_id: str = "",
    extra: str = "",
) -> None:
    parts = [f"{endpoint} -> {status_code}"]
    if project_id:
        parts.append(f"project_id={project_id}")
    if recording_id:
        parts.append(f"recording_id={recording_id}")
    if extra:
        parts.append(extra)
    print(" ".join(parts))


def _tenant_headers() -> dict[str, str]:
    tenant_id = os.getenv("SMOKE_TENANT_ID", "").strip()
    if not tenant_id or tenant_id == "system":
        return {}
    return {"X-Tenant-ID": tenant_id}


def _api_headers(api_key: str) -> dict[str, str]:
    return {"X-DecisionDoc-Api-Key": api_key, **_tenant_headers()}


def _fixture_audio_path() -> Path:
    if not FIXTURE_AUDIO_PATH.exists():
        raise SystemExit(f"Missing fixture audio file: {FIXTURE_AUDIO_PATH}")
    return FIXTURE_AUDIO_PATH


def main() -> int:
    base_url = _required_env("SMOKE_BASE_URL").rstrip("/")
    api_key = _required_env("SMOKE_API_KEY")
    timeout_sec = float(os.getenv("SMOKE_TIMEOUT_SEC", "120"))
    language = os.getenv("MEETING_RECORDING_SMOKE_LANGUAGE", "en").strip() or "en"
    headers = _api_headers(api_key)
    fixture_path = _fixture_audio_path()

    with httpx.Client(timeout=timeout_sec) as client:
        create_project = client.post(
            f"{base_url}/projects",
            headers={**headers, "Content-Type": "application/json"},
            json={
                "name": f"Meeting Recording Smoke {uuid4().hex[:8]}",
                "fiscal_year": 2026,
            },
        )
        create_body = _assert_status("POST /projects", create_project, 200)
        project_id = str(create_body.get("project_id", "")).strip()
        if not project_id:
            raise SystemExit("POST /projects missing project_id")

        with fixture_path.open("rb") as audio_file:
            upload = client.post(
                f"{base_url}/projects/{project_id}/recordings",
                headers=headers,
                files={
                    "file": (
                        fixture_path.name,
                        audio_file,
                        "audio/wav",
                    )
                },
            )
        upload_body = _assert_status("POST /projects/{project_id}/recordings", upload, 200)
        recording = upload_body.get("recording")
        if not isinstance(recording, dict):
            raise SystemExit("Upload response missing recording payload")
        recording_id = str(recording.get("recording_id", "")).strip()
        if not recording_id:
            raise SystemExit("Upload response missing recording_id")

        transcribe = client.post(
            f"{base_url}/projects/{project_id}/recordings/{recording_id}/transcribe",
            headers={**headers, "Content-Type": "application/json"},
            json={"language": language},
        )
        transcribe_body = _assert_status(
            "POST /projects/{project_id}/recordings/{recording_id}/transcribe",
            transcribe,
            200,
        )
        transcribed_recording = transcribe_body.get("recording")
        if not isinstance(transcribed_recording, dict):
            raise SystemExit("Transcribe response missing recording payload")
        transcript_text = str(transcribed_recording.get("transcript_text", "")).strip()
        if not transcript_text:
            raise SystemExit("Transcribe response returned empty transcript_text")

        approve = client.post(
            f"{base_url}/projects/{project_id}/recordings/{recording_id}/approve",
            headers=headers,
        )
        approve_body = _assert_status(
            "POST /projects/{project_id}/recordings/{recording_id}/approve",
            approve,
            200,
        )
        approved_recording = approve_body.get("recording")
        if (
            not isinstance(approved_recording, dict)
            or approved_recording.get("approval_status") != "approved"
        ):
            raise SystemExit("Approve response missing approval_status=approved")

        generate = client.post(
            f"{base_url}/projects/{project_id}/recordings/{recording_id}/generate-documents",
            headers={**headers, "Content-Type": "application/json"},
            json={"bundle_types": ["meeting_minutes_kr", "project_report_kr"]},
        )
        generate_body = _assert_status(
            "POST /projects/{project_id}/recordings/{recording_id}/generate-documents",
            generate,
            200,
        )
        generated_documents = generate_body.get("generated_documents")
        if not isinstance(generated_documents, list) or len(generated_documents) != 2:
            raise SystemExit("Generate response missing generated_documents payload")
        generated_bundle_types = [
            str(item.get("bundle_type", "")).strip()
            for item in generated_documents
            if isinstance(item, dict)
        ]
        if generated_bundle_types != ["meeting_minutes_kr", "project_report_kr"]:
            raise SystemExit(f"Unexpected generated bundle types: {generated_bundle_types}")

        project_detail = client.get(f"{base_url}/projects/{project_id}", headers=headers)
        project_body = _assert_status("GET /projects/{project_id}", project_detail, 200)
        documents = project_body.get("documents")
        if not isinstance(documents, list) or len(documents) < 2:
            raise SystemExit("Project detail missing generated documents")
        meeting_docs = [
            item
            for item in documents
            if isinstance(item, dict)
            and item.get("source_kind") == "meeting_recording"
            and item.get("source_recording_id") == recording_id
        ]
        if len(meeting_docs) < 2:
            raise SystemExit("Project detail missing source-linked meeting recording documents")

        _print_result(
            "POST /projects/{project_id}/recordings/{recording_id}/generate-documents",
            generate.status_code,
            project_id=project_id,
            recording_id=recording_id,
            extra=f"transcript_preview={transcript_text[:80]!r}",
        )

    print("Meeting recording smoke completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
