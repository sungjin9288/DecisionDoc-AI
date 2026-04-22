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
- provider: `claude,openai,gemini`
- quality_first: `ok`

## Pilot Run Log

### Run 1. 기본 문서 생성
- started_at:
- operator:
- business_owner:
- bundle_type:
- input_summary:
- request_id:
- bundle_id:
- export_checked:
- quality_feedback:
- issues:
- stop_decision:

### Run 2. 첨부 기반 문서 생성
- started_at:
- operator:
- business_owner:
- bundle_type:
- attachment_list:
- request_id:
- bundle_id:
- export_checked:
- quality_feedback:
- issues:
- stop_decision:

## Escalation / Stop Log

- [ ] `/health` 이상 없음

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


def test_record_pilot_run_updates_run1_fields(tmp_path: Path, capsys) -> None:
    script = _load_script_module("decisiondoc_record_pilot_run", "scripts/record_pilot_run.py")
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(_run_sheet_text(), encoding="utf-8")

    result = script.main(
        [
            "--run-sheet-file",
            str(run_sheet_file),
            "--target",
            "run1",
            "--field",
            "started_at=2026-04-22T09:00:00+09:00",
            "--field",
            "operator=sungjin",
            "--field",
            "request_id=req-run-1",
            "--field",
            "bundle_id=bundle-run-1",
            "--field",
            "stop_decision=continue",
        ]
    )

    captured = capsys.readouterr().out
    content = run_sheet_file.read_text(encoding="utf-8")
    assert result == 0
    assert "Recorded pilot run updates:" in captured
    assert "- started_at: 2026-04-22T09:00:00+09:00" in content
    assert "- operator: sungjin" in content
    assert "- request_id: req-run-1" in content
    assert "- bundle_id: bundle-run-1" in content
    assert "- stop_decision: continue" in content


def test_record_pilot_run_updates_closeout_evidence_fields(tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_record_pilot_run_closeout", "scripts/record_pilot_run.py")
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(_run_sheet_text(), encoding="utf-8")

    result = script.main(
        [
            "--run-sheet-file",
            str(run_sheet_file),
            "--target",
            "closeout",
            "--field",
            "overall_result=성공",
            "--field",
            "accepted_for_next_batch=예",
            "--field",
            "post-deploy=post-deploy-20260422T004726Z.json",
            "--field",
            "uat summary=reports/uat/uat-session-summary.md",
        ]
    )

    content = run_sheet_file.read_text(encoding="utf-8")
    assert result == 0
    assert "- overall_result: 성공" in content
    assert "- accepted_for_next_batch: 예" in content
    assert "  - post-deploy: post-deploy-20260422T004726Z.json" in content
    assert "  - uat summary: reports/uat/uat-session-summary.md" in content


def test_record_pilot_run_requires_existing_run_sheet(tmp_path: Path) -> None:
    script = _load_script_module("decisiondoc_record_pilot_run_missing", "scripts/record_pilot_run.py")
    missing_path = tmp_path / "missing.md"

    try:
        script.main(
            [
                "--run-sheet-file",
                str(missing_path),
                "--target",
                "run1",
                "--field",
                "request_id=req-run-1",
            ]
        )
    except SystemExit as exc:
        assert str(exc) == f"Pilot run sheet not found: {missing_path}"
    else:
        raise AssertionError("Expected SystemExit for missing pilot run sheet")
