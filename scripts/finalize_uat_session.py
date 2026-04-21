#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_show_uat_module():
    module_path = REPO_ROOT / "scripts" / "show_uat_session.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_show_uat_session", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_show_uat = _load_show_uat_module()
parse_uat_session = _show_uat.parse_uat_session


def _is_success_text(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text or text == "-":
        return False
    return any(token in text for token in ("성공", "확인", "일치", "pass", "ready", "200"))


def _needs_follow_up(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text or text == "-":
        return False
    return text not in {"아니오", "no", "n", "none"}


def summarize_uat_payload(payload: dict) -> dict:
    entries = list(payload.get("entries") or [])
    blockers: list[dict[str, str]] = []
    follow_ups: list[dict[str, str]] = []
    passes = 0

    for entry in entries:
        generation_ok = _is_success_text(entry.get("generation_status", ""))
        export_ok = _is_success_text(entry.get("export_status", ""))
        visual_ok = _is_success_text(entry.get("visual_asset_status", ""))
        history_ok = _is_success_text(entry.get("history_restore_status", ""))
        issues = str(entry.get("issues", "") or "").strip()
        follow_up = str(entry.get("follow_up", "") or "").strip()

        if generation_ok and export_ok and (visual_ok or history_ok or entry.get("scenario", "").startswith("시나리오 4")):
            passes += 1

        if issues and issues not in {"-", "- 없음", "없음"}:
            blockers.append(
                {
                    "scenario": entry.get("scenario", "-"),
                    "issues": issues,
                }
            )
        elif _needs_follow_up(follow_up):
            follow_ups.append(
                {
                    "scenario": entry.get("scenario", "-"),
                    "follow_up": follow_up,
                }
            )

    status = "READY_FOR_PILOT" if entries and not blockers and not follow_ups else "FOLLOW_UP_REQUIRED"
    return {
        "session_title": payload.get("session_title", "-"),
        "session_file": payload.get("session_file", "-"),
        "entry_count": len(entries),
        "pass_count": passes,
        "blockers": blockers,
        "follow_ups": follow_ups,
        "status": status,
        "entries": entries,
    }


def build_uat_summary_markdown(*, summary: dict, generated_at: datetime) -> str:
    blockers = summary.get("blockers") or []
    follow_ups = summary.get("follow_ups") or []
    entries = summary.get("entries") or []

    blocker_lines = "\n".join(
        f"- `{item.get('scenario', '-')}`: {item.get('issues', '-')}" for item in blockers
    ) or "- 없음"
    follow_up_lines = "\n".join(
        f"- `{item.get('scenario', '-')}`: {item.get('follow_up', '-')}" for item in follow_ups
    ) or "- 없음"
    entry_lines = "\n".join(
        "- "
        f"{entry.get('recorded_at', '-')} | "
        f"{entry.get('scenario', '-')} | "
        f"bundle={entry.get('bundle', '-')} | "
        f"generation={entry.get('generation_status', '-')} | "
        f"export={entry.get('export_status', '-')} | "
        f"visual={entry.get('visual_asset_status', '-')} | "
        f"history={entry.get('history_restore_status', '-')}"
        for entry in entries
    ) or "- 없음"

    return f"""# UAT Final Summary — {summary.get('session_title', '-')}

- generated_at: {generated_at.isoformat()}
- session_file: `{summary.get('session_file', '-')}`
- overall_status: **{summary.get('status', 'FOLLOW_UP_REQUIRED')}**

## Summary

- recorded_entries: `{summary.get('entry_count', 0)}`
- pass_count: `{summary.get('pass_count', 0)}`
- blocker_count: `{len(blockers)}`
- follow_up_count: `{len(follow_ups)}`

## Blockers

{blocker_lines}

## Follow-ups

{follow_up_lines}

## Scenario Results

{entry_lines}
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def finalize_uat_session(*, session_file: Path, output_dir: Path) -> tuple[dict, Path]:
    payload = parse_uat_session(session_file)
    summary = summarize_uat_payload(payload)
    generated_at = datetime.now(timezone.utc)
    session_stem = Path(summary.get("session_file", session_file)).stem
    output_path = output_dir / f"{session_stem}-summary.md"
    markdown = build_uat_summary_markdown(summary=summary, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return summary, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a final markdown summary from an existing UAT session file.",
    )
    parser.add_argument("--session-file", required=True, help="Existing UAT session markdown file path.")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "reports" / "uat"), help="Directory to write the final summary markdown.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    summary, output_path = finalize_uat_session(
        session_file=Path(args.session_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created UAT summary: {output_path}", flush=True)
    print(f"Overall status: {summary.get('status', 'FOLLOW_UP_REQUIRED')}", flush=True)
    print(f"Recorded entries: {summary.get('entry_count', 0)}", flush=True)
    print(f"Blockers: {len(summary.get('blockers') or [])}", flush=True)
    print(f"Follow-ups: {len(summary.get('follow_ups') or [])}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
