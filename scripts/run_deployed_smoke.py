#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / ".env.prod"
DEFAULT_COMPOSE_FILE = REPO_ROOT / "docker-compose.prod.yml"
DEFAULT_SERVICE = "app"


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


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _required_value(name: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise SystemExit(f"Missing required value for {name}")
    return normalized


def _resolve_base_url(base_url: str, env_values: dict[str, str]) -> str:
    normalized = str(base_url or "").strip()
    if normalized:
        return normalized.rstrip("/")
    origins = _split_csv(env_values.get("ALLOWED_ORIGINS", ""))
    if origins:
        return origins[0].rstrip("/")
    raise SystemExit("Missing deployed smoke base URL. Pass --base-url or set ALLOWED_ORIGINS in the env file.")


def _resolve_api_key(api_key: str, env_values: dict[str, str]) -> str:
    normalized = str(api_key or "").strip()
    if normalized:
        return normalized
    keys = _split_csv(env_values.get("DECISIONDOC_API_KEYS", ""))
    if keys:
        return keys[0]
    legacy_key = env_values.get("DECISIONDOC_API_KEY", "").strip()
    if legacy_key:
        return legacy_key
    raise SystemExit("Missing deployed smoke API key. Set DECISIONDOC_API_KEYS or pass --api-key.")


def _resolve_provider(provider: str, env_values: dict[str, str]) -> str:
    normalized = str(provider or "").strip()
    if normalized:
        return normalized
    providers = _split_csv(env_values.get("DECISIONDOC_PROVIDER", ""))
    if providers:
        return providers[0]
    return "mock"


def run_deployed_smoke(
    *,
    env_file: Path,
    compose_file: Path,
    service: str,
    base_url: str = "",
    api_key: str = "",
    provider: str = "",
) -> int:
    resolved_env_file = Path(env_file).expanduser()
    resolved_compose_file = Path(compose_file).expanduser()
    if not resolved_compose_file.exists():
        raise SystemExit(f"Compose file not found: {resolved_compose_file}")

    env_values = _load_env_file(resolved_env_file)
    resolved_base_url = _resolve_base_url(base_url, env_values)
    resolved_api_key = _resolve_api_key(api_key, env_values)
    resolved_provider = _resolve_provider(provider, env_values)
    resolved_service = _required_value("service", service)

    command = [
        "docker",
        "compose",
        "--env-file",
        str(resolved_env_file),
        "-f",
        str(resolved_compose_file),
        "exec",
        "-T",
        "-e",
        f"SMOKE_BASE_URL={resolved_base_url}",
        "-e",
        f"SMOKE_API_KEY={resolved_api_key}",
        "-e",
        f"SMOKE_PROVIDER={resolved_provider}",
        resolved_service,
        "python",
        "scripts/smoke.py",
    ]
    completed = subprocess.run(command, cwd=REPO_ROOT, check=False)
    return int(completed.returncode)


def _suggested_command(*, env_file: Path, compose_file: Path, service: str) -> str:
    return (
        ".venv/bin/python scripts/run_deployed_smoke.py "
        f"--env-file {Path(env_file).expanduser()} "
        f"--compose-file {Path(compose_file).expanduser()} "
        f"--service {service}"
    )


def _print_env_template(*, env_file: Path, compose_file: Path, service: str) -> None:
    print("# Required", flush=True)
    print("ALLOWED_ORIGINS=https://your-domain.example.com", flush=True)
    print("DECISIONDOC_API_KEYS=your-runtime-api-key", flush=True)
    print("DECISIONDOC_PROVIDER=openai", flush=True)
    print("", flush=True)
    print("# Run", flush=True)
    print(_suggested_command(env_file=env_file, compose_file=compose_file, service=service), flush=True)


def _run_preflight(*, env_file: Path, base_url: str, api_key: str, provider: str) -> int:
    env_values = _load_env_file(env_file)
    resolved_base_url = _resolve_base_url(base_url, env_values)
    resolved_api_key = _resolve_api_key(api_key, env_values)
    resolved_provider = _resolve_provider(provider, env_values)

    print("Deployed smoke preflight", flush=True)
    print("", flush=True)
    print(f"[ok] SMOKE_BASE_URL={resolved_base_url}", flush=True)
    print(f"[ok] SMOKE_API_KEY={'set' if resolved_api_key else 'missing'}", flush=True)
    print(f"[ok] SMOKE_PROVIDER={resolved_provider}", flush=True)
    print("", flush=True)
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the standard DecisionDoc smoke against a deployed docker-compose environment.",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="Path to the deployment env file. Default: .env.prod in repo root",
    )
    parser.add_argument(
        "--compose-file",
        default=str(DEFAULT_COMPOSE_FILE),
        help="Path to the docker compose file. Default: docker-compose.prod.yml",
    )
    parser.add_argument(
        "--service",
        default=DEFAULT_SERVICE,
        help="Compose service name that contains the app runtime. Default: app",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="Override SMOKE_BASE_URL. Defaults to the first ALLOWED_ORIGINS value in the env file.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Override SMOKE_API_KEY. Defaults to the first DECISIONDOC_API_KEYS entry or DECISIONDOC_API_KEY.",
    )
    parser.add_argument(
        "--provider",
        default="",
        help="Override SMOKE_PROVIDER. Defaults to DECISIONDOC_PROVIDER from the env file.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Print resolved smoke inputs without executing the smoke script.",
    )
    parser.add_argument(
        "--print-env-template",
        action="store_true",
        help="Print a minimal env template and suggested command.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else None)
    env_file = Path(args.env_file).expanduser()
    compose_file = Path(args.compose_file).expanduser()
    if args.print_env_template:
        _print_env_template(env_file=env_file, compose_file=compose_file, service=args.service)
        return 0
    if args.preflight:
        return _run_preflight(
            env_file=env_file,
            base_url=args.base_url,
            api_key=args.api_key,
            provider=args.provider,
        )
    return run_deployed_smoke(
        env_file=env_file,
        compose_file=compose_file,
        service=args.service,
        base_url=args.base_url,
        api_key=args.api_key,
        provider=args.provider,
    )


if __name__ == "__main__":
    raise SystemExit(main())
