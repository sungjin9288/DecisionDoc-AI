#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"

LATEST_STATUS = "latest-pilot-delivery-status.json"
LATEST_AUDIT = "latest-pilot-delivery-audit.md"
LATEST_READINESS_JSON = "latest-pilot-delivery-readiness.json"
LATEST_READINESS_MD = "latest-pilot-delivery-readiness.md"
LATEST_OVERVIEW_MD = "latest-pilot-delivery-overview.md"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def show_pilot_delivery_latest_summary(*, output_dir: Path) -> dict[str, object]:
    status_path = output_dir / LATEST_STATUS
    audit_path = output_dir / LATEST_AUDIT
    readiness_json_path = output_dir / LATEST_READINESS_JSON
    readiness_md_path = output_dir / LATEST_READINESS_MD
    overview_path = output_dir / LATEST_OVERVIEW_MD

    checks: list[dict[str, str]] = []
    required_paths = {
        "status_json": status_path,
        "audit_markdown": audit_path,
        "readiness_json": readiness_json_path,
        "readiness_markdown": readiness_md_path,
        "overview_markdown": overview_path,
    }

    missing: list[str] = []
    for name, path in required_paths.items():
        exists = path.exists()
        checks.append({"name": name, "status": "ok" if exists else "missing", "path": str(path)})
        if not exists:
            missing.append(name)

    errors: list[str] = []
    if missing:
        errors.extend(f"missing latest artifact: {name}" for name in missing)
        return {
            "ok": False,
            "status": "FAIL",
            "stale": True,
            "receipt_matches": False,
            "bundle_sha256": "-",
            "entry_count": 0,
            "checks": checks,
            "errors": errors,
        }

    status_payload = _load_json(status_path)
    readiness_payload = _load_json(readiness_json_path)
    ok = (
        status_payload.get("status") == "PASS"
        and readiness_payload.get("ok") is True
        and status_payload.get("stale") is False
        and readiness_payload.get("stale") is False
        and status_payload.get("receipt_matches") is True
        and readiness_payload.get("receipt_matches") is True
    )
    if not ok:
        errors.append("latest pilot delivery artifacts are present but not ready")

    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "stale": bool(status_payload.get("stale") or readiness_payload.get("stale")),
        "receipt_matches": bool(
            status_payload.get("receipt_matches") and readiness_payload.get("receipt_matches")
        ),
        "bundle_sha256": status_payload.get("bundle_sha256", "-"),
        "entry_count": status_payload.get("entry_count", 0),
        "latest_status_file": str(status_path),
        "latest_audit_file": str(audit_path),
        "latest_readiness_json": str(readiness_json_path),
        "latest_readiness_markdown": str(readiness_md_path),
        "latest_overview_markdown": str(overview_path),
        "checks": checks,
        "errors": errors,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show current stable latest pilot delivery artifacts summary without regenerating them.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory containing stable latest pilot delivery artifacts.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Print machine-readable JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = show_pilot_delivery_latest_summary(output_dir=Path(args.output_dir))

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        return 0 if result["ok"] else 1

    print(f"Pilot delivery latest summary: {'PASS' if result['ok'] else 'FAIL'}", flush=True)
    print(f"Bundle SHA256: {result.get('bundle_sha256', '-')}", flush=True)
    print(f"Entry count: {result.get('entry_count', 0)}", flush=True)
    print(f"Stale: {str(result.get('stale', False)).lower()}", flush=True)
    print(f"Receipt matches: {str(result.get('receipt_matches', False)).lower()}", flush=True)
    for item in result["checks"]:
        print(f"{item['name']}: {item['status']} -> {item['path']}", flush=True)
    if result["errors"]:
        print("Errors:", flush=True)
        for error in result["errors"]:
            print(f"- {error}", flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
