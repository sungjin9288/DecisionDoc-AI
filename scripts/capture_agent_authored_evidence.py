#!/usr/bin/env python3
"""Reproduce the local session-authored document path and record evidence.

Replays a tracked, session-authored ``bundle.json`` against an in-process
DecisionDoc app with a temporary data directory, then records what the
platform did with it: brief, validation, rendering and five export formats.
No model provider is called, ``.env`` is not read, and the exported binaries
stay in a temporary directory; only Markdown, preview images and a receipt
are written to the repository. Preview images need PyMuPDF (and LibreOffice
``soffice`` for PPTX); ``--no-previews`` runs with the declared dependencies.

    python3 scripts/capture_agent_authored_evidence.py
    python3 scripts/capture_agent_authored_evidence.py --check-only
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.decisiondoc_author import API_KEY_HEADER, submit, write_brief  # noqa: E402

SCHEMA_VERSION = "decisiondoc.agent_authored_evidence.v1"
SAMPLE_DIR = REPO_ROOT / "docs" / "samples" / "agent_authored_local"
DEFAULT_MARKDOWN_DIR = REPO_ROOT / "evidence" / "generated-samples" / "agent-authored"
DEFAULT_SCREENSHOT_DIR = REPO_ROOT / "evidence" / "screenshots"
DEFAULT_RECEIPT_PATH = REPO_ROOT / "evidence" / "cli-logs" / "agent_authored_evidence.json"
FORMATS = ("docx", "pdf", "pptx", "hwpx", "xlsx")
EVIDENCE_API_KEY = "agent-authored-evidence-key"
# Authored strings shorter than this are too generic to prove they survived.
PROBE_MIN_CHARS = 20
PREVIEW_DPI = 110
THUMBNAIL_WIDTH = 520
EXCLUDED_EXTERNAL_ACTIONS = (
    "provider API execution",
    "G2B live API execution",
    "AWS runtime execution",
    "dataset upload",
    "training execution",
    "model promotion",
    "external submission",
)
APP_ENV = {
    "DECISIONDOC_PROVIDER": "mock",
    "DECISIONDOC_PROVIDER_GENERATION": "",
    "DECISIONDOC_PROVIDER_ATTACHMENT": "",
    "DECISIONDOC_PROVIDER_VISUAL": "",
    "DECISIONDOC_ENV": "dev",
    "DECISIONDOC_MAINTENANCE": "0",
    "DECISIONDOC_STORAGE": "local",
    "DECISIONDOC_CACHE_ENABLED": "0",
    "DECISIONDOC_SEARCH_ENABLED": "0",
    "DECISIONDOC_API_KEYS": EVIDENCE_API_KEY,
    "JWT_SECRET_KEY": "agent-authored-evidence-secret-32chars!",
}
REMOVED_ENV = ("DECISIONDOC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "G2B_API_KEY")


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


@contextmanager
def _isolated_environment(data_dir: Path) -> Iterator[None]:
    saved = dict(os.environ)
    try:
        for name in REMOVED_ENV:
            os.environ.pop(name, None)
        os.environ.update({**APP_ENV, "DATA_DIR": str(data_dir)})
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def _string_leaves(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _string_leaves(item)


def authored_probes(bundle: dict[str, Any]) -> list[str]:
    """Distinct authored sentences long enough to identify the session's own text."""
    return sorted({text.strip() for text in _string_leaves(bundle) if len(text.strip()) >= PROBE_MIN_CHARS})


def _save_png(image: Any, path: Path) -> None:
    # A 256-colour palette keeps rendered text legible at a fraction of the size.
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").quantize(colors=256).save(path, optimize=True)


