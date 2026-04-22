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


def parse_pilot_closeout(closeout_file: Path) -> dict[str, object]:
    text = Path(closeout_file).read_text(encoding="utf-8")

    def _match(pattern: str, default: str = "-") -> str:
        matched = re.search(pattern, text, re.MULTILINE)
        return matched.group(1).strip() if matched else default

    run1_block = _extract_section(text, "### Run 1", "### Run 2")
    run2_block = _extract_section(text, "### Run 2", "## Incident Summary")
    incident_block = _extract_section(text, "## Incident Summary", "## Pilot Close-Out Decision")
    decision_block = _extract_section(text, "## Pilot Close-Out Decision", "## Next Action")

    return {
        "session_title": _match(r"^# Pilot Close-Out — (.+)$"),
        "generated_at": _match(r"generated_at:\s+(.+)$"),
        "closeout_status": _match(r"closeout_status:\s+\*\*(.+?)\*\*"),
        "completed_runs": _match(r"completed_runs:\s+`([^`]+)`", "0"),
        "source_run_status": _match(r"source_run_status:\s+`([^`]+)`"),
        "base_url": _match(r"base_url:\s+`([^`]+)`"),
        "latest_report": _match(r"latest_report:\s+`([^`]+)`"),
        "provider": _match(r"provider:\s+`([^`]+)`"),
        "quality_first": _match(r"quality_first:\s+`([^`]+)`"),
        "run1": _parse_dash_fields(run1_block),
        "run2": _parse_dash_fields(run2_block),
        "incident": _parse_dash_fields(incident_block),
        "decision": _parse_dash_fields(decision_block),
    }


def build_pilot_completion_payload(parsed: dict[str, object], *, closeout_file: Path) -> dict[str, object]:
    run1 = parsed.get("run1") or {}
    run2 = parsed.get("run2") or {}
    decision = parsed.get("decision") or {}
    incident = parsed.get("incident") or {}
    return {
        **parsed,
        "closeout_file": str(Path(closeout_file)),
        "run_count": 2,
        "request_ids": [
            run1.get("request_id", "-"),
            run2.get("request_id", "-"),
        ],
        "bundle_ids": [
            run1.get("bundle_id", "-"),
            run2.get("bundle_id", "-"),
        ],
        "has_incident": any(
            str(incident.get(key, "-")).strip() not in {"", "-"}
            for key in ("symptom", "request_id", "temporary_action", "final_decision")
        ),
        "accepted_for_next_batch": str(decision.get("accepted_for_next_batch", "-")).strip(),
    }


def build_pilot_completion_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    run1 = payload.get("run1") or {}
    run2 = payload.get("run2") or {}
    decision = payload.get("decision") or {}
    return f"""# Pilot Completion Report — {payload.get('session_title', '-')}

- generated_at: {generated_at.isoformat()}
- closeout_file: `{payload.get('closeout_file', '-')}`
- pilot_status: **{payload.get('closeout_status', 'INCOMPLETE')}**
- accepted_for_next_batch: `{payload.get('accepted_for_next_batch', '-')}`

## Pilot Summary

- completed_runs: `{payload.get('completed_runs', '0')}`
- source_run_status: `{payload.get('source_run_status', '-')}`
- base_url: `{payload.get('base_url', '-')}`
- latest_report: `{payload.get('latest_report', '-')}`
- provider: `{payload.get('provider', '-')}`
- quality_first: `{payload.get('quality_first', '-')}`

## Execution Evidence

### Run 1
- request_id: {run1.get('request_id', '-')}
- bundle_id: {run1.get('bundle_id', '-')}
- export_checked: {run1.get('export_checked', '-')}
- quality_feedback: {run1.get('quality_feedback', '-')}

### Run 2
- request_id: {run2.get('request_id', '-')}
- bundle_id: {run2.get('bundle_id', '-')}
- export_checked: {run2.get('export_checked', '-')}
- quality_feedback: {run2.get('quality_feedback', '-')}

## Decision Evidence

- overall_result: {decision.get('overall_result', '-')}
- follow_up_items: {decision.get('follow_up_items', '-')}
- post-deploy: {decision.get('post-deploy', '-')}
- uat summary: {decision.get('uat summary', '-')}
- pilot handoff: {decision.get('pilot handoff', '-')}
- launch checklist: {decision.get('launch checklist', '-')}

## Outcome

- `{"Pilot approved for the next batch." if payload.get('closeout_status') == 'PILOT_COMPLETE' else "Pilot remains incomplete and requires follow-up."}`
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_completion_report(*, closeout_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    parsed = parse_pilot_closeout(closeout_file)
    payload = build_pilot_completion_payload(parsed, closeout_file=closeout_file)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{Path(closeout_file).stem}-completion-report.md"
    markdown = build_pilot_completion_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a concise pilot completion report from a finalized pilot close-out artifact.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot completion report.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_completion_report(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot completion report: {output_path}", flush=True)
    print(f"Pilot status: {payload.get('closeout_status', 'INCOMPLETE')}", flush=True)
    print(f"Accepted for next batch: {payload.get('accepted_for_next_batch', '-')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
