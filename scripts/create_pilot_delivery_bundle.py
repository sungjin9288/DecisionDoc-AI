#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def _load_module(filename: str, module_name: str):
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_DELIVERY = _load_module("create_pilot_delivery_index.py", "decisiondoc_create_pilot_delivery_index")

build_pilot_delivery_payload = _DELIVERY.build_pilot_delivery_payload


def _gather_bundle_files(delivery_payload: dict[str, object]) -> list[Path]:
    artifacts = delivery_payload.get("artifact_paths") or {}
    ordered_keys = (
        "share_note",
        "completion_report",
        "delivery_index",
        "closeout",
        "run_sheet",
        "launch_checklist",
        "pilot_handoff",
        "uat_summary",
    )
    paths: list[Path] = []
    for key in ordered_keys:
        raw = str(artifacts.get(key, "")).strip()
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            paths.append(path)
    return paths


def build_pilot_delivery_bundle_payload(*, closeout_file: Path) -> dict[str, object]:
    payload = build_pilot_delivery_payload(closeout_file=closeout_file)
    artifacts = dict(payload.get("artifact_paths") or {})
    closeout_path = Path(closeout_file)
    artifacts["delivery_index"] = str(closeout_path.parent / f"{closeout_path.stem}-delivery-index.md")
    payload["artifact_paths"] = artifacts
    payload["bundle_files"] = [str(path) for path in _gather_bundle_files(payload)]
    return payload


def _write_zip(bundle_zip: Path, *, files: list[Path]) -> None:
    bundle_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in files:
            zf.write(file_path, arcname=file_path.name)


def create_pilot_delivery_bundle(*, closeout_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    payload = build_pilot_delivery_bundle_payload(closeout_file=closeout_file)
    output_path = output_dir / f"{Path(closeout_file).stem}-delivery-bundle.zip"
    bundle_files = [Path(item) for item in payload.get("bundle_files") or []]
    _write_zip(output_path, files=bundle_files)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a zip bundle containing the final pilot delivery artifacts.",
    )
    parser.add_argument("--closeout-file", required=True, help="Pilot close-out markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery bundle.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_delivery_bundle(
        closeout_file=Path(args.closeout_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot delivery bundle: {output_path}", flush=True)
    print(f"Pilot status: {payload.get('pilot_status', 'INCOMPLETE')}", flush=True)
    print(f"Bundled files: {len(payload.get('bundle_files') or [])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
