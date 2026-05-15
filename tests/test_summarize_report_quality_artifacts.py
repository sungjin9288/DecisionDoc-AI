from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts/summarize_report_quality_artifacts.py"
TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/correction_artifact_template.json"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("summarize_report_quality_artifacts", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _ready_artifact(artifact_id: str, *, reviewer: str = "pm-reviewer", document_type: str = "proposal") -> dict:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    payload["artifact_id"] = artifact_id
    payload["document_profile"]["document_type"] = document_type
    payload["quality_baseline"]["overall_score"] = 0.88
    for key in payload["quality_baseline"]["dimension_scores"]:
        payload["quality_baseline"]["dimension_scores"][key] = 0.86
    payload["correction"]["reviewer"] = reviewer
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


def _write_jsonl(path: Path, artifacts: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in artifacts) + "\n", encoding="utf-8")


def test_summarize_report_quality_artifacts_creates_ready_manifest(tmp_path):
    script = _load_script_module()
    jsonl_path = tmp_path / "report_quality_correction_artifacts.jsonl"
    _write_jsonl(
        jsonl_path,
        [
            _ready_artifact("rqc_1", reviewer="pm", document_type="proposal"),
            _ready_artifact("rqc_2", reviewer="exec", document_type="onepager"),
            _ready_artifact("rqc_3", reviewer="pm", document_type="proposal"),
        ],
    )

    manifest = script.create_report_quality_batch_manifest(
        jsonl_path=jsonl_path,
        batch_id="batch-test",
        min_records=3,
    )

    assert manifest["report_type"] == "report_quality_correction_batch_manifest"
    assert manifest["batch_id"] == "batch-test"
    assert manifest["readiness"]["ok"] is True
    assert manifest["readiness"]["status"] == "ready_for_human_training_review"
    assert manifest["readiness"]["training_execution_authorized"] is False
    assert manifest["counts"]["artifact_count"] == 3
    assert manifest["counts"]["ready_artifacts"] == 3
    assert manifest["counts"]["reviewer_count"] == 2
    assert manifest["distribution"]["document_types"] == {"proposal": 2, "onepager": 1}
    assert manifest["distribution"]["reviewers"] == {"pm": 2, "exec": 1}
    assert manifest["quality"]["overall_score"]["avg"] == 0.88
    assert manifest["side_effect_boundary"]["provider_fine_tune_api_called"] is False

    markdown = script.render_batch_markdown(manifest)
    assert "Report Quality Correction Batch Summary" in markdown
    assert "ready_for_human_training_review" in markdown
    assert "provider_fine_tune_api_called: `false`" in markdown


def test_summarize_report_quality_artifacts_blocks_small_batch(tmp_path):
    script = _load_script_module()
    jsonl_path = tmp_path / "small_batch.jsonl"
    _write_jsonl(jsonl_path, [_ready_artifact("rqc_1")])

    manifest = script.create_report_quality_batch_manifest(jsonl_path=jsonl_path, min_records=2)

    assert manifest["readiness"]["ok"] is False
    assert manifest["readiness"]["status"] == "follow_up_required"
    assert "minimum_record_count_not_met" in manifest["readiness"]["blocker_reasons"]
    assert manifest["counts"]["artifact_count"] == 1


def test_summarize_report_quality_artifacts_reports_parse_and_boundary_errors(tmp_path):
    script = _load_script_module()
    bad = _ready_artifact("rqc_bad")
    bad["training_boundary"]["training_execution_authorized"] = True
    jsonl_path = tmp_path / "bad_batch.jsonl"
    jsonl_path.write_text(json.dumps(bad, ensure_ascii=False) + "\nnot-json\n", encoding="utf-8")

    manifest = script.create_report_quality_batch_manifest(jsonl_path=jsonl_path, min_records=1)

    assert manifest["readiness"]["ok"] is False
    assert "jsonl_parse_errors" in manifest["readiness"]["blocker_reasons"]
    assert "invalid_artifacts_present" in manifest["readiness"]["blocker_reasons"]
    assert "training_boundary_violation" in manifest["readiness"]["blocker_reasons"]
    assert manifest["counts"]["parse_errors"] == 1
    assert manifest["boundary_issues"]


def test_summarize_report_quality_artifacts_cli_writes_outputs(tmp_path, capsys):
    script = _load_script_module()
    jsonl_path = tmp_path / "report_quality_correction_artifacts.jsonl"
    manifest_path = tmp_path / "manifest.json"
    markdown_path = tmp_path / "summary.md"
    _write_jsonl(jsonl_path, [_ready_artifact("rqc_1"), _ready_artifact("rqc_2")])

    exit_code = script.main([
        str(jsonl_path),
        "--batch-id",
        "batch-cli",
        "--min-records",
        "2",
        "--output",
        str(manifest_path),
        "--markdown",
        str(markdown_path),
    ])

    assert exit_code == 0
    assert manifest_path.exists()
    assert markdown_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["batch_id"] == "batch-cli"
    assert "Report quality batch readiness: PASS" in capsys.readouterr().out
