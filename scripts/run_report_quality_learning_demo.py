#!/usr/bin/env python3
"""Run the report quality learning flow with mock providers and local storage."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.report_quality_learning import (  # noqa: E402
    REQUIRED_DIMENSIONS,
    validate_correction_artifact,
)


SCHEMA_VERSION = "decisiondoc.report_quality_learning_demo.v1"
DEFAULT_RECEIPT_PATH = (
    Path(tempfile.gettempdir()) / "decisiondoc-report-quality-learning-demo.json"
)
EXCLUDED_EXTERNAL_ACTIONS = (
    "provider_api_execution",
    "aws_runtime_execution",
    "dataset_upload",
    "provider_job_creation",
    "training_execution",
    "model_promotion",
    "production_service_resume",
)


class DemoError(RuntimeError):
    """Raised when a local demo stage does not satisfy its contract."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with temporary_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_path, path)


@contextmanager
def local_demo_environment(data_dir: Path) -> Iterator[None]:
    overrides = {
        "DECISIONDOC_PROVIDER": "mock",
        "DECISIONDOC_PROVIDER_GENERATION": "mock",
        "DECISIONDOC_PROVIDER_ATTACHMENT": "mock",
        "DECISIONDOC_PROVIDER_VISUAL": "mock",
        "DECISIONDOC_STORAGE": "local",
        "DATA_DIR": str(data_dir),
        "EXPORT_DIR": str(data_dir / "exports"),
        "DECISIONDOC_ENV": "dev",
        "DECISIONDOC_MAINTENANCE": "0",
    }
    with patch.dict(os.environ, overrides, clear=False):
        for key in (
            "DECISIONDOC_API_KEY",
            "DECISIONDOC_API_KEYS",
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "ANTHROPIC_API_KEY",
        ):
            os.environ.pop(key, None)
        yield


