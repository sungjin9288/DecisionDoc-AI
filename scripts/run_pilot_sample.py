#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib import request
import uuid


def _load_record_module():
    path = Path(__file__).with_name("record_pilot_run.py")
    spec = importlib.util.spec_from_file_location("decisiondoc_record_pilot_run", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_RECORD = _load_record_module()


def _resolve_api_key(explicit_api_key: str = "") -> str:
    key = explicit_api_key.strip()
    if key:
        return key
    multi_key = os.getenv("DECISIONDOC_API_KEYS", "").split(",")[0].strip()
    if multi_key:
        return multi_key
    single_key = os.getenv("DECISIONDOC_API_KEY", "").strip()
    if single_key:
        return single_key
    raise SystemExit("Missing API key. Pass --api-key or set DECISIONDOC_API_KEYS / DECISIONDOC_API_KEY.")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _post_json(base_url: str, *, path: str, api_key: str, payload: dict[str, Any], timeout_sec: int) -> dict[str, Any]:
    req = request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-DecisionDoc-Api-Key": api_key,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_multipart_body(*, payload: dict[str, Any], filename: str, content: bytes, content_type: str) -> tuple[bytes, str]:
    boundary = f"----Codex{uuid.uuid4().hex}"
    payload_text = json.dumps(payload, ensure_ascii=False)
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="payload"\r\n\r\n')
    body.extend(payload_text.encode("utf-8"))
    body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="attachments"; filename="{filename}"\r\n'.encode())
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(content)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), boundary


def _post_multipart(
    base_url: str,
    *,
    path: str,
    api_key: str,
    payload: dict[str, Any],
    filename: str,
    content: bytes,
    content_type: str,
    timeout_sec: int,
) -> dict[str, Any]:
    body, boundary = _build_multipart_body(
        payload=payload,
        filename=filename,
        content=content,
        content_type=content_type,
    )
    req = request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-DecisionDoc-Api-Key": api_key,
        },
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_sec) as response:
        return json.loads(response.read().decode("utf-8"))


def _record(run_sheet_file: Path, *, target: str, fields: dict[str, str]) -> None:
    _RECORD.record_pilot_run(
        run_sheet_file=run_sheet_file,
        target=target,
        fields=fields,
    )


def run_pilot_sample(
    *,
    run_sheet_file: Path,
    base_url: str,
    api_key: str,
    operator: str,
    business_owner: str,
    bundle_type: str,
    timeout_sec: int = 180,
) -> dict[str, Any]:
    resolved_api_key = _resolve_api_key(api_key)
    run1_payload = {
        "title": "Pilot Run 1",
        "goal": "Run 1 pilot verification",
        "context": "basic pilot flow",
        "bundle_type": bundle_type,
    }
    run2_payload = {
        "title": "Pilot Run 2",
        "goal": "Run 2 pilot attachment verification",
        "context": "attachment pilot flow",
        "bundle_type": bundle_type,
    }

    run1_started = _now_utc_iso()
    run1 = _post_json(
        base_url,
        path="/generate",
        api_key=resolved_api_key,
        payload=run1_payload,
        timeout_sec=timeout_sec,
    )
    run1_export = _post_json(
        base_url,
        path="/generate/export",
        api_key=resolved_api_key,
        payload=run1_payload,
        timeout_sec=timeout_sec,
    )
    _record(
        Path(run_sheet_file),
        target="run1",
        fields={
            "started_at": run1_started,
            "operator": operator,
            "business_owner": business_owner,
            "bundle_type": bundle_type,
            "input_summary": "live basic proposal generate",
            "request_id": str(run1.get("request_id", "")),
            "bundle_id": str(run1.get("bundle_id", "")),
            "export_checked": f"generate/export 200 files={len(run1_export.get('files') or [])}",
            "quality_feedback": "API success; manual quality review pending",
            "issues": "없음",
            "stop_decision": "continue",
        },
    )

    run2_started = _now_utc_iso()
    attachment_bytes = "Pilot attachment context\n교차로 안전 강화와 보행자 보호를 위한 AI 기반 현장 모니터링 검토\n".encode("utf-8")
    run2 = _post_multipart(
        base_url,
        path="/generate/with-attachments",
        api_key=resolved_api_key,
        payload=run2_payload,
        filename="pilot-attachment.txt",
        content=attachment_bytes,
        content_type="text/plain",
        timeout_sec=max(timeout_sec, 300),
    )
    _record(
        Path(run_sheet_file),
        target="run2",
        fields={
            "started_at": run2_started,
            "operator": operator,
            "business_owner": business_owner,
            "bundle_type": bundle_type,
            "attachment_list": "pilot-attachment.txt",
            "request_id": str(run2.get("request_id", "")),
            "bundle_id": str(run2.get("bundle_id", "")),
            "export_checked": "미검증",
            "quality_feedback": f"with-attachments 200 docs={len(run2.get('docs') or [])}; manual quality review pending",
            "issues": "없음",
            "stop_decision": "continue",
        },
    )

    return {
        "run1_request_id": str(run1.get("request_id", "")),
        "run1_bundle_id": str(run1.get("bundle_id", "")),
        "run2_request_id": str(run2.get("request_id", "")),
        "run2_bundle_id": str(run2.get("bundle_id", "")),
        "run1_export_files": len(run1_export.get("files") or []),
        "run2_docs": len(run2.get("docs") or []),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute live pilot sample Run 1 and Run 2, then record request metadata into the pilot run sheet.",
    )
    parser.add_argument("--run-sheet-file", required=True, help="Existing pilot run sheet markdown file path.")
    parser.add_argument("--base-url", required=True, help="Target DecisionDoc base URL, e.g. https://admin.decisiondoc.kr")
    parser.add_argument("--api-key", default="", help="Explicit API key. Falls back to DECISIONDOC_API_KEYS / DECISIONDOC_API_KEY.")
    parser.add_argument("--operator", default="codex", help="Operator name to record on the run sheet.")
    parser.add_argument("--business-owner", default="sungjin", help="Business owner name to record on the run sheet.")
    parser.add_argument("--bundle-type", default="proposal_kr", help="Bundle type to use for the pilot sample.")
    parser.add_argument("--timeout-sec", type=int, default=180, help="Base timeout in seconds for API requests.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary = run_pilot_sample(
        run_sheet_file=Path(args.run_sheet_file),
        base_url=args.base_url,
        api_key=args.api_key,
        operator=args.operator,
        business_owner=args.business_owner,
        bundle_type=args.bundle_type,
        timeout_sec=max(int(args.timeout_sec), 30),
    )
    for key, value in summary.items():
        print(f"{key}={value}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
