#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def _extract_section(text: str, start_heading: str, end_heading: str | None = None) -> str:
    start = text.find(start_heading)
    if start == -1:
        return ""
    end = text.find(end_heading, start) if end_heading else len(text)
    if end == -1:
        end = len(text)
    return text[start:end]


def _parse_dash_fields(block: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        fields[key.strip()] = value.strip() or "-"
    return fields


def parse_pilot_run_sheet(run_sheet_file: Path) -> dict[str, object]:
    text = Path(run_sheet_file).read_text(encoding="utf-8")

    def _match(pattern: str, default: str = "-") -> str:
        matched = re.search(pattern, text, re.MULTILINE)
        return matched.group(1).strip() if matched else default

    run1_block = _extract_section(text, "### Run 1. 기본 문서 생성", "### Run 2. 첨부 기반 문서 생성")
    run2_block = _extract_section(text, "### Run 2. 첨부 기반 문서 생성", "## Escalation / Stop Log")
    incident_block = _extract_section(text, "### Incident Notes", "## Pilot Close-Out")
    closeout_block = _extract_section(text, "## Pilot Close-Out")

    return {
        "session_title": _match(r"^# Pilot Run Sheet — (.+)$"),
        "run_status": _match(r"run_status:\s+\*\*(.+?)\*\*"),
        "launch_status": _match(r"launch_status:\s+`([^`]+)`"),
        "launch_decision": _match(r"launch_decision:\s+`([^`]+)`"),
        "base_url": _match(r"base_url:\s+`([^`]+)`"),
        "latest_report": _match(r"latest_report:\s+`([^`]+)`"),
        "provider": _match(r"provider:\s+`([^`]+)`"),
        "quality_first": _match(r"quality_first:\s+`([^`]+)`"),
        "run1": _parse_dash_fields(run1_block),
        "run2": _parse_dash_fields(run2_block),
        "incident": _parse_dash_fields(incident_block),
        "closeout": _parse_dash_fields(closeout_block),
    }


def _has_value(value: str | None) -> bool:
    text = str(value or "").strip()
    return bool(text and text != "-")


def _run_completed(fields: dict[str, str]) -> bool:
    return all(
        _has_value(fields.get(key))
        for key in ("started_at", "operator", "request_id", "bundle_id", "stop_decision")
    )


def build_pilot_closeout_payload(parsed: dict[str, object]) -> dict[str, object]:
    run1 = parsed.get("run1") or {}
    run2 = parsed.get("run2") or {}
    closeout = parsed.get("closeout") or {}
    completed_runs = int(_run_completed(run1)) + int(_run_completed(run2))
    overall_result = str(closeout.get("overall_result", "-")).strip()
    accepted = str(closeout.get("accepted_for_next_batch", "-")).strip()
    ready = (
        completed_runs >= 2
        and _has_value(overall_result)
        and _has_value(accepted)
        and accepted.lower().startswith(("yes", "예"))
    )
    return {
        **parsed,
        "completed_runs": completed_runs,
        "closeout_status": "PILOT_COMPLETE" if ready else "INCOMPLETE",
    }


def build_pilot_closeout_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    closeout = payload.get("closeout") or {}
    run1 = payload.get("run1") or {}
    run2 = payload.get("run2") or {}
    incident = payload.get("incident") or {}
    return f"""# Pilot Close-Out — {payload.get('session_title', '-')}

- generated_at: {generated_at.isoformat()}
- closeout_status: **{payload.get('closeout_status', 'INCOMPLETE')}**
- completed_runs: `{payload.get('completed_runs', 0)}`
- source_run_status: `{payload.get('run_status', '-')}`

## Pilot Context

- base_url: `{payload.get('base_url', '-')}`
- latest_report: `{payload.get('latest_report', '-')}`
- provider: `{payload.get('provider', '-')}`
- quality_first: `{payload.get('quality_first', '-')}`

## Run Summary

### Run 1
- request_id: {run1.get('request_id', '-')}
- bundle_id: {run1.get('bundle_id', '-')}
- export_checked: {run1.get('export_checked', '-')}
- quality_feedback: {run1.get('quality_feedback', '-')}
- issues: {run1.get('issues', '-')}
- stop_decision: {run1.get('stop_decision', '-')}

### Run 2
- request_id: {run2.get('request_id', '-')}
- bundle_id: {run2.get('bundle_id', '-')}
- export_checked: {run2.get('export_checked', '-')}
- quality_feedback: {run2.get('quality_feedback', '-')}
- issues: {run2.get('issues', '-')}
- stop_decision: {run2.get('stop_decision', '-')}

## Incident Summary

- symptom: {incident.get('증상', '-')}
- request_id: {incident.get('request_id', '-')}
- temporary_action: {incident.get('temporary action', '-')}
- final_decision: {incident.get('final decision', '-')}

## Pilot Close-Out Decision

- overall_result: {closeout.get('overall_result', '-')}
- accepted_for_next_batch: {closeout.get('accepted_for_next_batch', '-')}
- follow_up_items: {closeout.get('follow_up_items', '-')}
- evidence_paths:
  - post-deploy: {closeout.get('post-deploy', '-')}
  - uat summary: {closeout.get('uat summary', '-')}
  - pilot handoff: {closeout.get('pilot handoff', '-')}
  - launch checklist: {closeout.get('launch checklist', '-')}

## Next Action

- `{"Proceed to next pilot batch" if payload.get('closeout_status') == 'PILOT_COMPLETE' else "Complete the run sheet fields before using this as a pilot close-out artifact"}` 
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def finalize_pilot_run(*, run_sheet_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    parsed = parse_pilot_run_sheet(run_sheet_file)
    payload = build_pilot_closeout_payload(parsed)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{Path(run_sheet_file).stem}-closeout.md"
    markdown = build_pilot_closeout_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a pilot close-out summary markdown from an existing pilot run sheet.",
    )
    parser.add_argument("--run-sheet-file", required=True, help="Pilot run sheet markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot close-out markdown.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = finalize_pilot_run(
        run_sheet_file=Path(args.run_sheet_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot close-out: {output_path}", flush=True)
    print(f"Close-out status: {payload.get('closeout_status', 'INCOMPLETE')}", flush=True)
    return 0 if payload.get("closeout_status") == "PILOT_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
