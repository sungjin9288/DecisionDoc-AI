from __future__ import annotations

from pathlib import Path

from scripts.create_pilot_completion_report import (
    build_pilot_completion_payload,
    create_pilot_completion_report,
    parse_pilot_closeout,
)


def _closeout_text(status: str = "PILOT_COMPLETE", accepted: str = "예") -> str:
    return f"""# Pilot Close-Out — business-uat

- generated_at: 2026-04-22T09:31:18+00:00
- closeout_status: **{status}**
- completed_runs: `2`
- source_run_status: `OPEN`

## Pilot Context

- base_url: `https://admin.decisiondoc.kr`
- latest_report: `post-deploy-20260422T004726Z.json`
- provider: `claude,gemini,openai`
- quality_first: `ok`

## Run Summary

### Run 1
- request_id: req-run-1
- bundle_id: bundle-run-1
- export_checked: generate/export 200 files=4
- quality_feedback: ok
- issues: 없음
- stop_decision: continue

### Run 2
- request_id: req-run-2
- bundle_id: bundle-run-2
- export_checked: 미검증
- quality_feedback: ok
- issues: 없음
- stop_decision: continue

## Incident Summary

- symptom: -
- request_id: -
- temporary_action: -
- final_decision: -

## Pilot Close-Out Decision

- overall_result: Pilot accepted
- accepted_for_next_batch: {accepted}
- follow_up_items: 없음
- evidence_paths:
  - post-deploy: post-deploy-20260422T004726Z.json
  - uat summary: reports/uat/uat-session-20260421T091014Z-business-uat-summary.md
  - pilot handoff: reports/pilot/uat-session-20260421T091014Z-business-uat-summary-pilot.md
  - launch checklist: reports/pilot/uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md

## Next Action

- `Proceed to next pilot batch`
"""


def test_parse_pilot_closeout_reads_fields(tmp_path):
    closeout_file = tmp_path / "pilot-closeout.md"
    closeout_file.write_text(_closeout_text(), encoding="utf-8")

    parsed = parse_pilot_closeout(closeout_file)

    assert parsed["closeout_status"] == "PILOT_COMPLETE"
    assert parsed["run1"]["request_id"] == "req-run-1"
    assert parsed["decision"]["accepted_for_next_batch"] == "예"


def test_build_pilot_completion_payload_keeps_decision():
    payload = build_pilot_completion_payload(
        parse_pilot_closeout_payload(),
        closeout_file=Path("/tmp/pilot-closeout.md"),
    )

    assert payload["accepted_for_next_batch"] == "예"
    assert payload["request_ids"] == ["req-run-1", "req-run-2"]


def test_create_pilot_completion_report_writes_markdown(tmp_path):
    closeout_file = tmp_path / "pilot-closeout.md"
    closeout_file.write_text(_closeout_text(), encoding="utf-8")

    payload, output_path = create_pilot_completion_report(
        closeout_file=closeout_file,
        output_dir=tmp_path / "reports" / "pilot",
    )

    text = output_path.read_text(encoding="utf-8")
    assert payload["closeout_status"] == "PILOT_COMPLETE"
    assert "pilot_status: **PILOT_COMPLETE**" in text
    assert "accepted_for_next_batch: `예`" in text
    assert "Pilot approved for the next batch." in text


def parse_pilot_closeout_payload() -> dict[str, object]:
    return {
        "session_title": "business-uat",
        "closeout_status": "PILOT_COMPLETE",
        "completed_runs": "2",
        "source_run_status": "OPEN",
        "base_url": "https://admin.decisiondoc.kr",
        "latest_report": "post-deploy-20260422T004726Z.json",
        "provider": "claude,gemini,openai",
        "quality_first": "ok",
        "run1": {"request_id": "req-run-1", "bundle_id": "bundle-run-1"},
        "run2": {"request_id": "req-run-2", "bundle_id": "bundle-run-2"},
        "incident": {},
        "decision": {
            "accepted_for_next_batch": "예",
            "overall_result": "Pilot accepted",
            "follow_up_items": "없음",
            "post-deploy": "post-deploy-20260422T004726Z.json",
            "uat summary": "reports/uat/uat-session-20260421T091014Z-business-uat-summary.md",
            "pilot handoff": "reports/pilot/uat-session-20260421T091014Z-business-uat-summary-pilot.md",
            "launch checklist": "reports/pilot/uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md",
        },
    }
