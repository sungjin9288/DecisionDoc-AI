from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_PACK_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
APPLY_SCRIPT_PATH = REPO_ROOT / "scripts/apply_report_quality_review_decisions.py"
RECEIPT_VALIDATOR_PATH = REPO_ROOT / "scripts/validate_report_quality_review_decision_receipt.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _create_pack(tmp_path: Path) -> Path:
    create_script = _load_module(CREATE_PACK_SCRIPT_PATH, "create_report_quality_pilot_pack_for_apply")
    result = create_script.create_report_quality_pilot_pack(
        batch_id="pilot-rqc-apply",
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
            "sha256": "b" * 64,
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


def _ready_decision(artifact_id: str) -> dict:
    return {
        "artifact_id": artifact_id,
        "decision": "accepted",
        "reviewer": "pm-reviewer",
        "reviewed_at": "2026-05-15T12:00:00+09:00",
        "overall_score": 0.88,
        "dimension_scores": {
            "logic": 0.86,
            "evidence": 0.86,
            "audience_fit": 0.86,
            "slide_structure": 0.86,
            "visual_design": 0.82,
            "public_sector_tone": 0.86,
            "export_readiness": 0.86,
            "learning_value": 0.86,
        },
        "hard_failures": [],
        "forbidden_terms_scan": "pass",
        "privacy_security_scan": "pass",
        "confirmed_claims": ["최종 기획 구조를 검수자가 확인함"],
        "assumed_claims": [],
        "todo_claims": [],
        "rationale_by_dimension": {
            "logic": "문제-원인-대안-실행 흐름이 개선됨",
            "evidence": "근거 확인 항목이 분리됨",
            "audience_fit": "PM 승인 질문이 명확함",
            "slide_structure": "장표별 핵심 메시지가 분리됨",
            "visual_design": "편집 가능한 시각자료 방향이 명확함",
            "public_sector_tone": "공공 제안서 톤을 유지함",
            "export_readiness": "PPTX export 검수 기준을 충족함",
            "learning_value": "교정 전후 차이가 학습 가능한 형태임",
        },
    }


def _remove_placeholders_for_acceptance(pack_dir: Path, artifact_id: str) -> None:
    draft_path = pack_dir / "drafts" / f"{artifact_id}.json"
    payload = json.loads(draft_path.read_text(encoding="utf-8"))
    payload["workflow_reference"]["report_workflow_id"] = f"workflow-{artifact_id}"
    payload["workflow_reference"]["project_id"] = f"project-{artifact_id}"
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
    payload["after"]["planning_summary"] = "검수자가 승인한 최종 기획 구조"
    payload["after"]["slide_outline_summary"] = [
        {
            "slide_no": 1,
            "title": "현황 진단",
            "message": "핵심 문제와 실행 계획을 승인 판단 기준으로 연결",
            "layout": "상단 핵심 메시지, 좌측 근거, 우측 실행 흐름",
            "visual_asset": "문제-원인-대안 흐름도",
        }
    ]
    payload["after"]["final_output_reference"] = f"report_workflow_snapshot:workflow-{artifact_id}"
    draft_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_browser_draft(
    pack_dir: Path,
    output_path: Path,
    *,
    first_decision: str = "pending",
) -> bytes:
    payload = json.loads((pack_dir / "review_decisions.json").read_text(encoding="utf-8"))
    payload["decisions"][0]["decision"] = first_decision
    content = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(content)
    return content


def test_create_review_decision_template_writes_non_training_template(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions")
    pack_dir = _create_pack(tmp_path)
    output_path = tmp_path / "review_decisions.json"

    result = apply_script.create_review_decision_template(pack_dir=pack_dir, output_path=output_path)

    assert result["ok"] is True
    assert result["artifact_count"] == 3
    assert result["side_effect_boundary"]["provider_fine_tune_api_called"] is False
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["training_authorized"] is False
    assert payload["pack_binding"]["schema_version"] == "decisiondoc_report_quality_pilot_pack_binding.v1"
    assert payload["review_started_pending"] is False
    assert len(payload["decisions"]) == 3
    assert payload["decisions"][0]["previous_decision"] == "pending"
    assert payload["decisions"][0]["decision"] == "pending"

    original_bytes = output_path.read_bytes()
    with pytest.raises(ValueError, match="refusing to overwrite existing decision template"):
        apply_script.create_review_decision_template(
            pack_dir=pack_dir,
            output_path=output_path,
        )
    assert output_path.read_bytes() == original_bytes

    linked_path = tmp_path / "linked-review-decisions.json"
    linked_path.symlink_to(output_path)
    with pytest.raises(ValueError, match="symlink decision template files are not allowed"):
        apply_script.create_review_decision_template(
            pack_dir=pack_dir,
            output_path=linked_path,
        )


def test_apply_review_decisions_accepts_ready_decision(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions")
    pack_dir = _create_pack(tmp_path)
    artifact_id = "pilot-rqc-apply_sample_001"
    _remove_placeholders_for_acceptance(pack_dir, artifact_id)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps({"decisions": [_ready_decision(artifact_id)]}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = apply_script.apply_review_decisions(
        pack_dir=pack_dir,
        decisions_path=decisions_path,
        require_ready=True,
    )

    assert result["ok"] is True
    assert result["applied_count"] == 1
    assert result["ready_decisions"] == 1
    updated = json.loads((pack_dir / "drafts" / f"{artifact_id}.json").read_text(encoding="utf-8"))
    assert updated["learning_labels"]["accepted_for_learning"] is True
    assert updated["learning_labels"]["human_review_status"] == "accepted"
    assert updated["training_boundary"]["training_execution_authorized"] is False


def test_apply_review_decisions_blocks_incomplete_accepted_decision(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions")
    pack_dir = _create_pack(tmp_path)
    artifact_id = "pilot-rqc-apply_sample_001"
    decisions_path = tmp_path / "bad_decisions.json"
    bad_decision = _ready_decision(artifact_id)
    bad_decision["reviewed_at"] = ""
    decisions_path.write_text(json.dumps({"decisions": [bad_decision]}, ensure_ascii=False), encoding="utf-8")

    result = apply_script.apply_review_decisions(pack_dir=pack_dir, decisions_path=decisions_path)

    assert result["ok"] is False
    assert result["applied_count"] == 0
    assert any("accepted decision requires reviewed_at" in error for error in result["errors"])


def test_apply_review_decisions_dry_run_does_not_write(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions")
    pack_dir = _create_pack(tmp_path)
    artifact_id = "pilot-rqc-apply_sample_001"
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps({"decisions": [{"artifact_id": artifact_id, "decision": "changes_requested"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    worksheet_path = pack_dir / "HUMAN_REVIEW_WORKSHEET.md"
    manifest_path = pack_dir / "human_review_manifest.json"
    original_worksheet = worksheet_path.read_bytes()
    original_manifest = manifest_path.read_bytes()

    result = apply_script.apply_review_decisions(pack_dir=pack_dir, decisions_path=decisions_path, dry_run=True)

    assert result["ok"] is True
    assert result["applied_count"] == 0
    unchanged = json.loads((pack_dir / "drafts" / f"{artifact_id}.json").read_text(encoding="utf-8"))
    assert unchanged["learning_labels"]["human_review_status"] == "pending"
    assert result["review_sheet_refreshed"] is False
    assert worksheet_path.read_bytes() == original_worksheet
    assert manifest_path.read_bytes() == original_manifest


def test_apply_review_decisions_allows_pending_bound_template_without_writes(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions")
    pack_dir = _create_pack(tmp_path)
    decisions_path = tmp_path / "review_decisions.json"
    apply_script.create_review_decision_template(pack_dir=pack_dir, output_path=decisions_path)

    result = apply_script.apply_review_decisions(pack_dir=pack_dir, decisions_path=decisions_path, dry_run=True)

    assert result["ok"] is True
    assert result["applied_count"] == 0
    assert result["ready_decisions"] == 0


def test_source_bound_review_decisions_require_current_pack_binding(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions_source_binding")
    pack_dir = _create_pack(tmp_path)
    artifact_ids = [
        "pilot-rqc-apply_sample_003",
        "pilot-rqc-apply_sample_001",
        "pilot-rqc-apply_sample_002",
    ]
    _write_source_manifest(pack_dir, artifact_ids)
    template_path = tmp_path / "source_review_decisions.json"

    template_result = apply_script.create_review_decision_template(
        pack_dir=pack_dir,
        output_path=template_path,
    )
    template = json.loads(template_path.read_text(encoding="utf-8"))

    assert template_result["source_bound"] is True
    assert [item["artifact_id"] for item in template["decisions"]] == artifact_ids
    assert template["pack_binding"]["source_manifest"]["source_jsonl_sha256"] == "b" * 64

    unbound_path = tmp_path / "unbound.json"
    unbound_path.write_text(
        json.dumps({"decisions": [{"artifact_id": artifact_ids[0], "decision": "changes_requested"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="requires a pack_binding"):
        apply_script.apply_review_decisions(
            pack_dir=pack_dir,
            decisions_path=unbound_path,
            dry_run=True,
        )


def test_apply_review_decisions_rejects_stale_bound_draft(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions_stale_binding")
    pack_dir = _create_pack(tmp_path)
    decisions_path = tmp_path / "review_decisions.json"
    apply_script.create_review_decision_template(pack_dir=pack_dir, output_path=decisions_path)
    draft_path = pack_dir / "drafts/pilot-rqc-apply_sample_001.json"
    draft_path.write_text(draft_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="draft SHA-256 values are stale"):
        apply_script.apply_review_decisions(
            pack_dir=pack_dir,
            decisions_path=decisions_path,
            dry_run=True,
        )


def test_apply_review_decisions_does_not_partially_write_invalid_batch(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions_atomic_batch")
    pack_dir = _create_pack(tmp_path)
    first_artifact_id = "pilot-rqc-apply_sample_001"
    second_artifact_id = "pilot-rqc-apply_sample_002"
    first_path = pack_dir / "drafts" / f"{first_artifact_id}.json"
    original_first = first_path.read_bytes()
    worksheet_path = pack_dir / "HUMAN_REVIEW_WORKSHEET.md"
    manifest_path = pack_dir / "human_review_manifest.json"
    original_worksheet = worksheet_path.read_bytes()
    original_manifest = manifest_path.read_bytes()
    invalid_accepted = _ready_decision(second_artifact_id)
    invalid_accepted["reviewed_at"] = ""
    decisions_path = pack_dir / "mixed_decisions.json"
    receipt_path = pack_dir / "mixed_decisions_receipt.json"
    decisions_path.write_text(
        json.dumps({
            "decisions": [
                {"artifact_id": first_artifact_id, "decision": "changes_requested"},
                invalid_accepted,
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    result = apply_script.apply_review_decisions(
        pack_dir=pack_dir,
        decisions_path=decisions_path,
        receipt_path=receipt_path,
    )

    assert result["ok"] is False
    assert result["applied_count"] == 0
    assert result["receipt_path"] is None
    assert first_path.read_bytes() == original_first
    assert not receipt_path.exists()
    assert result["review_sheet_refreshed"] is False
    assert worksheet_path.read_bytes() == original_worksheet
    assert manifest_path.read_bytes() == original_manifest


def test_import_browser_review_draft_dry_run_does_not_archive_or_apply(tmp_path, capsys):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "dry_run_browser_review_draft")
    pack_dir = _create_pack(tmp_path / "pack-root")
    browser_draft_path = tmp_path / "downloads" / "review_decisions.browser-draft.json"
    source_bytes = _write_browser_draft(pack_dir, browser_draft_path)
    original_drafts = {
        path.name: path.read_bytes()
        for path in (pack_dir / "drafts").glob("*.json")
    }
    worksheet_path = pack_dir / "HUMAN_REVIEW_WORKSHEET.md"
    manifest_path = pack_dir / "human_review_manifest.json"
    original_worksheet = worksheet_path.read_bytes()
    original_manifest = manifest_path.read_bytes()

    result = apply_script.import_browser_review_draft(
        pack_dir=pack_dir,
        browser_draft_path=browser_draft_path,
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["dry_run"] is True
    assert result["applied_count"] == 0
    assert result["archived_decisions_path"] is None
    assert result["receipt_path"] is None
    assert result["review_sheet_refreshed"] is False
    assert browser_draft_path.read_bytes() == source_bytes
    assert original_drafts == {
        path.name: path.read_bytes()
        for path in (pack_dir / "drafts").glob("*.json")
    }
    assert worksheet_path.read_bytes() == original_worksheet
    assert manifest_path.read_bytes() == original_manifest

    exit_code = apply_script.main([
        str(pack_dir),
        "--browser-draft",
        str(browser_draft_path),
        "--dry-run",
        "--json",
    ])
    cli_result = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert cli_result["browser_draft_sha256"] == hashlib.sha256(source_bytes).hexdigest()


def test_import_browser_review_draft_archives_exact_bytes_and_writes_receipt(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "import_browser_review_draft")
    receipt_validator = _load_module(RECEIPT_VALIDATOR_PATH, "validate_imported_browser_draft_receipt")
    pack_dir = _create_pack(tmp_path / "pack-root")
    browser_draft_path = tmp_path / "downloads" / "review_decisions.browser-draft.json"
    source_bytes = _write_browser_draft(
        pack_dir,
        browser_draft_path,
        first_decision="changes_requested",
    )
    expected_sha256 = hashlib.sha256(source_bytes).hexdigest()

    result = apply_script.import_browser_review_draft(
        pack_dir=pack_dir,
        browser_draft_path=browser_draft_path,
    )

    archived_path = Path(result["archived_decisions_path"])
    receipt_path = Path(result["receipt_path"])
    assert result["ok"] is True
    assert result["browser_draft_sha256"] == expected_sha256
    assert result["applied_count"] == 3
    assert archived_path.name == f"review_decisions.browser-draft.{expected_sha256[:12]}.json"
    assert archived_path.read_bytes() == source_bytes
    assert receipt_path.name == f"review_decision_application_receipt.{expected_sha256[:12]}.json"
    assert receipt_validator.validate_review_decision_receipt(receipt_path)["ok"] is True
    assert result["review_sheet_refreshed"] is True
    assert Path(result["review_sheet_path"]) == pack_dir / "HUMAN_REVIEW_WORKSHEET.md"
    assert Path(result["review_manifest_path"]) == pack_dir / "human_review_manifest.json"
    updated = json.loads(
        (pack_dir / "drafts" / "pilot-rqc-apply_sample_001.json").read_text(encoding="utf-8")
    )
    assert updated["learning_labels"]["human_review_status"] == "changes_requested"
    assert updated["training_boundary"]["training_execution_authorized"] is False
    manifest = json.loads(Path(result["review_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["counts"]["changes_requested_artifacts"] == 1
    assert manifest["artifacts"][0]["human_review_status"] == "changes_requested"
    assert manifest["artifacts"][0]["draft_sha256"] == hashlib.sha256(
        pack_dir.joinpath("drafts", "pilot-rqc-apply_sample_001.json").read_bytes()
    ).hexdigest()
    worksheet = Path(result["review_sheet_path"]).read_text(encoding="utf-8")
    assert "| changes_requested |" in worksheet


def test_import_browser_review_draft_rejects_symlink_review_evidence_before_apply(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "reject_symlink_review_evidence")
    pack_dir = _create_pack(tmp_path / "pack-root")
    browser_draft_path = tmp_path / "downloads" / "review_decisions.browser-draft.json"
    _write_browser_draft(pack_dir, browser_draft_path, first_decision="changes_requested")
    original_drafts = {
        path.name: path.read_bytes()
        for path in (pack_dir / "drafts").glob("*.json")
    }
    manifest_path = pack_dir / "human_review_manifest.json"
    manifest_target = tmp_path / "protected-human-review-manifest.json"
    manifest_target.write_bytes(manifest_path.read_bytes())
    manifest_path.unlink()
    manifest_path.symlink_to(manifest_target)

    with pytest.raises(ValueError, match="symlink review manifest files"):
        apply_script.import_browser_review_draft(
            pack_dir=pack_dir,
            browser_draft_path=browser_draft_path,
        )

    assert original_drafts == {
        path.name: path.read_bytes()
        for path in (pack_dir / "drafts").glob("*.json")
    }
    assert manifest_target.read_bytes() == manifest_path.read_bytes()
    assert not list(pack_dir.glob("review_decisions.browser-draft.*.json"))
    assert not list(pack_dir.glob("review_decision_application_receipt.*.json"))


def test_import_browser_review_draft_preserves_audit_files_after_late_refresh_error(
    tmp_path,
    monkeypatch,
):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "preserve_audit_files_after_refresh_error")
    pack_dir = _create_pack(tmp_path / "pack-root")
    browser_draft_path = tmp_path / "downloads" / "review_decisions.browser-draft.json"
    _write_browser_draft(pack_dir, browser_draft_path, first_decision="changes_requested")

    def fail_after_receipt(**_kwargs):
        raise ValueError("review evidence refresh failed")

    monkeypatch.setattr(apply_script, "create_report_quality_review_sheet", fail_after_receipt)

    with pytest.raises(ValueError, match="review evidence refresh failed"):
        apply_script.import_browser_review_draft(
            pack_dir=pack_dir,
            browser_draft_path=browser_draft_path,
        )

    archived_paths = list(pack_dir.glob("review_decisions.browser-draft.*.json"))
    receipt_paths = list(pack_dir.glob("review_decision_application_receipt.*.json"))
    assert len(archived_paths) == 1
    assert len(receipt_paths) == 1
    receipt = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    assert receipt["decision_file"]["path"] == archived_paths[0].name
    updated = json.loads(
        (pack_dir / "drafts" / "pilot-rqc-apply_sample_001.json").read_text(encoding="utf-8")
    )
    assert updated["learning_labels"]["human_review_status"] == "changes_requested"


def test_import_browser_review_draft_rejects_invalid_unsafe_or_duplicate_input(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "reject_unsafe_browser_review_draft")

    invalid_pack = _create_pack(tmp_path / "invalid-root")
    invalid_path = tmp_path / "invalid-downloads" / "review_decisions.browser-draft.json"
    _write_browser_draft(invalid_pack, invalid_path, first_decision="accepted")
    invalid_result = apply_script.import_browser_review_draft(
        pack_dir=invalid_pack,
        browser_draft_path=invalid_path,
    )
    assert invalid_result["ok"] is False
    assert invalid_result["archived_decisions_path"] is None
    assert not list(invalid_pack.glob("review_decisions.browser-draft.*.json"))

    elevated = json.loads(invalid_path.read_text(encoding="utf-8"))
    elevated["training_authorized"] = True
    invalid_path.write_text(json.dumps(elevated), encoding="utf-8")
    with pytest.raises(ValueError, match="training_authorized=false"):
        apply_script.import_browser_review_draft(
            pack_dir=invalid_pack,
            browser_draft_path=invalid_path,
        )

    safe_path = tmp_path / "safe-browser-draft.json"
    safe_bytes = _write_browser_draft(invalid_pack, safe_path)
    symlink_path = tmp_path / "linked-browser-draft.json"
    symlink_path.symlink_to(safe_path)
    with pytest.raises(ValueError, match="symlink browser draft files"):
        apply_script.import_browser_review_draft(
            pack_dir=invalid_pack,
            browser_draft_path=symlink_path,
        )

    collision_pack = _create_pack(tmp_path / "collision-root")
    collision_source = tmp_path / "collision-browser-draft.json"
    collision_bytes = _write_browser_draft(collision_pack, collision_source)
    collision_sha256 = hashlib.sha256(collision_bytes).hexdigest()
    collision_path = collision_pack / f"review_decisions.browser-draft.{collision_sha256[:12]}.json"
    collision_path.write_bytes(safe_bytes)
    with pytest.raises(ValueError, match="refusing to overwrite archived browser draft"):
        apply_script.import_browser_review_draft(
            pack_dir=collision_pack,
            browser_draft_path=collision_source,
        )
