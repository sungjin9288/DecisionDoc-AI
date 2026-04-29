#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
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


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
        display_path = str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path)
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
        "pdf_check": not skip_pdf_check,
    }


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    result = check_company_handoff_ready(
        repo_root=args.repo,
        output_dir=args.output_dir,
        skip_pdf_check=args.skip_pdf_check,
    )
    if result["ok"]:
        print("PASS company handoff readiness check passed")
        print(f"release_tag={result['release_tag']}")
        print(f"acceptance_file={result['acceptance_file']}")
        print(f"pdf_check={'enabled' if result['pdf_check'] else 'skipped'}")
        print("next_action=send sales PDFs, handoff docs, and separate secret channel details")
        return 0

    print("FAIL company handoff readiness check failed")
    for error in result["errors"]:
        print(f"ERROR {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
