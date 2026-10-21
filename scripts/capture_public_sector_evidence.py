#!/usr/bin/env python3
"""Reproduce the public-sector proposal flow on synthetic material and record evidence.

Builds the synthetic RFP as HWPX and reads it back, checks the session-written condition
profile, then runs the proposal check, requirement trace, notation and submission checks on
a correct proposal and on one with planted mistakes. The correct proposal is exported
without the server and the cross-reference pages are confirmed against its PDF. Nothing
is called outside this process; exported binaries stay in a temporary directory.

    python3 scripts/capture_public_sector_evidence.py
    python3 scripts/capture_public_sector_evidence.py --check-only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.public_sector.crosswalk import build_crosswalk, crosswalk_table_markdown  # noqa: E402
from app.public_sector.export import export_drafts  # noqa: E402
from app.public_sector.models import load_profile  # noqa: E402
from app.public_sector.notation import check_notation  # noqa: E402
from app.public_sector.profile_check import check_profile  # noqa: E402
from app.public_sector.proposals import check_proposal  # noqa: E402
from app.public_sector.readers import metadata_text, read_document  # noqa: E402
from app.public_sector.requirements import scan_requirements, trace_requirements, trace_table_markdown  # noqa: E402
from app.public_sector.submission import check_submission  # noqa: E402

SCHEMA_VERSION = "decisiondoc.public_sector_evidence.v1"
SAMPLE_DIR = REPO_ROOT / "docs" / "samples" / "public_sector_local"
DEFAULT_MARKDOWN_DIR = REPO_ROOT / "evidence" / "generated-samples" / "public-sector"
DEFAULT_SCREENSHOT = REPO_ROOT / "evidence" / "screenshots" / "public-sector-proposal-page1.png"
DEFAULT_RECEIPT_PATH = REPO_ROOT / "evidence" / "cli-logs" / "public_sector_evidence.json"
TITLE = "[합성] 가상기관 문서관리시스템 고도화 사업 제안서"
BLIND_IDENTIFIERS = ["(주)가상솔루션"]
PLANTED = {
    "missing_requirement": "PSR-001",
    "unknown_requirement": "SFR-004",
    "identifier": "(주)가상솔루션",
    "date": "2026년 11월 2일",
}
PACKAGE_MARKERS = ("DecisionDoc AI Export", "완성형 문서 패키지", "DecisionDoc")
PREVIEW_DPI = 80
EXCLUDED_EXTERNAL_ACTIONS = (
    "provider API execution",
    "G2B live API execution",
    "AWS runtime execution",
    "proposal submission",
    "evaluation result claim",
)


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _read_rfp_as_hwpx(sample_dir: Path, scratch: Path) -> dict[str, Any]:
    from app.services.hwp_service import build_hwp

    rfp_path = scratch / "rfp.hwpx"
    markdown = (sample_dir / "rfp.md").read_text(encoding="utf-8")
    rfp_path.write_bytes(build_hwp([{"doc_type": "rfp", "markdown": markdown}], "[합성] 제안요청서"))
    scan = scan_requirements(read_document(rfp_path))
    return {
        "format": "hwpx",
        "requirement_candidates": [item["id"] for item in scan["candidates"]],
        "prefix_mentions": scan["prefix_mentions"],
    }


def _proposal_results(draft: Path, profile: Any, export_dir: Path) -> dict[str, Any]:
    document = read_document(draft)
    pdf = export_drafts([draft], ["pdf"], TITLE, export_dir, "정성제안서")[0]
    submission = check_submission(profile, [pdf], BLIND_IDENTIFIERS)
    proposal = check_proposal(document, profile)
    return {
        "document": document,
        "pdf": pdf,
        "proposal_check": {"passed": proposal["passed"], "counts": proposal["counts"]},
        "requirements": trace_requirements(profile, document),
        "notation": check_notation(document),
        "submission": {
            "passed": submission["passed"],
            "counts": submission["counts"],
            "codes": sorted({finding["code"] for finding in submission["findings"]}),
        },
    }


def _pdf_page_one_png(pdf: Path, path: Path) -> None:
    import fitz
    from PIL import Image

    fitz.TOOLS.mupdf_display_errors(False)
    with fitz.open(pdf) as document:
        pixmap = document[0].get_pixmap(dpi=PREVIEW_DPI)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.quantize(colors=256).save(path, optimize=True)


def capture_public_sector_evidence(
    *,
    sample_dir: Path = SAMPLE_DIR,
    markdown_dir: Path = DEFAULT_MARKDOWN_DIR,
    screenshot: Path = DEFAULT_SCREENSHOT,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
    previews: bool = True,
) -> dict[str, Any]:
    profile = load_profile(sample_dir / "rfp_profile.json")
    with tempfile.TemporaryDirectory(prefix="decisiondoc-public-sector-evidence-") as temp:
        scratch = Path(temp)
        rfp = _read_rfp_as_hwpx(sample_dir, scratch)
        clean = _proposal_results(sample_dir / "proposal.md", profile, scratch / "clean")
        flawed = _proposal_results(sample_dir / "proposal_flawed.md", profile, scratch / "flawed")
        crosswalk = build_crosswalk(profile, clean["document"], read_document(clean["pdf"]))
        exports = export_drafts([sample_dir / "proposal.md"], ["hwpx", "docx"], TITLE, scratch / "clean", "정성제안서")
        pdf_text = read_document(clean["pdf"]).full_text()
        pdf_metadata = metadata_text(clean["pdf"])

        markdown_dir.mkdir(parents=True, exist_ok=True)
        trace_table = markdown_dir / "requirement-trace-table.md"
        crosswalk_table = markdown_dir / "crosswalk-table.md"
        _write_text_atomic(trace_table, trace_table_markdown(clean["requirements"]))
        _write_text_atomic(crosswalk_table, crosswalk_table_markdown(crosswalk))
        if previews:
            _pdf_page_one_png(clean["pdf"], screenshot)

        flawed_dates = [f["message"] for f in flawed["notation"]["findings"] if f["rule"] == "date"]
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "scope": "in-process, temporary directory, synthetic RFP and proposals written by the session; nothing leaves the machine",
            "inputs": {name: _relative(sample_dir / name) for name in ("rfp.md", "rfp_profile.json", "proposal.md", "proposal_flawed.md")},
            "rfp": rfp,
            "profile_check": check_profile(profile)["counts"],
            "clean": {
                "proposal_check": clean["proposal_check"],
                "requirements": clean["requirements"]["summary"],
                "notation": clean["notation"]["counts"],
                "crosswalk": [
                    {"item": row["item"], "points": row["points"], "placements": [
                        {"heading": p["heading"], "page": p["page"], "basis": p["page_basis"]} for p in row["placements"]
                    ]}
                    for row in crosswalk["rows"]
                ],
                "submission": clean["submission"],
                "exports": {path.suffix.lstrip("."): path.stat().st_size for path in [clean["pdf"], *exports]},
                "pdf_package_cover": any(marker in pdf_text for marker in PACKAGE_MARKERS[:2]),
                "pdf_metadata_names_tool": "DecisionDoc" in pdf_metadata,
            },
            "flawed": {
                "planted": PLANTED,
                "detected": {
                    "missing_requirements": flawed["requirements"]["missing"],
                    "unknown_requirements": [item["id"] for item in flawed["requirements"]["unknown_ids"]],
                    "identifier_exposed": "identifier_exposed" in flawed["submission"]["codes"],
                    "date_findings": flawed_dates,
                },
                "proposal_check": flawed["proposal_check"],
            },
            "tables": [_relative(trace_table), _relative(crosswalk_table)],
            "preview": _relative(screenshot) if previews else None,
            "external_actions_excluded": list(EXCLUDED_EXTERNAL_ACTIONS),
        }
    validate_receipt(receipt)
    _write_text_atomic(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def validate_receipt(receipt: dict[str, Any]) -> None:
    """Reject a receipt where the correct proposal fails or a planted mistake goes unnoticed."""
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected schema_version")
    clean, flawed = receipt["clean"], receipt["flawed"]
    if not clean["proposal_check"]["passed"] or clean["requirements"]["missing"] or clean["notation"]["error"]:
        raise ValueError("the correct proposal must pass the proposal, requirement and notation checks")
    if not clean["submission"]["passed"] or clean["pdf_package_cover"] or clean["pdf_metadata_names_tool"]:
        raise ValueError("the correct proposal must pass submission without a DecisionDoc cover or tool name")
    unconfirmed = [p for row in clean["crosswalk"] for p in row["placements"] if p["basis"] != "본문 확인"]
    if unconfirmed:
        raise ValueError(f"cross-reference pages not confirmed by body text: {unconfirmed}")
    detected, planted = flawed["detected"], flawed["planted"]
    missed = [
        name for name, ok in (
            ("missing_requirement", planted["missing_requirement"] in detected["missing_requirements"]),
            ("unknown_requirement", planted["unknown_requirement"] in detected["unknown_requirements"]),
            ("identifier", detected["identifier_exposed"]),
            ("date", any(planted["date"] in message for message in detected["date_findings"])),
        ) if not ok
    ]
    if missed or flawed["proposal_check"]["passed"]:
        raise ValueError(f"planted mistakes were not detected: {missed}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--receipt-path", default=str(DEFAULT_RECEIPT_PATH))
    parser.add_argument("--markdown-dir", default=str(DEFAULT_MARKDOWN_DIR))
    parser.add_argument("--screenshot", default=str(DEFAULT_SCREENSHOT))
    parser.add_argument("--no-previews", action="store_true", help="Skip the PDF page preview (needs PyMuPDF).")
    parser.add_argument("--check-only", action="store_true", help="Validate an existing receipt.")
    args = parser.parse_args(argv)
    if args.check_only:
        validate_receipt(json.loads(Path(args.receipt_path).read_text(encoding="utf-8")))
        print(f"receipt ok: {args.receipt_path}")
        return 0
    receipt = capture_public_sector_evidence(
        markdown_dir=Path(args.markdown_dir),
        screenshot=Path(args.screenshot),
        receipt_path=Path(args.receipt_path),
        previews=not args.no_previews,
    )
    print(json.dumps({key: receipt[key] for key in ("rfp", "clean", "flawed")}, ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
