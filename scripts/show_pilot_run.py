#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Sequence


def _load_finalize_module():
    path = Path(__file__).with_name("finalize_pilot_run.py")
    spec = importlib.util.spec_from_file_location("decisiondoc_finalize_pilot_run", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_FINALIZE = _load_finalize_module()
_has_value = _FINALIZE._has_value
build_pilot_closeout_payload = _FINALIZE.build_pilot_closeout_payload
parse_pilot_run_sheet = _FINALIZE.parse_pilot_run_sheet


REQUIRED_RUN_FIELDS = ("started_at", "operator", "request_id", "bundle_id", "stop_decision")


def _missing_fields(fields: dict[str, str], required_fields: tuple[str, ...]) -> list[str]:
    return [key for key in required_fields if not _has_value(fields.get(key))]


def summarize_pilot_run_sheet(run_sheet_file: Path) -> dict[str, object]:
    parsed = parse_pilot_run_sheet(Path(run_sheet_file))
    payload = build_pilot_closeout_payload(parsed)
    run1 = payload.get("run1") or {}
    run2 = payload.get("run2") or {}
    closeout = payload.get("closeout") or {}
    return {
        "run_sheet_file": str(Path(run_sheet_file).expanduser()),
        "session_title": payload.get("session_title", "-"),
        "run_status": payload.get("run_status", "-"),
        "launch_status": payload.get("launch_status", "-"),
        "base_url": payload.get("base_url", "-"),
        "latest_report": payload.get("latest_report", "-"),
        "provider": payload.get("provider", "-"),
        "quality_first": payload.get("quality_first", "-"),
        "completed_runs": payload.get("completed_runs", 0),
        "closeout_status": payload.get("closeout_status", "INCOMPLETE"),
        "run1_missing": _missing_fields(run1, REQUIRED_RUN_FIELDS),
        "run2_missing": _missing_fields(run2, REQUIRED_RUN_FIELDS),
        "closeout_ready": bool(
            _has_value(str(closeout.get("overall_result", "-")))
            and _has_value(str(closeout.get("accepted_for_next_batch", "-")))
        ),
        "closeout_overall_result": closeout.get("overall_result", "-"),
        "closeout_accepted_for_next_batch": closeout.get("accepted_for_next_batch", "-"),
    }


def render_pilot_run_summary(payload: dict[str, object]) -> str:
    def _render_missing(keys: list[str]) -> str:
        return ",".join(keys) if keys else "none"

    lines = [
        f"Run sheet file: {payload.get('run_sheet_file', '-')}",
        f"Session title: {payload.get('session_title', '-')}",
        f"Run status: {payload.get('run_status', '-')}",
        f"Launch status: {payload.get('launch_status', '-')}",
        f"Completed runs: {payload.get('completed_runs', 0)}",
        f"Close-out status: {payload.get('closeout_status', 'INCOMPLETE')}",
        f"Base URL: {payload.get('base_url', '-')}",
        f"Latest report: {payload.get('latest_report', '-')}",
        f"Provider: {payload.get('provider', '-')}",
        f"Quality-first: {payload.get('quality_first', '-')}",
        f"Run 1 missing: {_render_missing(list(payload.get('run1_missing', [])))}",
        f"Run 2 missing: {_render_missing(list(payload.get('run2_missing', [])))}",
        f"Close-out overall_result: {payload.get('closeout_overall_result', '-')}",
        f"Close-out accepted_for_next_batch: {payload.get('closeout_accepted_for_next_batch', '-')}",
        f"Close-out ready: {'yes' if payload.get('closeout_ready') else 'no'}",
    ]
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read a pilot run sheet markdown file and print current run/close-out readiness.",
    )
    parser.add_argument("--run-sheet-file", required=True, help="Existing pilot run sheet markdown file path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload = summarize_pilot_run_sheet(Path(args.run_sheet_file))
    print(render_pilot_run_summary(payload), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
