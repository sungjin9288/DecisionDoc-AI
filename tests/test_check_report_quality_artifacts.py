from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/check_report_quality_artifacts.py"
TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/correction_artifact_template.json"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_report_quality_artifacts", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _ready_artifact(artifact_id: str, *, tenant_id: str = "tenant-a") -> dict:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    payload["artifact_id"] = artifact_id
    payload["workflow_reference"]["tenant_id"] = tenant_id
    payload["quality_baseline"]["overall_score"] = 0.88
    for key in payload["quality_baseline"]["dimension_scores"]:
        payload["quality_baseline"]["dimension_scores"][key] = 0.86
    payload["correction"]["reviewer"] = "pm-reviewer"
    payload["correction"]["reviewed_at"] = "2026-05-14T12:30:00+09:00"
    for key in payload["correction"]["rationale_by_dimension"]:
        payload["correction"]["rationale_by_dimension"][key] = f"{key} improved through manual correction"
    payload["learning_labels"]["accepted_for_learning"] = True
    payload["learning_labels"]["forbidden_terms_scan"] = "pass"
    payload["learning_labels"]["privacy_security_scan"] = "pass"
    payload["learning_labels"]["human_review_status"] = "accepted"
    payload["learning_labels"]["confirmed_claims"] = ["교정 후 최종 메시지는 사람이 확인함"]
    payload["after"]["final_output_reference"] = f"workflow_snapshot:{artifact_id}"
    return payload


def _summary_payload(*, ready_artifacts: int = 2) -> dict:
    return {
        "report_type": "report_quality_correction_artifact_summary",
        "tenant_id": "tenant-a",
        "total_artifacts": ready_artifacts,
        "ready_artifacts": ready_artifacts,
        "not_ready_artifacts": 0,
        "returned": ready_artifacts,
        "artifacts": [],
        "training_boundary": {
            "external_dataset_upload_authorized": False,
            "provider_fine_tune_api_call_authorized": False,
            "provider_job_creation_authorized": False,
            "provider_job_polling_authorized": False,
            "training_execution_authorized": False,
            "model_promotion_authorized": False,
        },
    }


def _jsonl_payload(count: int = 2) -> str:
    return "\n".join(json.dumps(_ready_artifact(f"rqc_{index}"), ensure_ascii=False) for index in range(count)) + "\n"


def test_check_report_quality_artifacts_fetches_exports_and_validates_jsonl(tmp_path):
    script = _load_script_module()
    output_path = tmp_path / "report_quality_correction_artifacts.jsonl"
    seen_headers: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(dict(request.headers))
        if request.url.path == "/report-workflows/learning/correction-artifacts":
            return httpx.Response(200, json=_summary_payload(ready_artifacts=2))
        if request.url.path == "/report-workflows/learning/correction-artifacts/export":
            return httpx.Response(200, text=_jsonl_payload(2))
        return httpx.Response(404, json={"detail": request.url.path})

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))

    result = script.run_report_quality_artifact_check(
        base_url="https://example.test",
        api_key="api-key",
        tenant_id="tenant-a",
        min_records=2,
        output_path=output_path,
        client=client,
    )

    assert result["status"] == "passed"
    assert result["summary"]["ready_artifacts"] == 2
    assert result["validation"]["artifact_count"] == 2
    assert result["validation"]["ready_artifacts"] == 2
    assert result["validation"]["unique_artifact_ids"] is True
    assert result["validation"]["tenant_ids"] == ["tenant-a"]
    assert result["output_written"] is True
    assert result["output_sha256"]
    assert result["side_effect_boundary"]["provider_fine_tune_api_call_authorized"] is False
    assert result["side_effect_boundary"]["writes_local_jsonl"] is True
    assert output_path.exists()
    assert len([line for line in output_path.read_text(encoding="utf-8").splitlines() if line.strip()]) == 2
    assert all(headers.get("x-decisiondoc-api-key") == "api-key" for headers in seen_headers)
    assert all(headers.get("x-tenant-id") == "tenant-a" for headers in seen_headers)


