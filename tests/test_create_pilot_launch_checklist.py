from __future__ import annotations

from scripts.create_pilot_launch_checklist import (
    build_launch_checklist_payload,
    create_pilot_launch_checklist,
    parse_pilot_handoff,
)


def _pilot_handoff_text(status: str = "READY_FOR_PILOT") -> str:
    return f"""# Pilot Handoff — business-uat

- pilot_status: **{status}**
- source_uat_status: `{status}`
- source_preflight_ready: `yes`
- source_latest_report_status: `passed`

## UAT Summary

- recorded_entries: `10`
- scenario_count: `5`
- pass_count: `2`
- blocker_count: `0`
- follow_up_count: `0`

## Runtime Snapshot

- base_url: `https://admin.decisiondoc.kr`
- provider: `claude,gemini,openai`
- quality_first: `ok`
- latest_report: `post-deploy-20260422T004726Z.json`
- provider_routes:
  - default: `claude,gemini,openai`
  - generation: `claude,openai,gemini`
  - attachment: `gemini,claude,openai`
  - visual: `openai`

## Pilot Go / No-Go

- Go decision: `{"GO" if status == "READY_FOR_PILOT" else "NO_GO"}`
"""


def test_parse_pilot_handoff_reads_fields(tmp_path):
    handoff_file = tmp_path / "pilot.md"
    handoff_file.write_text(_pilot_handoff_text(), encoding="utf-8")

    parsed = parse_pilot_handoff(handoff_file)

    assert parsed["pilot_status"] == "READY_FOR_PILOT"
    assert parsed["generation_route"] == "claude,openai,gemini"
    assert parsed["latest_report"] == "post-deploy-20260422T004726Z.json"


def test_build_launch_checklist_payload_ready():
    payload = build_launch_checklist_payload({"pilot_status": "READY_FOR_PILOT"})
    assert payload["launch_status"] == "READY_TO_EXECUTE"
    assert payload["launch_decision"] == "START"


def test_build_launch_checklist_payload_hold():
    payload = build_launch_checklist_payload({"pilot_status": "FOLLOW_UP_REQUIRED"})
    assert payload["launch_status"] == "HOLD"
    assert payload["launch_decision"] == "STOP"


def test_create_pilot_launch_checklist_writes_markdown(tmp_path):
    handoff_file = tmp_path / "pilot.md"
    handoff_file.write_text(_pilot_handoff_text(), encoding="utf-8")

    payload, output_path = create_pilot_launch_checklist(
        handoff_file=handoff_file,
        output_dir=tmp_path / "reports" / "pilot",
    )

    assert payload["launch_status"] == "READY_TO_EXECUTE"
    text = output_path.read_text(encoding="utf-8")
    assert "launch_status: **READY_TO_EXECUTE**" in text
    assert "Launch status: " not in text
    assert "Stop / Rollback Criteria" in text
    assert "decisiondoc-admin-local" in text
