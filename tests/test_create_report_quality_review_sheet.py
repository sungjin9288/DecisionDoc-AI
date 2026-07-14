from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_PACK_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
REVIEW_SHEET_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_review_sheet.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _create_pack(tmp_path: Path) -> Path:
    create_script = _load_module(CREATE_PACK_SCRIPT_PATH, "create_report_quality_pilot_pack_for_review")
    result = create_script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-review",
        output_root=tmp_path,
        sample_count=3,
        reviewer="pm-reviewer",
    )
    return Path(result["output_dir"])


def _write_source_manifest(pack_dir: Path, artifact_ids: list[str]) -> None:
    manifest = {
        "report_type": "report_quality_pilot_source_manifest",
        "schema_version": "decisiondoc_report_quality_pilot_source_manifest.v1",
        "batch_id": pack_dir.name,
        "source": {
            "artifact_count": len(artifact_ids),
            "artifact_ids": artifact_ids,
            "format": "jsonl",
            "order_preserved": True,
            "sha256": "a" * 64,
            "tenant_id": "system",
        },
        "validation": {
            "all_valid": True,
            "all_ready_for_learning": True,
            "unique_artifact_ids": True,
            "single_tenant": True,
        },
        "side_effect_boundary": {
            "external_dataset_upload_started": False,
            "provider_fine_tune_api_called": False,
            "provider_job_created": False,
            "training_execution_started": False,
            "model_promotion_started": False,
        },
    }
    (pack_dir / "SOURCE_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False),
        encoding="utf-8",
    )


def _make_first_draft_ready(pack_dir: Path) -> None:
    draft_path = pack_dir / "drafts/pilot-rqc-review_sample_001.json"
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    payload["workflow_reference"]["report_workflow_id"] = "workflow-ready-1"
    payload["workflow_reference"]["project_id"] = "project-ready-1"
    payload["correction"]["reviewer"] = "pm-reviewer"
    payload["correction"]["reviewed_at"] = "2026-05-15T12:00:00+09:00"
    payload["after"]["planning_summary"] = "검수자가 승인한 최종 기획 구조"
    payload["after"]["final_output_reference"] = "report_workflow_snapshot:workflow-ready-1"
    payload["before"]["planning_summary"] = "초안은 문제 정의와 실행 계획의 연결이 약함"
    payload["before"]["slide_outline_summary"] = [
        {
            "slide_no": 1,
            "title": "현황 진단",
            "message": "현황과 실행 계획의 연결이 필요함",
            "issue": "근거와 승인 판단 포인트가 분리되지 않음",
        }
    ]
    payload["before"]["visible_claims"] = [
        {
            "claim": "검수자가 확인한 개선 필요 주장",
            "status": "confirmed",
            "evidence_reference": "metadata only",
        }
    ]
    payload["correction"]["change_requests"] = [
        {
            "target": "slide:1",
            "issue": "문제 정의가 넓고 실행계획과 연결되지 않음",
            "correction": "문제, 원인, 개입, 운영, 기대효과를 한 문장 chain으로 재구성",
            "rationale": "의사결정자가 사업 필요성과 실행 가능성을 빠르게 판단해야 하기 때문",
        }
    ]
    payload["after"]["slide_outline_summary"] = [
        {
            "slide_no": 1,
            "title": "현황 진단",
            "message": "핵심 문제와 실행 계획을 승인 판단 기준으로 연결",
            "layout": "상단 핵심 메시지, 좌측 근거, 우측 실행 흐름",
            "visual_asset": "문제-원인-대안 흐름도",
        }
    ]
    payload["learning_labels"]["accepted_for_learning"] = True
    payload["learning_labels"]["forbidden_terms_scan"] = "pass"
    payload["learning_labels"]["privacy_security_scan"] = "pass"
    payload["learning_labels"]["human_review_status"] = "accepted"
    payload["learning_labels"]["todo_claims"] = []
    payload["learning_labels"]["confirmed_claims"] = ["최종 기획 구조를 검수자가 확인함"]
    payload["quality_baseline"]["overall_score"] = 0.88
    for key in payload["quality_baseline"]["dimension_scores"]:
        payload["quality_baseline"]["dimension_scores"][key] = 0.86
    for key in payload["correction"]["rationale_by_dimension"]:
        payload["correction"]["rationale_by_dimension"][key] = f"{key} 사람이 검수한 개선 근거"
    draft_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_create_report_quality_review_sheet_writes_pending_worksheet(tmp_path):
    review_script = _load_module(REVIEW_SHEET_SCRIPT_PATH, "create_report_quality_review_sheet")
    pack_dir = _create_pack(tmp_path)

    manifest = review_script.create_report_quality_review_sheet(pack_dir=pack_dir)

    assert manifest["report_type"] == "report_quality_human_review_sheet_manifest"
    assert manifest["counts"]["artifact_count"] == 3
    assert manifest["counts"]["ready_artifacts"] == 0
    assert manifest["counts"]["pending_artifacts"] == 3
    assert manifest["side_effect_boundary"]["provider_fine_tune_api_called"] is False
    assert Path(manifest["output_path"]).exists()
    assert Path(manifest["manifest_path"]).exists()
    worksheet = Path(manifest["output_path"]).read_text(encoding="utf-8")
    assert "Report Quality Human Review Worksheet" in worksheet
    assert "accepted_for_learning=true" in worksheet
    assert "training_authorized: `false`" in worksheet
    assert "`human_decision_pending`" in worksheet
    assert "`run_privacy_security_scan`" in worksheet


