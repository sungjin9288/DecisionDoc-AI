#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import archive_company_handoff_bundle  # noqa: E402
import create_company_handoff_bundle  # noqa: E402
import verify_company_handoff_bundle  # noqa: E402


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y%m%dT%H%M%SZ")


def _generated_at() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_package_reports(*, result: dict[str, object], report_dir: Path) -> list[str]:
    timestamped = report_dir / f"company-handoff-package-{_utc_timestamp()}.json"
    latest = report_dir / "package-latest.json"
    paths = [timestamped, latest]
    result["reports"] = [str(path) for path in paths]
    for path in paths:
        _write_json(path, result)
    return [str(path) for path in paths]


def _base_result() -> dict[str, object]:
    source = create_company_handoff_bundle.check_company_handoff_ready.build_source_metadata(
        create_company_handoff_bundle.REPO_ROOT
    )
    return {
        "ok": False,
        "generated_at": _generated_at(),
        "release_tag": create_company_handoff_bundle.check_company_handoff_ready.LATEST_RELEASE_TAG,
        "source": source,
        "warnings": list(source.get("warnings", [])),
        "errors": [],
        "reports": [],
    }


def package_company_handoff(
    *,
    output_dir: Path = Path("output/pdf"),
    report_dir: Path = Path("reports/company-handoff"),
    bundle_root: Path = Path("output/company-handoff"),
    bundle_name: str | None = None,
    skip_build: bool = False,
    skip_prepare: bool = False,
    force_archive: bool = False,
) -> dict[str, object]:
    result = _base_result()

    try:
        bundle = create_company_handoff_bundle.create_company_handoff_bundle(
            output_dir=output_dir,
            report_dir=report_dir,
            bundle_root=bundle_root,
            skip_prepare=skip_prepare,
            skip_build=skip_build,
            bundle_name=bundle_name,
        )
    except (FileExistsError, FileNotFoundError) as exc:
        result.update(
            {
                "failed_stage": "bundle",
                "bundle": None,
                "verification": None,
                "archive": None,
                "errors": [str(exc)],
            }
        )
        _write_package_reports(result=result, report_dir=report_dir)
        return result

    result["bundle"] = bundle
    source = bundle.get("source")
    if isinstance(source, dict):
        result["source"] = source
        result["warnings"] = list(source.get("warnings", []))
    if not bundle["ok"]:
        result.update(
            {
                "failed_stage": "bundle",
                "verification": None,
                "archive": None,
                "errors": list(bundle["errors"]),
            }
        )
        _write_package_reports(result=result, report_dir=report_dir)
        return result

    verification = verify_company_handoff_bundle.verify_company_handoff_bundle(
        bundle_or_manifest=Path(str(bundle["bundle_dir"]))
    )
    result["verification"] = verification
    if not verification["ok"]:
        result.update(
            {
                "failed_stage": "verify",
                "archive": None,
                "errors": list(verification["errors"]),
            }
        )
        _write_package_reports(result=result, report_dir=report_dir)
        return result

    archive = archive_company_handoff_bundle.archive_company_handoff_bundle(
        bundle_dir=Path(str(bundle["bundle_dir"])),
        force=force_archive,
        skip_verify=True,
    )
    result["archive"] = archive
    if not archive["ok"]:
        result.update(
            {
                "failed_stage": "archive",
                "errors": list(archive["errors"]),
            }
        )
        _write_package_reports(result=result, report_dir=report_dir)
        return result

    result.update(
        {
            "ok": True,
            "failed_stage": None,
            "errors": [],
            "summary": {
                "bundle_dir": bundle["bundle_dir"],
                "manifest_path": bundle["manifest_path"],
                "checked_artifacts": verification["checked_artifacts"],
                "archive_path": archive["archive_path"],
                "sha256_path": archive["sha256_path"],
                "archive_sha256": archive["archive_sha256"],
                "archive_size_bytes": archive["archive_size_bytes"],
                "source_describe": result["source"].get("source_describe") if isinstance(result.get("source"), dict) else "",
                "exact_release_tag": result["source"].get("exact_release_tag") if isinstance(result.get("source"), dict) else False,
            },
        }
    )
    _write_package_reports(result=result, report_dir=report_dir)
    return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the full company handoff flow: prepare, bundle, verify, archive, and write final evidence.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output/pdf"), help="Sales PDF output directory.")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports/company-handoff"),
        help="Directory for readiness and final package reports.",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=Path("output/company-handoff"),
        help="Root directory where the handoff bundle and archive will be created.",
    )
    parser.add_argument("--bundle-name", help="Optional deterministic bundle directory name.")
    parser.add_argument("--skip-build", action="store_true", help="Do not rebuild sales PDFs; validate existing files.")
    parser.add_argument("--skip-prepare", action="store_true", help="Do not run prepare_company_handoff first.")
    parser.add_argument("--force-archive", action="store_true", help="Overwrite an existing zip and .sha256 sidecar.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = package_company_handoff(
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        bundle_root=args.bundle_root,
        bundle_name=args.bundle_name,
        skip_build=args.skip_build,
        skip_prepare=args.skip_prepare,
        force_archive=args.force_archive,
    )
    if result["ok"]:
        summary = result["summary"]
        print("PASS company handoff final package created")
        print(f"bundle_dir={summary['bundle_dir']}")
        print(f"manifest_path={summary['manifest_path']}")
        print(f"archive_path={summary['archive_path']}")
        print(f"sha256_path={summary['sha256_path']}")
        print(f"archive_sha256={summary['archive_sha256']}")
        print(f"checked_artifacts={summary['checked_artifacts']}")
        print(f"source_describe={summary.get('source_describe') or '-'}")
        print(f"exact_release_tag={str(summary.get('exact_release_tag')).lower()}")
        for report in result["reports"]:
            print(f"report_written={report}")
        return 0

    print("FAIL company handoff final package creation failed")
    print(f"failed_stage={result.get('failed_stage') or 'unknown'}")
    for error in result["errors"]:
        print(f"ERROR {error}")
    for report in result["reports"]:
        print(f"report_written={report}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
