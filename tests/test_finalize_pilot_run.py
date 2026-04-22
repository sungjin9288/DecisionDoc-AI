from __future__ import annotations

from scripts.finalize_pilot_run import (
    build_pilot_closeout_payload,
    finalize_pilot_run,
    parse_pilot_run_sheet,
)


def _run_sheet_text(*, accepted_for_next_batch: str = "예", overall_result: str = "성공") -> str:
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
- started_at: 2026-04-22T09:00:00+09:00
- operator: sungjin
- business_owner: owner-a
- bundle_type: proposal_kr
- input_summary: 기본 제안서 생성
- request_id: req-run-1
- bundle_id: bundle-run-1
- export_checked: yes
- quality_feedback: 구조 안정적
- issues: 없음
- stop_decision: continue

### Run 2. 첨부 기반 문서 생성
- started_at: 2026-04-22T10:00:00+09:00
- operator: sungjin
- business_owner: owner-b
- bundle_type: proposal_kr
- attachment_list: intro.pdf, concept.pptx
- request_id: req-run-2
- bundle_id: bundle-run-2
- export_checked: yes
- quality_feedback: 첨부 문맥 반영 확인
- issues: 없음
- stop_decision: continue

## Escalation / Stop Log

- [ ] `/health` 이상 없음

### Incident Notes
- 발생 시각: -
- 증상: 없음
- request_id: -
- temporary action: -
- final decision: continue

## Pilot Close-Out

- overall_result: {overall_result}
- accepted_for_next_batch: {accepted_for_next_batch}
- follow_up_items: 없음
- evidence_paths:
  - post-deploy: post-deploy-20260422T004726Z.json
  - uat summary: reports/uat/uat-session-summary.md
  - pilot handoff: reports/pilot/pilot-handoff.md
  - launch checklist: reports/pilot/pilot-launch-checklist.md
"""


def test_parse_pilot_run_sheet_reads_completed_fields(tmp_path):
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(_run_sheet_text(), encoding="utf-8")

    parsed = parse_pilot_run_sheet(run_sheet_file)

    assert parsed["run_status"] == "OPEN"
    assert parsed["base_url"] == "https://admin.decisiondoc.kr"
    assert parsed["run1"]["request_id"] == "req-run-1"
    assert parsed["run2"]["bundle_id"] == "bundle-run-2"
    assert parsed["closeout"]["accepted_for_next_batch"] == "예"


def test_build_pilot_closeout_payload_marks_complete():
    payload = build_pilot_closeout_payload(parse_pilot_run_sheet_payload())

    assert payload["completed_runs"] == 2
    assert payload["closeout_status"] == "PILOT_COMPLETE"


def test_finalize_pilot_run_writes_incomplete_closeout(tmp_path):
    run_sheet_file = tmp_path / "pilot-run-sheet.md"
    run_sheet_file.write_text(
        _run_sheet_text(accepted_for_next_batch="-", overall_result="-"),
        encoding="utf-8",
    )

    payload, output_path = finalize_pilot_run(
        run_sheet_file=run_sheet_file,
        output_dir=tmp_path / "reports" / "pilot",
    )

    assert payload["completed_runs"] == 2
    assert payload["closeout_status"] == "INCOMPLETE"
    text = output_path.read_text(encoding="utf-8")
    assert "closeout_status: **INCOMPLETE**" in text
    assert "completed_runs: `2`" in text
    assert "Complete the run sheet fields before using this as a pilot close-out artifact" in text


def parse_pilot_run_sheet_payload() -> dict[str, object]:
    return {
        "session_title": "business-uat",
        "run_status": "OPEN",
        "launch_status": "READY_TO_EXECUTE",
        "launch_decision": "START",
        "base_url": "https://admin.decisiondoc.kr",
        "latest_report": "post-deploy-20260422T004726Z.json",
        "provider": "claude,openai,gemini",
        "quality_first": "ok",
        "run1": {
            "started_at": "2026-04-22T09:00:00+09:00",
            "operator": "sungjin",
            "request_id": "req-run-1",
            "bundle_id": "bundle-run-1",
            "stop_decision": "continue",
        },
        "run2": {
            "started_at": "2026-04-22T10:00:00+09:00",
            "operator": "sungjin",
            "request_id": "req-run-2",
            "bundle_id": "bundle-run-2",
            "stop_decision": "continue",
        },
        "incident": {},
        "closeout": {
            "overall_result": "성공",
            "accepted_for_next_batch": "예",
        },
    }
