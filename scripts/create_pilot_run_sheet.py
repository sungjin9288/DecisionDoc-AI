#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def parse_launch_checklist(checklist_file: Path) -> dict[str, str]:
    text = Path(checklist_file).read_text(encoding="utf-8")

    def _match(pattern: str, default: str = "-") -> str:
        matched = re.search(pattern, text, re.MULTILINE)
        return matched.group(1).strip() if matched else default

    return {
        "session_title": _match(r"^# Pilot Launch Checklist — (.+)$"),
        "launch_status": _match(r"launch_status:\s+\*\*(.+?)\*\*"),
        "launch_decision": _match(r"launch_decision:\s+`([^`]+)`"),
        "source_pilot_status": _match(r"source_pilot_status:\s+`([^`]+)`"),
        "base_url": _match(r"base_url:\s+`([^`]+)`"),
        "latest_report": _match(r"latest_report:\s+`([^`]+)`"),
        "provider": _match(r"provider:\s+`([^`]+)`"),
        "quality_first": _match(r"quality_first:\s+`([^`]+)`"),
        "default_route": _match(r"default:\s+`([^`]+)`"),
        "generation_route": _match(r"generation:\s+`([^`]+)`"),
        "attachment_route": _match(r"attachment:\s+`([^`]+)`"),
        "visual_route": _match(r"visual:\s+`([^`]+)`"),
    }


def build_pilot_run_payload(checklist: dict[str, str]) -> dict[str, str]:
    can_start = str(checklist.get("launch_status", "")).strip() == "READY_TO_EXECUTE"
    return {
        **checklist,
        "run_status": "OPEN" if can_start else "HOLD",
    }


def build_pilot_run_sheet_markdown(*, payload: dict[str, str], generated_at: datetime) -> str:
    return f"""# Pilot Run Sheet — {payload.get('session_title', '-')}

- generated_at: {generated_at.isoformat()}
- run_status: **{payload.get('run_status', 'HOLD')}**
- launch_status: `{payload.get('launch_status', '-')}`
- launch_decision: `{payload.get('launch_decision', '-')}`

## Pilot Context

- base_url: `{payload.get('base_url', '-')}`
- latest_report: `{payload.get('latest_report', '-')}`
- provider: `{payload.get('provider', '-')}`
- quality_first: `{payload.get('quality_first', '-')}`
- provider_routes:
  - default: `{payload.get('default_route', '-')}`
  - generation: `{payload.get('generation_route', '-')}`
  - attachment: `{payload.get('attachment_route', '-')}`
  - visual: `{payload.get('visual_route', '-')}`

## Pilot Run Log

### Run 1. 기본 문서 생성
- started_at:
- operator:
- business_owner:
- bundle_type:
- input_summary:
- request_id:
- bundle_id:
- export_checked:
- quality_feedback:
- issues:
- stop_decision:

### Run 2. 첨부 기반 문서 생성
- started_at:
- operator:
- business_owner:
- bundle_type:
- attachment_list:
- request_id:
- bundle_id:
- export_checked:
- quality_feedback:
- issues:
- stop_decision:

## Escalation / Stop Log

- [ ] `/health` 이상 없음
- [ ] latest post-deploy status 유지
- [ ] 5xx / timeout 반복 없음
- [ ] hallucination 재발 없음
- [ ] 운영 이미지와 provider route 이상 없음

### Incident Notes
- 발생 시각:
- 증상:
- request_id:
- temporary action:
- final decision:

## Pilot Close-Out

- overall_result:
- accepted_for_next_batch:
- follow_up_items:
- evidence_paths:
  - post-deploy:
  - uat summary:
  - pilot handoff:
  - launch checklist:
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_run_sheet(*, checklist_file: Path, output_dir: Path) -> tuple[dict[str, str], Path]:
    checklist = parse_launch_checklist(checklist_file)
    payload = build_pilot_run_payload(checklist)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{Path(checklist_file).stem}-run-sheet.md"
    markdown = build_pilot_run_sheet_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a pilot run sheet markdown from an existing pilot launch checklist.",
    )
    parser.add_argument("--checklist-file", required=True, help="Pilot launch checklist markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot run sheet markdown.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_run_sheet(
        checklist_file=Path(args.checklist_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot run sheet: {output_path}", flush=True)
    print(f"Run status: {payload.get('run_status', 'HOLD')}", flush=True)
    return 0 if payload.get("run_status") == "OPEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
