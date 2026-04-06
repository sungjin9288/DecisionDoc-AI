#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = REPO_ROOT / "scripts" / "local_procurement_smoke.env.example"

DEFAULT_DATA_DIR = Path("/tmp/decisiondoc-local-procurement-smoke")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8902
DEFAULT_API_KEY = "local-procurement-smoke-api-key"
DEFAULT_OPS_KEY = "local-procurement-smoke-ops-key"
DEFAULT_JWT_SECRET = "test-local-procurement-smoke-secret-32chars"
REQUIRED_PROCUREMENT_PREREQS = ("SMOKE_PROCUREMENT_URL_OR_NUMBER", "G2B_API_KEY")
OPTIONAL_PROCUREMENT_PREREQS = (
    "SMOKE_TENANT_ID",
    "PROCUREMENT_SMOKE_USERNAME",
    "PROCUREMENT_SMOKE_PASSWORD",
)


def _required_value(name: str, value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise SystemExit(f"Missing required value for {name}")
    return normalized


def _resolve_required_env(cli_value: str, env_name: str) -> str:
    normalized = str(cli_value or "").strip()
    if normalized:
        return normalized
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value
    raise SystemExit(
        f"Missing required procurement smoke prerequisite: {env_name}. "
        "Set it in the environment or pass the matching CLI flag."
    )


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


def _suggested_command(*, port: int, data_dir: Path, env_file: Path | None = None) -> str:
    if env_file is not None:
        return (
            f"JWT_SECRET_KEY={DEFAULT_JWT_SECRET} "
            f".venv/bin/python scripts/run_local_procurement_smoke.py --env-file {Path(env_file).expanduser()} --port {int(port)} --data-dir {data_dir}"
        )
    return (
        "G2B_API_KEY=... \\\n"
        f"JWT_SECRET_KEY={DEFAULT_JWT_SECRET} \\\n"
        "SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00 \\\n"
        f".venv/bin/python scripts/run_local_procurement_smoke.py --port {int(port)} --data-dir {data_dir}"
    )


def _print_env_template(*, port: int, data_dir: Path, env_file: Path | None = None) -> None:
    print("# Required", flush=True)
    print("export G2B_API_KEY=your-data-go-kr-key", flush=True)
    print("export SMOKE_PROCUREMENT_URL_OR_NUMBER=20260405001-00", flush=True)
    print("", flush=True)
    print("# Optional", flush=True)
    print("export SMOKE_TENANT_ID=system", flush=True)
    print("export PROCUREMENT_SMOKE_USERNAME=", flush=True)
    print("export PROCUREMENT_SMOKE_PASSWORD=", flush=True)
    print(f"export JWT_SECRET_KEY={DEFAULT_JWT_SECRET}", flush=True)
    print("", flush=True)
    print("# Run", flush=True)
    print(_suggested_command(port=port, data_dir=data_dir, env_file=env_file), flush=True)
    if env_file is not None:
        print("", flush=True)
        print("# Or edit the example env file directly", flush=True)
        print(f"# example file: {Path(env_file).expanduser()}", flush=True)
        print("# recommended: keep the inline JWT_SECRET_KEY prefix so the top-level Python process starts with the validated local auth secret", flush=True)


def _run_preflight(
    *,
    procurement_url_or_number: str,
    g2b_api_key: str,
    port: int,
    data_dir: Path,
    env_overrides: dict[str, str],
    env_file: Path | None = None,
) -> int:
    resolved_values = {
        "SMOKE_PROCUREMENT_URL_OR_NUMBER": str(procurement_url_or_number or "").strip() or _lookup_env("SMOKE_PROCUREMENT_URL_OR_NUMBER", env_overrides),
        "G2B_API_KEY": str(g2b_api_key or "").strip() or _lookup_env("G2B_API_KEY", env_overrides),
    }
    print("Local procurement smoke preflight", flush=True)
    print("", flush=True)
    missing_required = False
    for env_name in REQUIRED_PROCUREMENT_PREREQS:
        value = resolved_values.get(env_name, "")
        if value:
            print(f"[ok] {env_name}", flush=True)
        else:
            print(f"[missing] {env_name}", flush=True)
            missing_required = True
    print("", flush=True)
    for env_name in OPTIONAL_PROCUREMENT_PREREQS:
        value = _lookup_env(env_name, env_overrides)
        status = "set" if value else "unset"
        print(f"[info] {env_name}={status}", flush=True)
    print("", flush=True)
    print("Suggested command", flush=True)
    print(_suggested_command(port=port, data_dir=data_dir, env_file=env_file), flush=True)
    return 1 if missing_required else 0


def _build_base_url(host: str, port: int, base_url: str | None) -> str:
    if base_url and str(base_url).strip():
        return str(base_url).strip().rstrip("/")
    normalized_host = "127.0.0.1" if host == "0.0.0.0" else host
    return f"http://{normalized_host}:{int(port)}"


def _wait_for_health(
    base_url: str,
    *,
    process: subprocess.Popen[bytes | str] | None = None,
    timeout_seconds: float = 20.0,
    interval_seconds: float = 0.5,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: str = "unknown"
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise SystemExit(f"Local procurement smoke server exited before /health became ready (code={process.returncode})")
        try:
            response = httpx.get(f"{base_url}/health", timeout=2.0)
            if response.status_code == 200:
                return
            last_error = f"status={response.status_code}"
        except Exception as exc:  # pragma: no cover - exercised via live run
            last_error = str(exc)
        time.sleep(interval_seconds)
    raise SystemExit(f"Timed out waiting for {base_url}/health: {last_error}")


def _terminate_server(process: subprocess.Popen[bytes | str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _build_server_env(
    *,
    data_dir: Path,
    provider: str,
    api_key: str,
    ops_key: str,
    g2b_api_key: str,
    env_overrides: dict[str, str],
) -> dict[str, str]:
    env = os.environ.copy()
    env.update(env_overrides)
    env["DATA_DIR"] = str(data_dir)
    env["DECISIONDOC_ENV"] = "dev"
    env["DECISIONDOC_PROVIDER"] = provider
    env["DECISIONDOC_STORAGE"] = "local"
    env["DECISIONDOC_PROCUREMENT_COPILOT_ENABLED"] = "1"
    env["DECISIONDOC_SEARCH_ENABLED"] = "0"
    env["DECISIONDOC_API_KEY"] = api_key
    env["DECISIONDOC_OPS_KEY"] = ops_key
    env["JWT_SECRET_KEY"] = env.get("JWT_SECRET_KEY", DEFAULT_JWT_SECRET)
    env["G2B_API_KEY"] = g2b_api_key
    return env


def _build_smoke_env(
    *,
    base_url: str,
    provider: str,
    api_key: str,
    ops_key: str,
    g2b_api_key: str,
    procurement_url_or_number: str,
    timeout_sec: float,
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
    env["SMOKE_OPS_KEY"] = ops_key
    env["G2B_API_KEY"] = g2b_api_key
    for optional_name in (
        "SMOKE_TENANT_ID",
        "PROCUREMENT_SMOKE_USERNAME",
        "PROCUREMENT_SMOKE_PASSWORD",
    ):
        optional_value = _lookup_env(optional_name, env_overrides)
        if optional_value:
            env[optional_name] = optional_value
    return env


def run_local_procurement_smoke(
    *,
    data_dir: Path,
    procurement_url_or_number: str,
    g2b_api_key: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    base_url: str | None = None,
    provider: str = "mock",
    api_key: str = DEFAULT_API_KEY,
    ops_key: str = DEFAULT_OPS_KEY,
    timeout_sec: float = 30.0,
    keep_running: bool = False,
    env_overrides: dict[str, str] | None = None,
) -> int:
    active_env_overrides = dict(env_overrides or {})
    resolved_procurement_target = _required_value("procurement_url_or_number", procurement_url_or_number)
    resolved_g2b_api_key = _required_value("g2b_api_key", g2b_api_key)
    resolved_provider = _required_value("provider", provider)
    resolved_api_key = _required_value("api_key", api_key)
    resolved_ops_key = _required_value("ops_key", ops_key)
    resolved_base_url = _build_base_url(host, port, base_url)
    server_env = _build_server_env(
        data_dir=data_dir,
        provider=resolved_provider,
        api_key=resolved_api_key,
        ops_key=resolved_ops_key,
        g2b_api_key=resolved_g2b_api_key,
        env_overrides=active_env_overrides,
    )
    smoke_env = _build_smoke_env(
        base_url=resolved_base_url,
        provider=resolved_provider,
        api_key=resolved_api_key,
        ops_key=resolved_ops_key,
        g2b_api_key=resolved_g2b_api_key,
        procurement_url_or_number=resolved_procurement_target,
        timeout_sec=timeout_sec,
        env_overrides=active_env_overrides,
    )

    server_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]
    smoke_command = [sys.executable, "scripts/smoke.py"]

    print(f"Starting local procurement smoke server on {resolved_base_url}", flush=True)
    print(f"DATA_DIR: {data_dir}", flush=True)
    print(f"Procurement target: {resolved_procurement_target}", flush=True)
    server_process = subprocess.Popen(server_command, cwd=REPO_ROOT, env=server_env)
    try:
        _wait_for_health(resolved_base_url, process=server_process)
        print("", flush=True)
        print("Running procurement smoke against the local app...", flush=True)
        completed = subprocess.run(smoke_command, cwd=REPO_ROOT, env=smoke_env, check=False)
        if completed.returncode != 0:
            raise SystemExit(completed.returncode)
        print("", flush=True)
        print("Local procurement smoke completed.", flush=True)
        if keep_running:
            print("Server is still running for manual verification. Press Ctrl-C to stop.", flush=True)
            while True:
                time.sleep(1.0)
        return 0
    except KeyboardInterrupt:
        print("", flush=True)
        print("Stopping local procurement smoke server...", flush=True)
        return 0
    finally:
        _terminate_server(server_process)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a local app and run the procurement live smoke lane against it.",
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--base-url", default="")
    parser.add_argument("--provider", default=os.getenv("SMOKE_PROVIDER", "mock"))
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--ops-key", default=os.getenv("SMOKE_OPS_KEY", DEFAULT_OPS_KEY))
    parser.add_argument("--timeout-sec", type=float, default=30.0)
    parser.add_argument("--keep-running", action="store_true")
    parser.add_argument("--procurement-url-or-number", default="")
    parser.add_argument("--g2b-api-key", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Check required procurement smoke env/flags and print the suggested run command without starting the app.",
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
    data_dir = Path(str(args.data_dir)).expanduser()
    env_file = Path(str(args.env_file).strip()).expanduser() if str(args.env_file).strip() else None
    env_overrides = _load_env_file(env_file)
    if bool(args.print_env_template):
        _print_env_template(port=int(args.port), data_dir=data_dir, env_file=env_file or DEFAULT_ENV_FILE)
        return 0
    if bool(args.preflight):
        return _run_preflight(
            procurement_url_or_number=str(args.procurement_url_or_number).strip(),
            g2b_api_key=str(args.g2b_api_key).strip(),
            port=int(args.port),
            data_dir=data_dir,
            env_overrides=env_overrides,
            env_file=env_file,
        )
    resolved_procurement_target = _resolve_required_env(
        str(args.procurement_url_or_number).strip() or _lookup_env("SMOKE_PROCUREMENT_URL_OR_NUMBER", env_overrides),
        "SMOKE_PROCUREMENT_URL_OR_NUMBER",
    )
    resolved_g2b_api_key = _resolve_required_env(
        str(args.g2b_api_key).strip() or _lookup_env("G2B_API_KEY", env_overrides),
        "G2B_API_KEY",
    )
    return run_local_procurement_smoke(
        data_dir=data_dir,
        procurement_url_or_number=resolved_procurement_target,
        g2b_api_key=resolved_g2b_api_key,
        host=str(args.host).strip() or DEFAULT_HOST,
        port=int(args.port),
        base_url=str(args.base_url).strip() or None,
        provider=str(args.provider).strip() or "mock",
        api_key=str(args.api_key).strip() or DEFAULT_API_KEY,
        ops_key=str(args.ops_key).strip() or DEFAULT_OPS_KEY,
        timeout_sec=float(args.timeout_sec),
        keep_running=bool(args.keep_running),
        env_overrides=env_overrides,
    )


if __name__ == "__main__":
    raise SystemExit(main())
