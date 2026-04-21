#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Sequence


ENTRY_PATTERN = re.compile(r"^### UAT 기록 — (?P<scenario>.+)$", re.MULTILINE)
FIELD_PATTERN = re.compile(r"^- (?P<key>[^:]+): (?P<value>.*)$")
SUBFIELD_PATTERN = re.compile(r"^  - (?P<key>[^:]+): (?P<value>.*)$")


def parse_uat_session(session_file: Path) -> dict:
    resolved = Path(session_file).expanduser()
    if not resolved.exists():
        raise SystemExit(f"Session file not found: {resolved}")

    content = resolved.read_text(encoding="utf-8")
    entry_matches = list(ENTRY_PATTERN.finditer(content))
    entries: list[dict[str, str]] = []

    for index, match in enumerate(entry_matches):
        start = match.start()
        end = entry_matches[index + 1].start() if index + 1 < len(entry_matches) else len(content)
        block = content[start:end]
        entry = {
            "scenario": match.group("scenario").strip(),
            "recorded_at": "-",
            "owner": "-",
            "bundle": "-",
            "generation_status": "-",
            "export_status": "-",
            "visual_asset_status": "-",
            "history_restore_status": "-",
            "issues": "-",
            "follow_up": "-",
        }

        for line in block.splitlines():
            field_match = FIELD_PATTERN.match(line)
            if field_match:
                key = field_match.group("key").strip()
                value = field_match.group("value").strip()
                if key == "일시":
                    entry["recorded_at"] = value or "-"
                elif key == "담당자":
                    entry["owner"] = value or "-"
                elif key == "사용 번들":
                    entry["bundle"] = value or "-"
                elif key == "실패/이슈":
                    entry["issues"] = value or "-"
                elif key == "후속 조치 필요 여부":
                    entry["follow_up"] = value or "-"
                continue

            subfield_match = SUBFIELD_PATTERN.match(line)
            if not subfield_match:
                continue
            key = subfield_match.group("key").strip()
            value = subfield_match.group("value").strip()
            if key == "생성 성공/실패":
                entry["generation_status"] = value or "-"
            elif key == "export 성공/실패":
                entry["export_status"] = value or "-"
            elif key == "visual asset 일치 여부":
                entry["visual_asset_status"] = value or "-"
            elif key == "history 복원 여부":
                entry["history_restore_status"] = value or "-"

        entries.append(entry)

    session_title = "-"
    for line in content.splitlines():
        if line.startswith("# UAT Session — "):
            session_title = line.removeprefix("# UAT Session — ").strip() or "-"
            break

    return {
        "session_file": str(resolved),
        "session_title": session_title,
        "entry_count": len(entries),
        "entries": entries,
    }


def render_uat_session_summary(payload: dict, *, limit: int) -> str:
    lines = [
        f"Session file: {payload.get('session_file', '-')}",
        f"Session title: {payload.get('session_title', '-')}",
        f"Recorded entries: {payload.get('entry_count', 0)}",
    ]
    entries = payload.get("entries", [])
    if not entries:
        lines.append("Latest entries: none")
        return "\n".join(lines)

    lines.append("Latest entries:")
    for entry in reversed(entries[-limit:]):
        lines.append(
            "  - "
            f"{entry.get('recorded_at', '-')} | "
            f"{entry.get('scenario', '-')} | "
            f"owner={entry.get('owner', '-')} | "
            f"generation={entry.get('generation_status', '-')} | "
            f"export={entry.get('export_status', '-')} | "
            f"follow_up={entry.get('follow_up', '-')}"
        )
    return "\n".join(lines)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read a UAT session markdown file and print a compact summary.",
    )
    parser.add_argument("--session-file", required=True, help="Existing UAT session markdown file path.")
    parser.add_argument("--limit", type=int, default=5, help="Number of recent entries to print.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload = parse_uat_session(Path(args.session_file))
    print(render_uat_session_summary(payload, limit=max(int(args.limit), 1)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
