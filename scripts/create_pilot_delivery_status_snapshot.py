#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
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


_SHOW = _load_module("show_pilot_delivery_chain.py", "decisiondoc_show_pilot_delivery_chain")

show_pilot_delivery_chain = _SHOW.show_pilot_delivery_chain


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_delivery_status_snapshot(*, closeout_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    payload = show_pilot_delivery_chain(closeout_file=closeout_file)
    snapshot_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    output_path = output_dir / f"{closeout_file.stem}-delivery-status.json"
    _write_text_atomic(output_path, json.dumps(snapshot_payload, ensure_ascii=False, indent=2))
    return snapshot_payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a JSON snapshot of the current pilot delivery chain status.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery status snapshot.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_delivery_status_snapshot(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot delivery status snapshot: {output_path}", flush=True)
    print(f"Status: {payload.get('status', 'FAIL')}", flush=True)
    print(f"Stale: {str(payload.get('stale', False)).lower()}", flush=True)
    return 0 if payload.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
