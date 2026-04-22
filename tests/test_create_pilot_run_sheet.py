from __future__ import annotations

from scripts.create_pilot_run_sheet import (
    build_pilot_run_payload,
    create_pilot_run_sheet,
    parse_launch_checklist,
)


def _launch_checklist_text(status: str = "READY_TO_EXECUTE") -> str:
    return f"""# Pilot Launch Checklist — business-uat

- launch_status: **{status}**
- launch_decision: `{"START" if status == "READY_TO_EXECUTE" else "STOP"}`
- source_pilot_status: `READY_FOR_PILOT`

## Readiness Snapshot

- base_url: `https://admin.decisiondoc.kr`
- latest_report: `post-deploy-20260422T004726Z.json`
- provider: `claude,gemini,openai`
- quality_first: `ok`
- provider_routes:
  - default: `claude,gemini,openai`
  - generation: `claude,openai,gemini`
  - attachment: `gemini,claude,openai`
  - visual: `openai`
"""


def test_parse_launch_checklist_reads_fields(tmp_path):
    checklist_file = tmp_path / "launch.md"
    checklist_file.write_text(_launch_checklist_text(), encoding="utf-8")

    parsed = parse_launch_checklist(checklist_file)

    assert parsed["launch_status"] == "READY_TO_EXECUTE"
    assert parsed["base_url"] == "https://admin.decisiondoc.kr"
    assert parsed["generation_route"] == "claude,openai,gemini"


def test_build_pilot_run_payload_open():
    payload = build_pilot_run_payload({"launch_status": "READY_TO_EXECUTE"})
    assert payload["run_status"] == "OPEN"


def test_build_pilot_run_payload_hold():
    payload = build_pilot_run_payload({"launch_status": "HOLD"})
    assert payload["run_status"] == "HOLD"


def test_create_pilot_run_sheet_writes_markdown(tmp_path):
    checklist_file = tmp_path / "launch.md"
    checklist_file.write_text(_launch_checklist_text(), encoding="utf-8")

    payload, output_path = create_pilot_run_sheet(
        checklist_file=checklist_file,
        output_dir=tmp_path / "reports" / "pilot",
    )

    assert payload["run_status"] == "OPEN"
    text = output_path.read_text(encoding="utf-8")
    assert "run_status: **OPEN**" in text
    assert "### Run 1. 기본 문서 생성" in text
    assert "### Run 2. 첨부 기반 문서 생성" in text
    assert "## Escalation / Stop Log" in text
