#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence
import importlib.util


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_BUNDLE = _load_module("create_pilot_delivery_bundle.py", "decisiondoc_create_pilot_delivery_bundle")
_MANIFEST = _load_module("create_pilot_delivery_manifest.py", "decisiondoc_create_pilot_delivery_manifest")
_RECEIPT = _load_module("create_pilot_delivery_receipt.py", "decisiondoc_create_pilot_delivery_receipt")
_AUDIT = _load_module("audit_pilot_delivery.py", "decisiondoc_audit_pilot_delivery")

create_pilot_delivery_bundle = _BUNDLE.create_pilot_delivery_bundle
create_pilot_delivery_manifest = _MANIFEST.create_pilot_delivery_manifest
create_pilot_delivery_receipt = _RECEIPT.create_pilot_delivery_receipt
create_pilot_delivery_audit = _AUDIT.create_pilot_delivery_audit


def refresh_pilot_delivery_chain(*, closeout_file: Path, output_dir: Path) -> dict[str, object]:
    bundle_payload, bundle_file = create_pilot_delivery_bundle(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    manifest_payload, manifest_file = create_pilot_delivery_manifest(
        bundle_file=bundle_file,
        output_dir=output_dir,
    )
    receipt_payload, receipt_file = create_pilot_delivery_receipt(
        bundle_file=bundle_file,
        manifest_file=manifest_file,
        output_dir=output_dir,
    )
    audit_payload, audit_file = create_pilot_delivery_audit(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    return {
        "pilot_status": bundle_payload.get("pilot_status", "INCOMPLETE"),
        "bundle_file": str(bundle_file),
        "manifest_file": str(manifest_file),
        "receipt_file": str(receipt_file),
        "audit_file": str(audit_file),
        "bundle_sha256": manifest_payload.get("bundle_sha256", "-"),
        "entry_count": manifest_payload.get("entry_count", 0),
        "verification_status": receipt_payload.get("verification_status", "FAIL"),
        "audit_status": audit_payload.get("status", "FAIL"),
        "receipt_matches": audit_payload.get("receipt_matches", False),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh the full pilot delivery chain from closeout through bundle, manifest, receipt, and audit.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery artifacts.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = refresh_pilot_delivery_chain(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Refreshed pilot delivery chain from: {args.closeout_file}", flush=True)
    print(f"Pilot status: {result.get('pilot_status', 'INCOMPLETE')}", flush=True)
    print(f"Bundle SHA256: {result.get('bundle_sha256', '-')}", flush=True)
    print(f"Entry count: {result.get('entry_count', 0)}", flush=True)
    print(f"Verification status: {result.get('verification_status', 'FAIL')}", flush=True)
    print(f"Audit status: {result.get('audit_status', 'FAIL')}", flush=True)
    print(f"Receipt matches: {str(result.get('receipt_matches', False)).lower()}", flush=True)
    print(f"Bundle file: {result.get('bundle_file', '-')}", flush=True)
    print(f"Manifest file: {result.get('manifest_file', '-')}", flush=True)
    print(f"Receipt file: {result.get('receipt_file', '-')}", flush=True)
    print(f"Audit file: {result.get('audit_file', '-')}", flush=True)
    return 0 if result.get("audit_status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
