#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"
DEFAULT_LATEST_FILENAME = "latest-pilot-delivery-status.json"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_PUBLISH = _load_module(
    "publish_pilot_delivery_latest_status.py",
    "decisiondoc_publish_pilot_delivery_latest_status",
)
_ASSERT = _load_module(
    "assert_pilot_delivery_ready.py",
    "decisiondoc_assert_pilot_delivery_ready",
)

publish_pilot_delivery_latest_status = _PUBLISH.publish_pilot_delivery_latest_status
assert_pilot_delivery_ready = _ASSERT.assert_pilot_delivery_ready


def check_pilot_delivery_ready(
    *,
    closeout_file: Path,
    output_dir: Path,
    latest_filename: str = DEFAULT_LATEST_FILENAME,
) -> dict[str, object]:
    _, snapshot_path, latest_path = publish_pilot_delivery_latest_status(
        closeout_file=closeout_file,
        output_dir=output_dir,
        latest_filename=latest_filename,
    )
    gate_result = assert_pilot_delivery_ready(status_file=latest_path)
    return {
        **gate_result,
        "snapshot_file": str(snapshot_path),
        "latest_file": str(latest_path),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh latest pilot delivery status and assert readiness in one step.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery status files.")
    parser.add_argument("--latest-filename", default=DEFAULT_LATEST_FILENAME, help="Stable latest status JSON filename.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = check_pilot_delivery_ready(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
        latest_filename=args.latest_filename,
    )
    print(f"Pilot delivery readiness check: {'PASS' if result['ok'] else 'FAIL'}", flush=True)
    print(f"Snapshot file: {result['snapshot_file']}", flush=True)
    print(f"Latest file: {result['latest_file']}", flush=True)
    if not result["ok"]:
        for error in result["errors"]:
            print(f"- {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
