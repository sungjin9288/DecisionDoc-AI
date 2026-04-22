from __future__ import annotations

from pathlib import Path

from scripts.create_pilot_delivery_index import (
    build_pilot_delivery_payload,
    create_pilot_delivery_index,
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


def test_build_pilot_delivery_payload_derives_artifacts(tmp_path):
    closeout_file = tmp_path / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md"
    closeout_file.write_text(_closeout_text(), encoding="utf-8")

    payload = build_pilot_delivery_payload(closeout_file=closeout_file)

    artifacts = payload["artifact_paths"]
    assert payload["pilot_status"] == "PILOT_COMPLETE"
    assert artifacts["share_note"].endswith("-closeout-share-note.md")
    assert artifacts["completion_report"].endswith("-closeout-completion-report.md")
    assert artifacts["run_sheet"].endswith("-run-sheet.md")


def test_create_pilot_delivery_index_writes_markdown(tmp_path):
    closeout_file = tmp_path / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md"
    closeout_file.write_text(_closeout_text(), encoding="utf-8")

    payload, output_path = create_pilot_delivery_index(
        closeout_file=closeout_file,
        output_dir=tmp_path / "reports" / "pilot",
    )

    text = output_path.read_text(encoding="utf-8")
    assert payload["pilot_status"] == "PILOT_COMPLETE"
    assert "Pilot Delivery Index — business-uat" in text
    assert "Recommended Reading Order" in text
    assert "Pilot approved and ready to share." in text
    assert "share_note:" in text