def request_json(
    client: TestClient,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = client.request(method, path, json=payload)
    if response.status_code != 200:
        raise DemoError(f"{method} {path} returned HTTP {response.status_code}: {response.text}")
    body = response.json()
    if not isinstance(body, dict):
        raise DemoError(f"{method} {path} returned a non-object JSON response")
    return body


def _quality_correction_payload() -> dict[str, Any]:
    rationales = {
        "logic": "문제, 원인, 실행안, 기대효과의 연결을 사람이 확인했다.",
        "evidence": "확정 사실과 추가 확인 항목을 분리해 근거 경계를 확인했다.",
        "audience_fit": "PM과 최종 승인자가 핵심 판단 근거를 빠르게 읽을 수 있다.",
        "slide_structure": "각 장표가 하나의 결정 질문과 메시지에 집중한다.",
        "visual_design": "표와 도식이 본문을 반복하지 않고 판단 구조를 보완한다.",
        "public_sector_tone": "과장 표현 없이 공공기관 검토 문맥에 맞는 문장을 사용한다.",
        "export_readiness": "제목, 본문, 근거 상태가 최종 산출물에서 확인 가능하다.",
        "learning_value": "교정 전 문제와 교정 이유가 이후 품질 평가에 재사용 가능하다.",
    }
    if set(rationales) != set(REQUIRED_DIMENSIONS):
        raise DemoError("quality correction rationales do not match the required dimensions")
    return {
        "username": "demo-pm",
        "reviewer": "demo-pm",
        "reviewed_at": "2026-07-13T10:00:00+09:00",
        "domain": "decision_document_operations",
        "language": "ko",
        "overall_score": 0.88,
        "dimension_scores": {dimension: 0.86 for dimension in REQUIRED_DIMENSIONS},
        "hard_failures": [],
        "change_requests": [
            {
                "target": "planning",
                "issue": "초안의 문제 정의와 승인 판단 기준이 떨어져 있다.",
                "correction": "문제, 근거, 실행안, 승인 기준을 하나의 흐름으로 연결한다.",
                "rationale": "검토자가 문서 안에서 결정 근거와 다음 행동을 함께 확인해야 한다.",
            }
        ],
        "rationale_by_dimension": rationales,
        "after_planning_summary": "문제와 근거를 먼저 제시하고 실행안과 승인 기준으로 이어지는 구조로 교정했다.",
        "accepted_for_learning": True,
        "task_types": ["proposal_planning", "slide_message_design"],
        "skills": ["develop-document-improver", "evidence-gap-review"],
        "confirmed_claims": ["최종 승인 흐름과 품질 검수 완료"],
        "assumed_claims": [],
        "todo_claims": [],
        "forbidden_terms_scan": "pass",
        "privacy_security_scan": "pass",
        "human_review_status": "accepted",
    }


def _approve_workflow(client: TestClient, workflow_id: str) -> tuple[str, int]:
    planning = request_json(client, "POST", f"/report-workflows/{workflow_id}/planning/generate")
    if planning.get("status") != "planning_draft":
        raise DemoError("planning generation did not produce planning_draft")

    request_json(
        client,
        "POST",
        f"/report-workflows/{workflow_id}/planning/approve",
        payload={"username": "demo-pm", "comment": "로컬 데모 기획 승인"},
    )
    slides = request_json(
        client,
        "POST",
        f"/report-workflows/{workflow_id}/slides/generate",
        payload={},
    )
    slide_items = slides.get("slides")
    if not isinstance(slide_items, list) or not slide_items:
        raise DemoError("slide generation returned no slides")

    for slide in slide_items:
        slide_id = slide.get("slide_id") if isinstance(slide, dict) else None
        if not isinstance(slide_id, str) or not slide_id:
            raise DemoError("slide generation returned an invalid slide id")
        request_json(
            client,
            "POST",
            f"/report-workflows/{workflow_id}/slides/{slide_id}/approve",
            payload={"username": "demo-pm", "comment": "로컬 데모 장표 승인"},
        )

    request_json(
        client,
        "POST",
        f"/report-workflows/{workflow_id}/final/submit",
        payload={"username": "demo-owner", "comment": "최종 검토 요청"},
    )
    request_json(
        client,
        "POST",
        f"/report-workflows/{workflow_id}/final/pm-approve",
        payload={"username": "demo-pm", "comment": "PM 승인"},
    )
    approved = request_json(
        client,
        "POST",
        f"/report-workflows/{workflow_id}/final/executive-approve",
        payload={"username": "demo-executive", "comment": "최종 승인"},
    )
    status = approved.get("status")
    if status != "final_approved":
        raise DemoError(f"final approval ended in unexpected status: {status!r}")
    return status, len(slide_items)


def create_ready_report_quality_artifact(
    client: TestClient,
    *,
    title: str,
) -> dict[str, Any]:
    """Create one mock-backed workflow and persist its reviewed correction artifact."""
    created = request_json(
        client,
        "POST",
        "/report-workflows",
        payload={
            "title": title,
            "goal": "승인된 보고서와 사람 교정 근거를 학습 후보 artifact로 연결한다.",
            "client": "DecisionDoc local demo",
            "audience": "PM, executive approver",
            "owner": "demo-owner",
            "pm_reviewer": "demo-pm",
            "executive_approver": "demo-executive",
            "slide_count": 2,
            "learning_opt_in": True,
        },
    )
    workflow_id = created.get("report_workflow_id")
    if not isinstance(workflow_id, str) or not workflow_id:
        raise DemoError("workflow creation returned no report_workflow_id")

    workflow_status, slide_count = _approve_workflow(client, workflow_id)
    correction_payload = _quality_correction_payload()
    preview = request_json(
        client,
        "POST",
        f"/report-workflows/{workflow_id}/learning/correction-artifact/preview",
        payload=correction_payload,
    )
    if preview.get("persisted") is not False or preview.get("validation", {}).get("ready_for_learning") is not True:
        raise DemoError("correction artifact preview did not pass the learning gate")

    preview_fingerprint = preview.get("preview_fingerprint")
    if not isinstance(preview_fingerprint, str) or len(preview_fingerprint) != 64:
        raise DemoError("correction artifact preview returned no content fingerprint")
    correction_payload["preview_fingerprint"] = preview_fingerprint

    saved = request_json(
        client,
        "POST",
        f"/report-workflows/{workflow_id}/learning/correction-artifact",
        payload=correction_payload,
    )
    if saved.get("persisted") is not True or saved.get("validation", {}).get("ready_for_learning") is not True:
        raise DemoError("correction artifact was not persisted as a ready learning candidate")
    if saved.get("preview_fingerprint") != preview_fingerprint:
        raise DemoError("saved correction artifact does not match the preview fingerprint")
    if saved.get("artifact") != preview.get("artifact"):
        raise DemoError("saved correction artifact differs from the reviewed preview")

    validation = validate_correction_artifact(saved["artifact"])
    if validation.get("ok") is not True or validation.get("ready_for_learning") is not True:
        raise DemoError(
            f"saved correction artifact failed validation: {validation.get('errors', [])}"
        )

    return {
        "workflow_id": workflow_id,
        "workflow_status": workflow_status,
        "slide_count": slide_count,
        "artifact_id": saved["artifact"]["artifact_id"],
        "artifact_schema_version": validation.get("schema_version"),
        "preview_fingerprint": preview_fingerprint,
    }


def validate_ready_report_quality_export(
    client: TestClient,
    *,
    expected_artifact_ids: Sequence[str],
) -> dict[str, Any]:
    """Re-read and validate the current ready artifact pool through the public API."""
    expected_ids = list(expected_artifact_ids)
    summary = request_json(
        client,
        "GET",
        "/report-workflows/learning/correction-artifacts?ready_only=true&limit=10",
    )
    if (
        summary.get("ready_artifacts") != len(expected_ids)
        or summary.get("returned") != len(expected_ids)
    ):
        raise DemoError("ready artifact summary did not return the expected artifacts")

    exported = client.get("/report-workflows/learning/correction-artifacts/export?ready_only=true&limit=10")
    if exported.status_code != 200:
        raise DemoError(f"correction artifact export returned HTTP {exported.status_code}: {exported.text}")
    artifacts = [json.loads(line) for line in exported.text.splitlines() if line.strip()]
    if len(artifacts) != len(expected_ids) or any(
        not isinstance(artifact, dict) for artifact in artifacts
    ):
        raise DemoError("correction artifact export did not contain the expected JSONL records")

    validations = [validate_correction_artifact(artifact) for artifact in artifacts]
    failed = [
        validation.get("errors", [])
        for validation in validations
        if validation.get("ok") is not True
        or validation.get("ready_for_learning") is not True
    ]
    if failed:
        raise DemoError(f"exported correction artifacts failed validation: {failed}")

    exported_ids = [str(artifact.get("artifact_id") or "") for artifact in artifacts]
    if set(exported_ids) != set(expected_ids):
        raise DemoError("saved and exported artifact ids do not match")

    return {
        "ready_artifact_count": summary.get("ready_artifacts"),
        "exported_record_count": len(artifacts),
        "artifacts": artifacts,
    }


def _run_api_flow(client: TestClient) -> dict[str, Any]:
    artifact = create_ready_report_quality_artifact(
        client,
        title="Report quality learning local demo",
    )
    export = validate_ready_report_quality_export(
        client,
        expected_artifact_ids=[artifact["artifact_id"]],
    )
    return {**artifact, **export}


def run_demo() -> dict[str, Any]:
    """Run the complete local flow and return a compact evidence receipt."""
    with tempfile.TemporaryDirectory(prefix="decisiondoc-report-quality-demo-") as temporary_dir:
        with local_demo_environment(Path(temporary_dir)):
            from app.main import create_app

            with TestClient(create_app()) as client:
                result = _run_api_flow(client)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "passed",
        "generated_at": now_iso(),
        "execution_mode": {
            "provider": "mock",
            "storage": "temporary_local",
            "runtime_data_persisted": False,
        },
        "workflow": {
            "report_workflow_id": result["workflow_id"],
            "status": result["workflow_status"],
            "slide_count": result["slide_count"],
        },
        "quality_correction": {
            "artifact_id": result["artifact_id"],
            "schema_version": result["artifact_schema_version"],
            "ready_for_learning": True,
            "ready_artifact_count": result["ready_artifact_count"],
            "exported_record_count": result["exported_record_count"],
            "export_validation_passed": True,
            "preview_bound_save": True,
            "preview_fingerprint": result["preview_fingerprint"],
        },
        "completed_stages": [
            "workflow_created",
            "planning_approved",
            "slides_approved",
            "final_approved",
            "correction_previewed",
            "correction_saved",
            "ready_artifacts_listed",
            "jsonl_export_validated",
        ],
        "external_actions": {action: False for action in EXCLUDED_EXTERNAL_ACTIONS},
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local mock report quality learning demo and write a JSON receipt.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_RECEIPT_PATH,
        help=f"Receipt path (default: {DEFAULT_RECEIPT_PATH})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    try:
        receipt = run_demo()
        write_json_atomic(args.output, receipt)
    except Exception as exc:
        failure = {
            "schema_version": SCHEMA_VERSION,
            "status": "failed",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        print(json.dumps(failure, ensure_ascii=False))
        return 1

    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
