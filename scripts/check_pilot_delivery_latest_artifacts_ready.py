#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
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


_PUBLISH = _load_module(
    "publish_pilot_delivery_latest_artifacts.py",
    "decisiondoc_publish_pilot_delivery_latest_artifacts",
)
_ASSERT = _load_module(
    "assert_pilot_delivery_ready.py",
    "decisiondoc_assert_pilot_delivery_ready",
)

publish_pilot_delivery_latest_artifacts = _PUBLISH.publish_pilot_delivery_latest_artifacts
assert_pilot_delivery_ready = _ASSERT.assert_pilot_delivery_ready


def check_pilot_delivery_latest_artifacts_ready(
    *,
    closeout_file: Path,
    output_dir: Path,
) -> dict[str, object]:
    publish_result = publish_pilot_delivery_latest_artifacts(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    gate_result = assert_pilot_delivery_ready(
        status_file=Path(str(publish_result["latest_status_file"])),
    )
    return {
        **publish_result,
        **gate_result,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish latest human/machine pilot delivery artifacts and assert readiness in one step.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery artifacts.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = check_pilot_delivery_latest_artifacts_ready(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Pilot latest artifacts readiness check: {'PASS' if result['ok'] else 'FAIL'}", flush=True)
    print(f"Latest status file: {result['latest_status_file']}", flush=True)
    print(f"Latest audit file: {result['latest_audit_file']}", flush=True)
    if not result["ok"]:
        for error in result["errors"]:
            print(f"- {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
