#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import webbrowser
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_procurement_stale_share_demo import (
    DemoVerificationResult,
    _print_result as print_demo_verification_result,
    verify_procurement_stale_share_demo,
)
from scripts.seed_procurement_stale_share_demo import (
    DemoSeedResult,
    _print_result as print_demo_seed_result,
    seed_procurement_stale_share_demo,
)
from scripts.playtest_procurement_stale_share_demo import (
    DemoUIPlaytestResult,
    _print_result as print_demo_ui_playtest_result,
    playtest_procurement_stale_share_demo,
)

DEFAULT_DATA_DIR = Path("/tmp/decisiondoc-stale-share-demo")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_JWT_SECRET = "demo-local-runner-jwt-secret-key-32chars"
DEFAULT_MANIFEST_NAME = "procurement-stale-share-demo.json"


def _build_base_url(host: str, port: int, base_url: str | None) -> str:
    if base_url and str(base_url).strip():
        return str(base_url).strip().rstrip("/")
    normalized_host = "127.0.0.1" if host == "0.0.0.0" else host
    return f"http://{normalized_host}:{int(port)}"


def _build_env(data_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["DATA_DIR"] = str(data_dir)
    env.setdefault("DECISIONDOC_PROCUREMENT_COPILOT_ENABLED", "1")
    env.setdefault("DECISIONDOC_PROVIDER", "mock")
    env.setdefault("DECISIONDOC_ENV", "dev")
    env.setdefault("DECISIONDOC_SEARCH_ENABLED", "0")
    env.setdefault("JWT_SECRET_KEY", DEFAULT_JWT_SECRET)
    return env


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
            raise SystemExit(f"Local demo server exited before /health became ready (code={process.returncode})")
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


def _write_demo_manifest(
    *,
    data_dir: Path,
    base_url: str,
    seed_result: DemoSeedResult,
    verification_result: DemoVerificationResult,
) -> Path:
    manifest_path = data_dir / DEFAULT_MANIFEST_NAME
    manifest_payload = {
        "base_url": base_url,
        "data_dir": str(data_dir),
        "seed": asdict(seed_result),
        "verification": asdict(verification_result),
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _open_browser_urls(urls: Sequence[str]) -> None:
    for url in urls:
        if str(url).strip():
            webbrowser.open_new_tab(str(url).strip())


def run_procurement_stale_share_demo(
    *,
    data_dir: Path,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    base_url: str | None = None,
    exit_after_verify: bool = False,
    open_browser: bool = False,
    playtest_ui: bool = False,
    playtest_headed: bool = False,
    playtest_slow_mo_ms: int = 0,
) -> int:
    env = _build_env(data_dir)
    resolved_base_url = _build_base_url(host, port, base_url)
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
    print(f"Starting local DecisionDoc demo server on {resolved_base_url}", flush=True)
    print(f"DATA_DIR: {data_dir}", flush=True)
    server_process = subprocess.Popen(server_command, cwd=REPO_ROOT, env=env)
    try:
        _wait_for_health(resolved_base_url, process=server_process)
        print("", flush=True)
        print("Seeding deterministic stale-share demo...", flush=True)
        seed_result = seed_procurement_stale_share_demo(
            data_dir=data_dir,
            base_url=resolved_base_url,
        )
        print_demo_seed_result(seed_result)
        print("", flush=True)
        print("Verifying seeded demo against live app...", flush=True)
        verification_result = verify_procurement_stale_share_demo(
            base_url=resolved_base_url,
        )
        print_demo_verification_result(verification_result)
        manifest_path = _write_demo_manifest(
            data_dir=data_dir,
            base_url=resolved_base_url,
            seed_result=seed_result,
            verification_result=verification_result,
        )
        print("", flush=True)
        print(f"Demo manifest: {manifest_path}", flush=True)
        if open_browser:
            print("Opening browser tabs for focused review and public share...", flush=True)
            _open_browser_urls(
                [
                    seed_result.internal_focused_review_url,
                    seed_result.public_share_url,
                ]
            )
        if playtest_ui:
            print("", flush=True)
            print("Running browser playtest against the seeded demo...", flush=True)
            ui_result: DemoUIPlaytestResult = playtest_procurement_stale_share_demo(
                data_dir=data_dir,
                base_url=resolved_base_url,
                headed=playtest_headed,
                slow_mo_ms=playtest_slow_mo_ms,
            )
            print_demo_ui_playtest_result(ui_result)
        print("", flush=True)
        print("Local stale-share demo is ready.", flush=True)
        if exit_after_verify:
            return 0
        print("Server is still running for manual verification. Press Ctrl-C to stop.", flush=True)
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("", flush=True)
        print("Stopping local stale-share demo server...", flush=True)
        return 0
    finally:
        _terminate_server(server_process)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start a local app, seed one procurement stale-share demo, and verify it.",
    )
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--base-url", default="")
    parser.add_argument(
        "--exit-after-verify",
        action="store_true",
        help="Stop the server after seed and verification instead of keeping it open for manual checks.",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open focused internal review and public share URLs after the live verification succeeds.",
    )
    parser.add_argument(
        "--playtest-ui",
        action="store_true",
        help="Run a Playwright browser check against the seeded focused review and public share URLs.",
    )
    parser.add_argument(
        "--playtest-headed",
        action="store_true",
        help="Run the browser playtest in headed mode instead of headless mode.",
    )
    parser.add_argument(
        "--playtest-slow-mo-ms",
        type=int,
        default=0,
        help="Optional Playwright slow-motion delay in milliseconds when --playtest-ui is enabled.",
    )
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    return run_procurement_stale_share_demo(
        data_dir=Path(str(args.data_dir)).expanduser(),
        host=str(args.host).strip() or DEFAULT_HOST,
        port=int(args.port),
        base_url=str(args.base_url).strip() or None,
        exit_after_verify=bool(args.exit_after_verify),
        open_browser=bool(args.open_browser),
        playtest_ui=bool(args.playtest_ui),
        playtest_headed=bool(args.playtest_headed),
        playtest_slow_mo_ms=int(args.playtest_slow_mo_ms),
    )


if __name__ == "__main__":
    raise SystemExit(main())
