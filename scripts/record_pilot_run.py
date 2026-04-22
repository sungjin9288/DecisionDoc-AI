#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Sequence
from uuid import uuid4


SECTION_MARKERS = {
    "run1": ("### Run 1. 기본 문서 생성", "### Run 2. 첨부 기반 문서 생성"),
    "run2": ("### Run 2. 첨부 기반 문서 생성", "## Escalation / Stop Log"),
    "incident": ("### Incident Notes", "## Pilot Close-Out"),
    "closeout": ("## Pilot Close-Out", None),
}


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def _parse_field_args(items: Sequence[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"Invalid --field value: {item}. Expected key=value.")
        key, value = item.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            raise SystemExit(f"Invalid --field value: {item}. Key must not be empty.")
        fields[normalized_key] = value.strip() or "-"
    if not fields:
        raise SystemExit("At least one --field key=value pair is required.")
    return fields


def _replace_section(text: str, *, start_marker: str, end_marker: str | None, updated_block: str) -> str:
    start = text.find(start_marker)
    if start == -1:
        raise SystemExit(f"Section not found: {start_marker}")
    end = text.find(end_marker, start) if end_marker else len(text)
    if end == -1:
        end = len(text)
    return text[:start] + updated_block + text[end:]


def _update_dash_fields(block: str, updates: dict[str, str]) -> str:
    remaining = dict(updates)
    updated_lines: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("- ") and ":" in stripped:
            key, _ = stripped[2:].split(":", 1)
            normalized_key = key.strip()
            if normalized_key in remaining:
                indent = line[: len(line) - len(line.lstrip(" "))]
                updated_lines.append(f"{indent}- {normalized_key}: {remaining.pop(normalized_key)}")
                continue
        updated_lines.append(line)

    if remaining:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")
        updated_lines.extend(f"- {key}: {value}" for key, value in remaining.items())

    suffix = "\n" if block.endswith("\n") else ""
    return "\n".join(updated_lines) + suffix


def record_pilot_run(*, run_sheet_file: Path, target: str, fields: dict[str, str]) -> Path:
    resolved = Path(run_sheet_file).expanduser()
    if not resolved.exists():
        raise SystemExit(f"Pilot run sheet not found: {resolved}")

    start_marker, end_marker = SECTION_MARKERS[target]
    existing = resolved.read_text(encoding="utf-8")

    start = existing.find(start_marker)
    if start == -1:
        raise SystemExit(f"Section not found: {start_marker}")
    end = existing.find(end_marker, start) if end_marker else len(existing)
    if end == -1:
        end = len(existing)

    block = existing[start:end]
    updated_block = _update_dash_fields(block, fields)
    rewritten = _replace_section(
        existing,
        start_marker=start_marker,
        end_marker=end_marker,
        updated_block=updated_block,
    )
    _write_text_atomic(resolved, rewritten)
    return resolved


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update a pilot run sheet section with key=value fields.",
    )
    parser.add_argument("--run-sheet-file", required=True, help="Existing pilot run sheet markdown file path.")
    parser.add_argument(
        "--target",
        required=True,
        choices=tuple(SECTION_MARKERS.keys()),
        help="Target section to update: run1, run2, incident, closeout.",
    )
    parser.add_argument(
        "--field",
        action="append",
        default=[],
        help="Field update in key=value form. Repeat for multiple fields.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    output_path = record_pilot_run(
        run_sheet_file=Path(args.run_sheet_file),
        target=args.target,
        fields=_parse_field_args(args.field),
    )
    print(f"Recorded pilot run updates: {output_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
