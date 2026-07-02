from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (
    build_package_artifact_check_failure_result,
    build_package_artifact_check_result,
)


def _emit_result(result: dict[str, object], *, exit_code: int) -> int:
    print(json.dumps(result, indent=2))
    return exit_code


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check exported procurement decision package artifacts."
    )
    parser.add_argument("output_dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = build_package_artifact_check_result(args.output_dir)
    except Exception as exc:
        result = build_package_artifact_check_failure_result(args.output_dir, exc)
        return _emit_result(result, exit_code=1)

    return _emit_result(result, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
