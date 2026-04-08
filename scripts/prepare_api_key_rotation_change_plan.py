#!/usr/bin/env python3
"""Prepare a partially filled API key rotation change plan.

The script gathers the current git SHA and recent successful deploy-smoke runs,
then prints a Markdown plan that operators can paste into a change ticket or
save as a working note before the actual key rotation.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "sungjin9288/DecisionDoc-AI"
KST = ZoneInfo("Asia/Seoul")


def _run(command: list[str], *, cwd: Path = REPO_ROOT) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _placeholder(value: str | None, fallback: str) -> str:
    if value and value.strip():
        return value.strip()
    return fallback


def _infer_repo_slug() -> str:
    try:
        remote_url = _run(["git", "remote", "get-url", "origin"])
    except subprocess.CalledProcessError:
        return DEFAULT_REPO

    normalized = remote_url.strip()
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if normalized.startswith("git@github.com:"):
        return normalized.split(":", 1)[1]
    if normalized.startswith("https://github.com/"):
        return normalized.split("https://github.com/", 1)[1]
    return DEFAULT_REPO


def _get_head_sha() -> str:
    return _run(["git", "rev-parse", "HEAD"])


def _fetch_workflow_runs(repo_slug: str, *, per_page: int = 30) -> list[dict[str, Any]]:
    payload = _run(
        [
            "gh",
            "api",
            f"repos/{repo_slug}/actions/workflows/deploy-smoke.yml/runs?per_page={per_page}",
        ]
    )
    data = json.loads(payload)
    workflow_runs = data.get("workflow_runs")
    if not isinstance(workflow_runs, list):
        return []
    return [run for run in workflow_runs if isinstance(run, dict)]


def _fetch_actions_secret_names(repo_slug: str) -> set[str]:
    payload = _run(
        [
            "gh",
            "api",
            f"repos/{repo_slug}/actions/secrets",
        ]
    )
    data = json.loads(payload)
    secrets = data.get("secrets")
    if not isinstance(secrets, list):
        return set()

    names: set[str] = set()
    for item in secrets:
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
    return names


def _stage_matches(run: dict[str, Any], stage: str) -> bool:
    title = str(run.get("display_title") or "")
    return f"deploy-smoke [{stage}]" in title


def _same_sha_run(runs: list[dict[str, Any]], *, stage: str, head_sha: str) -> dict[str, Any] | None:
    for run in runs:
        if (
            run.get("conclusion") == "success"
            and run.get("head_sha") == head_sha
            and _stage_matches(run, stage)
        ):
            return run
    return None


def _select_run_url(runs: list[dict[str, Any]], *, stage: str, head_sha: str) -> str:
    successful = [
        run for run in runs if run.get("conclusion") == "success" and _stage_matches(run, stage)
    ]
    if not successful:
        return "<RUN_ID_OR_URL>"

    for run in successful:
        if run.get("head_sha") == head_sha and run.get("html_url"):
            return str(run["html_url"])

    first = successful[0]
    html_url = first.get("html_url")
    if html_url:
        return str(html_url)
    run_id = first.get("id")
    if run_id:
        return str(run_id)
    return "<RUN_ID_OR_URL>"


def _same_sha_run_url(runs: list[dict[str, Any]], *, stage: str, head_sha: str) -> str | None:
    run = _same_sha_run(runs, stage=stage, head_sha=head_sha)
    if run and run.get("html_url"):
        return str(run["html_url"])
    return None


def _run_id(run: dict[str, Any]) -> str | None:
    run_id = run.get("id")
    if run_id is None:
        return None
    return str(run_id)


def _fetch_run_jobs(repo_slug: str, *, run_id: str) -> list[dict[str, Any]]:
    payload = _run(
        [
            "gh",
            "api",
            f"repos/{repo_slug}/actions/runs/{run_id}/jobs",
        ]
    )
    data = json.loads(payload)
    jobs = data.get("jobs")
    if not isinstance(jobs, list):
        return []
    return [job for job in jobs if isinstance(job, dict)]


def _fetch_run_detail(repo_slug: str, *, run_id: str) -> dict[str, Any]:
    payload = _run(
        [
            "gh",
            "api",
            f"repos/{repo_slug}/actions/runs/{run_id}",
        ]
    )
    data = json.loads(payload)
    if not isinstance(data, dict):
        return {}
    return data


def _extract_step_conclusion(jobs: list[dict[str, Any]], *, step_name: str) -> str | None:
    for job in jobs:
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            if step.get("name") == step_name:
                conclusion = step.get("conclusion")
                if isinstance(conclusion, str) and conclusion.strip():
                    return conclusion.strip()
                status = step.get("status")
                if isinstance(status, str) and status.strip():
                    return status.strip()
    return None


def _describe_same_sha_evidence(runs: list[dict[str, Any]], *, stage: str, head_sha: str) -> str:
    same_sha_url = _same_sha_run_url(runs, stage=stage, head_sha=head_sha)
    if same_sha_url:
        run_id = same_sha_url.rstrip("/").split("/")[-1]
        return f"ready — deploy-smoke [{stage}] run {run_id} succeeded on {head_sha}"
    return f"missing — run deploy-smoke [{stage}] on {head_sha} first"


def _describe_openai_availability(stage: str, secret_names: set[str]) -> str:
    stage_key = f"OPENAI_API_KEY_{stage.upper()}"
    if stage_key in secret_names:
        return f"yes — stage secret `{stage_key}` present"
    if "OPENAI_API_KEY" in secret_names:
        return "yes — repo-level `OPENAI_API_KEY` fallback present"
    return f"no — missing `{stage_key}` and repo-level `OPENAI_API_KEY`"


def _format_run_updated_at_kst(timestamp: str) -> str | None:
    normalized = timestamp.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")


def _default_finalize_time(repo_slug: str, runs: list[dict[str, Any]], *, stage: str, head_sha: str) -> str:
    run = _same_sha_run(runs, stage=stage, head_sha=head_sha)
    if not run:
        return "<TIME>"

    updated_at = run.get("updated_at")
    if isinstance(updated_at, str):
        formatted = _format_run_updated_at_kst(updated_at)
        if formatted:
            return formatted

    run_id = _run_id(run)
    if not run_id:
        return "<TIME>"

    try:
        detail = _fetch_run_detail(repo_slug, run_id=run_id)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return "<TIME>"

    updated_at = detail.get("updated_at")
    if isinstance(updated_at, str):
        formatted = _format_run_updated_at_kst(updated_at)
        if formatted:
            return formatted
    return "<TIME>"


def _validation_defaults(
    repo_slug: str,
    runs: list[dict[str, Any]],
    *,
    stage: str,
    head_sha: str,
) -> dict[str, str]:
    placeholder_run = "<RUN_ID_OR_URL>" if stage == "dev" else "<RUN_ID_OR_URL_OR_NA>"
    result = {
        "run_url": placeholder_run,
        "run_smoke": "success / fail",
        "meeting_recording_smoke": "success / fail",
        "ops_smoke": "success / fail",
    }

    run = _same_sha_run(runs, stage=stage, head_sha=head_sha)
    if not run:
        return result

    html_url = run.get("html_url")
    if isinstance(html_url, str) and html_url.strip():
        result["run_url"] = html_url.strip()

    run_id = _run_id(run)
    if not run_id:
        return result

    try:
        jobs = _fetch_run_jobs(repo_slug, run_id=run_id)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return result

    result["run_smoke"] = _extract_step_conclusion(jobs, step_name="Run smoke") or result["run_smoke"]
    result["meeting_recording_smoke"] = (
        _extract_step_conclusion(jobs, step_name="Run meeting recording smoke")
        or result["meeting_recording_smoke"]
    )
    result["ops_smoke"] = _extract_step_conclusion(jobs, step_name="Run ops smoke") or result["ops_smoke"]
    return result


def _derive_defaults(
    args: argparse.Namespace,
    *,
    repo_slug: str,
    runs: list[dict[str, Any]],
    secret_names: set[str],
    head_sha: str,
) -> dict[str, str]:
    today = date.today().isoformat()
    owner = _placeholder(args.owner, "<OWNER_NAME>")
    cutover_mode = args.cutover_mode

    return {
        "approver": _placeholder(args.approver, owner),
        "window_start": _placeholder(args.window_start, "ad-hoc (no fixed maintenance window)"),
        "window_end": _placeholder(args.window_end, "ad-hoc (close when validation completes)"),
        "old_key_label": _placeholder(args.old_key_label, "decisiondoc-api-current"),
        "new_key_label": _placeholder(args.new_key_label, f"decisiondoc-api-next-{today}"),
        "client_rollout_owner": _placeholder(args.client_rollout_owner, owner),
        "rollback_owner": _placeholder(args.rollback_owner, owner),
        "openai_fallback": _placeholder(
            args.openai_fallback,
            _describe_openai_availability(args.stage, secret_names),
        ),
        "client_rollout_ready": _placeholder(
            args.client_rollout_ready,
            "yes — external caller 없음, repo 내부 smoke/deploy 경로만 사용"
            if cutover_mode == "direct"
            else "yes / no",
        ),
        "finalize_time": _placeholder(
            args.finalize_time,
            _default_finalize_time(repo_slug, runs, stage=args.stage, head_sha=head_sha),
        ),
        "old_key_deleted": _placeholder(args.old_key_deleted, "<YES_OR_NO>"),
        "cutover_mode": cutover_mode,
    }


def _render_secret_staging(repo_slug: str, *, cutover_mode: str) -> str:
    if cutover_mode == "direct":
        return f"""## 3. Secret staging

