#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def _load_completion_module():
    path = Path(__file__).with_name("create_pilot_completion_report.py")
    spec = importlib.util.spec_from_file_location("decisiondoc_pilot_completion_report", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_COMPLETION = _load_completion_module()
parse_pilot_closeout = _COMPLETION.parse_pilot_closeout
build_pilot_completion_payload = _COMPLETION.build_pilot_completion_payload


def build_pilot_share_payload(*, closeout_file: Path) -> dict[str, object]:
    parsed = parse_pilot_closeout(closeout_file)
    payload = build_pilot_completion_payload(parsed, closeout_file=closeout_file)
    decision = payload.get("decision") or {}
    run1 = payload.get("run1") or {}
    run2 = payload.get("run2") or {}
    return {
        "session_title": payload.get("session_title", "-"),
        "pilot_status": payload.get("closeout_status", "INCOMPLETE"),
        "accepted_for_next_batch": payload.get("accepted_for_next_batch", "-"),
        "completed_runs": payload.get("completed_runs", "0"),
        "base_url": payload.get("base_url", "-"),
        "latest_report": payload.get("latest_report", "-"),
        "provider": payload.get("provider", "-"),
        "quality_first": payload.get("quality_first", "-"),
        "overall_result": decision.get("overall_result", "-"),
        "follow_up_items": decision.get("follow_up_items", "-"),
        "post_deploy": decision.get("post-deploy", "-"),
        "uat_summary": decision.get("uat summary", "-"),
        "pilot_handoff": decision.get("pilot handoff", "-"),
        "launch_checklist": decision.get("launch checklist", "-"),
        "run1_request_id": run1.get("request_id", "-"),
        "run2_request_id": run2.get("request_id", "-"),
        "run1_bundle_id": run1.get("bundle_id", "-"),
        "run2_bundle_id": run2.get("bundle_id", "-"),
    }


def build_pilot_share_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    approved = payload.get("pilot_status") == "PILOT_COMPLETE"
    return f"""# Pilot Share Note — {payload.get('session_title', '-')}

- generated_at: {generated_at.isoformat()}
- pilot_status: **{payload.get('pilot_status', 'INCOMPLETE')}**
- accepted_for_next_batch: `{payload.get('accepted_for_next_batch', '-')}`

## Executive Summary

- 상태: {"Pilot 승인 완료" if approved else "Pilot follow-up 필요"}
- 결과 요약: {payload.get('overall_result', '-')}
- 다음 배치 진행 여부: {payload.get('accepted_for_next_batch', '-')}
- 운영 기준점:
  - base_url: `{payload.get('base_url', '-')}`
  - latest_report: `{payload.get('latest_report', '-')}`
  - provider: `{payload.get('provider', '-')}`
  - quality_first: `{payload.get('quality_first', '-')}`

## Execution Snapshot

- completed_runs: `{payload.get('completed_runs', '0')}`
- Run 1 request_id / bundle_id:
  - `{payload.get('run1_request_id', '-')}`
  - `{payload.get('run1_bundle_id', '-')}`
- Run 2 request_id / bundle_id:
  - `{payload.get('run2_request_id', '-')}`
  - `{payload.get('run2_bundle_id', '-')}`

## Evidence Links

- post-deploy: {payload.get('post_deploy', '-')}
- uat summary: {payload.get('uat_summary', '-')}
- pilot handoff: {payload.get('pilot_handoff', '-')}
- launch checklist: {payload.get('launch_checklist', '-')}

## Follow-up

- {payload.get('follow_up_items', '-')}
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_share_note(*, closeout_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    payload = build_pilot_share_payload(closeout_file=closeout_file)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{Path(closeout_file).stem}-share-note.md"
    markdown = build_pilot_share_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a concise stakeholder-facing pilot share note from a pilot close-out artifact.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot share note.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_share_note(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot share note: {output_path}", flush=True)
    print(f"Pilot status: {payload.get('pilot_status', 'INCOMPLETE')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
