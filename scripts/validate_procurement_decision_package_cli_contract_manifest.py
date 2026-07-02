from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.procurement_decision_package_service import (
    CLI_CONTRACT_MANIFEST_VALIDATION_RESULT_NAME as DEFAULT_VALIDATION_RESULT_NAME,
    LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH,
    build_cli_contract_manifest_validation_failure_result,
    validate_cli_contract_manifest,
    write_json_atomic,
)


DEFAULT_MANIFEST_PATH = ROOT / LOCAL_DEMO_CLI_CONTRACT_MANIFEST_PATH
RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR = (
    "--result-path requires --write-result for manifest validation result persistence"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the local procurement decision package CLI contract manifest."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--write-result",
        action="store_true",
        help="Persist the manifest validation result JSON next to the manifest or --result-path.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=None,
        help=(
            "Optional path for --write-result. Defaults to "
            "<manifest_dir>/cli_contract_manifest_validation_result.json."
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
    default_result_path = args.manifest.parent / DEFAULT_VALIDATION_RESULT_NAME
    result_path = args.result_path or default_result_path

    if args.result_path is not None and not args.write_result:
        result = build_cli_contract_manifest_validation_failure_result(
            manifest_path=args.manifest,
            exc=ValueError(RESULT_PATH_REQUIRES_WRITE_RESULT_ERROR),
        )
        return _emit_result(
            result,
            result_path=result_path,
            write_result=False,
            exit_code=1,
        )

    try:
        result = validate_cli_contract_manifest(args.manifest, repo_root=ROOT)
    except Exception as exc:
        result = build_cli_contract_manifest_validation_failure_result(
            manifest_path=args.manifest,
            exc=exc,
        )
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
