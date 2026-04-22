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
    run1_started = "2026-04-22T09:00:00+09:00" if completed else ""
    run2_started = "2026-04-22T10:00:00+09:00" if completed else ""
    operator = "sungjin" if completed else ""
    request_id = "req-1" if completed else ""
    bundle_id = "bundle-1" if completed else ""
    stop_decision = "continue" if completed else ""
    overall_result = "성공" if completed else ""
    accepted = "예" if completed else ""
    return f"""# Pilot Run Sheet — business-uat

- generated_at: 2026-04-22T00:00:00+00:00
- run_status: **OPEN**
- launch_status: `READY_TO_EXECUTE`
- launch_decision: `START`

## Pilot Context

- base_url: `https://admin.decisiondoc.kr`
- latest_report: `post-deploy-20260422T004726Z.json`
- provider: `claude,openai,gemini`
- quality_first: `ok`

## Pilot Run Log

### Run 1. 기본 문서 생성
- started_at: {run1_started}
- operator: {operator}
- business_owner:
- bundle_type:
- input_summary:
- request_id: {request_id}
- bundle_id: {bundle_id}
- export_checked:
- quality_feedback:
- issues:
- stop_decision: {stop_decision}

### Run 2. 첨부 기반 문서 생성
- started_at: {run2_started}
- operator: {operator}
- business_owner:
- bundle_type:
- attachment_list:
- request_id: {request_id}
- bundle_id: {bundle_id}
- export_checked:
- quality_feedback:
- issues:
- stop_decision: {stop_decision}

## Escalation / Stop Log

- [ ] `/health` 이상 없음

### Incident Notes
- 발생 시각:
- 증상:
- request_id:
- temporary action:
- final decision:

## Pilot Close-Out

- overall_result: {overall_result}
- accepted_for_next_batch: {accepted}
- follow_up_items:
- evidence_paths:
  - post-deploy:
  - uat summary:
  - pilot handoff:
  - launch checklist:
"""


def test_show_pilot_run_renders_incomplete_summary(tmp_path: Path, capsys) -> None:
    script = _load_script_module("decisiondoc_show_pilot_run", "scripts/show_pilot_run.py")
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(_run_sheet_text(completed=False), encoding="utf-8")

    result = script.main(["--run-sheet-file", str(run_sheet_file)])

    captured = capsys.readouterr().out
    assert result == 0
    assert "Completed runs: 0" in captured
    assert "Close-out status: INCOMPLETE" in captured
    assert "Run 1 missing: started_at,operator,request_id,bundle_id,stop_decision" in captured
    assert "Close-out ready: no" in captured


def test_show_pilot_run_renders_complete_summary(tmp_path: Path, capsys) -> None:
    script = _load_script_module("decisiondoc_show_pilot_run_complete", "scripts/show_pilot_run.py")
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(_run_sheet_text(completed=True), encoding="utf-8")

    result = script.main(["--run-sheet-file", str(run_sheet_file)])

    captured = capsys.readouterr().out
    assert result == 0
    assert "Completed runs: 2" in captured
    assert "Close-out status: PILOT_COMPLETE" in captured
    assert "Run 1 missing: none" in captured
    assert "Run 2 missing: none" in captured
    assert "Close-out ready: yes" in captured
