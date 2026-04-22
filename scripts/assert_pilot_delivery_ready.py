#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS_FILE = REPO_ROOT / "reports" / "pilot" / "latest-pilot-delivery-status.json"


def assert_pilot_delivery_ready(*, status_file: Path) -> dict[str, object]:
    if not status_file.exists():
        raise SystemExit(f"Pilot delivery status file not found: {status_file}")

    payload = json.loads(status_file.read_text(encoding="utf-8"))
    errors: list[str] = []
    if payload.get("status") != "PASS":
        errors.append(f"status is {payload.get('status', '-')}")
    if bool(payload.get("stale")):
        errors.append("delivery artifacts are stale")
    if not bool(payload.get("receipt_matches")):
        errors.append("receipt does not match current verification")

    return {
        "ok": not errors,
        "errors": errors,
        "status": payload.get("status", "-"),
        "stale": bool(payload.get("stale")),
        "receipt_matches": bool(payload.get("receipt_matches")),
        "status_file": str(status_file),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assert that the latest pilot delivery status is ready for downstream automation.",
    )
    parser.add_argument(
        "--status-file",
        default=str(DEFAULT_STATUS_FILE),
        help="Pilot delivery status JSON file path.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = assert_pilot_delivery_ready(status_file=Path(args.status_file))
    if result["ok"]:
        print(f"Pilot delivery ready: PASS ({result['status_file']})", flush=True)
        return 0

    print(f"Pilot delivery ready: FAIL ({result['status_file']})", flush=True)
    for error in result["errors"]:
        print(f"- {error}", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
