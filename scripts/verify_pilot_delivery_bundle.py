#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Sequence
import zipfile

from scripts.create_pilot_delivery_manifest import parse_pilot_delivery_manifest


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_pilot_delivery_bundle(*, bundle_file: Path, manifest_file: Path) -> dict[str, object]:
    if not bundle_file.exists():
        raise SystemExit(f"Pilot delivery bundle not found: {bundle_file}")

    manifest = parse_pilot_delivery_manifest(manifest_file=manifest_file)
    actual_bundle_sha256 = _sha256_file(bundle_file)
    errors: list[str] = []

    if actual_bundle_sha256 != manifest.get("bundle_sha256"):
        errors.append(
            f"bundle sha256 mismatch: expected {manifest.get('bundle_sha256', '-')}, got {actual_bundle_sha256}"
        )

    actual_entries: dict[str, dict[str, object]] = {}
    with zipfile.ZipFile(bundle_file) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            content = archive.read(info.filename)
            actual_entries[info.filename] = {
                "size_bytes": info.file_size,
                "compressed_size_bytes": info.compress_size,
                "sha256": _sha256_bytes(content),
            }

    expected_entries = {str(entry.get("name", "")): entry for entry in manifest.get("entries") or []}
    if len(actual_entries) != int(manifest.get("entry_count", 0)):
        errors.append(
            f"entry count mismatch: expected {manifest.get('entry_count', 0)}, got {len(actual_entries)}"
        )

    for name, expected in expected_entries.items():
        actual = actual_entries.get(name)
        if not actual:
            errors.append(f"missing entry: {name}")
            continue
        for field in ("size_bytes", "compressed_size_bytes", "sha256"):
            if actual.get(field) != expected.get(field):
                errors.append(
                    f"entry mismatch for {name} {field}: expected {expected.get(field)}, got {actual.get(field)}"
                )

    for name in sorted(set(actual_entries) - set(expected_entries)):
        errors.append(f"unexpected entry: {name}")

    return {
        "bundle_sha256": actual_bundle_sha256,
        "entry_count": len(actual_entries),
        "ok": not errors,
        "errors": errors,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a pilot delivery bundle zip against its markdown manifest.",
    )
    parser.add_argument("--bundle-file", required=True, help="Pilot delivery bundle zip path.")
    parser.add_argument("--manifest-file", required=True, help="Pilot delivery manifest markdown path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = verify_pilot_delivery_bundle(
        bundle_file=Path(args.bundle_file),
        manifest_file=Path(args.manifest_file),
    )
    if result["ok"]:
        print("Pilot delivery bundle verification: PASS", flush=True)
        print(f"Bundle SHA256: {result['bundle_sha256']}", flush=True)
        print(f"Entry count: {result['entry_count']}", flush=True)
        return 0

    print("Pilot delivery bundle verification: FAIL", flush=True)
    for error in result["errors"]:
        print(f"- {error}", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
