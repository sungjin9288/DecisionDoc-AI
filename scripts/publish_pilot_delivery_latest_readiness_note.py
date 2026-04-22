#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"
DEFAULT_LATEST_FILENAME = "latest-pilot-delivery-readiness.md"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_READINESS = _load_module(
    "publish_pilot_delivery_latest_readiness.py",
    "decisiondoc_publish_pilot_delivery_latest_readiness",
)

publish_pilot_delivery_latest_readiness = _READINESS.publish_pilot_delivery_latest_readiness


def _build_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    errors = payload.get("errors") or []
    error_lines = "\n".join(f"- {item}" for item in errors) if errors else "- 없음"
    return f"""# Pilot Delivery Latest Readiness

- generated_at: {generated_at.isoformat()}
- ready: **{"PASS" if payload.get("ok") else "FAIL"}**
- status: `{payload.get("status", "-")}`
- stale: `{str(payload.get("stale", False)).lower()}`
- receipt_matches: `{str(payload.get("receipt_matches", False)).lower()}`

## Stable Pointers

- latest_status_file: `{payload.get("latest_status_file", "-")}`
- latest_audit_file: `{payload.get("latest_audit_file", "-")}`
- status_file: `{payload.get("status_file", "-")}`

## Snapshot

- snapshot_file: `{payload.get("snapshot_file", "-")}`
- audit_file: `{payload.get("audit_file", "-")}`

## Errors

{error_lines}
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def publish_pilot_delivery_latest_readiness_note(
    *,
    closeout_file: Path,
    output_dir: Path,
    latest_filename: str = DEFAULT_LATEST_FILENAME,
) -> tuple[dict[str, object], Path]:
    payload, _ = publish_pilot_delivery_latest_readiness(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    latest_path = output_dir / latest_filename
    markdown = _build_markdown(payload=payload, generated_at=datetime.now(timezone.utc))
    _write_text_atomic(latest_path, markdown)
    return payload, latest_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish the latest pilot delivery readiness summary as stable markdown.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery artifacts.")
    parser.add_argument("--latest-filename", default=DEFAULT_LATEST_FILENAME, help="Stable latest readiness markdown filename.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, latest_path = publish_pilot_delivery_latest_readiness_note(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
        latest_filename=args.latest_filename,
    )
    print(f"Published latest pilot delivery readiness note: {latest_path}", flush=True)
    print(f"Ready: {'PASS' if payload.get('ok') else 'FAIL'}", flush=True)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
