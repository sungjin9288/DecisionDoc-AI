"""E2E test fixtures — run a real uvicorn server in a background thread."""
from __future__ import annotations

import json
import os
import threading
import time
from urllib import request as urllib_request

import pytest
import uvicorn


def _bootstrap_e2e_user(base_url: str) -> dict[str, str]:
    """Create the first admin user for E2E login flows."""
    username = "e2e_admin"
    password = "AdminPass1!"
    register_payload = json.dumps(
        {
            "username": username,
            "display_name": "E2E Admin",
            "email": "e2e-admin@test.local",
            "password": password,
        }
    ).encode("utf-8")

    def _post(path: str, payload: bytes) -> dict:
        req = urllib_request.Request(
            f"{base_url}{path}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    _post("/auth/register", register_payload)

    return {"username": username, "password": password}


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Session-scoped fixture: starts uvicorn on port 18765 with mock provider."""
    tmp = tmp_path_factory.mktemp("e2e_data")
    os.environ.update(
        {
            "DECISIONDOC_PROVIDER": "mock",
            "DATA_DIR": str(tmp),
            "DECISIONDOC_ENV": "dev",
            "DECISIONDOC_MAINTENANCE": "0",
            "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED": "1",
        }
    )
    os.environ.pop("DECISIONDOC_API_KEY", None)
    os.environ.pop("DECISIONDOC_API_KEYS", None)

    from app.main import create_app

    config = uvicorn.Config(
        create_app(),
        host="127.0.0.1",
        port=18765,
        log_level="error",
        # The app uses SSE in tests, not WebSocket endpoints. Disabling the
        # WebSocket protocol stack keeps the e2e fixture off uvicorn's
        # deprecated websockets implementation path.
        ws="none",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait up to 5 s for server to be ready
    for _ in range(50):
        time.sleep(0.1)
        if server.started:
            break

    base_url = "http://127.0.0.1:18765"
    auth = _bootstrap_e2e_user(base_url)

    yield {"base_url": base_url, "auth": auth}

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def page(playwright, live_server):  # noqa: ARG001
    """Per-test fixture: Chromium page pointed at the live server."""
    browser = playwright.chromium.launch()
    ctx = browser.new_context()
    ctx.add_init_script("localStorage.setItem('onboarding_done', '1');")
    pg = ctx.new_page()
    pg.goto(live_server["base_url"])
    pg.fill("#login-username", live_server["auth"]["username"])
    pg.fill("#login-password", live_server["auth"]["password"])
    pg.click("#login-btn")
    pg.wait_for_selector(".bundle-card", timeout=10000)
    yield pg
    ctx.close()
    browser.close()
