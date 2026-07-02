from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (
    DEFAULT_DEMO_DATA_DIR,
    DEFAULT_DEMO_OUT_DIR,
    build_demo_run_failure_result,
    run_demo,
)


DEFAULT_DATA_DIR = DEFAULT_DEMO_DATA_DIR
DEFAULT_OUT_DIR = DEFAULT_DEMO_OUT_DIR


def _emit_result(result: dict[str, object], *, exit_code: int) -> int:
    print(json.dumps(result, indent=2))
    return exit_code


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed and export a local procurement decision package demo."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--reviewer-owner", default="executive-reviewer")
    parser.add_argument(
        "--clean-output",
        action="store_true",
        help="Remove the output directory before writing fresh local demo artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = run_demo(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            reviewer_owner=args.reviewer_owner,
            clean_output=args.clean_output,
        )
    except Exception as exc:
        result = build_demo_run_failure_result(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            clean_output=args.clean_output,
            exc=exc,
        )
        return _emit_result(result, exit_code=1)

    return _emit_result(result, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
