#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Mapping, Sequence
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROD_ENV_FILE = REPO_ROOT / ".env.prod"
SCHEMA_VERSION = "decisiondoc.completion_readiness.v1"

EXCLUDED_EXTERNAL_ACTIONS = (
    "provider API execution",
    "G2B live API execution",
    "AWS runtime execution",
    "dataset upload",
    "training execution",
    "model promotion",
    "production service resume",
    "bid submission",
    "legal approval",
    "contractual commitment",
)

MILESTONE_COMMANDS = {
    "M1": (
        "DECISIONDOC_PROVIDER=openai python3 -m pytest -q tests/test_live_providers.py -m live -rs",
        "DECISIONDOC_PROVIDER=gemini python3 -m pytest -q tests/test_live_providers.py -m live -rs",
        "DECISIONDOC_PROVIDER=claude python3 -m pytest -q tests/test_live_providers.py -m live -rs",
        "DECISIONDOC_PROVIDER=openai,gemini DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1 python3 -m pytest -q tests/test_live_providers.py::test_live_openai_gemini_fallback_chain_ok -m live -rs",
        "gh workflow run live.yml --ref main -f provider=openai",
        "gh workflow run live.yml --ref main -f provider=gemini",
        "gh workflow run live.yml --ref main -f provider=claude",
        "gh workflow run live.yml --ref main -f provider='openai,gemini'",
    ),
    "M2": (
        "python3 scripts/run_stage_procurement_smoke.py --env-file .env.prod --preflight",
        "python3 scripts/run_stage_procurement_smoke.py --env-file .env.prod",
        "python3 scripts/run_stage_procurement_smoke.py --preflight",
        "python3 scripts/run_stage_procurement_smoke.py",
    ),
    "M6": (
        "python3 scripts/run_deployed_smoke.py --env-file .env.prod --preflight",
        "python3 scripts/run_deployed_smoke.py --env-file .env.prod",
        "python3 scripts/run_deployed_smoke.py --preflight",
        "python3 scripts/run_deployed_smoke.py",
    ),
}

ENV_TEMPLATE_LINES = (
    "# DecisionDoc completion readiness inputs",
    "# Fill these in a gitignored file such as .env.prod before running live/deploy proof.",
    "",
    "# M1: live provider proof",
    "OPENAI_API_KEY=your-openai-api-key",
    "GEMINI_API_KEY=your-gemini-api-key",
    "ANTHROPIC_API_KEY=your-anthropic-api-key",
    "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE=1",
    "",
    "# M2: G2B live procurement smoke",
    "SMOKE_BASE_URL=https://your-stage.example.com",
    "SMOKE_API_KEY=your-stage-api-key",
    "G2B_API_KEY=your-data-go-kr-key",
    "",
    "# M6: deployment and post-deploy smoke proof",
    "ALLOWED_ORIGINS=https://your-runtime.example.com",
    "DECISIONDOC_API_KEYS=your-runtime-api-key",
    "",
    "# Local readiness receipt",
    "python3 scripts/check_completion_readiness.py --env-file .env.prod",
    "python3 scripts/check_completion_readiness.py --env-file .env.prod --json --output reports/completion-readiness/latest.json",
    "python3 scripts/check_completion_readiness_result.py reports/completion-readiness/latest.json",
    "",
    "# No-secret proof receipts after approved external proof",
    "python3 scripts/check_completion_proof_receipt.py --print-template M1 > reports/completion-readiness/m1-live-provider-proof.json",
    "python3 scripts/check_completion_proof_receipt.py --print-template M2 > reports/completion-readiness/m2-g2b-stage-smoke-proof.json",
    "python3 scripts/check_completion_proof_receipt.py --print-template M6 > reports/completion-readiness/m6-deployment-smoke-proof.json",
    "python3 scripts/check_completion_proof_receipt.py reports/completion-readiness/m1-live-provider-proof.json",
    "python3 scripts/check_completion_proof_receipt.py reports/completion-readiness/m2-g2b-stage-smoke-proof.json",
    "python3 scripts/check_completion_proof_receipt.py reports/completion-readiness/m6-deployment-smoke-proof.json",
)


