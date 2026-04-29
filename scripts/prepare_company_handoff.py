#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import build_sales_pack  # noqa: E402
import check_company_handoff_ready  # noqa: E402


def _build_sales_pack_args(*, output_dir: Path, html_only: bool) -> list[str]:
    args = ["--output-dir", str(output_dir)]
    if html_only:
        args.append("--html-only")
    return args


def prepare_company_handoff(
    *,
    output_dir: Path = Path("output/pdf"),
    report_dir: Path = Path("reports/company-handoff"),
    skip_build: bool = False,
    html_only: bool = False,
) -> dict[str, object]:
    if html_only and not skip_build:
        # HTML-only builds are useful for fast local previews, but cannot satisfy the final PDF gate.
        skip_pdf_check = True
    else:
        skip_pdf_check = False

    build_result: int | None = None
    if not skip_build:
        build_result = build_sales_pack.main(_build_sales_pack_args(output_dir=output_dir, html_only=html_only))
        if build_result != 0:
            return {
                "ok": False,
                "build_result": build_result,
                "readiness": None,
                "reports": [],
                "errors": [f"sales pack build failed with exit code {build_result}"],
            }

    readiness = check_company_handoff_ready.check_company_handoff_ready(
        output_dir=output_dir,
        skip_pdf_check=skip_pdf_check,
    )
    reports = check_company_handoff_ready._write_reports(
        result=readiness,
        report_file=None,
        report_dir=report_dir,
    )
    return {
        "ok": bool(readiness["ok"]),
        "build_result": build_result,
        "readiness": readiness,
        "reports": reports,
        "errors": list(readiness["errors"]),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build the sales pack and write company handoff readiness evidence in one command.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output/pdf"), help="Sales PDF output directory.")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports/company-handoff"),
        help="Directory for company handoff readiness reports.",
    )
    parser.add_argument("--skip-build", action="store_true", help="Do not rebuild sales PDFs; validate existing files.")
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Build HTML artifacts only and run a markdown-only readiness gate.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = prepare_company_handoff(
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        skip_build=args.skip_build,
        html_only=args.html_only,
    )
    if result["ok"]:
        print("PASS company handoff package prepared")
        print(f"build_result={result['build_result'] if result['build_result'] is not None else 'skipped'}")
        for report in result["reports"]:
            print(f"report_written={report}")
        print("next_action=review PDFs visually, then send package with secrets through a separate channel")
        return 0

    print("FAIL company handoff package preparation failed")
    print(f"build_result={result['build_result'] if result['build_result'] is not None else 'skipped'}")
    for error in result["errors"]:
        print(f"ERROR {error}")
    for report in result["reports"]:
        print(f"report_written={report}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
