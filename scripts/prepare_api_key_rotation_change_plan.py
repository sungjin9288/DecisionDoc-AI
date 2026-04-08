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
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "sungjin9288/DecisionDoc-AI"


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
    for run in runs:
        if (
            run.get("conclusion") == "success"
            and run.get("head_sha") == head_sha
            and _stage_matches(run, stage)
            and run.get("html_url")
        ):
            return str(run["html_url"])
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


def _derive_defaults(args: argparse.Namespace, *, secret_names: set[str]) -> dict[str, str]:
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
    defaults = _derive_defaults(args, secret_names=secret_names)
    owner = _placeholder(args.owner, "<OWNER_NAME>")
    same_sha_dev_evidence = _describe_same_sha_evidence(runs, stage="dev", head_sha=head_sha)
    same_sha_prod_evidence = _describe_same_sha_evidence(runs, stage="prod", head_sha=head_sha)
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

| 항목 | 값 |
|------|----|
| `deploy-smoke [dev]` rerun | `<RUN_ID_OR_URL>` |
| `Run smoke` | `success / fail` |
| `Run meeting recording smoke` | `success / fail` |
| `Run ops smoke` | `success / fail` |
| Caller cutover 방식 | `{defaults["cutover_mode"]}` |
| `deploy-smoke [prod]` rerun | `<RUN_ID_OR_URL_OR_NA>` |

## 5. Finalize / Rollback

- finalize: `DECISIONDOC_API_KEYS=new` and `DECISIONDOC_API_KEY=new`
- rollback: `DECISIONDOC_API_KEYS=old` and `DECISIONDOC_API_KEY=old`

## 6. Closeout note

```text
API key rotation completed.
- Stage: {stage}
- Main SHA: {head_sha}
- Old key label: {defaults["old_key_label"]}
- New key label: {defaults["new_key_label"]}
- Dev validation run: <DEV_RUN_URL>
- Prod validation run: <PROD_RUN_URL_OR_NA>
- Finalize time: <TIME>
- Old key deleted: <YES_OR_NO>
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
