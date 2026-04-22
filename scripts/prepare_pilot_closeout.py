#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Sequence


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_SHOW = _load_module("show_pilot_run.py", "decisiondoc_show_pilot_run")
_RECORD = _load_module("record_pilot_run.py", "decisiondoc_record_pilot_run")


def _derive_related_paths(run_sheet_file: Path) -> dict[str, str]:
    name = run_sheet_file.name
    stem = run_sheet_file.stem
    if not stem.endswith("-run-sheet"):
        raise SystemExit(f"Unexpected pilot run sheet name: {name}")

    checklist_stem = stem.removesuffix("-run-sheet")
    handoff_stem = checklist_stem.removesuffix("-launch-checklist")
    summary_stem = handoff_stem.removesuffix("-pilot")
    return {
        "launch checklist": str(run_sheet_file.with_name(f"{checklist_stem}.md")),
        "pilot handoff": str(run_sheet_file.with_name(f"{handoff_stem}.md")),
        "uat summary": str(run_sheet_file.parents[1] / "uat" / f"{summary_stem}.md"),
    }


def prepare_pilot_closeout(*, run_sheet_file: Path) -> dict[str, object]:
    summary = _SHOW.summarize_pilot_run_sheet(Path(run_sheet_file))
    if int(summary.get("completed_runs", 0)) < 2:
        raise SystemExit("Pilot close-out preparation requires both Run 1 and Run 2 to be completed first.")

    related_paths = _derive_related_paths(Path(run_sheet_file))
    fields = {
        "overall_result": "Run 1/Run 2 API sample execution completed; manual business acceptance pending",
        "follow_up_items": "business owner 최종 판정, export 산출물 수동 검수, next batch go/no-go 입력 필요",
        "post-deploy": str(summary.get("latest_report", "-")),
        "uat summary": related_paths["uat summary"],
        "pilot handoff": related_paths["pilot handoff"],
        "launch checklist": related_paths["launch checklist"],
    }
    _RECORD.record_pilot_run(
        run_sheet_file=Path(run_sheet_file),
        target="closeout",
        fields=fields,
    )
    updated = _SHOW.summarize_pilot_run_sheet(Path(run_sheet_file))
    return {
        "run_sheet_file": str(Path(run_sheet_file)),
        "completed_runs": updated.get("completed_runs", 0),
        "closeout_status": updated.get("closeout_status", "INCOMPLETE"),
        "closeout_overall_result": updated.get("closeout_overall_result", "-"),
        "closeout_accepted_for_next_batch": updated.get("closeout_accepted_for_next_batch", "-"),
        "closeout_ready": updated.get("closeout_ready", False),
        "related_paths": related_paths,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pre-fill pilot close-out evidence fields after Run 1 and Run 2 are completed.",
    )
    parser.add_argument("--run-sheet-file", required=True, help="Existing pilot run sheet markdown file path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload = prepare_pilot_closeout(run_sheet_file=Path(args.run_sheet_file))
    print(f"Prepared pilot close-out: {payload['run_sheet_file']}", flush=True)
    print(f"Completed runs: {payload['completed_runs']}", flush=True)
    print(f"Close-out overall_result: {payload['closeout_overall_result']}", flush=True)
    print(f"Close-out accepted_for_next_batch: {payload['closeout_accepted_for_next_batch']}", flush=True)
    print(f"Close-out ready: {'yes' if payload['closeout_ready'] else 'no'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
