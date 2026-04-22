#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def parse_pilot_handoff(handoff_file: Path) -> dict[str, str]:
    text = Path(handoff_file).read_text(encoding="utf-8")

    def _match(pattern: str, default: str = "-") -> str:
        matched = re.search(pattern, text, re.MULTILINE)
        return matched.group(1).strip() if matched else default

    return {
        "session_title": _match(r"^# Pilot Handoff — (.+)$"),
        "pilot_status": _match(r"pilot_status:\s+\*\*(.+?)\*\*"),
        "source_uat_status": _match(r"source_uat_status:\s+`([^`]+)`"),
        "source_preflight_ready": _match(r"source_preflight_ready:\s+`([^`]+)`"),
        "source_latest_report_status": _match(r"source_latest_report_status:\s+`([^`]+)`"),
        "recorded_entries": _match(r"recorded_entries:\s+`([^`]+)`", "0"),
        "scenario_count": _match(r"scenario_count:\s+`([^`]+)`", "0"),
        "pass_count": _match(r"pass_count:\s+`([^`]+)`", "0"),
        "blocker_count": _match(r"blocker_count:\s+`([^`]+)`", "0"),
        "follow_up_count": _match(r"follow_up_count:\s+`([^`]+)`", "0"),
        "base_url": _match(r"base_url:\s+`([^`]+)`"),
        "provider": _match(r"provider:\s+`([^`]+)`"),
        "quality_first": _match(r"quality_first:\s+`([^`]+)`"),
        "latest_report": _match(r"latest_report:\s+`([^`]+)`"),
        "default_route": _match(r"default:\s+`([^`]+)`"),
        "generation_route": _match(r"generation:\s+`([^`]+)`"),
        "attachment_route": _match(r"attachment:\s+`([^`]+)`"),
        "visual_route": _match(r"visual:\s+`([^`]+)`"),
        "go_decision": _match(r"Go decision:\s+`([^`]+)`"),
    }


def build_launch_checklist_payload(handoff: dict[str, str]) -> dict[str, str]:
    ready = str(handoff.get("pilot_status", "")).strip() == "READY_FOR_PILOT"
    return {
        **handoff,
        "launch_status": "READY_TO_EXECUTE" if ready else "HOLD",
        "launch_decision": "START" if ready else "STOP",
    }


def build_launch_checklist_markdown(*, payload: dict[str, str], generated_at: datetime) -> str:
    return f"""# Pilot Launch Checklist — {payload.get('session_title', '-')}

- generated_at: {generated_at.isoformat()}
- launch_status: **{payload.get('launch_status', 'HOLD')}**
- launch_decision: `{payload.get('launch_decision', 'STOP')}`
- source_pilot_status: `{payload.get('pilot_status', '-')}`

## Readiness Snapshot

- base_url: `{payload.get('base_url', '-')}`
- latest_report: `{payload.get('latest_report', '-')}`
- provider: `{payload.get('provider', '-')}`
- quality_first: `{payload.get('quality_first', '-')}`
- provider_routes:
  - default: `{payload.get('default_route', '-')}`
  - generation: `{payload.get('generation_route', '-')}`
  - attachment: `{payload.get('attachment_route', '-')}`
  - visual: `{payload.get('visual_route', '-')}`

## Pre-Start Checks

- [ ] `source_uat_status = READY_FOR_PILOT` 인지 확인
- [ ] `source_preflight_ready = yes` 인지 확인
- [ ] `source_latest_report_status = passed` 인지 확인
- [ ] 운영 재기동 시 `DOCKER_IMAGE=decisiondoc-admin-local` 사용 여부 확인
- [ ] pilot 담당자와 business owner가 같은 샘플 문서/첨부 세트를 사용하기로 합의
- [ ] pilot 시작 전 증적 파일 보관
  - [ ] `{payload.get('latest_report', '-')}`
  - [ ] UAT summary
  - [ ] pilot handoff

## Pilot Execution

- [ ] 기본 문서 생성 1건 실행
- [ ] 첨부 기반 문서 생성 1건 실행
- [ ] 생성 결과에서 business owner가 내용 적합성 1차 확인
- [ ] 필요한 export 1종 이상 실제 다운로드 확인
- [ ] feedback / follow-up이 있으면 즉시 기록

## Stop / Rollback Criteria

- [ ] `/health`가 `ok`가 아니면 즉시 중단
- [ ] latest post-deploy smoke가 fail로 바뀌면 즉시 중단
- [ ] 문서 생성이 5xx 또는 timeout으로 반복 실패하면 즉시 중단
- [ ] 운영 이미지가 `decisiondoc-admin-local`이 아닌 것으로 확인되면 즉시 중단
- [ ] 근거 없는 핵심 정량 수치 hallucination이 다시 재현되면 결과 공유 전 중단

## Evidence To Capture

- [ ] request_id 2건 이상
- [ ] 생성된 bundle_id / export 결과
- [ ] 품질 코멘트 요약
- [ ] 문제가 있으면 재현 입력과 첨부 목록
- [ ] pilot 종료 후 latest post-deploy / UAT / handoff artifact 경로
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_launch_checklist(*, handoff_file: Path, output_dir: Path) -> tuple[dict[str, str], Path]:
    handoff = parse_pilot_handoff(handoff_file)
    payload = build_launch_checklist_payload(handoff)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{Path(handoff_file).stem}-launch-checklist.md"
    markdown = build_launch_checklist_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a pilot launch checklist markdown from an existing pilot handoff file.",
    )
    parser.add_argument("--handoff-file", required=True, help="Pilot handoff markdown file path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot checklist markdown.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    payload, output_path = create_pilot_launch_checklist(
        handoff_file=Path(args.handoff_file),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot launch checklist: {output_path}", flush=True)
    print(f"Launch status: {payload.get('launch_status', 'HOLD')}", flush=True)
    return 0 if payload.get("launch_status") == "READY_TO_EXECUTE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
