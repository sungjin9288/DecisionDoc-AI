#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_STATUS = _load_module(
    "publish_pilot_delivery_latest_status.py",
    "decisiondoc_publish_pilot_delivery_latest_status",
)
_AUDIT = _load_module(
    "publish_pilot_delivery_latest_audit.py",
    "decisiondoc_publish_pilot_delivery_latest_audit",
)

publish_pilot_delivery_latest_status = _STATUS.publish_pilot_delivery_latest_status
publish_pilot_delivery_latest_audit = _AUDIT.publish_pilot_delivery_latest_audit


def publish_pilot_delivery_latest_artifacts(
    *,
    closeout_file: Path,
    output_dir: Path,
) -> dict[str, object]:
    status_payload, snapshot_path, latest_status_path = publish_pilot_delivery_latest_status(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    audit_payload, audit_path, latest_audit_path = publish_pilot_delivery_latest_audit(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    return {
        "status": status_payload.get("status", "FAIL"),
        "stale": bool(status_payload.get("stale")),
        "receipt_matches": bool(status_payload.get("receipt_matches")),
        "snapshot_file": str(snapshot_path),
        "latest_status_file": str(latest_status_path),
        "audit_file": str(audit_path),
        "latest_audit_file": str(latest_audit_path),
        "audit_status": audit_payload.get("status", "FAIL"),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish both latest pilot delivery status JSON and latest audit markdown in one step.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery artifacts.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = publish_pilot_delivery_latest_artifacts(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Published latest pilot delivery status: {result['latest_status_file']}", flush=True)
    print(f"Published latest pilot delivery audit: {result['latest_audit_file']}", flush=True)
    print(f"Status: {result['status']}", flush=True)
    print(f"Audit status: {result['audit_status']}", flush=True)
    print(f"Stale: {str(result['stale']).lower()}", flush=True)
    return 0 if result["status"] == "PASS" and result["audit_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
