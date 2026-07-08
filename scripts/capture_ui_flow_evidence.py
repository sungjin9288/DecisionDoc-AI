#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib import request as urllib_request
from uuid import uuid4

import uvicorn
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCHEMA_VERSION = "decisiondoc.ui_flow_evidence.v1"

DEFAULT_SCREENSHOT_DIR = REPO_ROOT / "evidence" / "screenshots"
DEFAULT_RECEIPT_PATH = REPO_ROOT / "evidence" / "cli-logs" / "ui_flow_evidence.json"

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


@dataclass(frozen=True)
class LocalServer:
    base_url: str
    username: str
    password: str
    server: uvicorn.Server
    thread: threading.Thread


@dataclass(frozen=True)
class UIFlowEvidenceResult:
    base_url: str
    screenshots: dict[str, str]
    receipt_path: str
    browser_http_errors: list[dict[str, str | int]]


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid4().hex}")
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)


def _relative_to_repo(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _reserve_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib_request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(request, timeout=5) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Unexpected JSON response from {url}")
    return data


def _start_local_server(data_dir: Path) -> LocalServer:
    os.environ.update(
        {
            "DECISIONDOC_PROVIDER": "mock",
            "DECISIONDOC_PROVIDER_GENERATION": "",
            "DECISIONDOC_PROVIDER_ATTACHMENT": "",
            "DECISIONDOC_PROVIDER_VISUAL": "",
            "DATA_DIR": str(data_dir),
            "DECISIONDOC_ENV": "dev",
            "DECISIONDOC_MAINTENANCE": "0",
            "DECISIONDOC_API_KEYS": "ui-flow-evidence-api-key",
            "DECISIONDOC_OPS_KEY": "ui-flow-ops-key",
            "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED": "1",
            "JWT_SECRET_KEY": "ui-flow-evidence-secret-key-32chars!!",
        }
    )
    os.environ.pop("DECISIONDOC_API_KEY", None)

    from app.main import create_app

    port = _reserve_local_port()
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(),
            host="127.0.0.1",
            port=port,
            log_level="error",
            ws="none",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        time.sleep(0.1)
        if server.started:
            break
    if not server.started:
        raise SystemExit("Local evidence server did not start within 5 seconds.")

    base_url = f"http://127.0.0.1:{port}"
    username = "ui_flow_admin"
    password = "AdminPass1!"
    _post_json(
        f"{base_url}/auth/register",
        {
            "username": username,
            "display_name": "UI Flow Admin",
            "email": "ui-flow-admin@test.local",
            "password": password,
        },
    )
    return LocalServer(base_url=base_url, username=username, password=password, server=server, thread=thread)


def _stop_local_server(server: LocalServer) -> None:
    server.server.should_exit = True
    server.thread.join(timeout=5)


def _wait_until_any_visible(page, selectors: list[str], *, timeout_ms: int = 30000) -> str:
    deadline = time.monotonic() + (max(timeout_ms, 1) / 1000.0)
    while time.monotonic() < deadline:
        for selector in selectors:
            if page.locator(selector).is_visible():
                return selector
        page.wait_for_timeout(250)
    raise PlaywrightTimeoutError(f"None of the selectors became visible: {', '.join(selectors)}")


def _wait_until_text_contains(page, selector: str, expected: str, *, timeout_ms: int = 5000) -> str:
    deadline = time.monotonic() + (max(timeout_ms, 1) / 1000.0)
    locator = page.locator(selector)
    while time.monotonic() < deadline:
        text = locator.inner_text()
        if expected in text:
            return text
        page.wait_for_timeout(250)
    raise PlaywrightTimeoutError(f"{selector} did not contain {expected!r}")


def _capture_screenshot(page, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=False)


def capture_ui_flow_evidence(
    *,
    base_url: str,
    username: str,
    password: str,
    screenshot_dir: Path = DEFAULT_SCREENSHOT_DIR,
    receipt_path: Path = DEFAULT_RECEIPT_PATH,
    headed: bool = False,
    slow_mo_ms: int = 0,
    playwright_factory: Callable[[], Any] = sync_playwright,
) -> UIFlowEvidenceResult:
    screenshot_dir = Path(screenshot_dir).expanduser()
    receipt_path = Path(receipt_path).expanduser()
    screenshots = {
        "after_login": screenshot_dir / "ui-flow-01-after-login.png",
        "generate_ready": screenshot_dir / "ui-flow-02-generate-ready.png",
        "results": screenshot_dir / "ui-flow-03-results.png",
        "export_complete": screenshot_dir / "ui-flow-04-export-complete.png",
    }
    browser_http_errors: list[dict[str, str | int]] = []

    with playwright_factory() as playwright:
        browser = playwright.chromium.launch(headless=not headed, slow_mo=int(slow_mo_ms or 0))
        context = browser.new_context(viewport={"width": 1440, "height": 1100})
        context.add_init_script("localStorage.setItem('onboarding_done', '1');")
        page = context.new_page()
        try:
            page.goto(base_url)
            page.wait_for_selector("#login-screen", state="visible", timeout=15000)
            page.fill("#login-username", username)
            page.fill("#login-password", password)
            page.click("#login-btn")
            page.wait_for_selector(".bundle-card", state="visible", timeout=15000)
            page.wait_for_timeout(500)
            page.on(
                "response",
                lambda response: browser_http_errors.append({"url": response.url, "status": response.status})
                if response.status >= 400
                else None,
            )
            _capture_screenshot(page, screenshots["after_login"])

            page.locator(".bundle-card").first.click()
            page.fill("#f-title", "UI flow evidence")
            page.fill("#f-goal", "Capture login, generation result, and export states without external services.")
            page.wait_for_selector("#generate-btn:not([disabled])", timeout=5000)
            _capture_screenshot(page, screenshots["generate_ready"])

            page.click("#generate-btn")
            visible = _wait_until_any_visible(page, ["#sketch-panel", "#results"], timeout_ms=30000)
            if visible == "#sketch-panel":
                page.click("#sketch-confirm-btn")
            page.wait_for_selector("#results", state="visible", timeout=30000)
            page.wait_for_selector("#doc-pane", state="visible", timeout=10000)
            page.wait_for_selector("#tab-bar .tab-btn", state="visible", timeout=10000)
            page.locator("#results").scroll_into_view_if_needed()
            _capture_screenshot(page, screenshots["results"])

            page.click("#export-btn")
            _wait_until_text_contains(page, "#export-btn", "완료", timeout_ms=5000)
            page.locator("#results").scroll_into_view_if_needed()
            _capture_screenshot(page, screenshots["export_complete"])
        finally:
            context.close()
            browser.close()

    receipt = {
        "schema_version": SCHEMA_VERSION,
        "scope": "local mock browser UI flow; no external proof executed",
        "base_url": "local ephemeral server",
        "screenshots": {key: _relative_to_repo(path) for key, path in screenshots.items()},
        "verified_states": [
            "authenticated browser session reached bundle grid",
            "bundle selection enabled generate button",
            "generation result rendered document tabs and document pane",
            "export button reported completion",
        ],
        "browser_http_errors": browser_http_errors,
        "external_actions_excluded": list(EXCLUDED_EXTERNAL_ACTIONS),
    }
    _write_text_atomic(receipt_path, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")

    return UIFlowEvidenceResult(
        base_url=base_url,
        screenshots={key: str(path) for key, path in screenshots.items()},
        receipt_path=str(receipt_path),
        browser_http_errors=browser_http_errors,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture local mock UI-flow evidence screenshots.")
    parser.add_argument("--base-url", default="", help="Use an already running DecisionDoc server instead of starting one.")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--screenshot-dir", default=str(DEFAULT_SCREENSHOT_DIR))
    parser.add_argument("--receipt-path", default=str(DEFAULT_RECEIPT_PATH))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--slow-mo-ms", type=int, default=0)
    return parser.parse_args(argv)


def _print_result(result: UIFlowEvidenceResult) -> None:
    print("Captured local UI-flow evidence.")
    print(f"base_url: {result.base_url}")
    print(f"receipt: {_relative_to_repo(Path(result.receipt_path))}")
    print("screenshots:")
    for label, path in result.screenshots.items():
        print(f"  {label}: {_relative_to_repo(Path(path))}")
    print(f"browser_http_errors: {len(result.browser_http_errors)}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    base_url = str(args.base_url).strip()
    username = str(args.username).strip()
    password = str(args.password)

    if base_url:
        if not username or not password:
            raise SystemExit("--username and --password are required when --base-url is provided.")
        result = capture_ui_flow_evidence(
            base_url=base_url,
            username=username,
            password=password,
            screenshot_dir=Path(args.screenshot_dir),
            receipt_path=Path(args.receipt_path),
            headed=bool(args.headed),
            slow_mo_ms=int(args.slow_mo_ms or 0),
        )
        _print_result(result)
        return 0

    with tempfile.TemporaryDirectory(prefix="decisiondoc-ui-flow-") as tmp:
        local_server = _start_local_server(Path(tmp))
        try:
            result = capture_ui_flow_evidence(
                base_url=local_server.base_url,
                username=local_server.username,
                password=local_server.password,
                screenshot_dir=Path(args.screenshot_dir),
                receipt_path=Path(args.receipt_path),
                headed=bool(args.headed),
                slow_mo_ms=int(args.slow_mo_ms or 0),
            )
        finally:
            _stop_local_server(local_server)
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
