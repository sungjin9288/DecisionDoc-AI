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


_FINALIZE = _load_module("finalize_pilot_run.py", "decisiondoc_finalize_pilot_run")
_RECORD = _load_module("record_pilot_run.py", "decisiondoc_record_pilot_run")
_SHOW = _load_module("show_pilot_run.py", "decisiondoc_show_pilot_run")

_PENDING_MARKERS = (
    "pending",
    "manual business acceptance",
    "최종 판정",
    "go/no-go",
)


def _normalize_decision(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SystemExit("--accepted-for-next-batch is required.")

    lowered = text.lower()
    if lowered in {"yes", "y", "true", "1", "예", "승인"}:
        return "예"
    if lowered in {"no", "n", "false", "0", "아니오", "보류", "중단"}:
        return "아니오"
    raise SystemExit(
        f"Unsupported accepted-for-next-batch value: {value}. Use yes/no or 예/아니오."
    )


def _looks_like_placeholder(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized or normalized == "-":
        return True
    return any(marker in normalized for marker in _PENDING_MARKERS)


def complete_pilot_closeout(
    *,
    run_sheet_file: Path,
    output_dir: Path,
    accepted_for_next_batch: str,
    overall_result: str = "",
    follow_up_items: str = "",
) -> tuple[dict[str, object], Path]:
    summary = _SHOW.summarize_pilot_run_sheet(Path(run_sheet_file))
    if int(summary.get("completed_runs", 0)) < 2:
        raise SystemExit("Pilot close-out completion requires both Run 1 and Run 2 to be completed first.")

    parsed = _FINALIZE.parse_pilot_run_sheet(Path(run_sheet_file))
    existing_closeout = parsed.get("closeout") or {}
    normalized_decision = _normalize_decision(accepted_for_next_batch)
    decision_yes = normalized_decision == "예"

    final_overall_result = str(overall_result or existing_closeout.get("overall_result", "")).strip()
    if not overall_result and _looks_like_placeholder(final_overall_result):
        final_overall_result = (
            "Pilot sample execution completed and approved for next batch."
            if decision_yes
            else "Pilot sample execution completed but additional follow-up is required before the next batch."
        )

    final_follow_up = str(follow_up_items or existing_closeout.get("follow_up_items", "")).strip()
    if not follow_up_items and _looks_like_placeholder(final_follow_up):
        final_follow_up = "없음" if decision_yes else "business owner follow-up required"

    _RECORD.record_pilot_run(
        run_sheet_file=Path(run_sheet_file),
        target="closeout",
        fields={
            "overall_result": final_overall_result,
            "accepted_for_next_batch": normalized_decision,
            "follow_up_items": final_follow_up,
        },
    )
    payload, output_path = _FINALIZE.finalize_pilot_run(
        run_sheet_file=Path(run_sheet_file),
        output_dir=Path(output_dir),
    )
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Record final business decision on a pilot run sheet and regenerate the pilot close-out artifact.",
    )
    parser.add_argument("--run-sheet-file", required=True, help="Existing pilot run sheet markdown file path.")
    parser.add_argument("--output-dir", default=str(_FINALIZE.DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot close-out markdown.")
    parser.add_argument("--accepted-for-next-batch", required=True, help="Business decision: yes/no or 예/아니오.")
    parser.add_argument("--overall-result", default="", help="Optional final overall_result override.")
    parser.add_argument("--follow-up-items", default="", help="Optional final follow_up_items override.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = complete_pilot_closeout(
        run_sheet_file=Path(args.run_sheet_file),
        output_dir=Path(args.output_dir),
        accepted_for_next_batch=args.accepted_for_next_batch,
        overall_result=args.overall_result,
        follow_up_items=args.follow_up_items,
    )
    print(f"Completed pilot close-out: {output_path}", flush=True)
    print(f"Close-out status: {payload.get('closeout_status', 'INCOMPLETE')}", flush=True)
    return 0 if payload.get("closeout_status") == "PILOT_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
