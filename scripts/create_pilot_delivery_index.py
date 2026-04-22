#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_SHARE = _load_module("create_pilot_share_note.py", "decisiondoc_create_pilot_share_note")
_COMPLETION = _load_module("create_pilot_completion_report.py", "decisiondoc_create_pilot_completion_report")

build_pilot_share_payload = _SHARE.build_pilot_share_payload


def _derive_related_artifact_paths(closeout_file: Path) -> dict[str, str]:
    name = closeout_file.name
    stem = closeout_file.stem
    if not stem.endswith("-closeout"):
        raise SystemExit(f"Unexpected pilot closeout file name: {name}")

    run_sheet_stem = stem.removesuffix("-closeout")
    checklist_stem = run_sheet_stem.removesuffix("-run-sheet")
    handoff_stem = checklist_stem.removesuffix("-launch-checklist")
    summary_stem = handoff_stem.removesuffix("-pilot")

    pilot_dir = closeout_file.parent
    return {
        "closeout": str(closeout_file),
        "share_note": str(pilot_dir / f"{stem}-share-note.md"),
        "completion_report": str(pilot_dir / f"{stem}-completion-report.md"),
        "run_sheet": str(pilot_dir / f"{run_sheet_stem}.md"),
        "launch_checklist": str(pilot_dir / f"{checklist_stem}.md"),
        "pilot_handoff": str(pilot_dir / f"{handoff_stem}.md"),
        "uat_summary": str(closeout_file.parents[1] / "uat" / f"{summary_stem}.md"),
    }


def build_pilot_delivery_payload(*, closeout_file: Path) -> dict[str, object]:
    share_payload = build_pilot_share_payload(closeout_file=closeout_file)
    artifact_paths = _derive_related_artifact_paths(Path(closeout_file))
    return {
        **share_payload,
        "artifact_paths": artifact_paths,
    }


def build_pilot_delivery_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    artifacts = payload.get("artifact_paths") or {}
    approved = payload.get("pilot_status") == "PILOT_COMPLETE"
    return f"""# Pilot Delivery Index — {payload.get('session_title', '-')}

- generated_at: {generated_at.isoformat()}
- pilot_status: **{payload.get('pilot_status', 'INCOMPLETE')}**
- accepted_for_next_batch: `{payload.get('accepted_for_next_batch', '-')}`

## Recommended Reading Order

1. share note: `{artifacts.get('share_note', '-')}`
2. completion report: `{artifacts.get('completion_report', '-')}`
3. closeout: `{artifacts.get('closeout', '-')}`

## Delivery Summary

- 상태: {"Pilot approved and ready to share." if approved else "Pilot not yet ready for external delivery."}
- 결과 요약: {payload.get('overall_result', '-')}
- follow-up: {payload.get('follow_up_items', '-')}
- 운영 기준점:
  - base_url: `{payload.get('base_url', '-')}`
  - latest_report: `{payload.get('latest_report', '-')}`
  - provider: `{payload.get('provider', '-')}`
  - quality_first: `{payload.get('quality_first', '-')}`

## Artifact Index

- share_note: {artifacts.get('share_note', '-')}
- completion_report: {artifacts.get('completion_report', '-')}
- closeout: {artifacts.get('closeout', '-')}
- run_sheet: {artifacts.get('run_sheet', '-')}
- launch_checklist: {artifacts.get('launch_checklist', '-')}
- pilot_handoff: {artifacts.get('pilot_handoff', '-')}
- uat_summary: {artifacts.get('uat_summary', '-')}
- post_deploy: {payload.get('post_deploy', '-')}

## Evidence Snapshot

- Run 1 request_id / bundle_id:
  - `{payload.get('run1_request_id', '-')}`
  - `{payload.get('run1_bundle_id', '-')}`
- Run 2 request_id / bundle_id:
  - `{payload.get('run2_request_id', '-')}`
  - `{payload.get('run2_bundle_id', '-')}`
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_delivery_index(*, closeout_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    payload = build_pilot_delivery_payload(closeout_file=closeout_file)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{Path(closeout_file).stem}-delivery-index.md"
    markdown = build_pilot_delivery_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a final delivery index that points to all pilot artifacts in recommended reading order.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery index.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_delivery_index(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot delivery index: {output_path}", flush=True)
    print(f"Pilot status: {payload.get('pilot_status', 'INCOMPLETE')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
