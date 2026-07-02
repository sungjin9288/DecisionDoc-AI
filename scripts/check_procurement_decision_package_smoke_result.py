from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (
    SMOKE_CHECK_RESULT_NAME,
    build_smoke_check_failure_result,
    check_smoke_result,
    write_json_atomic,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check a persisted procurement decision package demo smoke result."
    )
    parser.add_argument("smoke_result_path", type=Path)
    parser.add_argument(
        "--write-result",
        action="store_true",
        help="Persist the smoke check result JSON next to the smoke result or --result-path.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=None,
        help=(
            "Optional path for --write-result. Defaults to "
            "<smoke_result_dir>/demo_smoke_check_result.json."
        ),
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
    result_path = args.result_path or (args.smoke_result_path.parent / SMOKE_CHECK_RESULT_NAME)
    require_recorded_smoke_check_result = not args.write_result

    if args.result_path is not None and not args.write_result:
        result = build_smoke_check_failure_result(
            args.smoke_result_path,
            ValueError("--result-path requires --write-result for smoke check result persistence"),
        )
        return _emit_result(
            result,
            result_path=result_path,
            write_result=False,
            exit_code=1,
        )

    try:
        result = check_smoke_result(
            args.smoke_result_path,
            require_recorded_smoke_check_result=require_recorded_smoke_check_result,
        )
    except Exception as exc:
        result = build_smoke_check_failure_result(args.smoke_result_path, exc)
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
