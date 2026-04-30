#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
LATEST_ACCEPTANCE_FILE = "docs/deployment/admin_v1_1_58_acceptance_20260430.md"
LATEST_RELEASE_TAG = "v1.1.58"


@dataclass(frozen=True)
class RequiredMarkdown:
    path: str
    required_text: tuple[str, ...] = ()
    min_bytes: int = 100


@dataclass(frozen=True)
class RequiredPdf:
    path: str
    min_bytes: int = 1024


REQUIRED_MARKDOWN: tuple[RequiredMarkdown, ...] = (
    RequiredMarkdown(
        "docs/deployment/admin_v1_handoff.md",
        required_text=(
            "Admin v1.1.58 Acceptance Record 2026-04-30",
            LATEST_ACCEPTANCE_FILE.rsplit("/", 1)[-1],
            "Sales Pack 인덱스",
        ),
    ),
    RequiredMarkdown(
        LATEST_ACCEPTANCE_FILE,
        required_text=(
            LATEST_RELEASE_TAG,
            "CD result | `success`",
            "Report Workflow ERP smoke",
            "ready for continued production use | `YES`",
        ),
    ),
    RequiredMarkdown(
        "docs/sales/company_delivery_guide.md",
        required_text=(
            "키 전달은 별도 안전 채널로 분리합니다.",
            "절대 같이 보내지 말아야 하는 것",
        ),
    ),
    RequiredMarkdown("docs/sales/README.md", required_text=("python3 scripts/build_sales_pack.py",)),
    RequiredMarkdown("docs/sales/meeting_onepager.md"),
    RequiredMarkdown("docs/sales/executive_intro.md"),
    RequiredMarkdown("docs/sales/notebooklm_comparison.md"),
    RequiredMarkdown("docs/sales/internal_deployment_brief.md"),
    RequiredMarkdown("docs/security_policy.md"),
    RequiredMarkdown("docs/v1_completion_snapshot.md"),
)

REQUIRED_PDFS: tuple[RequiredPdf, ...] = (
    RequiredPdf("decisiondoc_ai_meeting_onepager_ko.pdf"),
    RequiredPdf("decisiondoc_ai_executive_intro_ko.pdf"),
    RequiredPdf("decisiondoc_ai_notebooklm_comparison_ko.pdf"),
    RequiredPdf("decisiondoc_ai_internal_deployment_brief_ko.pdf"),
    RequiredPdf("decisiondoc_ai_company_delivery_guide_ko.pdf"),
)

FORBIDDEN_DELIVERY_TEXT: tuple[str, ...] = (
    "OPENAI_API_KEY=sk-",
    "DECISIONDOC_API_KEYS=",
    "DECISIONDOC_OPS_KEY=",
    "-----BEGIN OPENSSH PRIVATE KEY-----",
    "-----BEGIN RSA PRIVATE KEY-----",
)


def _git_stdout(repo_root: Path, args: Sequence[str]) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def build_source_metadata(repo_root: Path) -> dict[str, object]:
    source_commit = _git_stdout(repo_root, ["rev-parse", "HEAD"])
    source_describe = _git_stdout(repo_root, ["describe", "--tags", "--always", "--dirty", "--abbrev=12"])
    source_exact_tag = _git_stdout(repo_root, ["describe", "--tags", "--exact-match", "HEAD"])
    exact_release_tag = bool(source_exact_tag and source_exact_tag == LATEST_RELEASE_TAG)
    dirty = source_describe.endswith("-dirty")
    warnings: list[str] = []
    if not source_commit:
        warnings.append("git source metadata is unavailable")
    elif not exact_release_tag:
        warnings.append(
            "source commit is not exactly tagged with "
            f"{LATEST_RELEASE_TAG}; source_describe={source_describe or source_commit[:12]}"
        )
    if dirty:
        warnings.append("source working tree is dirty")
    return {
        "source_commit": source_commit,
        "source_describe": source_describe,
        "source_exact_tag": source_exact_tag,
        "expected_release_tag": LATEST_RELEASE_TAG,
        "exact_release_tag": exact_release_tag,
        "dirty": dirty,
        "warnings": warnings,
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _display_path(repo_root: Path, path: Path) -> str:
    return str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path)


def _file_record(repo_root: Path, path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "path": _display_path(repo_root, path),
            "exists": False,
            "is_file": False,
            "size_bytes": 0,
        }
    return {
        "path": _display_path(repo_root, path),
        "exists": True,
        "is_file": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
    }


def _check_markdown(repo_root: Path) -> list[str]:
    errors: list[str] = []
    for item in REQUIRED_MARKDOWN:
        path = repo_root / item.path
        if not path.exists():
            errors.append(f"missing required document: {item.path}")
            continue
        if not path.is_file():
            errors.append(f"required document is not a file: {item.path}")
            continue
        size = path.stat().st_size
        if size < item.min_bytes:
            errors.append(f"required document is too small: {item.path} ({size} bytes)")
            continue
        text = _read_text(path)
        for required in item.required_text:
            if required not in text:
                errors.append(f"required text not found in {item.path}: {required}")
        for forbidden in FORBIDDEN_DELIVERY_TEXT:
            if forbidden in text:
                errors.append(f"forbidden secret-like text found in {item.path}: {forbidden}")
    return errors


