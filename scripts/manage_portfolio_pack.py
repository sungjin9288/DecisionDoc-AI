#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from collections.abc import Iterable, Sequence
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK_DIR = REPO_ROOT / "_portfolio_export" / "decisiondoc_ai_portfolio_pack"
DEFAULT_ZIP_PATH = REPO_ROOT / "_portfolio_export" / "decisiondoc_ai_portfolio_pack.zip"
MANIFEST_NAME = "portfolio_manifest.json"
MANIFEST_SCHEMA_VERSION = "decisiondoc.portfolio_pack.v1"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
PRIVATE_HOME_PATH_PATTERN = re.compile(rb"/(?:Users|home)/[A-Za-z0-9._-]+/")

SOURCE_FILES = (
    "README.md",
    "DEV_LOG.md",
    "links.md",
    "portfolio_manifest.md",
    "docs/architecture.md",
    "docs/case-study.md",
    "docs/completion-readiness-runbook.md",
    "docs/contribution-note.md",
    "docs/development-plan.md",
    "docs/evidence-checklist.md",
    "docs/evidence-gallery.md",
    "docs/implementation-evidence.md",
    "docs/inspection-20260630.md",
    "docs/interview-story.md",
    "docs/product_demo_scenario.md",
    "docs/product_direction.md",
    "docs/product_execution_plan.md",
    "docs/product_local_demo_runbook.md",
    "docs/project-card.md",
    "docs/resume-bullets.md",
    "docs/roadmap.md",
    "docs/specs/report_quality_learning/PILOT_REVIEW_RUNBOOK.md",
    "evidence/evidence_manifest.md",
    "reports/eval/v1/eval_report.md",
)
SOURCE_DIRS = (
    "docs/samples/bundle_quality_evidence/current",
    "docs/samples/procurement_decision_package_local_demo",
    "evidence/api-responses",
    "evidence/architecture",
    "evidence/cli-logs",
    "evidence/execution-logs",
    "evidence/generated-samples",
    "evidence/input-samples",
    "evidence/output-artifacts",
    "evidence/screenshots",
    "evidence/swagger",
)
EXCLUDED_CONTENT = (
    "environment files and credentials",
    "application source code",
    "customer or internal source material",
    "provider API execution",
    "G2B live API execution",
    "AWS runtime execution",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError(f"portfolio source path must stay relative: {value}")
    return path.as_posix()


def _atomic_write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{uuid4().hex}")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def _assert_pack_directory_is_safe(pack_dir: Path) -> None:
    if pack_dir.name != "decisiondoc_ai_portfolio_pack":
        raise ValueError(
            "portfolio pack directory must be named decisiondoc_ai_portfolio_pack"
        )
    if pack_dir.is_symlink():
        raise ValueError("portfolio pack directory must not be a symlink")
    if pack_dir.exists():
        symlinks = [path for path in pack_dir.rglob("*") if path.is_symlink()]
        if symlinks:
            raise ValueError(f"portfolio pack contains symlinks: {symlinks}")


def collect_tracked_sources(root: Path = REPO_ROOT) -> tuple[str, ...]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "--", *SOURCE_FILES, *SOURCE_DIRS],
        cwd=root,
        check=True,
        capture_output=True,
    )
    tracked = {
        _safe_relative_path(item.decode("utf-8"))
        for item in completed.stdout.split(b"\0")
        if item
    }
    missing = [path for path in SOURCE_FILES if path not in tracked]
    if missing:
        raise ValueError(f"required portfolio source files are not tracked: {missing}")
    return tuple(sorted(tracked))


def build_manifest(root: Path, source_paths: Sequence[str]) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for relative_path in source_paths:
        safe_path = _safe_relative_path(relative_path)
        source = root / safe_path
        if not source.is_file():
            raise ValueError(f"portfolio source file is missing: {safe_path}")
        if source.is_symlink():
            raise ValueError(
                f"portfolio source file must not be a symlink: {safe_path}"
            )
        data = source.read_bytes()
        files.append(
            {
                "path": safe_path,
                "size_bytes": len(data),
                "sha256": _sha256(data),
            }
        )
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "scope": "tracked portfolio documents and local evidence only",
        "files": files,
        "excluded_content": list(EXCLUDED_CONTENT),
    }


