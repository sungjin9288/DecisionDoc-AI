from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _run_sheet_text() -> str:
    return """# Pilot Run Sheet — business-uat

- generated_at: 2026-04-22T00:00:00+00:00
- run_status: **OPEN**
- launch_status: `READY_TO_EXECUTE`
- launch_decision: `START`

## Pilot Context

- base_url: `https://admin.decisiondoc.kr`
- latest_report: `post-deploy-20260422T004726Z.json`
- provider: `claude,gemini,openai`
- quality_first: `ok`

## Pilot Run Log

### Run 1. 기본 문서 생성
- started_at: 2026-04-22T09:00:00Z
- operator: codex
- business_owner: sungjin
- bundle_type: proposal_kr
- input_summary: basic
- request_id: req-run-1
- bundle_id: bundle-run-1
- export_checked: checked
- quality_feedback: ok
- issues: 없음
- stop_decision: continue

### Run 2. 첨부 기반 문서 생성
- started_at: 2026-04-22T10:00:00Z
- operator: codex
- business_owner: sungjin
- bundle_type: proposal_kr
- attachment_list: pilot-attachment.txt
- request_id: req-run-2
- bundle_id: bundle-run-2
- export_checked: checked
- quality_feedback: ok
- issues: 없음
- stop_decision: continue

## Escalation / Stop Log

### Incident Notes
- 발생 시각:
- 증상:
- request_id:
- temporary action:
- final decision:

## Pilot Close-Out

- overall_result: Run 1/Run 2 API sample execution completed; manual business acceptance pending
- accepted_for_next_batch:
- follow_up_items: business owner 최종 판정 필요
- evidence_paths:
  - post-deploy: post-deploy-20260422T004726Z.json
  - uat summary: reports/uat/uat-session-20260421T091014Z-business-uat-summary.md
  - pilot handoff: reports/pilot/uat-session-20260421T091014Z-business-uat-summary-pilot.md
  - launch checklist: reports/pilot/uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md
"""


def test_complete_pilot_closeout_marks_complete_for_yes(tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_complete_pilot_closeout", "scripts/complete_pilot_closeout.py")
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(_run_sheet_text(), encoding="utf-8")

    payload, output_path = script.complete_pilot_closeout(
        run_sheet_file=run_sheet_file,
        output_dir=tmp_path / "reports" / "pilot",
        accepted_for_next_batch="yes",
    )

    content = run_sheet_file.read_text(encoding="utf-8")
    closeout = output_path.read_text(encoding="utf-8")
    assert payload["closeout_status"] == "PILOT_COMPLETE"
    assert "- overall_result: Pilot sample execution completed and approved for next batch." in content
    assert "- accepted_for_next_batch: 예" in content
    assert "- follow_up_items: 없음" in content
    assert "closeout_status: **PILOT_COMPLETE**" in closeout
    assert "Proceed to next pilot batch" in closeout


def test_complete_pilot_closeout_preserves_incomplete_for_no(tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_complete_pilot_closeout_no", "scripts/complete_pilot_closeout.py")
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(_run_sheet_text(), encoding="utf-8")

    payload, output_path = script.complete_pilot_closeout(
        run_sheet_file=run_sheet_file,
        output_dir=tmp_path / "reports" / "pilot",
        accepted_for_next_batch="아니오",
        follow_up_items="추가 검수 필요",
    )

    content = run_sheet_file.read_text(encoding="utf-8")
    closeout = output_path.read_text(encoding="utf-8")
    assert payload["closeout_status"] == "INCOMPLETE"
    assert "- overall_result: Pilot sample execution completed but additional follow-up is required before the next batch." in content
    assert "- accepted_for_next_batch: 아니오" in content
    assert "- follow_up_items: 추가 검수 필요" in content
    assert "closeout_status: **INCOMPLETE**" in closeout
