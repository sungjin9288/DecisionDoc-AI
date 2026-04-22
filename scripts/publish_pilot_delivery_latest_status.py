#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"
DEFAULT_LATEST_FILENAME = "latest-pilot-delivery-status.json"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_SNAPSHOT = _load_module(
    "create_pilot_delivery_status_snapshot.py",
    "decisiondoc_create_pilot_delivery_status_snapshot",
)

create_pilot_delivery_status_snapshot = _SNAPSHOT.create_pilot_delivery_status_snapshot


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def publish_pilot_delivery_latest_status(
    *,
    closeout_file: Path,
    output_dir: Path,
    latest_filename: str = DEFAULT_LATEST_FILENAME,
) -> tuple[dict[str, object], Path, Path]:
    payload, snapshot_path = create_pilot_delivery_status_snapshot(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    latest_path = output_dir / latest_filename
    _write_text_atomic(latest_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return payload, snapshot_path, latest_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish the latest pilot delivery status JSON to a stable path.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery status files.")
    parser.add_argument("--latest-filename", default=DEFAULT_LATEST_FILENAME, help="Stable latest status JSON filename.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, snapshot_path, latest_path = publish_pilot_delivery_latest_status(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
        latest_filename=args.latest_filename,
    )
    print(f"Created pilot delivery status snapshot: {snapshot_path}", flush=True)
    print(f"Published latest pilot delivery status: {latest_path}", flush=True)
    print(f"Status: {payload.get('status', 'FAIL')}", flush=True)
    print(f"Stale: {str(payload.get('stale', False)).lower()}", flush=True)
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