def _load_env_file(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    resolved = Path(path).expanduser()
    if not resolved.exists():
        return {}
    values: dict[str, str] = {}
    for lineno, raw_line in enumerate(resolved.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            raise SystemExit(f"Invalid env file line {lineno}: {resolved}")
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key:
            raise SystemExit(f"Invalid env file line {lineno}: {resolved}")
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {'"', "'"}
        ):
            normalized_value = normalized_value[1:-1]
        values[normalized_key] = normalized_value
    return values


def _env_value(name: str, env: Mapping[str, str], env_file_values: Mapping[str, str]) -> str:
    if name in env and str(env[name]).strip():
        return str(env[name]).strip()
    return str(env_file_values.get(name, "")).strip()


def _has_any_env(names: Sequence[str], env: Mapping[str, str], env_file_values: Mapping[str, str]) -> bool:
    return any(_env_value(name, env, env_file_values) for name in names)


def _missing_env(names: Sequence[str], env: Mapping[str, str], env_file_values: Mapping[str, str]) -> list[str]:
    return [name for name in names if not _env_value(name, env, env_file_values)]


def _missing_paths(repo: Path, relative_paths: Sequence[str]) -> list[str]:
    return [path for path in relative_paths if not (repo / path).exists()]


def _milestone(
    *,
    milestone_id: str,
    title: str,
    missing_env: Sequence[str],
    missing_files: Sequence[str],
    blockers: Sequence[str] = (),
) -> dict[str, object]:
    all_blockers = [*missing_env, *missing_files, *blockers]
    status = "ready_to_execute" if not all_blockers else "blocked"
    return {
        "id": milestone_id,
        "title": title,
        "status": status,
        "missing_env": list(missing_env),
        "missing_files": list(missing_files),
        "blockers": list(blockers),
        "commands": list(MILESTONE_COMMANDS[milestone_id]),
    }


def check_completion_readiness(
    *,
    repo: Path = REPO_ROOT,
    env: Mapping[str, str] | None = None,
    env_file: Path | None = None,
    stage_env_file: Path | None = None,
    prod_env_file: Path | None = None,
) -> dict[str, object]:
    resolved_repo = Path(repo).expanduser().resolve()
    effective_prod_env_file = prod_env_file or env_file or DEFAULT_PROD_ENV_FILE
    env_file_values = _load_env_file(env_file)
    active_env = {**env_file_values, **dict(os.environ if env is None else env)}
    stage_env_values = _load_env_file(stage_env_file)
    prod_env_values = _load_env_file(effective_prod_env_file)

    m1_missing_env = _missing_env(
        (
            "OPENAI_API_KEY",
            "GEMINI_API_KEY",
            "ANTHROPIC_API_KEY",
            "DECISIONDOC_LIVE_FALLBACK_FORCE_OPENAI_FAILURE",
        ),
        active_env,
        {},
    )
    m1_missing_files = _missing_paths(resolved_repo, ("tests/test_live_providers.py",))

    m2_missing_env = _missing_env(
        ("SMOKE_BASE_URL", "SMOKE_API_KEY", "G2B_API_KEY"),
        active_env,
        stage_env_values,
    )
    m2_missing_files = _missing_paths(
        resolved_repo,
        (
            "scripts/run_stage_procurement_smoke.py",
            "scripts/smoke.py",
            "app/services/g2b_collector.py",
            "docs/specs/public_procurement_copilot/STATUS.md",
        ),
    )

    m6_missing_env: list[str] = []
    if not _has_any_env(("ALLOWED_ORIGINS", "SMOKE_BASE_URL"), active_env, prod_env_values):
        m6_missing_env.append("ALLOWED_ORIGINS or SMOKE_BASE_URL")
    if not _has_any_env(("DECISIONDOC_API_KEYS", "DECISIONDOC_API_KEY", "SMOKE_API_KEY"), active_env, prod_env_values):
        m6_missing_env.append("DECISIONDOC_API_KEYS or DECISIONDOC_API_KEY or SMOKE_API_KEY")
    m6_missing_files = _missing_paths(
        resolved_repo,
        (
            "docker-compose.prod.yml",
            "infra/sam/template.yaml",
            "scripts/run_deployed_smoke.py",
            "scripts/smoke.py",
            "scripts/ops_smoke.py",
        ),
    )
    m6_blockers: list[str] = []
    if not Path(effective_prod_env_file).expanduser().exists():
        m6_blockers.append(f"prod env file not found: {Path(effective_prod_env_file).expanduser()}")

    milestones = [
        _milestone(
            milestone_id="M1",
            title="Live provider proof",
            missing_env=m1_missing_env,
            missing_files=m1_missing_files,
        ),
        _milestone(
            milestone_id="M2",
            title="G2B live procurement smoke",
            missing_env=m2_missing_env,
            missing_files=m2_missing_files,
        ),
        _milestone(
            milestone_id="M6",
            title="Deployment and post-deploy smoke proof",
            missing_env=m6_missing_env,
            missing_files=m6_missing_files,
            blockers=m6_blockers,
        ),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": all(item["status"] == "ready_to_execute" for item in milestones),
        "scope": "readiness only; no external proof executed",
        "milestones": milestones,
        "external_actions_excluded": list(EXCLUDED_EXTERNAL_ACTIONS),
    }


def write_json_artifact(path: Path, result: Mapping[str, object]) -> Path:
    resolved = Path(path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp = resolved.with_name(f".{resolved.name}.tmp.{uuid4().hex}")
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, resolved)
    finally:
        if tmp.exists():
            tmp.unlink()
    return resolved


def _print_text_report(result: Mapping[str, object]) -> None:
    print("DecisionDoc completion readiness")
    print("")
    print(f"scope={result['scope']}")
    print(f"status={'ready_to_execute' if result['ok'] else 'blocked'}")
    print("")
    for milestone in result["milestones"]:  # type: ignore[index]
        item = milestone
        print(f"[{item['status']}] {item['id']} {item['title']}")
        for env_name in item["missing_env"]:
            print(f"  missing_env: {env_name}")
        for file_name in item["missing_files"]:
            print(f"  missing_file: {file_name}")
        for blocker in item["blockers"]:
            print(f"  blocker: {blocker}")
        print("  commands:")
        for command in item["commands"]:
            print(f"    - {command}")
        print("")
    print("excluded_external_actions:")
    for action in result["external_actions_excluded"]:  # type: ignore[index]
        print(f"  - {action}")


def _print_env_template() -> None:
    print("\n".join(ENV_TEMPLATE_LINES))


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check local readiness for the remaining DecisionDoc completion milestones without external calls.",
    )
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--stage-env-file", type=Path, default=None)
    parser.add_argument("--prod-env-file", type=Path, default=None)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--output", type=Path, default=None, help="Write the JSON readiness result to this path.")
    parser.add_argument(
        "--print-env-template",
        action="store_true",
        help="Print a copy-paste env template for the remaining completion milestones.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    if args.print_env_template:
        _print_env_template()
        return 0
    result = check_completion_readiness(
        repo=args.repo,
        env_file=args.env_file,
        stage_env_file=args.stage_env_file,
        prod_env_file=args.prod_env_file,
    )
    if args.output is not None:
        write_json_artifact(args.output, result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_text_report(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
