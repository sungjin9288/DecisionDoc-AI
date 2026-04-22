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
DEFAULT_LATEST_FILENAME = "latest-pilot-delivery-overview.md"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_READINESS_ARTIFACTS = _load_module(
    "publish_pilot_delivery_latest_readiness_artifacts.py",
    "decisiondoc_publish_pilot_delivery_latest_readiness_artifacts",
)

publish_pilot_delivery_latest_readiness_artifacts = (
    _READINESS_ARTIFACTS.publish_pilot_delivery_latest_readiness_artifacts
)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _build_markdown(
    *,
    generated_at: datetime,
    status_payload: dict[str, object],
    readiness_payload: dict[str, object],
    paths: dict[str, str],
) -> str:
    return f"""# Pilot Delivery Latest Overview

- generated_at: {generated_at.isoformat()}
- pilot_delivery_status: **{status_payload.get("status", "FAIL")}**
- readiness: **{"PASS" if readiness_payload.get("ok") else "FAIL"}**
- stale: `{str(status_payload.get("stale", False)).lower()}`
- receipt_matches: `{str(status_payload.get("receipt_matches", False)).lower()}`
- bundle_sha256: `{status_payload.get("bundle_sha256", "-")}`
- entry_count: `{status_payload.get("entry_count", 0)}`

## Stable Latest Files

- status_json: `{paths["status_json"]}`
- audit_markdown: `{paths["audit_markdown"]}`
- readiness_json: `{paths["readiness_json"]}`
- readiness_markdown: `{paths["readiness_markdown"]}`

## Snapshot Files

- delivery_status_snapshot: `{readiness_payload.get("snapshot_file", "-")}`
- delivery_audit_snapshot: `{readiness_payload.get("audit_file", "-")}`
- readiness_status_snapshot: `{readiness_payload.get("snapshot_file", "-")}`

## Notes

- latest_status_file: `{readiness_payload.get("latest_status_file", "-")}`
- latest_audit_file: `{readiness_payload.get("latest_audit_file", "-")}`
- errors: `{", ".join(readiness_payload.get("errors", [])) if readiness_payload.get("errors") else "없음"}`
"""


def publish_pilot_delivery_latest_overview(
    *,
    closeout_file: Path,
    output_dir: Path,
    latest_filename: str = DEFAULT_LATEST_FILENAME,
) -> tuple[dict[str, object], Path]:
    publish_result = publish_pilot_delivery_latest_readiness_artifacts(
        closeout_file=closeout_file,
        output_dir=output_dir,
    )
    status_path = Path(str(publish_result["latest_status_file"]))
    audit_path = Path(str(publish_result["latest_audit_file"]))
    readiness_json_path = Path(str(publish_result["latest_readiness_json"]))
    readiness_note_path = Path(str(publish_result["latest_readiness_note"]))

    status_payload = _load_json(status_path)
    readiness_payload = _load_json(readiness_json_path)
    latest_path = output_dir / latest_filename
    markdown = _build_markdown(
        generated_at=datetime.now(timezone.utc),
        status_payload=status_payload,
        readiness_payload=readiness_payload,
        paths={
            "status_json": str(status_path),
            "audit_markdown": str(audit_path),
            "readiness_json": str(readiness_json_path),
            "readiness_markdown": str(readiness_note_path),
        },
    )
    _write_text_atomic(latest_path, markdown)
    return {
        "ok": bool(readiness_payload.get("ok")),
        "status": status_payload.get("status", "FAIL"),
        "stale": bool(status_payload.get("stale")),
        "receipt_matches": bool(status_payload.get("receipt_matches")),
        "bundle_sha256": status_payload.get("bundle_sha256", "-"),
        "entry_count": status_payload.get("entry_count", 0),
        "latest_status_file": str(status_path),
        "latest_audit_file": str(audit_path),
        "latest_readiness_json": str(readiness_json_path),
        "latest_readiness_note": str(readiness_note_path),
    }, latest_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish a human-readable latest pilot delivery overview markdown after syncing latest artifacts.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to write generated pilot delivery artifacts.",
    )
    parser.add_argument(
        "--latest-filename",
        default=DEFAULT_LATEST_FILENAME,
        help="Stable latest overview markdown filename.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, latest_path = publish_pilot_delivery_latest_overview(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
        latest_filename=args.latest_filename,
    )
    print(f"Published latest pilot delivery overview: {latest_path}", flush=True)
    print(f"Ready: {'PASS' if payload.get('ok') else 'FAIL'}", flush=True)
    print(f"Status: {payload.get('status', 'FAIL')}", flush=True)
    print(f"Stale: {str(payload.get('stale', False)).lower()}", flush=True)
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
