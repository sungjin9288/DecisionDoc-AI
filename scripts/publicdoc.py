#!/usr/bin/env python3
"""Public-sector proposal and report checks for a local Claude Code or Codex session.

    python3 scripts/publicdoc.py text rfp.hwpx --out work/rfp.txt
    python3 scripts/publicdoc.py scan-requirements rfp.hwpx --out work/candidates.json
    python3 scripts/publicdoc.py check-profile work/rfp_profile.json
    python3 scripts/publicdoc.py trace work/rfp_profile.json draft.docx --table work/대비표.md
    python3 scripts/publicdoc.py crosswalk work/rfp_profile.json draft.md --pdf proposal.pdf --table work/조견표.md
    python3 scripts/publicdoc.py notation draft.md --kind submission
    python3 scripts/publicdoc.py report-skeleton --type interim_report --profile work/rfp_profile.json --out work/중간보고서.md
    python3 scripts/publicdoc.py report-check work/중간보고서.md --type interim_report --profile work/rfp_profile.json
    python3 scripts/publicdoc.py submission work/rfp_profile.json work/제출/ --identifier "(주)회사명"

Exit codes: 0 passed, 1 findings to fix, 2 unreadable input. Nothing is sent anywhere.
See .claude/skills/public-sector-documents/SKILL.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pydantic import ValidationError  # noqa: E402

from app.public_sector.crosswalk import build_crosswalk, crosswalk_table_markdown  # noqa: E402
from app.public_sector.models import load_profile  # noqa: E402
from app.public_sector.notation import check_notation  # noqa: E402
from app.public_sector.profile_check import check_profile  # noqa: E402
from app.public_sector.readers import ReaderError, read_document  # noqa: E402
from app.public_sector.report_types import REPORT_TYPES  # noqa: E402
from app.public_sector.reports import check_report, report_skeleton  # noqa: E402
from app.public_sector.submission import check_submission  # noqa: E402
from app.public_sector.requirements import scan_requirements, trace_requirements, trace_table_markdown  # noqa: E402

EXIT_PASSED = 0
EXIT_FINDINGS = 1
EXIT_INVALID_INPUT = 2


def _emit(payload: Any, out: str | None) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"written: {out}")
    else:
        sys.stdout.write(text)


def _located_text(path: str) -> str:
    document = read_document(path)
    lines = []
    page = None
    for block in document.blocks:
        if block.page is not None and block.page != page:
            page = block.page
            lines.append(f"\n[p.{page}]")
        prefix = "#" * block.heading_level + " " if block.heading_level else ""
        lines.append(prefix + block.text)
    return "\n".join(lines).lstrip("\n") + "\n"


def _cmd_text(args: argparse.Namespace) -> int:
    _emit(_located_text(args.file), args.out)
    return EXIT_PASSED


def _cmd_scan(args: argparse.Namespace) -> int:
    _emit(scan_requirements(read_document(args.file), prefixes=args.prefix), args.out)
    return EXIT_PASSED


def _cmd_check_profile(args: argparse.Namespace) -> int:
    report = check_profile(load_profile(args.profile))
    _emit(report, args.out)
    return EXIT_PASSED if report["passed"] else EXIT_FINDINGS


def _cmd_trace(args: argparse.Namespace) -> int:
    report = trace_requirements(load_profile(args.profile), read_document(args.draft))
    if args.table:
        _emit(trace_table_markdown(report), args.table)
    _emit(report, args.out)
    return EXIT_PASSED if report["passed"] else EXIT_FINDINGS


def _cmd_crosswalk(args: argparse.Namespace) -> int:
    pdf = read_document(args.pdf) if args.pdf else None
    report = build_crosswalk(load_profile(args.profile), read_document(args.draft), pdf)
    if args.table:
        _emit(crosswalk_table_markdown(report), args.table)
    _emit(report, args.out)
    return EXIT_PASSED if report["passed"] else EXIT_FINDINGS


def _cmd_notation(args: argparse.Namespace) -> int:
    report = check_notation(read_document(args.file), kind=args.kind)
    _emit(report, args.out)
    return EXIT_PASSED if report["passed"] else EXIT_FINDINGS


def _cmd_report_types(args: argparse.Namespace) -> int:
    _emit([
        {
            "id": report.id,
            "name": report.name,
            "sections": [{"title": s.title, "basis": s.basis} for s in report.sections],
            "fulfilment_statuses": list(report.statuses),
            "note": report.note,
        }
        for report in REPORT_TYPES.values()
    ], args.out)
    return EXIT_PASSED


def _cmd_report_skeleton(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile) if args.profile else None
    _emit(report_skeleton(REPORT_TYPES[args.type], profile), args.out)
    return EXIT_PASSED


def _cmd_report_check(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile) if args.profile else None
    report = check_report(read_document(args.file), REPORT_TYPES[args.type], profile)
    _emit(report, args.out)
    return EXIT_PASSED if report["passed"] else EXIT_FINDINGS


def _cmd_submission(args: argparse.Namespace) -> int:
    report = check_submission(load_profile(args.profile), args.files, args.identifier)
    _emit(report, args.out)
    return EXIT_PASSED if report["passed"] else EXIT_FINDINGS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Public-sector proposal and report checks.")
    commands = parser.add_subparsers(dest="command", required=True)

    text = commands.add_parser("text", help="Print the full text with page and heading markers.")
    text.add_argument("file")
    text.add_argument("--out")
    text.set_defaults(handler=_cmd_text)

    scan = commands.add_parser("scan-requirements", help="List requirement ID candidates in an RFP.")
    scan.add_argument("file")
    scan.add_argument("--prefix", action="append", help="Only these ID prefixes (repeatable), e.g. SFR.")
    scan.add_argument("--out")
    scan.set_defaults(handler=_cmd_scan)

    check = commands.add_parser("check-profile", help="Validate an RFP profile and list unknown conditions.")
    check.add_argument("profile")
    check.add_argument("--out")
    check.set_defaults(handler=_cmd_check_profile)

    notation = commands.add_parser("notation", help="Check official notation: item symbols, dates, times, amounts, end mark.")
    notation.add_argument("file")
    notation.add_argument(
        "--kind", choices=("submission", "agency"), default="submission",
        help="agency: a document an administrative agency issues (rules bind); submission: a proposal or report (advice).",
    )
    notation.add_argument("--out")
    notation.set_defaults(handler=_cmd_notation)

    types = commands.add_parser("report-types", help="List stage report types, their sections and basis.")
    types.add_argument("--out")
    types.set_defaults(handler=_cmd_report_types)

    skeleton = commands.add_parser("report-skeleton", help="Write a report outline with the fulfilment table.")
    skeleton.add_argument("--type", required=True, choices=sorted(REPORT_TYPES))
    skeleton.add_argument("--profile", help="RFP profile with tasks and commitments.")
    skeleton.add_argument("--out")
    skeleton.set_defaults(handler=_cmd_report_skeleton)

    report_check = commands.add_parser("report-check", help="Check a stage report's sections and fulfilment table.")
    report_check.add_argument("file")
    report_check.add_argument("--type", required=True, choices=sorted(REPORT_TYPES))
    report_check.add_argument("--profile", help="RFP profile with tasks and commitments.")
    report_check.add_argument("--out")
    report_check.set_defaults(handler=_cmd_report_check)

    submission = commands.add_parser("submission", help="Check files to submit against the RFP conditions.")
    submission.add_argument("profile")
    submission.add_argument("files", nargs="+", help="Files or a folder to submit.")
    submission.add_argument(
        "--identifier", action="append", default=[],
        help="Company name, abbreviation or other identifier that must not appear under blind evaluation (repeatable).",
    )
    submission.add_argument("--out")
    submission.set_defaults(handler=_cmd_submission)

    for name, handler, help_text, table_help in (
        ("trace", _cmd_trace, "Trace profile requirements in a draft.", "Write the 요구사항 대비표 Markdown here."),
        ("crosswalk", _cmd_crosswalk, "Map evaluation items to draft headings and PDF pages.", "Write the 조견표 Markdown here."),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("profile")
        command.add_argument("draft", help="Draft as .md, .txt, .docx, .hwpx or .pdf")
        command.add_argument("--table", help=table_help)
        command.add_argument("--out", help="Write the JSON report here instead of stdout.")
        command.set_defaults(handler=handler)
    commands.choices["crosswalk"].add_argument(
        "--pdf", help="Submitted PDF; pages are confirmed against the draft's structure."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ReaderError, ValidationError, OSError, ValueError) as exc:
        print(f"입력을 읽을 수 없습니다: {exc}", file=sys.stderr)
        return EXIT_INVALID_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
