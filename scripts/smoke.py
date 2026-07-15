#!/usr/bin/env python3
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.procurement_smoke import run_procurement_smoke  # noqa: E402
from scripts.smoke_support import (  # noqa: E402
    _assert_status,
    _json_body,
    _print_result,
    _tenant_headers,
)

_DOCUMENT_UPLOAD_SAMPLE = (
    b"Project title: Smoke Upload\n"
    b"Goal: Validate uploaded document generation\n"
    b"Constraints: Keep auditability first.\n"
)
DEFAULT_SMOKE_TIMEOUT_SEC = "60"
_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK\x03\x04"


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _assert_binary_response(
    endpoint: str, response: httpx.Response, expected: int, expected_magic: bytes
) -> None:
    if response.status_code != expected:
        body = _json_body(response)
        code = body.get("code", "unknown")
        message = str(body.get("message", "")).strip()
        detail_suffix = f"; message={message}" if message else ""
        raise SystemExit(
            f"{endpoint} expected {expected}, got {response.status_code} (code={code}{detail_suffix})"
        )
    if not response.content.startswith(expected_magic):
        raise SystemExit(
            f"{endpoint} returned invalid binary magic bytes: {response.content[:8].hex()}"
        )


def _assert_zip_entries(
    endpoint: str, content: bytes, required_entries: set[str]
) -> None:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        raise SystemExit(f"{endpoint} returned invalid ZIP/HWPX bytes")
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = set(zf.namelist())
    missing = sorted(required_entries - names)
    if missing:
        raise SystemExit(
            f"{endpoint} missing required ZIP/HWPX entries: {', '.join(missing)}"
        )


def _assert_content_disposition_extension(
    endpoint: str, response: httpx.Response, expected_ext: str
) -> None:
    disposition = response.headers.get("content-disposition", "")
    needle = f".{expected_ext.lower()}"
    if needle not in disposition.lower():
        raise SystemExit(
            f"{endpoint} returned unexpected content-disposition: {disposition}"
        )


def _run_export_edited_pdf_smoke(
    client: httpx.Client, *, base_url: str, api_key: str
) -> None:
    endpoint = "POST /generate/export-edited PDF (auth)"
    headers = {"X-DecisionDoc-Api-Key": api_key, **_tenant_headers()}
    payload = {
        "format": "pdf",
        "title": "Smoke Export Edited PDF",
        "docs": [
            {
                "doc_type": "business_understanding",
                "markdown": "# Smoke Export Edited PDF\n\n- Validate deployed Playwright PDF rendering.\n- Confirm export-edited does not return a proxy/runtime error.",
            },
            {
                "doc_type": "tech_proposal",
                "markdown": "# Runtime Check\n\n| Check | Expected |\n| --- | --- |\n| Magic bytes | %PDF |\n| Content-Type | application/pdf |",
            },
        ],
    }
    response = client.post(
        f"{base_url}/generate/export-edited", headers=headers, json=payload
    )
    _assert_binary_response(endpoint, response, 200, _PDF_MAGIC)
    content_type = response.headers.get("content-type", "")
    if "application/pdf" not in content_type.lower():
        raise SystemExit(f"{endpoint} returned unexpected content-type: {content_type}")
    _print_result(
        endpoint, response.status_code, extra=f"bytes={len(response.content)}"
    )


def _run_export_edited_hwpx_smoke(
    client: httpx.Client, *, base_url: str, api_key: str
) -> None:
    endpoint = "POST /generate/export-edited HWPX (auth)"
    headers = {"X-DecisionDoc-Api-Key": api_key, **_tenant_headers()}
    payload = {
        "format": "hwp",
        "title": "Smoke Export Edited HWPX",
        "docs": [
            {
                "doc_type": "business_understanding",
                "markdown": "# Smoke Export Edited HWPX\n\n- Validate deployed HWPX ZIP rendering.\n- Confirm HWP button downloads `.hwpx` bytes, not legacy binary `.hwp`.",
            },
            {
                "doc_type": "tech_proposal",
                "markdown": "# Runtime Check\n\n| Check | Expected |\n| --- | --- |\n| Magic bytes | PK |\n| Content-Type | application/hwp+zip |\n| Extension | .hwpx |",
            },
        ],
    }
    response = client.post(
        f"{base_url}/generate/export-edited", headers=headers, json=payload
    )
    _assert_binary_response(endpoint, response, 200, _ZIP_MAGIC)
    content_type = response.headers.get("content-type", "")
    if "application/hwp+zip" not in content_type.lower():
        raise SystemExit(f"{endpoint} returned unexpected content-type: {content_type}")
    _assert_content_disposition_extension(endpoint, response, "hwpx")
    _assert_zip_entries(
        endpoint,
        response.content,
        {"mimetype", "Contents/header.xml", "Contents/section0.xml"},
    )
    _print_result(
        endpoint, response.status_code, extra=f"bytes={len(response.content)} ext=hwpx"
    )


