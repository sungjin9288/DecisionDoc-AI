from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (
    GATE_RESULT_NAME,
    build_gate_failure_result,
    gate_demo_output,
    write_json_atomic,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local procurement decision package demo evidence gate."
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument(
        "--write-result",
        action="store_true",
        help="Persist the gate result JSON to the output directory or --result-path.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=None,
        help="Optional path for --write-result. Defaults to <output_dir>/demo_gate_result.json.",
    )

    return parser.parse_args()


def _emit_result(
    result: dict[str, object],
    *,
    result_path: Path,
    write_result: bool,
    exit_code: int,
) -> int:
    if write_result:
        write_json_atomic(result_path, result)
    print(json.dumps(result, indent=2))
    return exit_code


def main() -> int:
    args = _parse_args()
    result_path = args.result_path or (args.output_dir / GATE_RESULT_NAME)

    if args.result_path is not None and not args.write_result:
        result = build_gate_failure_result(
            args.output_dir,
            ValueError("--result-path requires --write-result for gate result persistence"),
        )
        return _emit_result(
            result,
            result_path=result_path,
            write_result=False,
            exit_code=1,
        )

    try:
        result = gate_demo_output(args.output_dir)
    except Exception as exc:
        result = build_gate_failure_result(args.output_dir, exc)
        return _emit_result(
            result,
            result_path=result_path,
            write_result=args.write_result,
            exit_code=1,
        )

    return _emit_result(
        result,
        result_path=result_path,
        write_result=args.write_result,
        exit_code=0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
