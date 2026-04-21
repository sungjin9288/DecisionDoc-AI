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
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports" / "uat"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return normalized or "session"


def _render_check_lines(payload: dict) -> str:
    lines = []
    for check in payload.get("checks", []):
        marker = "PASS" if check.get("status") == "pass" else "FAIL"
        lines.append(f"- {marker} `{check.get('name', 'unknown')}`: {check.get('detail', '-')}")
    return "\n".join(lines)


def _render_quality_first_issues(payload: dict) -> str:
    issues = (payload.get("health") or {}).get("provider_policy_issues", {}).get("quality_first") or []
    if not issues:
        return "- 없음"
    return "\n".join(f"- {item}" for item in issues)


def build_uat_session_markdown(*, session_name: str, owner: str, payload: dict, generated_at: datetime) -> str:
    readiness = "READY" if payload.get("ready") else "BLOCKED"
    health = payload.get("health") or {}
    latest_report = payload.get("latest_report") or {}
    provider_routes = health.get("provider_routes") or {}
    return f"""# UAT Session — {session_name}

- 생성 시각: {generated_at.isoformat()}
- 담당자: {owner or '-'}
- 대상 URL: {payload.get('base_url', '-')}
- Preflight 상태: **{readiness}**

## 1. Preflight 결과

{_render_check_lines(payload)}

## 2. 운영 상태 스냅샷

- provider: `{health.get('provider', '-')}`
- provider_routes:
  - default: `{provider_routes.get('default', '-')}`
  - generation: `{provider_routes.get('generation', '-')}`
  - attachment: `{provider_routes.get('attachment', '-')}`
  - visual: `{provider_routes.get('visual', '-')}`
- quality_first: `{(health.get('provider_policy_checks') or {}).get('quality_first', '-')}`
- quality_first issues:
{_render_quality_first_issues(payload)}

## 3. Latest post-deploy

- report file: `{latest_report.get('file', '-')}`
- status: `{latest_report.get('status', '-')}`
- finished_at: `{latest_report.get('finished_at', '-')}`
- skip_smoke: `{"yes" if latest_report.get("skip_smoke") else "no"}`
- error: {latest_report.get('error', '-') or '-'}

## 4. UAT 체크리스트

### 시나리오 1. 기본 사업 제안서 생성
- [ ] 번들 선택
- [ ] 목표/배경/제약 조건 입력
- [ ] 생성 성공 확인
- [ ] 결과 탭 노출 확인
- [ ] export 버튼 동작 확인

### 시나리오 2. 첨부 기반 제안서 생성
- [ ] PDF/PPTX/DOCX 또는 HWPX 첨부 2~3건 업로드
- [ ] 첨부 기반 생성 성공 확인
- [ ] 첨부 문맥 반영 품질 기록
- [ ] timeout/504 여부 기록

### 시나리오 3. visual asset 및 export 일관성
- [ ] visual asset 생성
- [ ] DOCX export 확인
- [ ] PDF export 확인
- [ ] PPTX export 확인
- [ ] HWPX export 및 한글 열기 확인

### 시나리오 4. legacy .hwp 차단
- [ ] 구형 `.hwp` 업로드
- [ ] 차단 메시지 확인
- [ ] `HWPX/PDF/DOCX 변환` 안내 확인

### 시나리오 5. history 복원 + 재export
- [ ] history 또는 server history에 저장
- [ ] 새로고침 후 다시 열기
- [ ] visual asset snapshot 유지 확인
- [ ] 재export 결과 비교

## 5. 결과 기록

### UAT 기록
- 일시:
- 담당자:
- 시나리오:
- 사용 번들:
- 입력 데이터:
- 첨부 파일:
- 결과:
  - 생성 성공/실패:
  - export 성공/실패:
  - visual asset 일치 여부:
  - history 복원 여부:
- 품질 메모:
- 실패/이슈:
- 후속 조치 필요 여부:
"""


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def create_uat_session(*, base_url: str, report_dir: Path, output_dir: Path, session_name: str, owner: str) -> tuple[dict, Path]:
    payload = build_uat_preflight_payload(base_url=base_url, report_dir=report_dir)
    generated_at = datetime.now(timezone.utc)
    filename = f"uat-session-{generated_at.strftime('%Y%m%dT%H%M%SZ')}-{_slugify(session_name)}.md"
    output_path = output_dir / filename
    markdown = build_uat_session_markdown(
        session_name=session_name,
        owner=owner,
        payload=payload,
        generated_at=generated_at,
    )
    _write_text_atomic(output_path, markdown)
    return payload, output_path


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a timestamped UAT session markdown file from current preflight readiness.",
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="Environment file used to resolve the default base URL.")
    parser.add_argument("--base-url", default="", help="Optional explicit base URL.")
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR), help="Directory that contains post-deploy reports.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory to write generated UAT session markdown.")
    parser.add_argument("--session-name", default="business-uat", help="Logical session name used in the markdown title and filename.")
    parser.add_argument("--owner", default="", help="Owner or tester name to include in the generated session file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    env_values = _load_env_file(Path(args.env_file))
    base_url = _resolve_base_url(str(args.base_url or ""), env_values)
    payload, output_path = create_uat_session(
        base_url=base_url,
        report_dir=Path(args.report_dir),
        output_dir=Path(args.output_dir),
        session_name=str(args.session_name or "business-uat"),
        owner=str(args.owner or ""),
    )
    readiness = "READY" if payload.get("ready") else "BLOCKED"
    print(f"Created UAT session: {output_path}", flush=True)
    print(f"Preflight status: {readiness}", flush=True)
    return 0 if payload.get("ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
