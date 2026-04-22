#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from scripts.create_pilot_delivery_manifest import parse_pilot_delivery_manifest  # type: ignore[attr-defined]
from scripts.verify_pilot_delivery_bundle import verify_pilot_delivery_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def build_pilot_delivery_receipt_payload(*, bundle_file: Path, manifest_file: Path) -> dict[str, object]:
    manifest = parse_pilot_delivery_manifest(manifest_file=manifest_file)
    verification = verify_pilot_delivery_bundle(bundle_file=bundle_file, manifest_file=manifest_file)
    return {
        "bundle_file": str(bundle_file),
        "manifest_file": str(manifest_file),
        "bundle_name": bundle_file.name,
        "manifest_name": manifest_file.name,
        "bundle_sha256": verification.get("bundle_sha256", "-"),
        "entry_count": verification.get("entry_count", 0),
        "verification_status": "PASS" if verification.get("ok") else "FAIL",
        "verification_errors": verification.get("errors") or [],
        "manifest_bundle_sha256": manifest.get("bundle_sha256", "-"),
        "manifest_entry_count": manifest.get("entry_count", 0),
    }


def build_pilot_delivery_receipt_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    errors = payload.get("verification_errors") or []
    errors_block = "\n".join(f"- {item}" for item in errors) if errors else "- 없음"
    return f"""# Pilot Delivery Receipt — {payload.get('bundle_name', '-')}

- generated_at: {generated_at.isoformat()}
- verification_status: **{payload.get('verification_status', 'FAIL')}**
- bundle_file: `{payload.get('bundle_file', '-')}`
- manifest_file: `{payload.get('manifest_file', '-')}`

## Integrity Summary

- bundle_sha256: `{payload.get('bundle_sha256', '-')}`
- manifest_bundle_sha256: `{payload.get('manifest_bundle_sha256', '-')}`
- entry_count: `{payload.get('entry_count', 0)}`
- manifest_entry_count: `{payload.get('manifest_entry_count', 0)}`

## Verification Result

{errors_block}
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_delivery_receipt(*, bundle_file: Path, manifest_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    payload = build_pilot_delivery_receipt_payload(bundle_file=bundle_file, manifest_file=manifest_file)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{bundle_file.stem}-receipt.md"
    markdown = build_pilot_delivery_receipt_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a final pilot delivery receipt from a bundle and its verified manifest.",
    )
    parser.add_argument("--bundle-file", required=True, help="Pilot delivery bundle zip path.")
    parser.add_argument("--manifest-file", required=True, help="Pilot delivery manifest markdown path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery receipt.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_delivery_receipt(
        bundle_file=Path(args.bundle_file),
        manifest_file=Path(args.manifest_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot delivery receipt: {output_path}", flush=True)
    print(f"Verification status: {payload.get('verification_status', 'FAIL')}", flush=True)
    print(f"Bundle SHA256: {payload.get('bundle_sha256', '-')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