def test_check_report_quality_artifacts_blocks_when_ready_count_is_too_low():
    script = _load_script_module()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/report-workflows/learning/correction-artifacts":
            return httpx.Response(200, json=_summary_payload(ready_artifacts=1))
        if request.url.path == "/report-workflows/learning/correction-artifacts/export":
            return httpx.Response(200, text=_jsonl_payload(1))
        return httpx.Response(404, json={"detail": request.url.path})

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))

    with pytest.raises(SystemExit, match="ready_artifacts 1 is below min_records 2"):
        script.run_report_quality_artifact_check(
            base_url="https://example.test",
            api_key="api-key",
            min_records=2,
            client=client,
        )


def test_check_report_quality_artifacts_rejects_training_boundary_violation():
    script = _load_script_module()
    summary = _summary_payload(ready_artifacts=2)
    summary["training_boundary"]["training_execution_authorized"] = True

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/report-workflows/learning/correction-artifacts":
            return httpx.Response(200, json=summary)
        return httpx.Response(404, json={"detail": request.url.path})

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))

    with pytest.raises(SystemExit, match="summary.training_boundary.training_execution_authorized must be false"):
        script.run_report_quality_artifact_check(
            base_url="https://example.test",
            api_key="api-key",
            min_records=2,
            client=client,
        )


def test_check_report_quality_artifacts_rejects_summary_tenant_mismatch():
    script = _load_script_module()
    summary = _summary_payload(ready_artifacts=2)
    summary["tenant_id"] = "tenant-b"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/report-workflows/learning/correction-artifacts":
            return httpx.Response(200, json=summary)
        return httpx.Response(404, json={"detail": request.url.path})

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))

    with pytest.raises(SystemExit, match="does not match requested tenant"):
        script.run_report_quality_artifact_check(
            base_url="https://example.test",
            api_key="api-key",
            tenant_id="tenant-a",
            min_records=2,
            client=client,
        )


def test_check_report_quality_artifacts_preserves_output_when_export_is_invalid(tmp_path):
    script = _load_script_module()
    output_path = tmp_path / "report_quality_correction_artifacts.jsonl"
    output_path.write_text("existing validated export\n", encoding="utf-8")
    original_output = output_path.read_bytes()
    duplicate = _ready_artifact("rqc_duplicate", tenant_id="tenant-a")
    wrong_tenant = _ready_artifact("rqc_duplicate", tenant_id="tenant-b")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/report-workflows/learning/correction-artifacts":
            return httpx.Response(200, json=_summary_payload(ready_artifacts=2))
        if request.url.path == "/report-workflows/learning/correction-artifacts/export":
            text = "\n".join(
                json.dumps(item, ensure_ascii=False)
                for item in (duplicate, wrong_tenant)
            ) + "\n"
            return httpx.Response(200, text=text)
        return httpx.Response(404, json={"detail": request.url.path})

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))

    with pytest.raises(SystemExit, match="duplicate artifact_id values") as exc_info:
        script.run_report_quality_artifact_check(
            base_url="https://example.test",
            api_key="api-key",
            tenant_id="tenant-a",
            min_records=2,
            output_path=output_path,
            client=client,
        )

    assert "does not match expected tenant" in str(exc_info.value)
    assert output_path.read_bytes() == original_output

    symlink_output = tmp_path / "linked.jsonl"
    symlink_output.symlink_to("target.jsonl")
    with pytest.raises(SystemExit, match="must not be a symlink"):
        script.run_report_quality_artifact_check(
            base_url="https://example.test",
            api_key="api-key",
            output_path=symlink_output,
            client=client,
        )


def test_check_report_quality_artifacts_rejects_summary_export_count_mismatch():
    script = _load_script_module()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/report-workflows/learning/correction-artifacts":
            return httpx.Response(200, json=_summary_payload(ready_artifacts=3))
        if request.url.path == "/report-workflows/learning/correction-artifacts/export":
            return httpx.Response(200, text=_jsonl_payload(2))
        return httpx.Response(404, json={"detail": request.url.path})

    client = httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler))

    with pytest.raises(SystemExit, match="does not match expected count 3 from summary"):
        script.run_report_quality_artifact_check(
            base_url="https://example.test",
            api_key="api-key",
            tenant_id="tenant-a",
            min_records=2,
            client=client,
        )

    with pytest.raises(SystemExit, match="min_records must not exceed 200"):
        script.run_report_quality_artifact_check(
            base_url="https://example.test",
            api_key="api-key",
            min_records=201,
            client=client,
        )