def _is_enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _document_upload_files() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "files",
            (
                "smoke-upload.txt",
                _DOCUMENT_UPLOAD_SAMPLE,
                "text/plain",
            ),
        )
    ]


def _attachment_generation_files() -> list[tuple[str, tuple[str, bytes, str]]]:
    return [
        (
            "attachments",
            (
                "smoke-attachment.txt",
                _DOCUMENT_UPLOAD_SAMPLE,
                "text/plain",
            ),
        )
    ]


def _run_attachment_generation_smoke(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
) -> None:
    payload = json.dumps(
        {
            "title": "Smoke Attachment",
            "goal": "Verify uploaded attachment generation",
            "context": "attachment smoke",
        }
    )

    no_auth = client.post(
        f"{base_url}/generate/with-attachments",
        data={"payload": payload},
        files=_attachment_generation_files(),
    )
    no_auth_body = _assert_status(
        "POST /generate/with-attachments (no key)", no_auth, 401
    )
    if no_auth_body.get("code") != "UNAUTHORIZED":
        raise SystemExit(
            "POST /generate/with-attachments (no key) did not return UNAUTHORIZED"
        )
    _print_result(
        "POST /generate/with-attachments (no key)",
        no_auth.status_code,
        request_id=str(no_auth_body.get("request_id", "")),
    )

    uploaded = client.post(
        f"{base_url}/generate/with-attachments",
        headers={"X-DecisionDoc-Api-Key": api_key},
        data={"payload": payload},
        files=_attachment_generation_files(),
    )
    uploaded_body = _assert_status(
        "POST /generate/with-attachments (auth)", uploaded, 200
    )
    uploaded_bundle_id = str(uploaded_body.get("bundle_id", ""))
    uploaded_request_id = str(uploaded_body.get("request_id", ""))
    docs = uploaded_body.get("docs")
    if not uploaded_bundle_id:
        raise SystemExit("POST /generate/with-attachments (auth) missing bundle_id")
    if not isinstance(docs, list) or not docs:
        raise SystemExit("POST /generate/with-attachments (auth) missing docs")
    _print_result(
        "POST /generate/with-attachments (auth)",
        uploaded.status_code,
        request_id=uploaded_request_id,
        bundle_id=uploaded_bundle_id,
        extra=f"files=1 docs={len(docs)}",
    )


def _run_document_upload_smoke(
    client: httpx.Client,
    *,
    base_url: str,
    api_key: str,
) -> None:
    data = {
        "doc_types": "adr,onepager",
        "goal": "Verify uploaded document generation",
    }

    no_auth = client.post(
        f"{base_url}/generate/from-documents",
        data=data,
        files=_document_upload_files(),
    )
    no_auth_body = _assert_status(
        "POST /generate/from-documents (no key)", no_auth, 401
    )
    if no_auth_body.get("code") != "UNAUTHORIZED":
        raise SystemExit(
            "POST /generate/from-documents (no key) did not return UNAUTHORIZED"
        )
    _print_result(
        "POST /generate/from-documents (no key)",
        no_auth.status_code,
        request_id=str(no_auth_body.get("request_id", "")),
    )

    uploaded = client.post(
        f"{base_url}/generate/from-documents",
        headers={"X-DecisionDoc-Api-Key": api_key},
        data=data,
        files=_document_upload_files(),
    )
    uploaded_body = _assert_status(
        "POST /generate/from-documents (auth)", uploaded, 200
    )
    uploaded_bundle_id = str(uploaded_body.get("bundle_id", ""))
    uploaded_request_id = str(uploaded_body.get("request_id", ""))
    docs = uploaded_body.get("docs")
    if not uploaded_bundle_id:
        raise SystemExit("POST /generate/from-documents (auth) missing bundle_id")
    if not isinstance(docs, list) or not docs:
        raise SystemExit("POST /generate/from-documents (auth) missing docs")
    actual_doc_types = [
        str(doc.get("doc_type", "")).strip() for doc in docs if isinstance(doc, dict)
    ]
    if actual_doc_types != ["adr", "onepager"]:
        raise SystemExit(
            "POST /generate/from-documents (auth) returned unexpected doc_types: "
            f"{actual_doc_types!r}"
        )
    _print_result(
        "POST /generate/from-documents (auth)",
        uploaded.status_code,
        request_id=uploaded_request_id,
        bundle_id=uploaded_bundle_id,
        extra=f"files=1 docs={len(docs)}",
    )


