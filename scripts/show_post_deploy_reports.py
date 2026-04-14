#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ops.report_history import (
    build_post_deploy_reports_payload,
    get_default_post_deploy_report_dir,
    load_report_json,
)


DEFAULT_REPORT_DIR = get_default_post_deploy_report_dir()
DEFAULT_LIMIT = 5


def _print_entry(entry: dict[str, Any]) -> None:
    status = str(entry.get("status", "unknown")).upper()
    finished_at = str(entry.get("finished_at", "-"))
    file_name = str(entry.get("file", "-"))
    base_url = str(entry.get("base_url", "-"))
    skip_smoke = "yes" if entry.get("skip_smoke") else "no"
    print(f"- [{status}] {finished_at}  file={file_name}  base_url={base_url}  skip_smoke={skip_smoke}", flush=True)


def _print_latest_details(report_dir: Path) -> None:
    latest_path = Path(report_dir).expanduser() / "latest.json"
    payload = load_report_json(latest_path)
    print("", flush=True)
    print("Latest report details", flush=True)
    print(f"- status={payload.get('status', 'unknown')}", flush=True)
    print(f"- base_url={payload.get('base_url', '-')}", flush=True)
    print(f"- started_at={payload.get('started_at', '-')}", flush=True)
    print(f"- finished_at={payload.get('finished_at', '-')}", flush=True)
    print(f"- skip_smoke={'yes' if payload.get('skip_smoke') else 'no'}", flush=True)
    if payload.get("error"):
        print(f"- error={payload['error']}", flush=True)
    checks = payload.get("checks", [])
    print("Checks", flush=True)
    for check in checks:
        name = check.get("name", "unknown")
        status = check.get("status", "unknown")
        exit_code = check.get("exit_code")
        suffix = f" exit_code={exit_code}" if exit_code is not None else ""
        print(f"- [{status}] {name}{suffix}", flush=True)


def _build_json_payload(*, report_dir: Path, limit: int, latest: bool) -> dict[str, Any]:
    try:
        return build_post_deploy_reports_payload(report_dir=report_dir, limit=limit, latest=latest)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


def show_post_deploy_reports(*, report_dir: Path, limit: int, latest: bool, json_output: bool) -> int:
    payload = _build_json_payload(report_dir=report_dir, limit=limit, latest=latest)
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
        return 0

    latest_report = payload["latest_report"]
    updated_at = payload["updated_at"]

    print(f"Report directory: {Path(report_dir).expanduser()}", flush=True)
    print(f"Index file: {payload['index_file']}", flush=True)
    print(f"Latest report: {latest_report}", flush=True)
    print(f"Updated at: {updated_at}", flush=True)
    print("", flush=True)
    print(f"Recent reports (limit={max(1, int(limit))})", flush=True)
    for entry in payload["reports"]:
        _print_entry(entry)

    if latest:
        _print_latest_details(report_dir)

    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show recent DecisionDoc post-deploy verification reports from the local report history.",
    )
    parser.add_argument(
        "--report-dir",
        default=str(DEFAULT_REPORT_DIR),
        help="Directory that contains post-deploy report history. Default: reports/post-deploy",
    )
    parser.add_argument(
        "--limit",
        default=DEFAULT_LIMIT,
        type=int,
        help="Number of recent reports to display from index.json. Default: 5",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Also print detailed checks from latest.json.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON payload instead of human-readable text.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    return show_post_deploy_reports(
        report_dir=Path(args.report_dir),
        limit=int(args.limit),
        latest=bool(args.latest),
        json_output=bool(args.json),
    )


if __name__ == "__main__":
    raise SystemExit(main())
