from __future__ import annotations

from pathlib import Path
import zipfile

from scripts.create_pilot_delivery_bundle import (
    build_pilot_delivery_bundle_payload,
    create_pilot_delivery_bundle,
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
  - uat summary: {{}}
  - pilot handoff: {{}}
  - launch checklist: {{}}

## Next Action

- `Proceed to next pilot batch`
"""


def test_build_pilot_delivery_bundle_payload_includes_delivery_index(tmp_path):
    pilot_dir = tmp_path / "reports" / "pilot"
    uat_dir = tmp_path / "reports" / "uat"
    pilot_dir.mkdir(parents=True)
    uat_dir.mkdir(parents=True)

    closeout_file = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md"
    handoff = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot.md"
    checklist = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md"
    run_sheet = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet.md"
    share_note = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-share-note.md"
    completion = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-completion-report.md"
    delivery_index = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-index.md"
    uat_summary = uat_dir / "uat-session-20260421T091014Z-business-uat-summary.md"

    text = _closeout_text().format(uat_summary, handoff, checklist)
    closeout_file.write_text(text, encoding="utf-8")
    for path in (handoff, checklist, run_sheet, share_note, completion, delivery_index, uat_summary):
        path.write_text(path.name, encoding="utf-8")

    payload = build_pilot_delivery_bundle_payload(closeout_file=closeout_file)

    assert payload["pilot_status"] == "PILOT_COMPLETE"
    assert any(item.endswith("-delivery-index.md") for item in payload["bundle_files"])
    assert any(item.endswith("-share-note.md") for item in payload["bundle_files"])


def test_create_pilot_delivery_bundle_writes_zip(tmp_path):
    pilot_dir = tmp_path / "reports" / "pilot"
    uat_dir = tmp_path / "reports" / "uat"
    pilot_dir.mkdir(parents=True)
    uat_dir.mkdir(parents=True)

    closeout_file = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md"
    handoff = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot.md"
    checklist = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md"
    run_sheet = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet.md"
    share_note = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-share-note.md"
    completion = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-completion-report.md"
    delivery_index = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-index.md"
    uat_summary = uat_dir / "uat-session-20260421T091014Z-business-uat-summary.md"

    text = _closeout_text().format(uat_summary, handoff, checklist)
    closeout_file.write_text(text, encoding="utf-8")
    for path in (handoff, checklist, run_sheet, share_note, completion, delivery_index, uat_summary):
        path.write_text(path.name, encoding="utf-8")

    payload, bundle_zip = create_pilot_delivery_bundle(
        closeout_file=closeout_file,
        output_dir=pilot_dir,
    )

    assert payload["pilot_status"] == "PILOT_COMPLETE"
    assert bundle_zip.exists()
    with zipfile.ZipFile(bundle_zip) as zf:
        names = set(zf.namelist())
    assert closeout_file.name in names
    assert share_note.name in names
    assert completion.name in names
    assert delivery_index.name in names
