from __future__ import annotations

from pathlib import Path
import zipfile

from scripts.audit_pilot_delivery import build_pilot_delivery_audit_payload, create_pilot_delivery_audit
from scripts.create_pilot_delivery_manifest import create_pilot_delivery_manifest
from scripts.create_pilot_delivery_receipt import create_pilot_delivery_receipt


def _closeout_text() -> str:
    return """# Pilot Close-Out — business-uat

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
  - uat summary: /tmp/reports/uat/uat-session-20260421T091014Z-business-uat-summary.md
  - pilot handoff: /tmp/reports/pilot/uat-session-20260421T091014Z-business-uat-summary-pilot.md
  - launch checklist: /tmp/reports/pilot/uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md

## Next Action

- `Proceed to next pilot batch`
"""


def _write_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    pilot_dir = tmp_path / "reports" / "pilot"
    uat_dir = tmp_path / "reports" / "uat"
    pilot_dir.mkdir(parents=True)
    uat_dir.mkdir(parents=True)

    closeout_file = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout.md"
    closeout_file.write_text(_closeout_text(), encoding="utf-8")

    artifact_names = [
        "uat-session-20260421T091014Z-business-uat-summary-pilot.md",
        "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist.md",
        "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet.md",
        "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-share-note.md",
        "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-completion-report.md",
        "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-index.md",
    ]
    for name in artifact_names:
        (pilot_dir / name).write_text(name, encoding="utf-8")
    (uat_dir / "uat-session-20260421T091014Z-business-uat-summary.md").write_text("summary", encoding="utf-8")

    bundle_file = pilot_dir / "uat-session-20260421T091014Z-business-uat-summary-pilot-launch-checklist-run-sheet-closeout-delivery-bundle.zip"
    with zipfile.ZipFile(bundle_file, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in artifact_names:
            zf.writestr(name, name)
        zf.writestr("uat-session-20260421T091014Z-business-uat-summary.md", "summary")
        zf.writestr(closeout_file.name, closeout_file.read_text(encoding="utf-8"))

    _, manifest_file = create_pilot_delivery_manifest(bundle_file=bundle_file, output_dir=pilot_dir)
    create_pilot_delivery_receipt(bundle_file=bundle_file, manifest_file=manifest_file, output_dir=pilot_dir)
    return closeout_file, pilot_dir


def test_build_pilot_delivery_audit_payload_passes_when_chain_matches(tmp_path):
    closeout_file, _ = _write_artifacts(tmp_path)

    payload = build_pilot_delivery_audit_payload(closeout_file=closeout_file)

    assert payload["status"] == "PASS"
    assert payload["receipt_matches"] is True
    assert payload["verification_errors"] == []


def test_create_pilot_delivery_audit_writes_markdown(tmp_path):
    closeout_file, pilot_dir = _write_artifacts(tmp_path)

    payload, output_path = create_pilot_delivery_audit(closeout_file=closeout_file, output_dir=pilot_dir)

    assert payload["status"] == "PASS"
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "audit_status" in content
    assert "receipt_matches_current_verification" in content
