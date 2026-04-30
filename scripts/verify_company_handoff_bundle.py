#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence


EXPECTED_SCHEMA = "decisiondoc_company_handoff_bundle.v1"
HIGH_CONFIDENCE_FORBIDDEN_TEXT: tuple[str, ...] = (
    "OPENAI_API_KEY=" "sk-",
    "-----BEGIN " "OPENSSH PRIVATE KEY-----",
    "-----BEGIN " "RSA PRIVATE KEY-----",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_manifest_path(bundle_or_manifest: Path) -> Path:
    path = bundle_or_manifest.expanduser().resolve()
    return path / "manifest.json" if path.is_dir() else path


def _safe_artifact_path(bundle_dir: Path, bundle_path: str) -> Path | None:
    if not bundle_path or Path(bundle_path).is_absolute():
        return None
    resolved = (bundle_dir / bundle_path).resolve()
    if resolved == bundle_dir or bundle_dir not in resolved.parents:
        return None
    return resolved


def _scan_forbidden_text(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [pattern for pattern in HIGH_CONFIDENCE_FORBIDDEN_TEXT if pattern in text]


def verify_company_handoff_bundle(*, bundle_or_manifest: Path) -> dict[str, object]:
    manifest_path = _resolve_manifest_path(bundle_or_manifest)
    errors: list[str] = []
    if not manifest_path.exists() or not manifest_path.is_file():
        return {
            "ok": False,
            "errors": [f"manifest file is missing: {manifest_path}"],
            "manifest_path": str(manifest_path),
            "bundle_dir": str(manifest_path.parent),
            "checked_artifacts": 0,
        }

    bundle_dir = manifest_path.parent.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "errors": [f"manifest is not valid JSON: {exc}"],
            "manifest_path": str(manifest_path),
            "bundle_dir": str(bundle_dir),
            "checked_artifacts": 0,
        }

    if manifest.get("schema") != EXPECTED_SCHEMA:
        errors.append(f"unexpected manifest schema: {manifest.get('schema')!r}")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
        errors.append("manifest artifacts must be a list")
    artifact_count = manifest.get("artifact_count")
    if artifact_count != len(artifacts):
        errors.append(f"artifact_count mismatch: {artifact_count!r} != {len(artifacts)}")

    seen_bundle_paths: set[str] = set()
    checked_artifacts = 0
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            errors.append(f"artifact #{index} must be an object")
            continue
        bundle_path = item.get("bundle_path")
        if not isinstance(bundle_path, str):
            errors.append(f"artifact #{index} has invalid bundle_path")
            continue
        if bundle_path in seen_bundle_paths:
            errors.append(f"duplicate artifact bundle_path: {bundle_path}")
            continue
        seen_bundle_paths.add(bundle_path)
        path = _safe_artifact_path(bundle_dir, bundle_path)
        if path is None:
            errors.append(f"unsafe artifact bundle_path: {bundle_path}")
            continue
        if not path.exists() or not path.is_file():
            errors.append(f"artifact file is missing: {bundle_path}")
            continue
        checked_artifacts += 1
        expected_size = item.get("size_bytes")
        actual_size = path.stat().st_size
        if expected_size != actual_size:
            errors.append(f"artifact size mismatch: {bundle_path} ({actual_size} != {expected_size!r})")
        expected_sha = item.get("sha256")
        actual_sha = _sha256(path)
        if expected_sha != actual_sha:
            errors.append(f"artifact sha256 mismatch: {bundle_path}")
        for forbidden in _scan_forbidden_text(path):
            errors.append(f"forbidden secret-like text found in {bundle_path}: {forbidden}")

    return {
        "ok": not errors,
        "errors": errors,
        "manifest_path": str(manifest_path),
        "bundle_dir": str(bundle_dir),
        "checked_artifacts": checked_artifacts,
        "release_tag": manifest.get("release_tag"),
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a DecisionDoc company handoff bundle manifest, hashes, and file integrity.",
    )
    parser.add_argument("bundle_or_manifest", type=Path, help="Bundle directory or manifest.json path.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = verify_company_handoff_bundle(bundle_or_manifest=args.bundle_or_manifest)
    if result["ok"]:
        print("PASS company handoff bundle verification passed")
        print(f"manifest_path={result['manifest_path']}")
        print(f"checked_artifacts={result['checked_artifacts']}")
        print(f"release_tag={result.get('release_tag') or '-'}")
        return 0

    print("FAIL company handoff bundle verification failed")
    print(f"manifest_path={result['manifest_path']}")
    for error in result["errors"]:
        print(f"ERROR {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
