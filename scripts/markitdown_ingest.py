#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert source documents to Markdown using MarkItDown.",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="One or more input files to convert (pdf, docx, pptx, xlsx, etc).",
    )
    parser.add_argument(
        "--output-dir",
        default="data/ingest",
        help="Directory to write converted Markdown files (default: data/ingest).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files if they already exist.",
    )
    parser.add_argument(
        "--enable-plugins",
        action="store_true",
        help="Enable MarkItDown plugins if installed.",
    )
    return parser


def _load_markitdown():
    try:
        from markitdown import MarkItDown  # type: ignore
    except ImportError:
        print(
            "markitdown is not installed. Install optional deps with:\n"
            "  pip install 'markitdown[all]'\n"
            "or add it via requirements-integrations.txt.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return MarkItDown


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    MarkItDown = _load_markitdown()
    converter = MarkItDown(enable_plugins=args.enable_plugins)

    exit_code = 0
    for input_path in args.inputs:
        src = Path(input_path).expanduser().resolve()
        if not src.exists():
            print(f"[skip] missing input: {src}", file=sys.stderr)
            exit_code = 1
            continue

        out_path = output_dir / f"{src.stem}.md"
        if out_path.exists() and not args.overwrite:
            print(f"[skip] output exists (use --overwrite): {out_path}")
            continue

        try:
            result = converter.convert(str(src))
        except Exception as exc:  # pragma: no cover - CLI resilience
            print(f"[error] failed to convert {src}: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        out_path.write_text(result.text_content, encoding="utf-8")
        print(f"[ok] {src} -> {out_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