def test_create_report_quality_review_sheet_counts_ready_artifact(tmp_path):
    review_script = _load_module(REVIEW_SHEET_SCRIPT_PATH, "create_report_quality_review_sheet")
    pack_dir = _create_pack(tmp_path)
    _make_first_draft_ready(pack_dir)

    manifest = review_script.create_report_quality_review_sheet(pack_dir=pack_dir)

    assert manifest["counts"]["artifact_count"] == 3
    assert manifest["counts"]["ready_artifacts"] == 1
    first = manifest["artifacts"][0]
    assert first["ready_for_learning"] is True
    assert first["required_actions"] == []


def test_create_report_quality_review_sheet_preserves_source_order_and_binding(tmp_path):
    review_script = _load_module(REVIEW_SHEET_SCRIPT_PATH, "create_report_quality_review_sheet_source")
    pack_dir = _create_pack(tmp_path)
    artifact_ids = [
        "pilot-rqc-review_sample_003",
        "pilot-rqc-review_sample_001",
        "pilot-rqc-review_sample_002",
    ]
    _write_source_manifest(pack_dir, artifact_ids)

    manifest = review_script.create_report_quality_review_sheet(pack_dir=pack_dir)

    assert [row["artifact_id"] for row in manifest["artifacts"]] == artifact_ids
    source_binding = manifest["pack_binding"]["source_manifest"]
    assert source_binding["source_jsonl_sha256"] == "a" * 64
    assert source_binding["tenant_id"] == "system"
    first_path = pack_dir / "drafts" / f"{artifact_ids[0]}.json"
    assert manifest["artifacts"][0]["draft_sha256"] == hashlib.sha256(first_path.read_bytes()).hexdigest()
    worksheet = Path(manifest["output_path"]).read_text(encoding="utf-8")
    assert "source_bound: `yes`" in worksheet
    assert source_binding["sha256"] in worksheet


def test_create_report_quality_review_sheet_cli_outputs_json(tmp_path, capsys):
    review_script = _load_module(REVIEW_SHEET_SCRIPT_PATH, "create_report_quality_review_sheet")
    pack_dir = _create_pack(tmp_path)
    output_path = tmp_path / "worksheet.md"
    manifest_path = tmp_path / "worksheet_manifest.json"

    exit_code = review_script.main([
        str(pack_dir),
        "--output",
        str(output_path),
        "--manifest",
        str(manifest_path),
        "--json",
    ])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["counts"]["artifact_count"] == 3
    assert output_path.exists()
    assert manifest_path.exists()


def test_create_report_quality_review_sheet_rejects_symlink_targets(tmp_path):
    review_script = _load_module(REVIEW_SHEET_SCRIPT_PATH, "reject_symlink_review_sheet")
    pack_dir = _create_pack(tmp_path / "pack-root")
    protected_path = tmp_path / "protected-worksheet.md"
    protected_path.write_text("keep this evidence\n", encoding="utf-8")
    worksheet_path = pack_dir / "HUMAN_REVIEW_WORKSHEET.md"
    worksheet_path.unlink()
    worksheet_path.symlink_to(protected_path)

    with pytest.raises(ValueError, match="symlink review sheet files"):
        review_script.create_report_quality_review_sheet(pack_dir=pack_dir)

    assert protected_path.read_text(encoding="utf-8") == "keep this evidence\n"
