from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CREATE_PACK_SCRIPT_PATH = REPO_ROOT / "scripts/create_report_quality_pilot_pack.py"
APPLY_SCRIPT_PATH = REPO_ROOT / "scripts/apply_report_quality_review_decisions.py"


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
    assert len(payload["decisions"]) == 3
    assert payload["decisions"][0]["decision"] == "pending"


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

    result = apply_script.apply_review_decisions(pack_dir=pack_dir, decisions_path=decisions_path, dry_run=True)

    assert result["ok"] is True
    assert result["applied_count"] == 0
    unchanged = json.loads((pack_dir / "drafts" / f"{artifact_id}.json").read_text(encoding="utf-8"))
    assert unchanged["learning_labels"]["human_review_status"] == "pending"


def test_apply_review_decisions_allows_pending_template_with_empty_scores(tmp_path):
    apply_script = _load_module(APPLY_SCRIPT_PATH, "apply_report_quality_review_decisions")
    pack_dir = _create_pack(tmp_path)
    decisions_path = tmp_path / "review_decisions.json"
    apply_script.create_review_decision_template(pack_dir=pack_dir, output_path=decisions_path)

    result = apply_script.apply_review_decisions(pack_dir=pack_dir, decisions_path=decisions_path, dry_run=True)

    assert result["ok"] is True
    assert result["applied_count"] == 0
    assert result["ready_decisions"] == 0
