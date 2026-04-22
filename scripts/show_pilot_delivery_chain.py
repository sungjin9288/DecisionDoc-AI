#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Sequence


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_AUDIT = _load_module("audit_pilot_delivery.py", "decisiondoc_audit_pilot_delivery")

build_pilot_delivery_audit_payload = _AUDIT.build_pilot_delivery_audit_payload


def show_pilot_delivery_chain(*, closeout_file: Path) -> dict[str, object]:
    return build_pilot_delivery_audit_payload(closeout_file=closeout_file)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show current pilot delivery chain status without regenerating artifacts.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = show_pilot_delivery_chain(closeout_file=Path(args.closeout_file))
    print(f"Pilot delivery status: {result.get('status', 'FAIL')}", flush=True)
    print(f"Bundle SHA256: {result.get('bundle_sha256', '-')}", flush=True)
    print(f"Entry count: {result.get('entry_count', 0)}", flush=True)
    print(f"Receipt matches: {str(result.get('receipt_matches', False)).lower()}", flush=True)
    print(f"Stale: {str(result.get('stale', False)).lower()}", flush=True)
    stale_artifacts = result.get("stale_artifacts") or []
    print(f"Stale artifacts: {', '.join(stale_artifacts) if stale_artifacts else '-'}", flush=True)
    for item in result.get("checks") or []:
        print(f"{item['name']}: {item['status']} -> {item['path']}", flush=True)
    errors = result.get("verification_errors") or []
    if errors:
        print("Verification errors:", flush=True)
        for error in errors:
            print(f"- {error}", flush=True)
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
