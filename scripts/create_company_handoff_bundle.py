#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import check_company_handoff_ready  # noqa: E402
import prepare_company_handoff  # noqa: E402


HANDOFF_DOCUMENTS: tuple[str, ...] = (
    "docs/deployment/admin_v1_handoff.md",
    "docs/deployment/admin_aws_ec2_setup.md",
    "docs/deployment/prod_checklist.md",
    "docs/deployment/admin_v1_1_58_acceptance_20260430.md",
    "docs/security_policy.md",
    "docs/v1_completion_snapshot.md",
    "docs/sales/company_delivery_guide.md",
)


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_artifact(*, repo_root: Path, source: Path, bundle_dir: Path) -> dict[str, object]:
    if not source.exists() or not source.is_file():
        display_path = str(source.relative_to(repo_root)) if source.is_relative_to(repo_root) else str(source)
        raise FileNotFoundError(f"handoff artifact is missing: {display_path}")
    relative = source.relative_to(repo_root) if source.is_relative_to(repo_root) else Path(source.name)
    destination = bundle_dir / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return {
        "path": str(relative),
        "bundle_path": str(destination.relative_to(bundle_dir)),
        "size_bytes": destination.stat().st_size,
        "sha256": _sha256(destination),
    }


def _pdf_paths(repo_root: Path, output_dir: Path) -> list[Path]:
    resolved_output = output_dir if output_dir.is_absolute() else repo_root / output_dir
    return [resolved_output / item.path for item in check_company_handoff_ready.REQUIRED_PDFS]


def _document_paths(repo_root: Path) -> list[Path]:
    return [repo_root / path for path in HANDOFF_DOCUMENTS]


def _write_manifest(bundle_dir: Path, payload: dict[str, object]) -> Path:
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def create_company_handoff_bundle(
    *,
    repo_root: Path = REPO_ROOT,
    output_dir: Path = Path("output/pdf"),
    report_dir: Path = Path("reports/company-handoff"),
    bundle_root: Path = Path("output/company-handoff"),
    skip_prepare: bool = False,
    skip_build: bool = False,
    bundle_name: str | None = None,
) -> dict[str, object]:
    resolved_repo = repo_root.expanduser().resolve()
    resolved_bundle_root = bundle_root if bundle_root.is_absolute() else resolved_repo / bundle_root
    resolved_report_dir = report_dir if report_dir.is_absolute() else resolved_repo / report_dir

    prepare_result: dict[str, object] | None = None
    if not skip_prepare:
        prepare_result = prepare_company_handoff.prepare_company_handoff(
            output_dir=output_dir,
            report_dir=report_dir,
            skip_build=skip_build,
        )
        if not prepare_result["ok"]:
            return {
                "ok": False,
                "bundle_dir": "",
                "manifest_path": "",
                "prepare_result": prepare_result,
                "errors": list(prepare_result["errors"]),
            }

    latest_report = resolved_report_dir / "latest.json"
    if not latest_report.exists():
        return {
            "ok": False,
            "bundle_dir": "",
            "manifest_path": "",
            "prepare_result": prepare_result,
            "errors": [f"company handoff readiness report is missing: {latest_report}"],
        }

    name = bundle_name or f"company-handoff-{_utc_timestamp()}"
    bundle_dir = resolved_bundle_root / name
    if bundle_dir.exists():
        raise FileExistsError(f"bundle directory already exists: {bundle_dir}")
    bundle_dir.mkdir(parents=True)

    artifacts: list[dict[str, object]] = []
    for path in [*_pdf_paths(resolved_repo, output_dir), *_document_paths(resolved_repo), latest_report]:
        artifacts.append(_copy_artifact(repo_root=resolved_repo, source=path, bundle_dir=bundle_dir))

    manifest = {
        "schema": "decisiondoc_company_handoff_bundle.v1",
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "release_tag": check_company_handoff_ready.LATEST_RELEASE_TAG,
        "acceptance_file": check_company_handoff_ready.LATEST_ACCEPTANCE_FILE,
        "readiness_report": str(latest_report.relative_to(resolved_repo)) if latest_report.is_relative_to(resolved_repo) else str(latest_report),
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    manifest_path = _write_manifest(bundle_dir, manifest)
    return {
        "ok": True,
        "bundle_dir": str(bundle_dir),
        "manifest_path": str(manifest_path),
        "prepare_result": prepare_result,
        "errors": [],
    }


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a reproducible company handoff bundle with manifest hashes.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output/pdf"), help="Sales PDF output directory.")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports/company-handoff"),
        help="Directory containing company handoff readiness reports.",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=Path("output/company-handoff"),
        help="Root directory where the handoff bundle directory will be created.",
    )
    parser.add_argument("--bundle-name", help="Optional deterministic bundle directory name.")
    parser.add_argument("--skip-prepare", action="store_true", help="Do not run prepare_company_handoff first.")
    parser.add_argument("--skip-build", action="store_true", help="Pass --skip-build to prepare_company_handoff.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    try:
        result = create_company_handoff_bundle(
            output_dir=args.output_dir,
            report_dir=args.report_dir,
            bundle_root=args.bundle_root,
            skip_prepare=args.skip_prepare,
            skip_build=args.skip_build,
            bundle_name=args.bundle_name,
        )
    except (FileExistsError, FileNotFoundError) as exc:
        print("FAIL company handoff bundle creation failed")
        print(f"ERROR {exc}")
        return 1

    if result["ok"]:
        print("PASS company handoff bundle created")
        print(f"bundle_dir={result['bundle_dir']}")
        print(f"manifest_path={result['manifest_path']}")
        print("next_action=visually review bundle contents and share secrets through a separate channel")
        return 0

    print("FAIL company handoff bundle creation failed")
    for error in result["errors"]:
        print(f"ERROR {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