def main() -> int:
    base_url = _required_env("SMOKE_BASE_URL").rstrip("/")
    api_key = _required_env("SMOKE_API_KEY")
    provider = os.getenv("SMOKE_PROVIDER", "mock").strip() or "mock"
    timeout_sec = float(os.getenv("SMOKE_TIMEOUT_SEC", DEFAULT_SMOKE_TIMEOUT_SEC))
    include_procurement = _is_enabled(os.getenv("SMOKE_INCLUDE_PROCUREMENT", "0"))
    procurement_url_or_number = os.getenv("SMOKE_PROCUREMENT_URL_OR_NUMBER", "").strip()

    payload = {
        "title": "Smoke Check",
        "goal": "Verify deployed generate endpoints",
        "context": f"provider={provider}",
    }

    with httpx.Client(timeout=timeout_sec) as client:
        health = client.get(f"{base_url}/health")
        _assert_status("GET /health", health, 200)
        _print_result(
            "GET /health",
            health.status_code,
            request_id=health.headers.get("X-Request-Id", ""),
        )

        no_auth = client.post(f"{base_url}/generate", json=payload)
        no_auth_body = _assert_status("POST /generate (no key)", no_auth, 401)
        if no_auth_body.get("code") != "UNAUTHORIZED":
            raise SystemExit("POST /generate (no key) did not return UNAUTHORIZED")
        _print_result(
            "POST /generate (no key)",
            no_auth.status_code,
            request_id=str(no_auth_body.get("request_id", "")),
        )

        api_key_headers = {"X-DecisionDoc-Api-Key": api_key}
        generate = client.post(
            f"{base_url}/generate", headers=api_key_headers, json=payload
        )
        generate_body = _assert_status("POST /generate (auth)", generate, 200)
        generate_bundle_id = str(generate_body.get("bundle_id", ""))
        generate_request_id = str(generate_body.get("request_id", ""))
        if not generate_bundle_id:
            raise SystemExit("POST /generate (auth) missing bundle_id")
        _print_result(
            "POST /generate (auth)",
            generate.status_code,
            request_id=generate_request_id,
            bundle_id=generate_bundle_id,
        )

        export = client.post(
            f"{base_url}/generate/export", headers=api_key_headers, json=payload
        )
        export_body = _assert_status("POST /generate/export (auth)", export, 200)
        export_bundle_id = str(export_body.get("bundle_id", ""))
        export_request_id = str(export_body.get("request_id", ""))
        files = export_body.get("files")
        if not export_bundle_id:
            raise SystemExit("POST /generate/export (auth) missing bundle_id")
        if not isinstance(files, list) or not files:
            raise SystemExit("POST /generate/export (auth) missing export files")
        _print_result(
            "POST /generate/export (auth)",
            export.status_code,
            request_id=export_request_id,
            bundle_id=export_bundle_id,
            extra=f"files={len(files)}",
        )

        _run_export_edited_pdf_smoke(
            client,
            base_url=base_url,
            api_key=api_key,
        )
        _run_export_edited_hwpx_smoke(
            client,
            base_url=base_url,
            api_key=api_key,
        )

        _run_attachment_generation_smoke(
            client,
            base_url=base_url,
            api_key=api_key,
        )

        _run_document_upload_smoke(
            client,
            base_url=base_url,
            api_key=api_key,
        )

        if include_procurement:
            run_procurement_smoke(
                client,
                base_url=base_url,
                api_key=api_key,
                provider=provider,
                url_or_number=procurement_url_or_number,
            )

    print("Smoke completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