def _thumbnail_sheet(images: list[Any], path: Path, *, columns: int = 3) -> None:
    from PIL import Image

    thumbs = []
    for image in images:
        ratio = THUMBNAIL_WIDTH / image.width
        thumbs.append(image.resize((THUMBNAIL_WIDTH, round(image.height * ratio))))
    gap = 16
    cell_height = max(thumb.height for thumb in thumbs)
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (columns * THUMBNAIL_WIDTH + (columns + 1) * gap, rows * cell_height + (rows + 1) * gap),
        "#e5e7eb",
    )
    for index, thumb in enumerate(thumbs):
        row, column = divmod(index, columns)
        sheet.paste(thumb, (gap + column * (THUMBNAIL_WIDTH + gap), gap + row * (cell_height + gap)))
    _save_png(sheet, path)


def _pdf_page_images(pdf_path: Path, *, limit: int | None = None) -> list[Any]:
    import fitz
    from PIL import Image

    fitz.TOOLS.mupdf_display_errors(False)
    images = []
    with fitz.open(pdf_path) as document:
        for page in list(document)[:limit]:
            pixmap = page.get_pixmap(dpi=PREVIEW_DPI)
            images.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
    return images


def _pdf_page_count(pdf_path: Path) -> int:
    # pdfplumber is a declared dependency; PyMuPDF is only needed for previews.
    try:
        import pdfplumber
    except ImportError:
        import fitz

        with fitz.open(pdf_path) as document:
            return document.page_count
    with pdfplumber.open(pdf_path) as document:
        return len(document.pages)


def _pptx_slide_count(pptx_path: Path) -> int:
    from pptx import Presentation

    return len(Presentation(str(pptx_path)).slides)


def _render_previews(exported: dict[str, Path], screenshot_dir: Path, scratch: Path) -> dict[str, Any]:
    previews: dict[str, Any] = {}
    pdf_page1 = screenshot_dir / "agent-authored-pdf-page1.png"
    _save_png(_pdf_page_images(exported["pdf"], limit=1)[0], pdf_page1)
    previews["pdf_page1"] = _relative(pdf_page1)

    pdf_pages = screenshot_dir / "agent-authored-pdf-pages.png"
    _thumbnail_sheet(_pdf_page_images(exported["pdf"], limit=6), pdf_pages)
    previews["pdf_pages"] = _relative(pdf_pages)

    soffice = shutil.which("soffice")
    if soffice is None:
        previews["pptx_slides"] = "skipped: soffice not found"
        return previews
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(scratch), str(exported["pptx"])],
        check=True,
        capture_output=True,
        timeout=180,
    )
    slides_pdf = scratch / f"{exported['pptx'].stem}.pdf"
    pptx_slides = screenshot_dir / "agent-authored-pptx-slides.png"
    _thumbnail_sheet(_pdf_page_images(slides_pdf), pptx_slides)
    previews["pptx_slides"] = _relative(pptx_slides)
    return previews