Direct cutover 를 사용한다. 전제는 external caller 가 없고 repo 내부 smoke / deploy 경로만 검증하면 충분하다는 것이다.

1. `DECISIONDOC_API_KEYS=new`
2. `DECISIONDOC_API_KEY=new`

예시:

```bash
gh secret set DECISIONDOC_API_KEYS -R {repo_slug} --body "NEW_KEY"
gh secret set DECISIONDOC_API_KEY -R {repo_slug} --body "NEW_KEY"
```"""

    return f"""## 3. Secret staging

Overlap-first 순서를 사용한다.

1. `DECISIONDOC_API_KEYS=old,new`
2. `DECISIONDOC_API_KEY=old`

예시:

```bash
gh secret set DECISIONDOC_API_KEYS -R {repo_slug} --body "OLD_KEY,NEW_KEY"
gh secret set DECISIONDOC_API_KEY -R {repo_slug} --body "OLD_KEY"
```"""


def _render_plan(
    args: argparse.Namespace,
    *,
    repo_slug: str,
    head_sha: str,
    runs: list[dict[str, Any]],
    secret_names: set[str],
    dev_run_url: str,
    prod_run_url: str,
) -> str:
    stage = args.stage
    stage_prod = "yes" if stage == "prod" else "no"
    defaults = _derive_defaults(
        args,
        repo_slug=repo_slug,
        runs=runs,
        secret_names=secret_names,
        head_sha=head_sha,
    )
    owner = _placeholder(args.owner, "<OWNER_NAME>")
    same_sha_dev_evidence = _describe_same_sha_evidence(runs, stage="dev", head_sha=head_sha)
    same_sha_prod_evidence = _describe_same_sha_evidence(runs, stage="prod", head_sha=head_sha)
    dev_validation = _validation_defaults(repo_slug, runs, stage="dev", head_sha=head_sha)
    prod_validation = _validation_defaults(repo_slug, runs, stage="prod", head_sha=head_sha)
    additional_dev_validation_run = (
        "N/A (direct cutover)"
        if defaults["cutover_mode"] == "direct"
        else "<RUN_ID_OR_NA>"
    )
    secret_staging = _render_secret_staging(repo_slug, cutover_mode=defaults["cutover_mode"])

    return f"""# API Key Rotation Change Plan

