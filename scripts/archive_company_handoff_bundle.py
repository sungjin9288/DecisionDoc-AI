#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
from typing import Sequence
import zipfile


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import verify_company_handoff_bundle  # noqa: E402


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_files(bundle_dir: Path) -> list[Path]:
    return sorted(path for path in bundle_dir.rglob("*") if path.is_file())


def _default_archive_path(bundle_dir: Path) -> Path:
    return bundle_dir.with_suffix(".zip")


def _write_sha256_sidecar(archive_path: Path, archive_sha256: str) -> Path:
    sidecar_path = archive_path.with_suffix(f"{archive_path.suffix}.sha256")
    sidecar_path.write_text(f"{archive_sha256}  {archive_path.name}\n", encoding="utf-8")
    return sidecar_path


def archive_company_handoff_bundle(
    *,
    bundle_dir: Path,
    output_path: Path | None = None,
    force: bool = False,
    skip_verify: bool = False,
) -> dict[str, object]:
    resolved_bundle = bundle_dir.expanduser().resolve()
    if not resolved_bundle.exists() or not resolved_bundle.is_dir():
        return {
            "ok": False,
            "errors": [f"bundle directory is missing: {resolved_bundle}"],
            "archive_path": "",
            "sha256_path": "",
        }

    verification: dict[str, object] | None = None
    if not skip_verify:
        verification = verify_company_handoff_bundle.verify_company_handoff_bundle(bundle_or_manifest=resolved_bundle)
        if not verification["ok"]:
            return {
                "ok": False,
                "errors": [f"bundle verification failed: {error}" for error in verification["errors"]],
                "archive_path": "",
                "sha256_path": "",
                "verification": verification,
            }

    archive_path = (
        output_path.expanduser().resolve()
        if output_path is not None
        else _default_archive_path(resolved_bundle)
    )
    sha256_path = archive_path.with_suffix(f"{archive_path.suffix}.sha256")
    if not force and (archive_path.exists() or sha256_path.exists()):
        return {
            "ok": False,
            "errors": [f"archive output already exists: {archive_path}"],
            "archive_path": str(archive_path),
            "sha256_path": str(sha256_path),
            "verification": verification,
        }

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _bundle_files(resolved_bundle):
            archive.write(path, arcname=Path(resolved_bundle.name) / path.relative_to(resolved_bundle))

    archive_sha256 = _sha256(archive_path)
    sha256_path = _write_sha256_sidecar(archive_path, archive_sha256)
    return {
        "ok": True,
        "errors": [],
        "bundle_dir": str(resolved_bundle),
        "archive_path": str(archive_path),
        "sha256_path": str(sha256_path),
        "archive_sha256": archive_sha256,
        "archive_size_bytes": archive_path.stat().st_size,
        "file_count": len(_bundle_files(resolved_bundle)),
        "verification": verification,
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a zip archive and SHA-256 sidecar for a verified company handoff bundle.",
    )
    parser.add_argument("bundle_dir", type=Path, help="Company handoff bundle directory.")
    parser.add_argument("--output-path", type=Path, help="Optional zip output path. Defaults to <bundle_dir>.zip.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing zip and .sha256 sidecar.")
    parser.add_argument("--skip-verify", action="store_true", help="Skip bundle verification before archiving.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = archive_company_handoff_bundle(
        bundle_dir=args.bundle_dir,
        output_path=args.output_path,
        force=args.force,
        skip_verify=args.skip_verify,
    )
    if result["ok"]:
        print("PASS company handoff archive created")
        print(f"archive_path={result['archive_path']}")
        print(f"sha256_path={result['sha256_path']}")
        print(f"archive_sha256={result['archive_sha256']}")
        print(f"archive_size_bytes={result['archive_size_bytes']}")
        print(f"file_count={result['file_count']}")
        return 0

    print("FAIL company handoff archive creation failed")
    for error in result["errors"]:
        print(f"ERROR {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
