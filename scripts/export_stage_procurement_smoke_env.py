#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ENV_FILE = REPO_ROOT / ".github-actions.env"
DEFAULT_PROVIDER = "mock"
DEFAULT_TIMEOUT_SEC = "30"
DEFAULT_STACK_NAME_PREFIX = "decisiondoc-ai-"


def _load_env_file(env_file: Path) -> dict[str, str]:
    resolved = Path(env_file).expanduser()
    if not resolved.exists():
        raise SystemExit(f"Env file not found: {resolved}")
    loaded: dict[str, str] = {}
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
        loaded[normalized_key] = normalized_value
    return loaded


def _resolve_required(name: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise SystemExit(f"Missing required value for {name}")
    return normalized


def _resolve_required_cli_or_env(cli_value: str, env_name: str) -> str:
    normalized = str(cli_value or "").strip()
    if normalized:
        return normalized
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value
    raise SystemExit(
        f"Missing required stage smoke export prerequisite: {env_name}. "
        "Set it in the environment or pass the matching CLI flag."
    )


def _resolve_optional_cli_or_env(cli_value: str, env_name: str, *, default: str = "") -> str:
    normalized = str(cli_value or "").strip()
    if normalized:
        return normalized
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value
    return default


def _resolve_required_cli_env_or_loaded(cli_value: str, env_name: str, loaded_env: dict[str, str]) -> str:
    normalized = str(cli_value or "").strip()
    if normalized:
        return normalized
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value
    loaded_value = str(loaded_env.get(env_name, "")).strip()
    if loaded_value:
        return loaded_value
    raise SystemExit(
        f"Missing required stage smoke export prerequisite: {env_name}. "
        "Set it in the CLI, process environment, or env file."
    )


def _resolve_optional_cli_env_or_loaded(
    cli_value: str,
    env_name: str,
    loaded_env: dict[str, str],
    *,
    default: str = "",
) -> str:
    normalized = str(cli_value or "").strip()
    if normalized:
        return normalized
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value
    loaded_value = str(loaded_env.get(env_name, "")).strip()
    if loaded_value:
        return loaded_value
    return default


def _get_loaded_required(loaded_env: dict[str, str], name: str) -> str:
    return _resolve_required(name, loaded_env.get(name, ""))


def _get_loaded_optional(loaded_env: dict[str, str], name: str) -> str:
    return str(loaded_env.get(name, "")).strip()


def _resolve_base_url_from_stack(*, stack_name: str, aws_region: str) -> str:
    command = [
        "aws",
        "cloudformation",
        "describe-stacks",
        "--stack-name",
        stack_name,
        "--region",
        aws_region,
        "--query",
        "Stacks[0].Outputs[?OutputKey==`HttpApiUrl`].OutputValue",
        "--output",
        "text",
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise SystemExit(
            f"Failed to resolve HttpApiUrl from stack {stack_name} in {aws_region}: "
            f"{detail or f'aws exited with code {completed.returncode}'}"
        )
    resolved = str(completed.stdout or "").strip()
    if not resolved or resolved == "None":
        raise SystemExit(
            f"Missing HttpApiUrl stack output for {stack_name} in {aws_region}"
        )
    return resolved.rstrip("/")


def _render_output_lines(
    *,
    base_url: str,
    api_key: str,
    g2b_api_key: str,
    procurement_url_or_number: str,
    provider: str,
    timeout_sec: str,
    ops_key: str,
    tenant_id: str,
    username: str,
    password: str,
) -> list[str]:
    lines = [
        "# Generated stage procurement smoke env",
        f"SMOKE_BASE_URL={base_url}",
        f"SMOKE_API_KEY={api_key}",
        f"G2B_API_KEY={g2b_api_key}",
        f"SMOKE_PROCUREMENT_URL_OR_NUMBER={procurement_url_or_number}",
        f"SMOKE_PROVIDER={provider}",
        f"SMOKE_TIMEOUT_SEC={timeout_sec}",
        f"SMOKE_OPS_KEY={ops_key}",
        f"SMOKE_TENANT_ID={tenant_id}",
        f"PROCUREMENT_SMOKE_USERNAME={username}",
        f"PROCUREMENT_SMOKE_PASSWORD={password}",
    ]
    return lines


def build_stage_procurement_smoke_env_values(
    *,
    stage: str,
    input_env_file: Path,
    base_url: str = "",
    resolve_base_url_from_stack: bool = False,
    stack_name: str = "",
    aws_region: str = "",
    provider: str = DEFAULT_PROVIDER,
    timeout_sec: str = DEFAULT_TIMEOUT_SEC,
) -> dict[str, str]:
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage not in {"dev", "prod"}:
        raise SystemExit("stage must be one of: dev, prod")
    loaded_env = _load_env_file(input_env_file)
    stage_upper = normalized_stage.upper()
    if bool(resolve_base_url_from_stack):
        resolved_stack_name = _resolve_optional_cli_env_or_loaded(
            str(stack_name).strip(),
            "SMOKE_STACK_NAME",
            loaded_env,
            default=f"{DEFAULT_STACK_NAME_PREFIX}{normalized_stage}",
        )
        resolved_region = _resolve_required_cli_env_or_loaded(
            str(aws_region).strip(),
            "AWS_REGION",
            loaded_env,
        )
        resolved_base_url = _resolve_base_url_from_stack(
            stack_name=resolved_stack_name,
            aws_region=resolved_region,
        )
    else:
        resolved_base_url = _resolve_required_cli_env_or_loaded(
            str(base_url).strip(),
            "SMOKE_BASE_URL",
            loaded_env,
        )
    resolved_provider = _resolve_optional_cli_or_env(
        str(provider).strip(),
        "SMOKE_PROVIDER",
        default=DEFAULT_PROVIDER,
    )
    resolved_timeout = _resolve_optional_cli_or_env(
        str(timeout_sec).strip(),
        "SMOKE_TIMEOUT_SEC",
        default=DEFAULT_TIMEOUT_SEC,
    )
    return {
        "SMOKE_BASE_URL": resolved_base_url.rstrip("/"),
        "SMOKE_API_KEY": _get_loaded_required(loaded_env, "DECISIONDOC_API_KEY"),
        "G2B_API_KEY": _get_loaded_required(loaded_env, f"G2B_API_KEY_{stage_upper}"),
        "SMOKE_PROCUREMENT_URL_OR_NUMBER": _get_loaded_optional(
            loaded_env,
            f"PROCUREMENT_SMOKE_URL_OR_NUMBER_{stage_upper}",
        ),
        "SMOKE_PROVIDER": _resolve_required("provider", resolved_provider),
        "SMOKE_TIMEOUT_SEC": _resolve_required("timeout_sec", resolved_timeout),
        "SMOKE_OPS_KEY": _get_loaded_optional(loaded_env, "DECISIONDOC_OPS_KEY"),
        "SMOKE_TENANT_ID": _get_loaded_optional(loaded_env, f"PROCUREMENT_SMOKE_TENANT_ID_{stage_upper}"),
        "PROCUREMENT_SMOKE_USERNAME": _get_loaded_optional(
            loaded_env,
            f"PROCUREMENT_SMOKE_USERNAME_{stage_upper}",
        ),
        "PROCUREMENT_SMOKE_PASSWORD": _get_loaded_optional(
            loaded_env,
            f"PROCUREMENT_SMOKE_PASSWORD_{stage_upper}",
        ),
    }


def export_stage_procurement_smoke_env(
    *,
    stage: str,
    input_env_file: Path,
    output_env_file: Path,
    base_url: str,
    resolve_base_url_from_stack: bool = False,
    stack_name: str = "",
    aws_region: str = "",
    provider: str = DEFAULT_PROVIDER,
    timeout_sec: str = DEFAULT_TIMEOUT_SEC,
) -> Path:
    normalized_stage = str(stage or "").strip().lower()
    env_values = build_stage_procurement_smoke_env_values(
        stage=normalized_stage,
        input_env_file=input_env_file,
        base_url=base_url,
        resolve_base_url_from_stack=resolve_base_url_from_stack,
        stack_name=stack_name,
        aws_region=aws_region,
        provider=provider,
        timeout_sec=timeout_sec,
    )
    rendered_lines = _render_output_lines(
        base_url=env_values["SMOKE_BASE_URL"],
        api_key=env_values["SMOKE_API_KEY"],
        g2b_api_key=env_values["G2B_API_KEY"],
        procurement_url_or_number=env_values["SMOKE_PROCUREMENT_URL_OR_NUMBER"],
        provider=env_values["SMOKE_PROVIDER"],
        timeout_sec=env_values["SMOKE_TIMEOUT_SEC"],
        ops_key=env_values["SMOKE_OPS_KEY"],
        tenant_id=env_values["SMOKE_TENANT_ID"],
        username=env_values["PROCUREMENT_SMOKE_USERNAME"],
        password=env_values["PROCUREMENT_SMOKE_PASSWORD"],
    )
    output_path = Path(output_env_file).expanduser()
    output_path.write_text("\n".join(rendered_lines) + "\n", encoding="utf-8")
    print(f"Generated stage procurement smoke env: {output_path}", flush=True)
    print(f"Stage: {normalized_stage}", flush=True)
    print(f"Base URL: {env_values['SMOKE_BASE_URL']}", flush=True)
    return output_path


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a deployed stage procurement smoke env file from .github-actions.env-style stage values.",
    )
    parser.add_argument("--stage", required=True, choices=["dev", "prod"])
    parser.add_argument("--env-file", default=str(DEFAULT_INPUT_ENV_FILE))
    parser.add_argument("--output", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--resolve-base-url-from-stack", action="store_true")
    parser.add_argument("--stack-name", default="")
    parser.add_argument("--aws-region", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--timeout-sec", default="")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    active_argv = list(argv if argv is not None else sys.argv[1:])
    args = _parse_args(active_argv)
    stage = str(args.stage).strip().lower()
    input_env_file = Path(str(args.env_file).strip()).expanduser()
    output_env_file = Path(
        str(args.output).strip()
        or f"/tmp/stage_procurement_smoke.{stage}.env"
    ).expanduser()
    export_stage_procurement_smoke_env(
        stage=stage,
        input_env_file=input_env_file,
        output_env_file=output_env_file,
        base_url=str(args.base_url).strip(),
        resolve_base_url_from_stack=bool(args.resolve_base_url_from_stack),
        stack_name=str(args.stack_name).strip(),
        aws_region=str(args.aws_region).strip(),
        provider=str(args.provider).strip(),
        timeout_sec=str(args.timeout_sec).strip(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