Generated by `python3 scripts/prepare_api_key_rotation_change_plan.py --stage {stage}`

## 1. Change metadata

| 항목 | 값 |
|------|----|
| Change ticket / Incident | {_placeholder(args.ticket, "<TICKET_ID>")} |
| Change owner | {owner} |
| Approver | {defaults["approver"]} |
| Change window start | {defaults["window_start"]} |
| Change window end | {defaults["window_end"]} |
| Target stage | {stage} |
| Old key label | {defaults["old_key_label"]} |
| New key label | {defaults["new_key_label"]} |
| Client rollout owner | {defaults["client_rollout_owner"]} |
| Rollback owner | {defaults["rollback_owner"]} |

## 2. Preconditions

- `prod` rotation인가: `{stage_prod}`
- Current repo: `{repo_slug}`
- Current `main` SHA가 실제 rollout 대상인지 확인
- 새 key 전달 대상과 old key 복구 경로 확인

| 체크 | 값 |
|------|----|
| Current `main` SHA | `{head_sha}` |
| Same-SHA `deploy-smoke [dev]` evidence for current `main` | `{same_sha_dev_evidence}` |
| Same-SHA `deploy-smoke [prod]` evidence for current `main` | `{same_sha_prod_evidence}` |
| Latest `deploy-smoke [dev]` run | {dev_run_url} |
| Latest `deploy-smoke [prod]` run | {prod_run_url} |
| OpenAI fallback 확인 | {defaults["openai_fallback"]} |
| Client rollout 대상 목록 확인 | {defaults["client_rollout_ready"]} |