def _manifest_bytes(manifest: dict[str, object]) -> bytes:
    return (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _pack_files(pack_dir: Path) -> set[str]:
    if not pack_dir.exists():
        return set()
    return {
        path.relative_to(pack_dir).as_posix()
        for path in pack_dir.rglob("*")
        if path.is_file()
    }


def _remove_empty_directories(pack_dir: Path) -> None:
    directories = sorted(
        (path for path in pack_dir.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        if not any(directory.iterdir()):
            directory.rmdir()


def _validate_relative_links(pack_dir: Path) -> None:
    pack_root = pack_dir.resolve()
    for markdown_path in sorted(pack_dir.rglob("*.md")):
        text = markdown_path.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK_PATTERN.finditer(text):
            raw_target = match.group(1).strip()
            if raw_target.startswith("<"):
                closing = raw_target.find(">")
                target = raw_target[1:closing] if closing >= 0 else raw_target
            else:
                target = raw_target.split(maxsplit=1)[0]
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            resolved = (markdown_path.parent / unquote(parsed.path)).resolve()
            try:
                resolved.relative_to(pack_root)
            except ValueError as exc:
                raise ValueError(
                    f"portfolio Markdown link escapes the pack: "
                    f"{markdown_path.relative_to(pack_dir)} -> {target}"
                ) from exc
            if not resolved.exists():
                raise ValueError(
                    f"portfolio Markdown link target is missing: "
                    f"{markdown_path.relative_to(pack_dir)} -> {target}"
                )


def _validate_no_private_home_paths(pack_dir: Path) -> None:
    for path in sorted(item for item in pack_dir.rglob("*") if item.is_file()):
        if PRIVATE_HOME_PATH_PATTERN.search(path.read_bytes()):
            raise ValueError(
                f"portfolio file contains a private home path: "
                f"{path.relative_to(pack_dir)}"
            )


def sync_pack(
    *,
    root: Path,
    pack_dir: Path,
    source_paths: Sequence[str],
    prune: bool,
) -> dict[str, object]:
    _assert_pack_directory_is_safe(pack_dir)
    manifest = build_manifest(root, source_paths)
    expected_files = {*source_paths, MANIFEST_NAME}
    if prune:
        for relative_path in sorted(_pack_files(pack_dir) - expected_files):
            (pack_dir / relative_path).unlink()
        _remove_empty_directories(pack_dir)

    for relative_path in source_paths:
        _atomic_write(pack_dir / relative_path, (root / relative_path).read_bytes())
    _atomic_write(pack_dir / MANIFEST_NAME, _manifest_bytes(manifest))
    return check_pack(root=root, pack_dir=pack_dir, source_paths=source_paths)


def check_pack(
    *,
    root: Path,
    pack_dir: Path,
    source_paths: Sequence[str],
) -> dict[str, object]:
    _assert_pack_directory_is_safe(pack_dir)
    expected_manifest = build_manifest(root, source_paths)
    expected_files = {*source_paths, MANIFEST_NAME}
    actual_files = _pack_files(pack_dir)
    if actual_files != expected_files:
        missing = sorted(expected_files - actual_files)
        unexpected = sorted(actual_files - expected_files)
        raise ValueError(
            f"portfolio pack membership drifted: missing={missing}, unexpected={unexpected}"
        )

    for relative_path in source_paths:
        source_data = (root / relative_path).read_bytes()
        pack_data = (pack_dir / relative_path).read_bytes()
        if pack_data != source_data:
            raise ValueError(f"portfolio pack file drifted: {relative_path}")

    try:
        actual_manifest = json.loads(
            (pack_dir / MANIFEST_NAME).read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise ValueError("portfolio pack manifest is not valid JSON") from exc
    if actual_manifest != expected_manifest:
        raise ValueError("portfolio pack manifest drifted")
    _validate_relative_links(pack_dir)
    _validate_no_private_home_paths(pack_dir)
    return {
        "ok": True,
        "pack_dir": str(pack_dir),
        "source_file_count": len(source_paths),
        "manifest_sha256": _sha256(_manifest_bytes(expected_manifest)),
    }


def _zip_bytes(pack_dir: Path, relative_paths: Iterable[str]) -> bytes:
    temporary = pack_dir.parent / f".portfolio-pack-zip.{uuid4().hex}"
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
        ) as archive:
            for relative_path in sorted(relative_paths):
                info = zipfile.ZipInfo(relative_path, ZIP_TIMESTAMP)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, (pack_dir / relative_path).read_bytes())
        return temporary.read_bytes()
    finally:
        if temporary.exists():
            temporary.unlink()


def package_zip(
    *,
    root: Path,
    pack_dir: Path,
    zip_path: Path,
    source_paths: Sequence[str],
) -> dict[str, object]:
    try:
        zip_path.relative_to(pack_dir)
    except ValueError:
        pass
    else:
        raise ValueError(
            "portfolio ZIP must be written outside the portfolio pack directory"
        )
    check_pack(root=root, pack_dir=pack_dir, source_paths=source_paths)
    archive_data = _zip_bytes(pack_dir, _pack_files(pack_dir))
    _atomic_write(zip_path, archive_data)
    result = verify_zip(pack_dir=pack_dir, zip_path=zip_path)
    return {**result, "zip_sha256": _sha256(archive_data)}


def verify_zip(*, pack_dir: Path, zip_path: Path) -> dict[str, object]:
    _assert_pack_directory_is_safe(pack_dir)
    expected_files = _pack_files(pack_dir)
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise ValueError("portfolio ZIP contains duplicate entries")
            if set(names) != expected_files:
                raise ValueError("portfolio ZIP membership drifted")
            for relative_path in sorted(expected_files):
                if (
                    archive.read(relative_path)
                    != (pack_dir / relative_path).read_bytes()
                ):
                    raise ValueError(f"portfolio ZIP file drifted: {relative_path}")
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        raise ValueError(
            f"portfolio ZIP is unavailable or invalid: {zip_path}"
        ) from exc
    return {
        "ok": True,
        "zip_path": str(zip_path),
        "entry_count": len(expected_files),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync and verify the DecisionDoc portfolio pack."
    )
    parser.add_argument("command", choices=("sync", "check", "package", "verify-zip"))
    parser.add_argument("--pack-dir", type=Path, default=DEFAULT_PACK_DIR)
    parser.add_argument("--zip-path", type=Path, default=DEFAULT_ZIP_PATH)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove files not present in the tracked source allowlist.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    pack_dir = args.pack_dir.expanduser().resolve()
    zip_path = args.zip_path.expanduser().resolve()
    try:
        source_paths = collect_tracked_sources(REPO_ROOT)
        if args.command == "sync":
            result = sync_pack(
                root=REPO_ROOT,
                pack_dir=pack_dir,
                source_paths=source_paths,
                prune=args.prune,
            )
        elif args.command == "check":
            result = check_pack(
                root=REPO_ROOT, pack_dir=pack_dir, source_paths=source_paths
            )
        elif args.command == "package":
            result = package_zip(
                root=REPO_ROOT,
                pack_dir=pack_dir,
                zip_path=zip_path,
                source_paths=source_paths,
            )
        else:
            result = verify_zip(pack_dir=pack_dir, zip_path=zip_path)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
