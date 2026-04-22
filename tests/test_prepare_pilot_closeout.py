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


def _run_sheet_text(*, completed: bool) -> str:
    started = "2026-04-22T09:00:00Z" if completed else ""
    request_id = "req-1" if completed else ""
    bundle_id = "bundle-1" if completed else ""
    stop_decision = "continue" if completed else ""
    return f"""# Pilot Run Sheet — business-uat

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
- started_at: {started}
- operator: codex
- business_owner: sungjin
- bundle_type: proposal_kr
- input_summary: basic
- request_id: {request_id}
- bundle_id: {bundle_id}
- export_checked: checked
- quality_feedback: ok
- issues: 없음
- stop_decision: {stop_decision}

### Run 2. 첨부 기반 문서 생성
- started_at: {started}
- operator: codex
- business_owner: sungjin
- bundle_type: proposal_kr
- attachment_list: pilot-attachment.txt
- request_id: {request_id}
- bundle_id: {bundle_id}
- export_checked: checked
- quality_feedback: ok
- issues: 없음
- stop_decision: {stop_decision}

## Escalation / Stop Log

### Incident Notes
- 발생 시각:
- 증상:
- request_id:
- temporary action:
- final decision:

## Pilot Close-Out

- overall_result:
- accepted_for_next_batch:
- follow_up_items:
- evidence_paths:
  - post-deploy:
  - uat summary:
  - pilot handoff:
  - launch checklist:
"""


def test_prepare_pilot_closeout_prefills_evidence(tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_prepare_pilot_closeout", "scripts/prepare_pilot_closeout.py")
    pilot_dir = tmp_path / "reports" / "pilot"
    uat_dir = tmp_path / "reports" / "uat"
    pilot_dir.mkdir(parents=True)
    uat_dir.mkdir(parents=True)
    run_sheet = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet.md"
    run_sheet.write_text(_run_sheet_text(completed=True), encoding="utf-8")

    payload = script.prepare_pilot_closeout(run_sheet_file=run_sheet)

    content = run_sheet.read_text(encoding="utf-8")
    assert payload["completed_runs"] == 2
    assert payload["closeout_ready"] is False
    assert "Run 1/Run 2 API sample execution completed; manual business acceptance pending" in content
    assert "- accepted_for_next_batch:" in content
    assert "  - post-deploy: post-deploy-20260422T004726Z.json" in content
    assert "  - pilot handoff: " in content
    assert "  - launch checklist: " in content
    assert "  - uat summary: " in content


def test_prepare_pilot_closeout_requires_completed_runs(tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_prepare_pilot_closeout_incomplete", "scripts/prepare_pilot_closeout.py")
    run_sheet = tmp_path / "pilot-run-sheet.md"
    run_sheet.write_text(_run_sheet_text(completed=False), encoding="utf-8")

    try:
        script.prepare_pilot_closeout(run_sheet_file=run_sheet)
    except SystemExit as exc:
        assert str(exc) == "Pilot close-out preparation requires both Run 1 and Run 2 to be completed first."
    else:
        raise AssertionError("Expected SystemExit for incomplete pilot runs")
