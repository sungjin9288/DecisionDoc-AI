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
    GATE_RESULT_NAME,
    SMOKE_CHECK_RESULT_NAME,
    SMOKE_RESULT_NAME,
    build_smoke_failure_result as build_failure_payload,
    check_smoke_result,
    smoke_demo_gate,
    write_json_atomic,
)

DEFAULT_DATA_DIR = DEFAULT_DEMO_DATA_DIR
DEFAULT_OUT_DIR = DEFAULT_DEMO_OUT_DIR


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the local procurement decision package demo and evidence gate "
            "in one command."
        )
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--reviewer-owner", default="executive-reviewer")
    parser.add_argument(
        "--no-clean-output",
        action="store_true",
        help="Keep existing output directory contents before running the demo.",
    )
    parser.add_argument(
        "--no-write-gate-result",
        action="store_true",
        help="Do not persist demo_gate_result.json after the gate passes.",
    )
    parser.add_argument(
        "--gate-result-path",
        type=Path,
        default=None,
        help="Optional path for the persisted gate result JSON.",
    )
    parser.add_argument(
        "--no-write-smoke-result",
        action="store_true",
        help="Do not persist demo_smoke_result.json after the smoke wrapper finishes.",
    )
    parser.add_argument(
        "--smoke-result-path",
        type=Path,
        default=None,
        help="Optional path for the persisted smoke result JSON.",
    )
    parser.add_argument(
        "--no-write-smoke-check-result",
        action="store_true",
        help="Do not persist demo_smoke_check_result.json after the smoke result is finalized.",
    )
    parser.add_argument(
        "--smoke-check-result-path",
        type=Path,
        default=None,
        help="Optional path for the persisted smoke check result JSON.",
    )
    return parser.parse_args()


def _emit_result(result: dict[str, object], *, exit_code: int) -> int:
    print(json.dumps(result, indent=2))
    return exit_code


