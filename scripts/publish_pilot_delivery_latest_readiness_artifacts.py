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


_READINESS_JSON = _load_module(
    "publish_pilot_delivery_latest_readiness.py",
    "decisiondoc_publish_pilot_delivery_latest_readiness",
)
_READINESS_NOTE = _load_module(
    "publish_pilot_delivery_latest_readiness_note.py",
    "decisiondoc_publish_pilot_delivery_latest_readiness_note",
)

publish_pilot_delivery_latest_readiness = _READINESS_JSON.publish_pilot_delivery_latest_readiness
publish_pilot_delivery_latest_readiness_note = _READINESS_NOTE.publish_pilot_delivery_latest_readiness_note


def publish_pilot_delivery_latest_readiness_artifacts(
    *,
    closeout_file: Path,
    output_dir: Path,
) -> dict[str, object]:
    readiness_payload, latest_readiness_json = publish_pilot_delivery_latest_readiness(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    _, latest_readiness_note = publish_pilot_delivery_latest_readiness_note(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    return {
        "ok": bool(readiness_payload.get("ok")),
        "status": readiness_payload.get("status", "FAIL"),
        "stale": bool(readiness_payload.get("stale")),
        "receipt_matches": bool(readiness_payload.get("receipt_matches")),
        "latest_readiness_json": str(latest_readiness_json),
        "latest_readiness_note": str(latest_readiness_note),
        "latest_status_file": readiness_payload.get("latest_status_file", "-"),
        "latest_audit_file": readiness_payload.get("latest_audit_file", "-"),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish both stable latest pilot delivery readiness JSON and markdown in one step.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to write generated pilot delivery artifacts.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = publish_pilot_delivery_latest_readiness_artifacts(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Published latest pilot delivery readiness JSON: {result['latest_readiness_json']}", flush=True)
    print(f"Published latest pilot delivery readiness note: {result['latest_readiness_note']}", flush=True)
    print(f"Ready: {'PASS' if result['ok'] else 'FAIL'}", flush=True)
    print(f"Status: {result['status']}", flush=True)
    print(f"Stale: {str(result['stale']).lower()}", flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
