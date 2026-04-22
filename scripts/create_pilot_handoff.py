#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_uat_preflight_module():
    module_path = REPO_ROOT / "scripts" / "uat_preflight.py"
    spec = importlib.util.spec_from_file_location("decisiondoc_uat_preflight", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


_uat_preflight = _load_uat_preflight_module()

build_uat_preflight_payload = _uat_preflight.build_uat_preflight_payload
_load_env_file = _uat_preflight._load_env_file
_resolve_base_url = _uat_preflight._resolve_base_url
DEFAULT_ENV_FILE = _uat_preflight.DEFAULT_ENV_FILE
DEFAULT_REPORT_DIR = _uat_preflight.DEFAULT_REPORT_DIR
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "pilot"


def parse_uat_summary(summary_file: Path) -> dict[str, str]:
    text = Path(summary_file).read_text(encoding="utf-8")

    def _match(pattern: str, default: str = "-") -> str:
        matched = re.search(pattern, text, re.MULTILINE)
        return matched.group(1).strip() if matched else default

    return {
        "session_title": _match(r"^# UAT Final Summary — (.+)$"),
        "overall_status": _match(r"overall_status:\s+\*\*(.+?)\*\*"),
        "recorded_entries": _match(r"recorded_entries:\s+`([^`]+)`", "0"),
        "scenario_count": _match(r"scenario_count:\s+`([^`]+)`", "0"),
        "pass_count": _match(r"pass_count:\s+`([^`]+)`", "0"),
        "blocker_count": _match(r"blocker_count:\s+`([^`]+)`", "0"),
        "follow_up_count": _match(r"follow_up_count:\s+`([^`]+)`", "0"),
    }


def build_pilot_handoff_payload(*, uat_summary: dict[str, str], preflight_payload: dict) -> dict[str, object]:
    latest_report = preflight_payload.get("latest_report") or {}
    health = preflight_payload.get("health") or {}
    uat_ready = str(uat_summary.get("overall_status", "")).strip() == "READY_FOR_PILOT"
    preflight_ready = bool(preflight_payload.get("ready"))
    latest_report_passed = str(latest_report.get("status", "")).strip() == "passed"
    pilot_ready = uat_ready and preflight_ready and latest_report_passed
    return {
        "pilot_status": "READY_FOR_PILOT" if pilot_ready else "FOLLOW_UP_REQUIRED",
        "uat_summary": uat_summary,
        "preflight": preflight_payload,
        "latest_report": latest_report,
        "health": health,
    }


def build_pilot_handoff_markdown(*, payload: dict[str, object], generated_at: datetime) -> str:
    uat_summary = payload.get("uat_summary") or {}
    preflight = payload.get("preflight") or {}
    latest_report = payload.get("latest_report") or {}
    health = payload.get("health") or {}
    provider_routes = health.get("provider_routes") or {}
    quality_first = (health.get("provider_policy_checks") or {}).get("quality_first", "-")

    return f"""# Pilot Handoff — {uat_summary.get('session_title', '-')}

- generated_at: {generated_at.isoformat()}
- pilot_status: **{payload.get('pilot_status', 'FOLLOW_UP_REQUIRED')}**
- source_uat_status: `{uat_summary.get('overall_status', '-')}`
- source_preflight_ready: `{"yes" if preflight.get("ready") else "no"}`
- source_latest_report_status: `{latest_report.get('status', '-')}`

## UAT Summary

- recorded_entries: `{uat_summary.get('recorded_entries', '0')}`
- scenario_count: `{uat_summary.get('scenario_count', '0')}`
- pass_count: `{uat_summary.get('pass_count', '0')}`
- blocker_count: `{uat_summary.get('blocker_count', '0')}`
- follow_up_count: `{uat_summary.get('follow_up_count', '0')}`

## Runtime Snapshot

- base_url: `{preflight.get('base_url', '-')}`
- provider: `{health.get('provider', '-')}`
- quality_first: `{quality_first}`
- latest_report: `{latest_report.get('file', '-')}`
- provider_routes:
  - default: `{provider_routes.get('default', '-')}`
  - generation: `{provider_routes.get('generation', '-')}`
  - attachment: `{provider_routes.get('attachment', '-')}`
  - visual: `{provider_routes.get('visual', '-')}`

## Pilot Go / No-Go

- Go decision: `{"GO" if payload.get("pilot_status") == "READY_FOR_PILOT" else "NO_GO"}`
- Reason:
  - UAT summary status = `{uat_summary.get('overall_status', '-')}`
  - preflight ready = `{"yes" if preflight.get("ready") else "no"}`
  - latest post-deploy status = `{latest_report.get('status', '-')}`

## Recommended Next Actions

1. 운영 기준 파일은 `DOCKER_IMAGE=decisiondoc-admin-local`을 명시해 재기동한다.
2. 실제 pilot 대상 문서 1~2건을 business owner와 함께 생성해 품질 피드백을 수집한다.
3. `reports/post-deploy/latest.json`과 UAT summary를 pilot 시작 기준 증적으로 보관한다.
4. 큰 첨부 다건 케이스는 별도 확장 UAT로 분리해 추적한다.
5. full browser click-path spot check은 환경 제약이 없는 운영 브라우저에서 한 번 더 확인한다.
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_pilot_handoff(
    *,
    summary_file: Path,
    base_url: str,
    report_dir: Path,
    output_dir: Path,
) -> tuple[dict[str, object], Path]:
    uat_summary = parse_uat_summary(summary_file)
    preflight_payload = build_uat_preflight_payload(base_url=base_url, report_dir=report_dir)
    payload = build_pilot_handoff_payload(uat_summary=uat_summary, preflight_payload=preflight_payload)
    generated_at = datetime.now(timezone.utc)
    output_path = output_dir / f"{Path(summary_file).stem}-pilot.md"
    markdown = build_pilot_handoff_markdown(payload=payload, generated_at=generated_at)
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a pilot handoff markdown from a finalized UAT summary and current preflight state.",
    )
    parser.add_argument("--summary-file", required=True, help="UAT summary markdown file path.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Environment file used to resolve the default base URL.")
    parser.add_argument("--base-url", default="", help="Optional explicit base URL.")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Directory that contains post-deploy reports.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated pilot handoff markdown.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    env_values = _load_env_file(Path(args.env_file))
    base_url = _resolve_base_url(str(args.base_url or ""), env_values)
    payload, output_path = create_pilot_handoff(
        summary_file=Path(args.summary_file),
        base_url=base_url,
        report_dir=Path(args.report_dir),
        output_dir=Path(args.output_dir),
    )
    print(f"Created pilot handoff: {output_path}", flush=True)
    print(f"Pilot status: {payload.get('pilot_status', 'FOLLOW_UP_REQUIRED')}", flush=True)
    return 0 if payload.get("pilot_status") == "READY_FOR_PILOT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
