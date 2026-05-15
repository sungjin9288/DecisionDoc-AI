from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = REPO_ROOT / "docs/specs/report_quality_learning"
VALIDATOR_PATH = SPEC_DIR / "validate_correction_artifact.py"
TEMPLATE_PATH = SPEC_DIR / "correction_artifact_template.json"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_correction_artifact", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _accepted_payload() -> dict:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
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
    payload["after"]["final_output_reference"] = "workflow_snapshot:rw_example"
    return payload


def test_report_quality_learning_docs_and_template_exist():
    for path in (
        SPEC_DIR / "README.md",
        SPEC_DIR / "QUALITY_RUBRIC.md",
        SPEC_DIR / "PILOT_REVIEW_RUNBOOK.md",
        TEMPLATE_PATH,
        VALIDATOR_PATH,
    ):
        assert path.exists(), path

    rubric = (SPEC_DIR / "QUALITY_RUBRIC.md").read_text(encoding="utf-8")
    assert "Hard Fail" in rubric
    assert "slide_structure" in rubric
    assert "visual_design" in rubric
    assert "export_readiness" in rubric


def test_correction_artifact_template_is_valid_shape_but_not_learning_ready():
    validator = _load_validator()
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is True
    assert result["ready_for_learning"] is False


def test_completed_correction_artifact_is_learning_ready():
    validator = _load_validator()

    result = validator.validate_correction_artifact(_accepted_payload())

    assert result["ok"] is True
    assert result["ready_for_learning"] is True
    assert result["errors"] == []


def test_validator_accepts_exported_jsonl_with_require_ready(tmp_path, capsys):
    validator = _load_validator()
    first = _accepted_payload()
    second = _accepted_payload()
    second["artifact_id"] = "rqc_second"
    export_path = tmp_path / "report_quality_correction_artifacts.jsonl"
    export_path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in (first, second)) + "\n",
        encoding="utf-8",
    )

    exit_code = validator.main([str(export_path), "--require-ready"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "PASS report quality correction artifact JSONL validated" in out
    assert "ready_for_learning=true" in out
    assert "artifact_count=2" in out
    assert "min_records=1" in out
    assert "ready_artifacts=2" in out
    assert "not_ready_artifacts=0" in out


def test_validator_enforces_jsonl_min_records(tmp_path, capsys):
    validator = _load_validator()
    export_path = tmp_path / "small_batch.jsonl"
    export_path.write_text(json.dumps(_accepted_payload(), ensure_ascii=False) + "\n", encoding="utf-8")

    exit_code = validator.main([str(export_path), "--require-ready", "--min-records", "2", "--json"])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert result["artifact_count"] == 1
    assert result["min_records"] == 2
    assert "artifact_count 1 is below min_records 2" in "\n".join(result["errors"])


def test_validator_rejects_jsonl_parse_errors(tmp_path, capsys):
    validator = _load_validator()
    export_path = tmp_path / "broken_export.jsonl"
    export_path.write_text(json.dumps(_accepted_payload(), ensure_ascii=False) + "\nnot-json\n", encoding="utf-8")

    exit_code = validator.main([str(export_path), "--require-ready", "--json"])

    assert exit_code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert result["artifact_count"] == 1
    assert result["ready_artifacts"] == 1
    assert "line 2: invalid JSON" in "\n".join(result["errors"])


def test_validator_require_ready_fails_for_valid_but_pending_json(tmp_path):
    validator = _load_validator()
    artifact_path = tmp_path / "pending_correction_artifact.json"
    artifact_path.write_text(TEMPLATE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    exit_code = validator.main([str(artifact_path), "--require-ready"])

    assert exit_code == 1


def test_learning_ready_artifact_requires_opt_in():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["workflow_reference"]["learning_opt_in"] = False

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert "learning_opt_in=true" in "\n".join(result["errors"])


def test_correction_artifact_rejects_training_authorization_and_raw_content_keys():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["training_boundary"]["provider_fine_tune_api_call_authorized"] = True
    payload["before"]["raw_attachment"] = "must not be present"

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    joined = "\n".join(result["errors"])
    assert "provider_fine_tune_api_call_authorized must be false" in joined
    assert "forbidden raw or secret-like content key" in joined


def test_completed_artifact_requires_quality_thresholds():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["quality_baseline"]["dimension_scores"]["logic"] = 0.5

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    assert "logic >= 0.75" in "\n".join(result["errors"])


def test_completed_artifact_rejects_todo_placeholders():
    validator = _load_validator()
    payload = _accepted_payload()
    payload["after"]["planning_summary"] = "TODO_사람이 승인 가능한 최종 기획 구조 요약"

    result = validator.validate_correction_artifact(payload)

    assert result["ok"] is False
    assert result["ready_for_learning"] is False
    assert "placeholder value" in "\n".join(result["errors"])