def _check_pdfs(repo_root: Path, *, output_dir: Path, skip_pdf_check: bool) -> list[str]:
    if skip_pdf_check:
        return []
    errors: list[str] = []
    resolved_output_dir = output_dir if output_dir.is_absolute() else repo_root / output_dir
    for item in REQUIRED_PDFS:
        path = resolved_output_dir / item.path
        display_path = _display_path(repo_root, path)
        if not path.exists():
            errors.append(f"missing required PDF: {display_path}")
            continue
        if not path.is_file():
            errors.append(f"required PDF is not a file: {display_path}")
            continue
        size = path.stat().st_size
        if size < item.min_bytes:
            errors.append(f"required PDF is too small: {display_path} ({size} bytes)")
            continue
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                errors.append(f"required PDF does not start with %PDF-: {display_path}")
    return errors


def _build_manifest(repo_root: Path, *, output_dir: Path, skip_pdf_check: bool) -> dict[str, object]:
    resolved_output_dir = output_dir if output_dir.is_absolute() else repo_root / output_dir
    markdown = [_file_record(repo_root, repo_root / item.path) for item in REQUIRED_MARKDOWN]
    pdfs = [] if skip_pdf_check else [_file_record(repo_root, resolved_output_dir / item.path) for item in REQUIRED_PDFS]
    return {
        "markdown": markdown,
        "pdfs": pdfs,
    }


def check_company_handoff_ready(
    *,
    repo_root: Path = REPO_ROOT,
    output_dir: Path = Path("output/pdf"),
    skip_pdf_check: bool = False,
) -> dict[str, object]:
    resolved_repo = repo_root.expanduser().resolve()
    errors = [
        *_check_markdown(resolved_repo),
        *_check_pdfs(resolved_repo, output_dir=output_dir, skip_pdf_check=skip_pdf_check),
    ]
    return {
        "ok": not errors,
        "errors": errors,
        "repo_root": str(resolved_repo),
        "output_dir": str(output_dir),
        "release_tag": LATEST_RELEASE_TAG,
        "acceptance_file": LATEST_ACCEPTANCE_FILE,
        "source": build_source_metadata(resolved_repo),
        "pdf_check": not skip_pdf_check,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "manifest": _build_manifest(resolved_repo, output_dir=output_dir, skip_pdf_check=skip_pdf_check),
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_reports(*, result: dict[str, object], report_file: Path | None, report_dir: Path | None) -> list[str]:
    written: list[str] = []
    if report_file is not None:
        _write_json(report_file, result)
        written.append(str(report_file))
    if report_dir is not None:
        generated_at = str(result["generated_at"]).replace("-", "").replace(":", "").replace("Z", "Z")
        timestamped = report_dir / f"company-handoff-readiness-{generated_at}.json"
        latest = report_dir / "latest.json"
        _write_json(timestamped, result)
        _write_json(latest, result)
        written.extend([str(timestamped), str(latest)])
    return written


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check whether the DecisionDoc AI company handoff package is ready to send.",
    )
    parser.add_argument("--repo", type=Path, default=REPO_ROOT, help=f"Repository root. Default: {REPO_ROOT}")
    parser.add_argument("--output-dir", type=Path, default=Path("output/pdf"), help="Directory containing sales PDFs.")
    parser.add_argument(
        "--skip-pdf-check",
        action="store_true",
        help="Only validate markdown handoff material. Use this before rebuilding the PDF pack.",
    )
    parser.add_argument("--report-file", type=Path, help="Optional JSON report file to write.")
    parser.add_argument("--report-dir", type=Path, help="Optional directory for timestamped and latest JSON reports.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = check_company_handoff_ready(
        repo_root=args.repo,
        output_dir=args.output_dir,
        skip_pdf_check=args.skip_pdf_check,
    )
    written_reports = _write_reports(result=result, report_file=args.report_file, report_dir=args.report_dir)
    if result["ok"]:
        print("PASS company handoff readiness check passed")
        print(f"release_tag={result['release_tag']}")
        print(f"acceptance_file={result['acceptance_file']}")
        source = result["source"]
        if isinstance(source, dict):
            print(f"source_describe={source.get('source_describe') or '-'}")
            print(f"exact_release_tag={str(source.get('exact_release_tag')).lower()}")
        print(f"pdf_check={'enabled' if result['pdf_check'] else 'skipped'}")
        for report in written_reports:
            print(f"report_written={report}")
        print("next_action=send sales PDFs, handoff docs, and separate secret channel details")
        return 0

    print("FAIL company handoff readiness check failed")
    for error in result["errors"]:
        print(f"ERROR {error}")
    for report in written_reports:
        print(f"report_written={report}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
