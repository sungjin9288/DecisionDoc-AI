from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_SCHEMA_PURPOSE as EXPECTED_SCHEMA_PURPOSE,
    CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME as DEFAULT_VALIDATION_RESULT_NAME,
    CLI_CONTRACT_MANIFEST_VALIDATION_CHECK_RESULT_NAME as DEFAULT_CHECK_RESULT_NAME,
    build_cli_contract_manifest_validation_check_failure_result,
    check_cli_contract_manifest_validation_result,
    LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH,
    validate_cli_contract_manifest,
    write_json_atomic,
)


DEFAULT_MANIFEST_PATH = ROOT / LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH


DEFAULT_VALIDATION_RESULT_PATH = DEFAULT_MANIFEST_PATH.parent / DEFAULT_VALIDATION_RESULT_NAME
RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR = (
    "--result-path requires --write-result for manifest validation check result persistence"
)


def _validate_current_manifest(manifest_path: Path) -> dict[str, object]:
    return validate_cli_contract_manifest(manifest_path, repo_root=ROOT)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check a persisted local procurement decision package CLI contract "
            "manifest validation result."
        )
    )
    parser.add_argument(
        "validation_result_path",
        type=Path,
        nargs="?",
        default=None,
        help=(
            f"Path to {DEFAULT_VALIDATION_RESULT_NAME}. "
            "Defaults to the manifest directory result file."
        ),
    )
    parser.add_argument(
        "--write-result",
        action="store_true",
        help="Persist the check result JSON next to the validation result or --result-path.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=None,
        help=(
            "Optional path for --write-result. Defaults to "
            "<validation_result_dir>/cli_contract_manifest_validation_check_result.json."
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
    validation_result_path = args.validation_result_path or DEFAULT_VALIDATION_RESULT_PATH
    default_check_result_path = validation_result_path.parent / DEFAULT_CHECK_RESULT_NAME
    check_result_path = args.result_path or default_check_result_path

    if args.result_path is not None and not args.write_result:
        result = build_cli_contract_manifest_validation_check_failure_result(
            validation_result_path,
            ValueError(RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR),
        )
        return _emit_result(
            result,
            result_path=check_result_path,
            write_result=False,
            exit_code=1,
        )

    try:
        result = check_cli_contract_manifest_validation_result(
            validation_result_path,
            expected_schema_purpose=EXPECTED_SCHEMA_PURPOSE,
            validate_current_manifest=_validate_current_manifest,
            display_base_dir=ROOT,
        )
    except Exception as exc:
        result = build_cli_contract_manifest_validation_check_failure_result(
            validation_result_path,
            exc,
        )
        return _emit_result(
            result,
            result_path=check_result_path,
            write_result=args.write_result,
            exit_code=1,
        )

    return _emit_result(
        result,
        result_path=check_result_path,
        write_result=args.write_result,
        exit_code=0,
    )


if __name__ == "__main__":
    raise SystemExit(main())