def main() -> int:
    args = _parse_args()
    clean_output = not args.no_clean_output
    write_gate_result = not args.no_write_gate_result
    write_smoke_result = not args.no_write_smoke_result
    write_smoke_check_result = write_smoke_result and not args.no_write_smoke_check_result
    resolved_gate_result_path = args.gate_result_path or (args.out_dir / GATE_RESULT_NAME)
    resolved_smoke_result_path = args.smoke_result_path or (args.out_dir / SMOKE_RESULT_NAME)
    resolved_smoke_check_result_path = args.smoke_check_result_path or (
        args.out_dir / SMOKE_CHECK_RESULT_NAME
    )
    recorded_gate_result_path = resolved_gate_result_path if write_gate_result else None
    recorded_smoke_result_path = resolved_smoke_result_path if write_smoke_result else None
    recorded_smoke_check_result_path = (
        resolved_smoke_check_result_path if write_smoke_check_result else None
    )

    if args.gate_result_path is not None and not write_gate_result:
        result = build_failure_payload(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            clean_output=clean_output,
            gate_result_path=recorded_gate_result_path,
            gate_result_written=False,
            smoke_result_path=None,
            smoke_result_written=False,
            smoke_check_result_path=None,
            smoke_check_result_written=False,
            exc=ValueError(
                "--gate-result-path requires persisted gate result writing; "
                "remove --no-write-gate-result or remove --gate-result-path"
            ),
        )
        return _emit_result(result, exit_code=1)

    if args.smoke_result_path is not None and not write_smoke_result:
        result = build_failure_payload(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            clean_output=clean_output,
            gate_result_path=None,
            gate_result_written=False,
            smoke_result_path=None,
            smoke_result_written=False,
            smoke_check_result_path=None,
            smoke_check_result_written=False,
            exc=ValueError(
                "--smoke-result-path requires persisted smoke result writing; "
                "remove --no-write-smoke-result or remove --smoke-result-path"
            ),
        )
        return _emit_result(result, exit_code=1)

    if args.smoke_check_result_path is not None and not write_smoke_check_result:
        result = build_failure_payload(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            clean_output=clean_output,
            gate_result_path=None,
            gate_result_written=False,
            smoke_result_path=recorded_smoke_result_path,
            smoke_result_written=write_smoke_result,
            smoke_check_result_path=None,
            smoke_check_result_written=False,
            exc=ValueError(
                "--smoke-check-result-path requires persisted smoke check result writing; "
                "remove --no-write-smoke-result/--no-write-smoke-check-result "
                "or remove --smoke-check-result-path"
            ),
        )
        if write_smoke_result:
            write_json_atomic(resolved_smoke_result_path, result)
        return _emit_result(result, exit_code=1)

    if write_smoke_result and not write_gate_result:
        result = build_failure_payload(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            clean_output=clean_output,
            gate_result_path=None,
            gate_result_written=False,
            smoke_result_path=recorded_smoke_result_path,
            smoke_result_written=True,
            smoke_check_result_path=recorded_smoke_check_result_path,
            smoke_check_result_written=False,
            exc=ValueError(
                "persisted smoke result requires persisted gate result; "
                "remove --no-write-gate-result or add --no-write-smoke-result"
            ),
        )
        write_json_atomic(resolved_smoke_result_path, result)
        return _emit_result(result, exit_code=1)

    try:
        result = smoke_demo_gate(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            reviewer_owner=args.reviewer_owner,
            clean_output=clean_output,
            write_gate_result=write_gate_result,
            gate_result_path=args.gate_result_path,
        )
    except Exception as exc:
        result = build_failure_payload(
            data_dir=args.data_dir,
            out_dir=args.out_dir,
            clean_output=clean_output,
            gate_result_path=recorded_gate_result_path,
            gate_result_written=write_gate_result,
            smoke_result_path=recorded_smoke_result_path,
            smoke_result_written=False,
            smoke_check_result_path=recorded_smoke_check_result_path,
            smoke_check_result_written=False,
            exc=exc,
        )
        if write_smoke_result:
            result["smoke_result_written"] = True
        if write_gate_result:
            write_json_atomic(resolved_gate_result_path, result)
        if write_smoke_result:
            write_json_atomic(resolved_smoke_result_path, result)
        return _emit_result(result, exit_code=1)

    if write_smoke_result:
        smoke_result_path = str(resolved_smoke_result_path)
        smoke_check_result_path = (
            str(recorded_smoke_check_result_path)
            if recorded_smoke_check_result_path is not None
            else None
        )
        result["smoke_result_path"] = smoke_result_path
        result["smoke_result_written"] = True
        result["smoke_check_result_path"] = smoke_check_result_path
        result["smoke_check_result_written"] = write_smoke_check_result
        evidence_files = result.get("evidence_files")
        if isinstance(evidence_files, dict):
            evidence_files["smoke_result"] = smoke_result_path
            evidence_files["smoke_check_result"] = smoke_check_result_path
        result["package_artifacts_checked"] = False
        result["smoke_result_checked"] = False
        write_json_atomic(resolved_smoke_result_path, result)
        smoke_check_result = check_smoke_result(
            resolved_smoke_result_path,
            require_recorded_smoke_check=False,
            require_recorded_smoke_check_result=False,
        )
        result["package_artifacts_checked"] = smoke_check_result["package_artifacts_checked"]
        result["smoke_result_checked"] = smoke_check_result["smoke_result_checked"]
        write_json_atomic(resolved_smoke_result_path, result)
        if write_smoke_check_result:
            final_smoke_check_result = check_smoke_result(
                resolved_smoke_result_path,
                require_recorded_smoke_check_result=False,
            )
            write_json_atomic(resolved_smoke_check_result_path, final_smoke_check_result)
    return _emit_result(result, exit_code=0)


if __name__ == "__main__":
    raise SystemExit(main())
