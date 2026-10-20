"""Convert Markdown drafts to submission formats in-process, without the server.

Uses the same converters as the web app with ``package_cover=False``: no DecisionDoc cover
or per-document cards, since a proposal or report submitted to an agency carries only its
own body (and must not show tool names under blind evaluation).
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from app.public_sector.readers import ReaderError

EXPORT_FORMATS = ("hwpx", "docx", "pdf")
_UNSAFE_NAME_RE = re.compile(r"[\\/:*?\"<>|\x00-\x1f]+")


def _options() -> Any:
    # Imported here: the app.schemas package pulls in auth modules that this package avoids.
    from app.schemas.visual_assets import GovDocOptions

    return GovDocOptions(package_cover=False)


def _docs(paths: list[str | Path]) -> list[dict[str, str]]:
    docs = []
    for item in map(Path, paths):
        if item.suffix.lower() != ".md" or not item.is_file():
            raise ReaderError(f"Markdown 원고만 변환한다: {item}")
        docs.append({"doc_type": item.stem, "markdown": item.read_text(encoding="utf-8")})
    return docs


def _convert(fmt: str, docs: list[dict[str, str]], title: str) -> bytes:
    if fmt == "hwpx":
        from app.services.hwp_service import build_hwp

        return build_hwp(docs, title=title, gov_options=_options())
    if fmt == "docx":
        from app.services.docx_service import build_docx

        return build_docx(docs, title=title, gov_options=_options())
    from app.services.pdf_service import build_pdf

    return asyncio.run(build_pdf(docs, title=title, gov_options=_options()))


def export_drafts(paths: list[str | Path], formats: list[str], title: str, out_dir: str | Path, stem: str = "") -> list[Path]:
    """Write one file per format combining the drafts in order; returns the written paths."""
    unknown = sorted(set(formats) - set(EXPORT_FORMATS))
    if unknown:
        raise ReaderError(f"지원하지 않는 형식: {', '.join(unknown)} (지원: {', '.join(EXPORT_FORMATS)})")
    docs = _docs(paths)
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    name = _UNSAFE_NAME_RE.sub("_", stem or title).strip(" ._") or "document"
    written = []
    for fmt in formats:
        path = target / f"{name}.{fmt}"
        path.write_bytes(_convert(fmt, docs, title))
        written.append(path)
    return written
