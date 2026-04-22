#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_pilot_delivery_manifest_payload(*, bundle_file: Path) -> dict[str, object]:
    if not bundle_file.exists():
        raise SystemExit(f"Pilot delivery bundle not found: {bundle_file}")

    entries: list[dict[str, object]] = []
    with zipfile.ZipFile(bundle_file) as archive:
        for info in sorted(archive.infolist(), key=lambda item: item.filename):
            if info.is_dir():
                continue
            content = archive.read(info.filename)
            entries.append(
                {
                    "name": info.filename,
                    "size_bytes": info.file_size,
                    "compressed_size_bytes": info.compress_size,
                    "sha256": _sha256_bytes(content),
                }
            )

    return {
        "bundle_path": str(bundle_file),
        "bundle_name": bundle_file.name,
        "bundle_size_bytes": bundle_file.stat().st_size,
        "bundle_sha256": _sha256_file(bundle_file),
        "entry_count": len(entries),
        "entries": entries,
    }


def build_pilot_delivery_manifest_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    entry_lines = []
    for entry in payload.get("entries") or []:
        entry_lines.append(
            "\n".join(
                [
                    f"### {entry.get('name', '-')}",
                    f"- size_bytes: `{entry.get('size_bytes', 0)}`",
                    f"- compressed_size_bytes: `{entry.get('compressed_size_bytes', 0)}`",
                    f"- sha256: `{entry.get('sha256', '-')}`",
                ]
            )
        )

    entries_block = "\n\n".join(entry_lines) if entry_lines else "_No bundle entries found._"
    return f"""# Pilot Delivery Manifest — {payload.get('bundle_name', '-')}

- generated_at: {generated_at.isoformat()}
- bundle_path: `{payload.get('bundle_path', '-')}`
- bundle_size_bytes: `{payload.get('bundle_size_bytes', 0)}`
- bundle_sha256: `{payload.get('bundle_sha256', '-')}`
- entry_count: `{payload.get('entry_count', 0)}`

## Included Files

{entries_block}
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_delivery_manifest(*, bundle_file: Path, output_dir: Path) -> tuple[dict[str, object], Path]:
    payload = build_pilot_delivery_manifest_payload(bundle_file=bundle_file)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{bundle_file.stem}-manifest.md"
    markdown = build_pilot_delivery_manifest_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a SHA256 manifest for the pilot delivery bundle and its included files.",
    )
    parser.add_argument("--bundle-file", required=True, help="Pilot delivery bundle zip path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot delivery manifest.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_delivery_manifest(
        bundle_file=Path(args.bundle_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot delivery manifest: {output_path}", flush=True)
    print(f"Bundle SHA256: {payload.get('bundle_sha256', '-')}", flush=True)
    print(f"Included files: {payload.get('entry_count', 0)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
