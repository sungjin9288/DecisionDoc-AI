#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
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


_PUBLISH_OVERVIEW = _load_module(
    "publish_pilot_delivery_latest_overview.py",
    "decisiondoc_publish_pilot_delivery_latest_overview",
)
_SHOW_SUMMARY = _load_module(
    "show_pilot_delivery_latest_summary.py",
    "decisiondoc_show_pilot_delivery_latest_summary",
)

publish_pilot_delivery_latest_overview = _PUBLISH_OVERVIEW.publish_pilot_delivery_latest_overview
show_pilot_delivery_latest_summary = _SHOW_SUMMARY.show_pilot_delivery_latest_summary


def check_pilot_delivery_latest_summary_ready(
    *,
    closeout_file: Path,
    output_dir: Path,
) -> dict[str, object]:
    _, latest_overview_path = publish_pilot_delivery_latest_overview(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    summary = show_pilot_delivery_latest_summary(output_dir=output_dir)
    return {
        **summary,
        "latest_overview_markdown": str(latest_overview_path),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh latest pilot delivery overview and print current latest summary in one step.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory containing pilot delivery artifacts.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = check_pilot_delivery_latest_summary_ready(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0 if result["ok"] else 1

    print(f"Pilot delivery latest summary readiness: {'PASS' if result['ok'] else 'FAIL'}", flush=True)
    print(f"Latest overview file: {result['latest_overview_markdown']}", flush=True)
    print(f"Bundle SHA256: {result.get('bundle_sha256', '-')}", flush=True)
    print(f"Entry count: {result.get('entry_count', 0)}", flush=True)
    print(f"Stale: {str(result.get('stale', False)).lower()}", flush=True)
    print(f"Receipt matches: {str(result.get('receipt_matches', False)).lower()}", flush=True)
    if result["errors"]:
        print("Errors:", flush=True)
        for error in result["errors"]:
            print(f"- {error}", flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
