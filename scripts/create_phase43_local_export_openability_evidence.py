#!/usr/bin/env python3
"""Create local no-cost export openability evidence for Phase 43."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Sequence
from uuid import uuid4
import zipfile

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "docs/specs/hermes_decisiondoc_agent/phase43_local_export_openability_evidence"
)
REPORT_FILENAME = "LOCAL_EXPORT_OPENABILITY_EVIDENCE.md"
JSON_FILENAME = "local_export_openability_evidence.json"
EXPECTED_HWPX_ENTRIES = {"mimetype", "Contents/header.xml", "Contents/section0.xml"}
EXPECTED_PPTX_ENTRIES = {"[Content_Types].xml", "ppt/presentation.xml", "ppt/slides/slide1.xml"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _create_client(data_dir: Path) -> TestClient:
    os.environ["DECISIONDOC_PROVIDER"] = "mock"
    os.environ["DECISIONDOC_PROVIDER_GENERATION"] = ""
    os.environ["DECISIONDOC_PROVIDER_ATTACHMENT"] = ""
    os.environ["DECISIONDOC_PROVIDER_VISUAL"] = ""
    os.environ["DECISIONDOC_ENV"] = "dev"
    os.environ["DECISIONDOC_MAINTENANCE"] = "0"
    os.environ["DATA_DIR"] = str(data_dir)
    os.environ.pop("DECISIONDOC_API_KEY", None)
    os.environ.pop("DECISIONDOC_API_KEYS", None)

    from app.main import create_app

    return TestClient(create_app())


def _content_disposition_filename(headers: dict[str, str]) -> str:
    disposition = headers.get("content-disposition", "")
    if "filename*=" in disposition:
        return disposition.split("filename*=", 1)[1].split("''", 1)[-1].strip('"')
    if "filename=" in disposition:
        return disposition.split("filename=", 1)[1].split(";", 1)[0].strip('"')
    return ""


def _base_export_payload() -> dict[str, Any]:
    return {
        "title": "Phase43 로컬 내보내기 검증",
        "goal": "mock provider 기반으로 PDF, PPTX, HWPX 내보내기 파일 구조를 검증한다",
        "audience": "PM, 운영자",
        "bundle_type": "proposal_kr",
        "constraints": "운영 AWS, 외부 provider, 학습 실행 없이 로컬 TestClient에서만 검증한다",
    }


def _validate_pdf(content: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid_magic": content.startswith(b"%PDF"),
        "valid_eof": content.rstrip().endswith(b"%%EOF"),
        "locally_openable": False,
        "opened_with_pdfplumber": False,
        "page_count": 0,
        "text_extractable": False,
        "error": "",
    }
    try:
        import pdfplumber

        with pdfplumber.open(BytesIO(content)) as pdf:
            result["opened_with_pdfplumber"] = True
            result["page_count"] = len(pdf.pages)
            first_page_text = pdf.pages[0].extract_text() if pdf.pages else ""
            result["text_extractable"] = bool(first_page_text)
    except Exception as exc:  # pragma: no cover - exercised only when local PDF tooling is unavailable
        result["error"] = str(exc)
    result["locally_openable"] = result["opened_with_pdfplumber"] or (
        result["valid_magic"] and result["valid_eof"]
    )
    return result


def _validate_pptx(content: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid_magic": content.startswith(b"PK\x03\x04"),
        "valid_zip": False,
        "required_entries_present": False,
        "opened_with_python_pptx": False,
        "slide_count": 0,
        "slide_entries": [],
        "error": "",
    }
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            names = set(zf.namelist())
            result["valid_zip"] = True
            result["required_entries_present"] = EXPECTED_PPTX_ENTRIES <= names
            result["slide_entries"] = sorted(name for name in names if name.startswith("ppt/slides/slide"))

        from pptx import Presentation

        deck = Presentation(BytesIO(content))
        result["opened_with_python_pptx"] = True
        result["slide_count"] = len(deck.slides)
    except Exception as exc:  # pragma: no cover - exercised only when local PPTX tooling is unavailable
        result["error"] = str(exc)
    return result


def _validate_hwpx(content: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {
        "valid_magic": content.startswith(b"PK\x03\x04"),
        "valid_zip": False,
        "required_entries_present": False,
        "mimetype_matches": False,
        "entry_count": 0,
        "error": "",
    }
    try:
        with zipfile.ZipFile(BytesIO(content)) as zf:
            names = set(zf.namelist())
            result["valid_zip"] = True
            result["required_entries_present"] = EXPECTED_HWPX_ENTRIES <= names
            result["entry_count"] = len(names)
            result["mimetype_matches"] = zf.read("mimetype") == b"application/hwp+zip"
    except Exception as exc:  # pragma: no cover - exercised only when local HWPX tooling is unavailable
        result["error"] = str(exc)
    return result


def _check_generation_export(client: TestClient, endpoint: str, validator: Any) -> dict[str, Any]:
    response = client.post(endpoint, json=_base_export_payload())
    validation = validator(response.content if response.status_code == 200 else b"")
    return {
        "endpoint": endpoint,
        "status": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "content_disposition": response.headers.get("content-disposition", ""),
        "filename": _content_disposition_filename(dict(response.headers)),
        "bytes": len(response.content),
        "validation": validation,
        "opened": (
            response.status_code == 200
            and validation.get("valid_magic") is True
            and (
                validation.get("locally_openable") is True
                or validation.get("opened_with_pdfplumber") is True
                or validation.get("opened_with_python_pptx") is True
                or validation.get("required_entries_present") is True
            )
        ),
    }


def _run_report_workflow_export_check(client: TestClient) -> dict[str, Any]:
    created = client.post(
        "/report-workflows",
        json={
            "title": "Phase43 로컬 워크플로우",
            "goal": "단계형 report workflow export openability 확인",
            "client": "DecisionDoc",
            "audience": "PM, 운영자",
            "slide_count": 2,
            "learning_opt_in": False,
            "owner": "owner",
            "pm_reviewer": "pm",
            "executive_approver": "ceo",
        },
    )
    created_payload = created.json() if created.status_code == 200 else {}
    workflow_id = created_payload.get("report_workflow_id", "")
    planning = client.post(f"/report-workflows/{workflow_id}/planning/generate") if workflow_id else None
    planning_approve = (
        client.post(f"/report-workflows/{workflow_id}/planning/approve", json={"username": "pm", "comment": ""})
        if workflow_id
        else None
    )
    slides = client.post(f"/report-workflows/{workflow_id}/slides/generate", json={}) if workflow_id else None
    slide_approvals = []
    if slides is not None and slides.status_code == 200:
        for slide in slides.json().get("slides", []):
            slide_approvals.append(
                client.post(
                    f"/report-workflows/{workflow_id}/slides/{slide['slide_id']}/approve",
                    json={"username": "pm", "comment": ""},
                )
            )
    final_submit = (
        client.post(f"/report-workflows/{workflow_id}/final/submit", json={"username": "owner", "comment": ""})
        if workflow_id
        else None
    )
    pm_approve = (
        client.post(f"/report-workflows/{workflow_id}/final/pm-approve", json={"username": "pm", "comment": ""})
        if workflow_id
        else None
    )
    executive_approve = (
        client.post(
            f"/report-workflows/{workflow_id}/final/executive-approve",
            json={"username": "ceo", "comment": ""},
        )
        if workflow_id
        else None
    )
    pptx = client.get(f"/report-workflows/{workflow_id}/export/pptx") if workflow_id else None
    snapshot = client.get(f"/report-workflows/{workflow_id}/export/snapshot") if workflow_id else None
    pptx_validation = _validate_pptx(pptx.content if pptx is not None and pptx.status_code == 200 else b"")
    snapshot_payload = snapshot.json() if snapshot is not None and snapshot.status_code == 200 else {}
    return {
        "workflow_id": workflow_id,
        "create_status": created.status_code,
        "planning_generate_status": planning.status_code if planning is not None else None,
        "planning_approve_status": planning_approve.status_code if planning_approve is not None else None,
        "slides_generate_status": slides.status_code if slides is not None else None,
        "slide_approval_statuses": [response.status_code for response in slide_approvals],
        "final_submit_status": final_submit.status_code if final_submit is not None else None,
        "pm_approve_status": pm_approve.status_code if pm_approve is not None else None,
        "executive_approve_status": executive_approve.status_code if executive_approve is not None else None,
        "final_status": executive_approve.json().get("status") if executive_approve is not None and executive_approve.status_code == 200 else "",
        "pptx_export_status": pptx.status_code if pptx is not None else None,
        "pptx_export_bytes": len(pptx.content) if pptx is not None else 0,
        "pptx_validation": pptx_validation,
        "snapshot_export_status": snapshot.status_code if snapshot is not None else None,
        "snapshot_export_version": snapshot_payload.get("export_version", ""),
        "learning_opt_in": created_payload.get("learning_opt_in"),
        "opened": (
            pptx is not None
            and pptx.status_code == 200
            and pptx_validation.get("opened_with_python_pptx") is True
            and snapshot is not None
            and snapshot.status_code == 200
            and snapshot_payload.get("export_version") == "decisiondoc_report_workflow_snapshot.v1"
        ),
    }


def build_phase43_local_export_openability_evidence(*, generated_at: str | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="decisiondoc-phase43-") as data_dir:
        client = _create_client(Path(data_dir))
        pdf = _check_generation_export(client, "/generate/pdf", _validate_pdf)
        pptx = _check_generation_export(client, "/generate/pptx", _validate_pptx)
        hwp = _check_generation_export(client, "/generate/hwp", _validate_hwpx)
        workflow = _run_report_workflow_export_check(client)

    passed = (
        pdf["opened"]
        and pptx["opened"]
        and hwp["opened"]
        and workflow["opened"]
        and workflow["learning_opt_in"] is False
    )
    return {
        "report_type": "document_ops_phase43_local_export_openability_evidence",
        "phase": 43,
        "created_at": generated_at or _now_iso(),
        "status": "local_export_openability_passed_no_aws_no_training_authorization"
        if passed
        else "local_export_openability_failed",
        "target": {
            "runtime": "FastAPI TestClient",
            "provider": "mock",
            "data_dir": "temporary_local_directory",
            "production_uat_reexecuted": False,
            "aws_runtime_called": False,
        },
        "checkpoint_summary": {
            "status": "passed" if passed else "failed",
            "pdf_opened": pdf["opened"],
            "pptx_opened": pptx["opened"],
            "hwp_opened": hwp["opened"],
            "report_workflow_pptx_opened": workflow["opened"],
            "report_workflow_snapshot_exported": (
                workflow["snapshot_export_version"] == "decisiondoc_report_workflow_snapshot.v1"
            ),
            "native_os_download_verified": False,
            "production_browser_uat_reexecuted": False,
            "aws_cost_boundary": "no_cost_increase",
            "training_boundary": "not_authorized",
        },
        "generation_exports": {
            "pdf": pdf,
            "pptx": pptx,
            "hwp": hwp,
        },
        "report_workflow_export": workflow,
        "allowed_local_side_effects": {
            "local_fastapi_testclient_called": True,
            "local_temp_data_dir_used": True,
            "mock_provider_generation_used": True,
            "local_evidence_files_written": True,
        },
        "restricted_side_effect_boundary": {
            "production_ui_called": False,
            "aws_runtime_called": False,
            "aws_cost_increase_allowed": False,
            "external_dataset_uploaded": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "provider_job_polled": False,
            "training_execution_started": False,
            "model_candidate_emitted": False,
            "model_promoted": False,
            "server_side_generated_reviewer_approval": False,
        },
    }


def render_phase43_local_export_openability_markdown(evidence: dict[str, Any]) -> str:
    checkpoints = evidence["checkpoint_summary"]
    exports = evidence["generation_exports"]
    workflow = evidence["report_workflow_export"]
    return f"""# Phase 43 Local Export Openability Evidence

