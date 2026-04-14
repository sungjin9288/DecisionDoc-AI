#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "post-deploy"
DEFAULT_LIMIT = 5


def _load_json(path: Path) -> dict[str, Any]:
    resolved = Path(path).expanduser()
    if not resolved.exists():
        raise SystemExit(f"Report file not found: {resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON report: {resolved}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Unexpected JSON payload: {resolved}")
    return payload


def _resolve_index(report_dir: Path) -> tuple[dict[str, Any], Path]:
    resolved_dir = Path(report_dir).expanduser()
    index_path = resolved_dir / "index.json"
    if not index_path.exists():
        raise SystemExit(f"Report index not found: {index_path}")
    payload = _load_json(index_path)
    return payload, index_path


def _print_entry(entry: dict[str, Any]) -> None:
    status = str(entry.get("status", "unknown")).upper()
    finished_at = str(entry.get("finished_at", "-"))
    file_name = str(entry.get("file", "-"))
    base_url = str(entry.get("base_url", "-"))
    skip_smoke = "yes" if entry.get("skip_smoke") else "no"
    print(f"- [{status}] {finished_at}  file={file_name}  base_url={base_url}  skip_smoke={skip_smoke}", flush=True)


def _print_latest_details(report_dir: Path) -> None:
    latest_path = Path(report_dir).expanduser() / "latest.json"
    payload = _load_json(latest_path)
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
    index_payload, index_path = _resolve_index(report_dir)
    reports = list(index_payload.get("reports", []))
    if not reports:
        raise SystemExit(f"No reports listed in index: {index_path}")

    normalized_limit = max(1, int(limit))
    payload: dict[str, Any] = {
        "report_dir": str(Path(report_dir).expanduser()),
        "index_file": str(index_path),
        "latest_report": index_payload.get("latest_report", "-"),
        "updated_at": index_payload.get("updated_at", "-"),
        "reports": [entry for entry in reports[:normalized_limit] if isinstance(entry, dict)],
    }
    if latest:
        latest_path = Path(report_dir).expanduser() / "latest.json"
        payload["latest_details"] = _load_json(latest_path)
    return payload


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
