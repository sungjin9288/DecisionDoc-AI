from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from app.services.report_quality_pilot_receipt import (
    build_pilot_export_receipt,
    serialize_pilot_export_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_PACK_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
APPLY_SCRIPT_PATH = REPO_ROOT / "scripts/apply_report_quality_review_decisions.py"
VALIDATOR_SCRIPT_PATH = REPO_ROOT / "scripts/validate_report_quality_review_decision_receipt.py"
TEMPLATE_PATH = REPO_ROOT / "docs/specs/report_quality_learning/correction_artifact_template.json"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _ready_artifact(artifact_id: str) -> dict:
    artifact = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    artifact["artifact_id"] = artifact_id
    artifact["workflow_reference"]["tenant_id"] = "receipt-tenant"
    artifact["quality_baseline"]["overall_score"] = 0.88
    for dimension in artifact["quality_baseline"]["dimension_scores"]:
        artifact["quality_baseline"]["dimension_scores"][dimension] = 0.86
    artifact["correction"]["reviewer"] = "receipt-reviewer"
    artifact["correction"]["reviewed_at"] = "2026-07-14T16:00:00+09:00"
    for dimension in artifact["correction"]["rationale_by_dimension"]:
        artifact["correction"]["rationale_by_dimension"][dimension] = (
            f"{dimension} receipt validation rationale"
        )
    artifact["learning_labels"]["accepted_for_learning"] = True
    artifact["learning_labels"]["forbidden_terms_scan"] = "pass"
    artifact["learning_labels"]["privacy_security_scan"] = "pass"
    artifact["learning_labels"]["human_review_status"] = "accepted"
    artifact["after"]["final_output_reference"] = f"report_workflow_snapshot:{artifact_id}"
    return artifact


def _create_source_pack(tmp_path: Path) -> Path:
    creator = _load_module(CREATE_PACK_SCRIPT_PATH, "create_pack_for_decision_receipt")
    source_path = tmp_path / "pilot.jsonl"
    artifacts = [_ready_artifact(f"receipt-artifact-{index}") for index in range(1, 4)]
    source_path.write_text(
        "\n".join(json.dumps(artifact, ensure_ascii=False) for artifact in artifacts) + "\n",
        encoding="utf-8",
    )
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    receipt_path = tmp_path / "pilot_receipt.json"
    receipt_path.write_bytes(
        serialize_pilot_export_receipt(
            build_pilot_export_receipt(
                preview={
                    "filename": f"report_quality_pilot_artifacts_{source_sha256[:12]}.jsonl",
                    "export_sha256": source_sha256,
                    "ordered_artifact_ids": [artifact["artifact_id"] for artifact in artifacts],
                },
                tenant_id="receipt-tenant",
                request_id="pilot-receipt-request",
            )
        )
    )
    result = creator.create_report_quality_pilot_pack(
        batch_id="pilot-receipt",
        output_root=tmp_path / "packs",
        source_jsonl=source_path,
        source_receipt=receipt_path,
    )
    return Path(result["output_dir"])


def _apply_with_receipt(tmp_path: Path) -> tuple[Path, Path]:
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_for_decision_receipt")
    pack_dir = _create_source_pack(tmp_path)
    decisions_path = pack_dir / "review_decisions.json"
    receipt_path = pack_dir / "review_decision_application_receipt.json"
    decisions = json.loads(decisions_path.read_text(encoding="utf-8"))
    for decision in decisions["decisions"]:
        decision["decision"] = "accepted"
    decisions_path.write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    result = apply_script.apply_review_decisions(
        pack_dir=pack_dir,
        decisions_path=decisions_path,
        require_ready=True,
        receipt_path=receipt_path,
    )
    assert result["ok"] is True
    assert result["applied_count"] == 3
    assert result["receipt_path"] == str(receipt_path)
    assert result["receipt_sha256"]
    return pack_dir, receipt_path


def test_review_decision_application_receipt_validates_current_source_pack(tmp_path, capsys):
    validator = _load_module(VALIDATOR_SCRIPT_PATH, "validate_decision_receipt")
    _, receipt_path = _apply_with_receipt(tmp_path)

    result = validator.validate_review_decision_receipt(receipt_path)

    assert result["ok"] is True
    assert result["artifact_count"] == 3
    assert result["source_bound"] is True
    assert result["side_effect_boundary"]["training_execution_started"] is False

    exit_code = validator.main([str(receipt_path), "--json"])
    cli_result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert cli_result["receipt_sha256"] == result["receipt_sha256"]

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["artifacts"][0]["ready_for_learning"] = False
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="ready_for_learning does not match current validation"):
        validator.validate_review_decision_receipt(receipt_path)


def test_review_decision_application_receipt_rejects_changed_draft(tmp_path):
    validator = _load_module(VALIDATOR_SCRIPT_PATH, "validate_stale_decision_receipt")
    pack_dir, receipt_path = _apply_with_receipt(tmp_path)
    draft_path = pack_dir / "drafts/receipt-artifact-1.json"
    draft_path.write_text(draft_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="draft SHA-256 values are stale"):
        validator.validate_review_decision_receipt(receipt_path)


def test_review_decision_application_rejects_symlink_inputs(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_for_symlink_rejection")

    decision_case = tmp_path / "decision-case"
    decision_case.mkdir()
    decision_pack = _create_source_pack(decision_case)
    decision_target = decision_pack / "decision_target.json"
    decision_link = decision_pack / "review_decisions.json"
    apply_script.create_review_decision_template(
        pack_dir=decision_pack,
        output_path=decision_target,
    )
    decision_link.unlink()
    decision_link.symlink_to(decision_target.name)
    with pytest.raises(ValueError, match="symlink decision files are not allowed"):
        apply_script.apply_review_decisions(
            pack_dir=decision_pack,
            decisions_path=decision_link,
            receipt_path=decision_pack / "receipt.json",
        )

    receipt_case = tmp_path / "receipt-case"
    receipt_case.mkdir()
    receipt_pack = _create_source_pack(receipt_case)
    decisions_path = receipt_pack / "review_decisions.json"
    receipt_link = receipt_pack / "receipt.json"
    receipt_link.symlink_to("receipt_target.json")
    with pytest.raises(ValueError, match="symlink receipt files are not allowed"):
        apply_script.apply_review_decisions(
            pack_dir=receipt_pack,
            decisions_path=decisions_path,
            receipt_path=receipt_link,
        )
