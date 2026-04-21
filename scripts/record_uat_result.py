#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


def _normalize_text(value: str) -> str:
    return str(value or "").strip()


def _normalize_multiline(value: str) -> str:
    text = _normalize_text(value)
    return text if text else "-"


def _normalize_csv_lines(value: str) -> str:
    text = _normalize_text(value)
    if not text:
        return "- 없음"
    parts = [item.strip() for item in re.split(r"[,\n]+", text) if item.strip()]
    if not parts:
        return "- 없음"
    return "\n".join(f"  - {item}" for item in parts)


def build_uat_result_entry(
    *,
    recorded_at: datetime,
    owner: str,
    scenario: str,
    bundle: str,
    input_data: str,
    attachments: str,
    generation_status: str,
    export_status: str,
    visual_asset_status: str,
    history_restore_status: str,
    quality_notes: str,
    issues: str,
    follow_up: str,
) -> str:
    return f"""
### UAT 기록 — {scenario}
- 일시: {recorded_at.isoformat()}
- 담당자: {owner or '-'}
- 시나리오: {scenario or '-'}
- 사용 번들: {bundle or '-'}
- 입력 데이터: {input_data or '-'}
- 첨부 파일:
{_normalize_csv_lines(attachments)}
- 결과:
  - 생성 성공/실패: {generation_status or '-'}
  - export 성공/실패: {export_status or '-'}
  - visual asset 일치 여부: {visual_asset_status or '-'}
  - history 복원 여부: {history_restore_status or '-'}
- 품질 메모: {_normalize_multiline(quality_notes)}
- 실패/이슈: {_normalize_multiline(issues)}
- 후속 조치 필요 여부: {follow_up or '-'}
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def record_uat_result(
    *,
    session_file: Path,
    owner: str,
    scenario: str,
    bundle: str,
    input_data: str,
    attachments: str,
    generation_status: str,
    export_status: str,
    visual_asset_status: str,
    history_restore_status: str,
    quality_notes: str,
    issues: str,
    follow_up: str,
) -> Path:
    resolved = Path(session_file).expanduser()
    if not resolved.exists():
        raise SystemExit(f"Session file not found: {resolved}")

    existing = resolved.read_text(encoding="utf-8")
    entry = build_uat_result_entry(
        recorded_at=datetime.now(timezone.utc),
        owner=_normalize_text(owner),
        scenario=_normalize_text(scenario),
        bundle=_normalize_text(bundle),
        input_data=_normalize_text(input_data),
        attachments=attachments,
        generation_status=_normalize_text(generation_status),
        export_status=_normalize_text(export_status),
        visual_asset_status=_normalize_text(visual_asset_status),
        history_restore_status=_normalize_text(history_restore_status),
        quality_notes=quality_notes,
        issues=issues,
        follow_up=_normalize_text(follow_up),
    )
    separator = "" if existing.endswith("\n") else "\n"
    _write_text_atomic(resolved, existing + separator + entry)
    return resolved


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append a timestamped UAT result block to an existing UAT session markdown file.",
    )
    parser.add_argument("--session-file", required=True, help="Existing UAT session markdown file path.")
    parser.add_argument("--owner", default="", help="Tester or owner name.")
    parser.add_argument("--scenario", required=True, help="Scenario name.")
    parser.add_argument("--bundle", default="", help="Bundle type or bundle name.")
    parser.add_argument("--input-data", default="", help="Short summary of the input data used.")
    parser.add_argument("--attachments", default="", help="Comma-separated or newline-separated attachment names.")
    parser.add_argument("--generation-status", default="", help="Generation result summary.")
    parser.add_argument("--export-status", default="", help="Export result summary.")
    parser.add_argument("--visual-asset-status", default="", help="Visual asset consistency result.")
    parser.add_argument("--history-restore-status", default="", help="History restore result.")
    parser.add_argument("--quality-notes", default="", help="Quality notes.")
    parser.add_argument("--issues", default="", help="Failures or issues observed.")
    parser.add_argument("--follow-up", default="", help="Whether follow-up is needed.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    output_path = record_uat_result(
        session_file=Path(args.session_file),
        owner=args.owner,
        scenario=args.scenario,
        bundle=args.bundle,
        input_data=args.input_data,
        attachments=args.attachments,
        generation_status=args.generation_status,
        export_status=args.export_status,
        visual_asset_status=args.visual_asset_status,
        history_restore_status=args.history_restore_status,
        quality_notes=args.quality_notes,
        issues=args.issues,
        follow_up=args.follow_up,
    )
    print(f"Recorded UAT result: {output_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