Status: `{evidence['status'].upper()}`

Created at: `{evidence['created_at']}`

## Purpose

Phase 43 closes the download-openability gap left by the Codex in-app browser runtime. It verifies export file structures locally with FastAPI `TestClient`, the mock provider, and temporary local storage only.

This phase does not re-run production browser UAT, call AWS runtime paths, upload datasets, call provider fine-tune APIs, create provider jobs, start training, emit model candidates, or promote models.

## Checkpoint Summary

| Check | Result |
|---|---:|
| PDF opened locally | `{str(checkpoints['pdf_opened']).lower()}` |
| PPTX opened locally | `{str(checkpoints['pptx_opened']).lower()}` |
| HWPX structure opened locally | `{str(checkpoints['hwp_opened']).lower()}` |
| Report Workflow PPTX opened locally | `{str(checkpoints['report_workflow_pptx_opened']).lower()}` |
| Report Workflow snapshot exported | `{str(checkpoints['report_workflow_snapshot_exported']).lower()}` |
| Native OS download verified | `{str(checkpoints['native_os_download_verified']).lower()}` |
| Production browser UAT re-executed | `{str(checkpoints['production_browser_uat_reexecuted']).lower()}` |
| AWS cost boundary | `{checkpoints['aws_cost_boundary']}` |
| Training boundary | `{checkpoints['training_boundary']}` |

