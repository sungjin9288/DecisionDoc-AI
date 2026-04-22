from __future__ import annotations

import json
from pathlib import Path

from scripts.publish_pilot_delivery_latest_readiness_artifacts import (
    publish_pilot_delivery_latest_readiness_artifacts,
)
from scripts.refresh_pilot_delivery_chain import refresh_pilot_delivery_chain


def _closeout_text(tmp_path: Path) -> str:
    return f"""# Pilot Close-Out — business-uat

- generated_at: 2026-04-22T09:31:18+00:00
- closeout_status: **PILOT_COMPLETE**
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
- accepted_for_next_batch: 예
- follow_up_items: 없음
- evidence_paths:
  - post-deploy: post-deploy-20260422T004726Z.json
  - uat summary: {tmp_path / "reports" / "uat" / "uat-session-20260421T091014Z-business-uat-summary.md"}
  - pilot handoff: {tmp_path / "reports" / "pilot" / "uat-session-20260421T091014Z-business-uat-summary-pilot.md"}
  - launch checklist: {tmp_path / "reports" / "pilot" / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md"}

## Next Action

- `Proceed to next pilot batch`
"""


def test_publish_pilot_delivery_latest_readiness_artifacts_syncs_json_and_note(tmp_path):
    pilot_dir = tmp_path / "reports" / "pilot"
    uat_dir = tmp_path / "reports" / "uat"
    pilot_dir.mkdir(parents=True)
    uat_dir.mkdir(parents=True)

    closeout_file = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md"
    closeout_file.write_text(_closeout_text(tmp_path), encoding="utf-8")

    (pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot.md").write_text("handoff", encoding="utf-8")
    (pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md").write_text("checklist", encoding="utf-8")
    (pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet.md").write_text("run-sheet", encoding="utf-8")
    (pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-share-note.md").write_text("share-note", encoding="utf-8")
    (pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-completion-report.md").write_text("completion", encoding="utf-8")
    (pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-index.md").write_text("delivery-index", encoding="utf-8")
    (uat_dir / "uat-session-20260421T091014Z-business-uat-summary.md").write_text("summary", encoding="utf-8")

    refresh_pilot_delivery_chain(closeout_file=closeout_file, output_dir=pilot_dir)

    result = publish_pilot_delivery_latest_readiness_artifacts(
        closeout_file=closeout_file,
        output_dir=pilot_dir,
    )

    assert result["ok"] is True
    assert result["status"] == "PASS"
    latest_json = json.loads(Path(result["latest_readiness_json"]).read_text(encoding="utf-8"))
    latest_note = Path(result["latest_readiness_note"]).read_text(encoding="utf-8")
    assert latest_json["ok"] is True
    assert latest_json["stale"] is False
    assert "ready: **PASS**" in latest_note
    assert "latest_status_file:" in latest_note
    assert "latest_audit_file:" in latest_note