def capture_agent_authored_evidence(
    *,
    sample_dir: Path = SAMPLE_DIR,
    markdown_dir: Path = DEFAULT_MARKDOWN_DIR,
    screenshot_dir: Path = DEFAULT_SCREENSHOT_DIR,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
    previews: bool = True,
) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    sample = json.loads((sample_dir / "input.json").read_text(encoding="utf-8"))
    bundle = json.loads((sample_dir / "bundle.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="decisiondoc-agent-evidence-") as temp:
        scratch = Path(temp)
        work_dir = scratch / "work"
        with _isolated_environment(scratch / "data"), mock.patch("app.main.load_dotenv", lambda *a, **k: False):
            from app.main import create_app

            with TestClient(create_app(), headers={API_KEY_HEADER: EVIDENCE_API_KEY}) as client:
                write_brief(client, sample, work_dir)
                shutil.copyfile(sample_dir / "bundle.json", work_dir / "bundle.json")
                summary = submit(client, work_dir, list(FORMATS))

        files = [Path(item) for item in summary["files"]]
        markdown_files = {path.stem: path for path in files if path.suffix == ".md"}
        exported = {path.suffix.lstrip("."): path for path in files if path.suffix != ".md"}
        # Authored slide notes render into the PPTX outline rather than the Markdown body.
        response = json.loads((work_dir / "response.json").read_text(encoding="utf-8"))
        outlines = [doc.get("slide_outline") or [] for doc in response["docs"]]
        combined = "\n".join(
            [path.read_text(encoding="utf-8") for path in markdown_files.values()] + list(_string_leaves(outlines))
        )
        probes = authored_probes(bundle)
        missing = [text for text in probes if text not in combined]

        markdown_dir.mkdir(parents=True, exist_ok=True)
        for doc_type, path in sorted(markdown_files.items()):
            shutil.copyfile(path, markdown_dir / f"{doc_type}.md")
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "scope": "in-process app, temporary data directory; the session-authored bundle is replayed, not regenerated",
            "inputs": {
                "request": _relative(sample_dir / "input.json"),
                "authored_bundle": _relative(sample_dir / "bundle.json"),
                "authored_by": "Claude Code session following .claude/skills/decisiondoc-authoring/SKILL.md (2026-10-07)",
            },
            "server_calls": ["POST /generate/authoring-brief", "POST /generate/authored", "POST /generate/export-edited"],
            "bundle_type": sample["bundle_type"],
            "provider": summary["provider"],
            "doc_types": sorted(markdown_files),
            "markdown": [_relative(markdown_dir / f"{doc_type}.md") for doc_type in sorted(markdown_files)],
            "authored_text": {
                "checked_in": "rendered Markdown and slide outline",
                "probes": len(probes),
                "survived": len(probes) - len(missing),
                "missing": missing,
            },
            "exports": {
                "docx": {"bytes": exported["docx"].stat().st_size},
                "pdf": {"bytes": exported["pdf"].stat().st_size, "pages": _pdf_page_count(exported["pdf"])},
                "pptx": {"bytes": exported["pptx"].stat().st_size, "slides": _pptx_slide_count(exported["pptx"])},
                "hwpx": {"bytes": exported["hwpx"].stat().st_size},
                "xlsx": {"bytes": exported["xlsx"].stat().st_size},
            },
            "exports_tracked": False,
            "previews": _render_previews(exported, screenshot_dir, scratch) if previews else {},
            "external_actions_excluded": list(EXCLUDED_EXTERNAL_ACTIONS),
        }
    validate_receipt(receipt)
    _write_text_atomic(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def validate_receipt(receipt: dict[str, Any]) -> None:
    """Reject a receipt that does not show the authored path end to end."""
    if receipt.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected schema_version")
    if receipt.get("provider") != "agent_authored":
        raise ValueError(f"provider must be agent_authored, got {receipt.get('provider')!r}")
    authored = receipt.get("authored_text", {})
    if not authored.get("probes") or authored.get("missing"):
        raise ValueError(f"authored text did not survive: {authored.get('missing')}")
    exports = receipt.get("exports", {})
    if sorted(exports) != sorted(FORMATS) or any(item.get("bytes", 0) <= 0 for item in exports.values()):
        raise ValueError("every export format must produce a non-empty file")
    if receipt.get("exports_tracked") is not False:
        raise ValueError("exported binaries must not be tracked")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--receipt-path", default=str(DEFAULT_RECEIPT_PATH))
    parser.add_argument("--markdown-dir", default=str(DEFAULT_MARKDOWN_DIR))
    parser.add_argument("--screenshot-dir", default=str(DEFAULT_SCREENSHOT_DIR))
    parser.add_argument("--no-previews", action="store_true", help="Skip PDF/PPTX preview images.")
    parser.add_argument("--check-only", action="store_true", help="Validate an existing receipt.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    receipt_path = Path(args.receipt_path)
    if args.check_only:
        validate_receipt(json.loads(receipt_path.read_text(encoding="utf-8")))
        print(f"receipt ok: {receipt_path}")
        return 0
    receipt = capture_agent_authored_evidence(
        markdown_dir=Path(args.markdown_dir),
        screenshot_dir=Path(args.screenshot_dir),
        receipt_path=receipt_path,
        previews=not args.no_previews,
    )
    print(json.dumps({key: receipt[key] for key in ("provider", "authored_text", "exports", "previews")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