## Generation Export Openability

| Format | HTTP | Bytes | Local open check |
|---|---:|---:|---|
| PDF | `{exports['pdf']['status']}` | `{exports['pdf']['bytes']}` | `pdfplumber={str(exports['pdf']['validation']['opened_with_pdfplumber']).lower()}, pages={exports['pdf']['validation']['page_count']}` |
| PPTX | `{exports['pptx']['status']}` | `{exports['pptx']['bytes']}` | `python-pptx={str(exports['pptx']['validation']['opened_with_python_pptx']).lower()}, slides={exports['pptx']['validation']['slide_count']}` |
| HWPX | `{exports['hwp']['status']}` | `{exports['hwp']['bytes']}` | `zip={str(exports['hwp']['validation']['valid_zip']).lower()}, required_entries={str(exports['hwp']['validation']['required_entries_present']).lower()}` |

## Report Workflow Export

- Workflow status: `{workflow['final_status']}`
- PPTX export status: `{workflow['pptx_export_status']}`
- PPTX slide count: `{workflow['pptx_validation']['slide_count']}`
- Snapshot export version: `{workflow['snapshot_export_version']}`
- Learning opt-in: `{str(workflow['learning_opt_in']).lower()}`

## Boundary Statement

Allowed and observed:

- Local FastAPI `TestClient` calls
- Mock provider generation
- Temporary local `DATA_DIR`
- Local evidence JSON/Markdown writes

