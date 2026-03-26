#!/usr/bin/env python3
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx


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


def _tenant_headers() -> dict[str, str]:
    tenant_id = os.getenv("SMOKE_TENANT_ID", "").strip()
    if not tenant_id or tenant_id == "system":
        return {}
    return {"X-Tenant-ID": tenant_id}


def _auth_headers(api_key: str, token: str) -> dict[str, str]:
    return {
        "X-DecisionDoc-Api-Key": api_key,
        "Authorization": f"Bearer {token}",
        **_tenant_headers(),
    }


def _register_or_login(client: httpx.Client, base_url: str) -> tuple[str, str]:
    username = os.getenv("VOICE_BRIEF_SMOKE_USERNAME", "").strip()
    password = os.getenv("VOICE_BRIEF_SMOKE_PASSWORD", "").strip()
    public_headers = _tenant_headers()

    if username and password:
        login = client.post(
            f"{base_url}/auth/login",
            headers=public_headers,
            json={"username": username, "password": password},
        )
        body = _assert_status("POST /auth/login", login, 200)
        token = str(body.get("access_token", "")).strip()
        if not token:
            raise SystemExit("POST /auth/login missing access_token")
        return token, username

    generated_username = f"vb_smoke_{int(time.time())}_{uuid4().hex[:6]}"
    generated_password = f"VoiceBriefSmoke1!{uuid4().hex[:8]}"
    register = client.post(
        f"{base_url}/auth/register",
        headers=public_headers,
        json={
            "username": generated_username,
            "display_name": "Voice Brief Smoke",
            "email": f"{generated_username}@example.invalid",
            "password": generated_password,
        },
    )
    if register.status_code == 403:
        raise SystemExit(
            "Voice Brief smoke could not bootstrap a user because the tenant already has users. "
            "Set VOICE_BRIEF_SMOKE_USERNAME and VOICE_BRIEF_SMOKE_PASSWORD for this stage."
        )
    body = _assert_status("POST /auth/register", register, 200)
    token = str(body.get("access_token", "")).strip()
    if not token:
        raise SystemExit("POST /auth/register missing access_token")
    return token, generated_username


def _print_result(
    endpoint: str,
    status_code: int,
    *,
    project_id: str = "",
    doc_id: str = "",
    recording_id: str = "",
    operation: str = "",
) -> None:
    parts = [f"{endpoint} -> {status_code}"]
    if project_id:
        parts.append(f"project_id={project_id}")
    if doc_id:
        parts.append(f"doc_id={doc_id}")
    if recording_id:
        parts.append(f"recording_id={recording_id}")
    if operation:
        parts.append(f"operation={operation}")
    print(" ".join(parts))


def main() -> int:
    base_url = _required_env("SMOKE_BASE_URL").rstrip("/")
    api_key = _required_env("SMOKE_API_KEY")
    recording_id = _required_env("VOICE_BRIEF_SMOKE_RECORDING_ID")
    revision_id = os.getenv("VOICE_BRIEF_SMOKE_REVISION_ID", "").strip()
    timeout_sec = float(os.getenv("SMOKE_TIMEOUT_SEC", "30"))
    fiscal_year = datetime.now(timezone.utc).year

    with httpx.Client(timeout=timeout_sec) as client:
        token, username = _register_or_login(client, base_url)
        headers = _auth_headers(api_key, token)

        create_project = client.post(
            f"{base_url}/projects",
            headers=headers,
            json={
                "name": f"Voice Brief Smoke {int(time.time())}",
                "description": f"smoke-created-by:{username}",
                "fiscal_year": fiscal_year,
            },
        )
        create_body = _assert_status("POST /projects", create_project, 200)
        project_id = str(create_body.get("project_id", "")).strip()
        if not project_id:
            raise SystemExit("POST /projects missing project_id")

        import_payload = {"recording_id": recording_id}
        if revision_id:
            import_payload["revision_id"] = revision_id

        voice_brief_import = client.post(
            f"{base_url}/projects/{project_id}/imports/voice-brief",
            headers=headers,
            json=import_payload,
        )
        import_body = _assert_status(
            "POST /projects/{project_id}/imports/voice-brief",
            voice_brief_import,
            200,
        )
        operation = str(import_body.get("operation", "")).strip()
        if operation not in {"created", "updated"}:
            raise SystemExit("Voice Brief import response missing valid operation")

        document = import_body.get("document")
        if not isinstance(document, dict):
            raise SystemExit("Voice Brief import response missing document payload")
        doc_id = str(document.get("doc_id", "")).strip()
        if not doc_id:
            raise SystemExit("Voice Brief import response missing doc_id")
        if document.get("source_kind") != "voice_brief":
            raise SystemExit("Imported project document missing source_kind=voice_brief")

        get_project = client.get(f"{base_url}/projects/{project_id}", headers=headers)
        project_body = _assert_status("GET /projects/{project_id}", get_project, 200)
        documents = project_body.get("documents")
        if not isinstance(documents, list) or not documents:
            raise SystemExit("Project detail missing imported document")

        imported_doc = next((item for item in documents if item.get("doc_id") == doc_id), None)
        if not isinstance(imported_doc, dict):
            raise SystemExit("Imported document was not found in project detail")

        returned_recording_id = str(
            import_body.get("voice_brief", {}).get("recording_id")
            or imported_doc.get("source_recording_id")
            or ""
        ).strip()
        if not returned_recording_id:
            raise SystemExit("Voice Brief import did not return source recording metadata")
        if imported_doc.get("source_recording_id") != returned_recording_id:
            raise SystemExit("Stored project document source_recording_id does not match import response")

        returned_revision_id = str(
            import_body.get("voice_brief", {}).get("summary_revision_id")
            or imported_doc.get("source_summary_revision_id")
            or ""
        ).strip()
        if not returned_revision_id:
            raise SystemExit("Voice Brief import did not persist source summary revision metadata")

        _print_result(
            "POST /projects/{project_id}/imports/voice-brief",
            voice_brief_import.status_code,
            project_id=project_id,
            doc_id=doc_id,
            recording_id=returned_recording_id,
            operation=operation,
        )

    print("Voice Brief smoke completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