{secret_staging}

## 4. Validation log

### 4.1 Dev validation

| 항목 | 값 |
|------|----|
| `deploy-smoke [dev]` rerun | `{dev_validation["run_url"]}` |
| `Run smoke` | `{dev_validation["run_smoke"]}` |
| `Run meeting recording smoke` | `{dev_validation["meeting_recording_smoke"]}` |
| `Run ops smoke` | `{dev_validation["ops_smoke"]}` |

### 4.2 Caller cutover

| 항목 | 값 |
|------|----|
| Caller cutover 방식 | `{defaults["cutover_mode"]}` |
| 추가 dev validation run | `{additional_dev_validation_run}` |

### 4.3 Prod validation

| 항목 | 값 |
|------|----|
| `deploy-smoke [prod]` rerun | `{prod_validation["run_url"]}` |
| `Run smoke` | `{prod_validation["run_smoke"]}` |
| `Run meeting recording smoke` | `{prod_validation["meeting_recording_smoke"]}` |
| `Run ops smoke` | `{prod_validation["ops_smoke"]}` |

## 5. Finalize / Rollback

- finalize: `DECISIONDOC_API_KEYS=new` and `DECISIONDOC_API_KEY=new`
- rollback: `DECISIONDOC_API_KEYS=old` and `DECISIONDOC_API_KEY=old`

| 항목 | 값 |
|------|----|
| Finalize time | `{defaults["finalize_time"]}` |
| Old key deleted | `{defaults["old_key_deleted"]}` |

## 6. Closeout note

```text
API key rotation completed.
- Stage: {stage}
- Main SHA: {head_sha}
- Old key label: {defaults["old_key_label"]}
- New key label: {defaults["new_key_label"]}
- Dev validation run: {dev_validation["run_url"]}
- Prod validation run: {prod_validation["run_url"]}
- Finalize time: {defaults["finalize_time"]}
- Old key deleted: {defaults["old_key_deleted"]}
- Owner: {owner}
```
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("dev", "prod"), default="prod")
    parser.add_argument("--repo", default="", help="GitHub repo slug, e.g. owner/name")
    parser.add_argument("--ticket", default="")
    parser.add_argument("--owner", default="")
    parser.add_argument("--approver", default="")
    parser.add_argument("--window-start", default="")
    parser.add_argument("--window-end", default="")
    parser.add_argument("--old-key-label", default="")
    parser.add_argument("--new-key-label", default="")
    parser.add_argument("--client-rollout-owner", default="")
    parser.add_argument("--rollback-owner", default="")
    parser.add_argument("--openai-fallback", default="")
    parser.add_argument("--client-rollout-ready", default="")
    parser.add_argument("--finalize-time", default="")
    parser.add_argument("--old-key-deleted", default="")
    parser.add_argument(
        "--cutover-mode",
        choices=("overlap", "smoke-first", "direct"),
        default="direct",
        help="Preferred cutover path for the generated plan",
    )
    parser.add_argument("--output", default="", help="Write the plan to a file instead of stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_slug = _placeholder(args.repo, _infer_repo_slug())
    try:
        head_sha = _get_head_sha()
        runs = _fetch_workflow_runs(repo_slug)
        secret_names = _fetch_actions_secret_names(repo_slug)
    except subprocess.CalledProcessError as exc:
        parser.exit(1, f"[prepare_api_key_rotation_change_plan] command failed: {exc}\n")
        return 1
    except json.JSONDecodeError as exc:
        parser.exit(1, f"[prepare_api_key_rotation_change_plan] invalid GitHub API payload: {exc}\n")
        return 1

    dev_run_url = _select_run_url(runs, stage="dev", head_sha=head_sha)
    prod_run_url = _select_run_url(runs, stage="prod", head_sha=head_sha)
    plan = _render_plan(
        args,
        repo_slug=repo_slug,
        head_sha=head_sha,
        runs=runs,
        secret_names=secret_names,
        dev_run_url=dev_run_url,
        prod_run_url=prod_run_url,
    )

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(plan, encoding="utf-8")
        print(f"[prepare_api_key_rotation_change_plan] wrote plan to {output_path}", file=sys.stderr)
    else:
        print(plan)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