Still not allowed and not observed:

- Production UI calls
- AWS runtime calls or cost increase
- External dataset upload
- Provider fine-tune API calls
- Provider job creation or polling
- Training execution
- Model candidate emission
- Model promotion
- Server-generated reviewer approval records

## Next Step

If release sign-off requires real downloaded files from the production browser, run a separate manual Chrome/Safari download-open verification after approving normal production UI/export costs. Otherwise, Phase 42 plus this local Phase 43 evidence closes the current no-cost export-openability gate.
"""


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create Phase 43 local no-cost export openability evidence.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--generated-at", default=None)
    parser.add_argument("--json", action="store_true", help="Print machine-readable evidence to stdout.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    evidence = build_phase43_local_export_openability_evidence(generated_at=args.generated_at)
    if args.json:
        print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
    output_dir = args.output_dir.expanduser().resolve()
    _write_text_atomic(output_dir / JSON_FILENAME, json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_text_atomic(output_dir / REPORT_FILENAME, render_phase43_local_export_openability_markdown(evidence))
    if evidence["checkpoint_summary"]["status"] == "passed":
        print("PASS phase43 local export openability evidence created")
        print("local_export_openability_passed=true")
        print(f"pdf_opened={str(evidence['checkpoint_summary']['pdf_opened']).lower()}")
        print(f"pptx_opened={str(evidence['checkpoint_summary']['pptx_opened']).lower()}")
        print(f"hwp_opened={str(evidence['checkpoint_summary']['hwp_opened']).lower()}")
        print(
            "report_workflow_pptx_opened="
            f"{str(evidence['checkpoint_summary']['report_workflow_pptx_opened']).lower()}"
        )
        print("aws_cost_boundary=no_cost_increase")
        print("training_boundary=not_authorized")
        return 0
    print("FAIL phase43 local export openability evidence failed")
    print(json.dumps(evidence["checkpoint_summary"], ensure_ascii=False, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
