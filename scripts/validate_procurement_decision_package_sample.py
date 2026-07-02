from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (
    LOCAL_DEMO_EXPECTED_PACKAGE_PATH,
    LOCAL_DEMO_SAMPLE_INPUT_PATH,
    build_sample_validation_failure_result,
    validate_sample_pair as validate_sample_pair_files,
)

DEFAULT_SAMPLE_INPUT_PATH = ROOT / LOCAL_DEMO_SAMPLE_INPUT_PATH
DEFAULT_EXPECTED_PACKAGE_PATH = ROOT / LOCAL_DEMO_EXPECTED_PACKAGE_PATH


def validate_sample_pair(
    *,
    sample_input_path: Path = DEFAULT_SAMPLE_INPUT_PATH,
    expected_package_path: Path = DEFAULT_EXPECTED_PACKAGE_PATH,
) -> dict[str, object]:
    return validate_sample_pair_files(
        sample_input_path=sample_input_path,
        expected_package_path=expected_package_path,
        display_base_dir=ROOT,
    )


def _emit_result(result: dict[str, object], *, exit_code: int) -> int:
    print(json.dumps(result, indent=2))
    return exit_code


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the local procurement decision package demo sample."
    )
    parser.add_argument("--sample-input", type=Path, default=DEFAULT_SAMPLE_INPUT_PATH)
    parser.add_argument(
        "--expected-package",
        type=Path,
        default=DEFAULT_EXPECTED_PACKAGE_PATH,
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = validate_sample_pair(
            sample_input_path=args.sample_input,
            expected_package_path=args.expected_package,
        )
    except Exception as exc:
        result = build_sample_validation_failure_result(
            sample_input_path=args.sample_input,
            expected_package_path=args.expected_package,
            exc=exc,
        )
        return _emit_result(result, exit_code=1)

    return _emit_result(result, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
