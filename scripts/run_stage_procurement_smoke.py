#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / "scripts" / "stage_procurement_smoke.env.example"

DEFAULT_PROVIDER = "mock"
DEFAULT_TIMEOUT_SEC = 30.0

REQUIRED_STAGE_PREREQS = (
    "SMOKE_BASE_URL",
    "SMOKE_API_KEY",
    "SMOKE_PROCUREMENT_URL_OR_NUMBER",
    "G2B_API_KEY",
)
OPTIONAL_STAGE_PREREQS = (
    "SMOKE_OPS_KEY",
    "SMOKE_PROVIDER",
    "SMOKE_TIMEOUT_SEC",
    "SMOKE_TENANT_ID",
    "PROCUREMENT_SMOKE_USERNAME",
    "PROCUREMENT_SMOKE_PASSWORD",
)


def _required_value(name: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise SystemExit(f"Missing required value for {name}")
    return normalized


def _load_env_file(env_file: Path | None) -> dict[str, str]:
    if env_file is None:
        return {}
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


def _lookup_env(name: str, env_overrides: dict[str, str]) -> str:
    if name in env_overrides:
        return str(env_overrides.get(name, "")).strip()
    return os.getenv(name, "").strip()


def _resolve_required_env(cli_value: str, env_name: str, env_overrides: dict[str, str]) -> str:
    normalized = str(cli_value or "").strip()
    if normalized:
        return normalized
    env_value = _lookup_env(env_name, env_overrides)
    if env_value:
        return env_value
    raise SystemExit(
        f"Missing required procurement smoke prerequisite: {env_name}. "
        "Set it in the environment, env file, or pass the matching CLI flag."
    )


def _resolve_optional_env(
    cli_value: str,
    env_name: str,
    env_overrides: dict[str, str],
    *,
    default: str = "",
) -> str:
    normalized = str(cli_value or "").strip()
    if normalized:
        return normalized
    env_value = _lookup_env(env_name, env_overrides)
    if env_value:
        return env_value
    return default


def _suggested_command(*, env_file: Path | None = None) -> str:
    if env_file is not None:
        return f".venv/bin/python scripts/run_stage_procurement_smoke.py --env-file {Path(env_file).expanduser()}"
    return (
        "SMOKE_BASE_URL=https://your-stage.example.com \\\n"
        "SMOKE_API_KEY=your-stage-api-key \\\n"
        "G2B_API_KEY=your-data-go-kr-key \\\n"
        "SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00 \\\n"
        ".venv/bin/python scripts/run_stage_procurement_smoke.py"
    )


def _print_env_template(*, env_file: Path | None = None) -> None:
    print("# Required", flush=True)
    print("export SMOKE_BASE_URL=https://your-stage.example.com", flush=True)
    print("export SMOKE_API_KEY=your-stage-api-key", flush=True)
    print("export G2B_API_KEY=your-data-go-kr-key", flush=True)
    print("export SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00", flush=True)
    print("", flush=True)
    print("# Optional", flush=True)
    print("export SMOKE_OPS_KEY=", flush=True)
    print(f"export SMOKE_PROVIDER={DEFAULT_PROVIDER}", flush=True)
    print(f"export SMOKE_TIMEOUT_SEC={DEFAULT_TIMEOUT_SEC}", flush=True)
    print("export SMOKE_TENANT_ID=system", flush=True)
    print("export PROCUREMENT_SMOKE_USERNAME=", flush=True)
    print("export PROCUREMENT_SMOKE_PASSWORD=", flush=True)
    print("", flush=True)
    print("# Run", flush=True)
    print(_suggested_command(env_file=env_file), flush=True)
    if env_file is not None:
        print("", flush=True)
        print("# Or edit the example env file directly", flush=True)
        print(f"# example file: {Path(env_file).expanduser()}", flush=True)


def _run_preflight(
    *,
    base_url: str,
    api_key: str,
    procurement_url_or_number: str,
    g2b_api_key: str,
    env_overrides: dict[str, str],
    env_file: Path | None = None,
) -> int:
    resolved_values = {
        "SMOKE_BASE_URL": str(base_url or "").strip() or _lookup_env("SMOKE_BASE_URL", env_overrides),
        "SMOKE_API_KEY": str(api_key or "").strip() or _lookup_env("SMOKE_API_KEY", env_overrides),
        "SMOKE_PROCUREMENT_URL_OR_NUMBER": str(procurement_url_or_number or "").strip()
        or _lookup_env("SMOKE_PROCUREMENT_URL_OR_NUMBER", env_overrides),
        "G2B_API_KEY": str(g2b_api_key or "").strip() or _lookup_env("G2B_API_KEY", env_overrides),
    }
    print("Stage procurement smoke preflight", flush=True)
    print("", flush=True)
    missing_required = False
    for env_name in REQUIRED_STAGE_PREREQS:
        value = resolved_values.get(env_name, "")
        if value:
            print(f"[ok] {env_name}", flush=True)
        else:
            print(f"[missing] {env_name}", flush=True)
            missing_required = True
    print("", flush=True)
    for env_name in OPTIONAL_STAGE_PREREQS:
        value = _lookup_env(env_name, env_overrides)
        status = "set" if value else "unset"
        print(f"[info] {env_name}={status}", flush=True)
    print("", flush=True)
    print("Suggested command", flush=True)
    print(_suggested_command(env_file=env_file), flush=True)
    return 1 if missing_required else 0


def _build_smoke_env(
    *,
    base_url: str,
    api_key: str,
    provider: str,
    timeout_sec: float,
    procurement_url_or_number: str,
    g2b_api_key: str,
    ops_key: str,
    tenant_id: str,
    username: str,
    password: str,
    env_overrides: dict[str, str],
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(env_overrides)
    env["SMOKE_BASE_URL"] = base_url
    env["SMOKE_API_KEY"] = api_key
    env["SMOKE_PROVIDER"] = provider
    env["SMOKE_TIMEOUT_SEC"] = str(timeout_sec)
    env["SMOKE_INCLUDE_PROCUREMENT"] = "1"
    env["SMOKE_PROCUREMENT_URL_OR_NUMBER"] = procurement_url_or_number
    env["G2B_API_KEY"] = g2b_api_key
    if ops_key:
        env["SMOKE_OPS_KEY"] = ops_key
    if tenant_id:
        env["SMOKE_TENANT_ID"] = tenant_id
    if username:
        env["PROCUREMENT_SMOKE_USERNAME"] = username
    if password:
        env["PROCUREMENT_SMOKE_PASSWORD"] = password
    return env


def run_stage_procurement_smoke(
    *,
    base_url: str,
    api_key: str,
    procurement_url_or_number: str,
    g2b_api_key: str,
    provider: str = DEFAULT_PROVIDER,
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    ops_key: str = "",
    tenant_id: str = "",
    username: str = "",
    password: str = "",
    env_overrides: dict[str, str] | None = None,
) -> int:
    active_env_overrides = dict(env_overrides or {})
    resolved_base_url = _required_value("base_url", base_url).rstrip("/")
    resolved_api_key = _required_value("api_key", api_key)
    resolved_procurement_target = _required_value("procurement_url_or_number", procurement_url_or_number)
    resolved_g2b_api_key = _required_value("g2b_api_key", g2b_api_key)
    resolved_provider = _required_value("provider", provider)
    smoke_env = _build_smoke_env(
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        provider=resolved_provider,
        timeout_sec=float(timeout_sec),
        procurement_url_or_number=resolved_procurement_target,
        g2b_api_key=resolved_g2b_api_key,
        ops_key=str(ops_key or "").strip(),
        tenant_id=str(tenant_id or "").strip(),
        username=str(username or "").strip(),
        password=str(password or "").strip(),
        env_overrides=active_env_overrides,
    )
    smoke_command = [sys.executable, "scripts/smoke.py"]
    print(f"Running stage procurement smoke against {resolved_base_url}", flush=True)
    print(f"Procurement target: {resolved_procurement_target}", flush=True)
    completed = subprocess.run(smoke_command, cwd=REPO_ROOT, env=smoke_env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)
    print("", flush=True)
    print("Stage procurement smoke completed.", flush=True)
    return 0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the deployed procurement live smoke lane against an existing base URL.",
    )
    parser.add_argument("--base-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--ops-key", default="")
    parser.add_argument("--timeout-sec", type=float, default=None)
    parser.add_argument("--procurement-url-or-number", default="")
    parser.add_argument("--g2b-api-key", default="")
    parser.add_argument("--tenant-id", default="")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Check required deployed procurement smoke env/flags and print the suggested run command without executing the smoke.",
    )
    parser.add_argument(
        "--print-env-template",
        action="store_true",
        help="Print a copy-paste env template and example command without running anything.",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    active_argv = list(argv if argv is not None else sys.argv[1:])
    args = _parse_args(active_argv)
    env_file = Path(str(args.env_file).strip()).expanduser() if str(args.env_file).strip() else None
    env_overrides = _load_env_file(env_file)
    if bool(args.print_env_template):
        _print_env_template(env_file=env_file or DEFAULT_ENV_FILE)
        return 0
    if bool(args.preflight):
        return _run_preflight(
            base_url=str(args.base_url).strip(),
            api_key=str(args.api_key).strip(),
            procurement_url_or_number=str(args.procurement_url_or_number).strip(),
            g2b_api_key=str(args.g2b_api_key).strip(),
            env_overrides=env_overrides,
            env_file=env_file,
        )
    resolved_base_url = _resolve_required_env(
        str(args.base_url).strip(),
        "SMOKE_BASE_URL",
        env_overrides,
    )
    resolved_api_key = _resolve_required_env(
        str(args.api_key).strip(),
        "SMOKE_API_KEY",
        env_overrides,
    )
    resolved_procurement_target = _resolve_required_env(
        str(args.procurement_url_or_number).strip(),
        "SMOKE_PROCUREMENT_URL_OR_NUMBER",
        env_overrides,
    )
    resolved_g2b_api_key = _resolve_required_env(
        str(args.g2b_api_key).strip(),
        "G2B_API_KEY",
        env_overrides,
    )
    resolved_provider = _resolve_optional_env(
        str(args.provider).strip(),
        "SMOKE_PROVIDER",
        env_overrides,
        default=DEFAULT_PROVIDER,
    )
    resolved_ops_key = _resolve_optional_env(
        str(args.ops_key).strip(),
        "SMOKE_OPS_KEY",
        env_overrides,
    )
    resolved_tenant_id = _resolve_optional_env(
        str(args.tenant_id).strip(),
        "SMOKE_TENANT_ID",
        env_overrides,
    )
    resolved_username = _resolve_optional_env(
        str(args.username).strip(),
        "PROCUREMENT_SMOKE_USERNAME",
        env_overrides,
    )
    resolved_password = _resolve_optional_env(
        str(args.password).strip(),
        "PROCUREMENT_SMOKE_PASSWORD",
        env_overrides,
    )
    resolved_timeout = _resolve_optional_env(
        "" if args.timeout_sec is None else str(args.timeout_sec),
        "SMOKE_TIMEOUT_SEC",
        env_overrides,
        default=str(DEFAULT_TIMEOUT_SEC),
    )
    return run_stage_procurement_smoke(
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        procurement_url_or_number=resolved_procurement_target,
        g2b_api_key=resolved_g2b_api_key,
        provider=resolved_provider,
        timeout_sec=float(resolved_timeout),
        ops_key=resolved_ops_key,
        tenant_id=resolved_tenant_id,
        username=resolved_username,
        password=resolved_password,
        env_overrides=env_overrides,
    )


if __name__ == "__main__":
    raise SystemExit(main())
