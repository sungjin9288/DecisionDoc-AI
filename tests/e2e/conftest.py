"""E2E test fixtures — run a real uvicorn server in a background thread."""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from urllib import request as urllib_request

import pytest
import uvicorn


def _reserve_local_port() -> int:
    """Return an available localhost TCP port for the session-scoped test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return int(sock.getsockname()[1])


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


def _seed_post_deploy_reports(report_dir: str) -> None:
    """Create a small post-deploy history fixture for browser ops tests."""
    report_path = os.path.abspath(report_dir)
    os.makedirs(report_path, exist_ok=True)
    latest_payload = {
        "status": "passed",
        "base_url": "https://admin.decisiondoc.kr",
        "started_at": "2026-04-14T04:09:00+00:00",
        "finished_at": "2026-04-14T04:10:00+00:00",
        "skip_smoke": False,
        "smoke_results_available": True,
        "smoke_results": [
            "GET /health -> 200 request_id=req-latest",
            "POST /generate/with-attachments (auth) -> 200 files=1 docs=4",
        ],
        "report_workflow_smoke_results_available": True,
        "report_workflow_smoke_results": [
            "PASS create workflow -> workflow-e2e status=planning_required",
            "PASS GET /export/snapshot -> 200 export_version=decisiondoc_report_workflow_snapshot.v1",
            "Report workflow smoke completed workflow_id=workflow-e2e slide_count=2",
        ],
        "checks": [
            {"name": "health", "status": "passed"},
            {"name": "smoke", "status": "passed", "exit_code": 0},
            {
                "name": "report workflow smoke",
                "status": "passed",
                "exit_code": 0,
                "report_workflow_smoke_results": [
                    "PASS create workflow -> workflow-e2e status=planning_required",
                    "PASS GET /export/snapshot -> 200 export_version=decisiondoc_report_workflow_snapshot.v1",
                    "Report workflow smoke completed workflow_id=workflow-e2e slide_count=2",
                ],
            },
        ],
    }
    previous_payload = {
        "status": "failed",
        "base_url": "https://admin.decisiondoc.kr",
        "started_at": "2026-04-14T03:09:00+00:00",
        "finished_at": "2026-04-14T03:10:00+00:00",
        "skip_smoke": True,
        "error": "docker compose ps failed with exit code 17",
        "smoke_results_available": False,
        "report_workflow_smoke_results_available": False,
        "checks": [
            {"name": "health", "status": "passed"},
            {"name": "smoke", "status": "failed", "exit_code": 17},
        ],
    }
    index_payload = {
        "updated_at": "2026-04-14T04:10:00+00:00",
        "latest": "latest.json",
        "latest_report": "post-deploy-20260414T041000Z.json",
        "reports": [
            {
                "file": "post-deploy-20260414T041000Z.json",
                "status": "passed",
                "base_url": "https://admin.decisiondoc.kr",
                "started_at": "2026-04-14T04:09:00+00:00",
                "finished_at": "2026-04-14T04:10:00+00:00",
                "skip_smoke": False,
                "smoke_results_available": True,
                "smoke_results": [
                    "GET /health -> 200 request_id=req-latest",
                    "POST /generate/with-attachments (auth) -> 200 files=1 docs=4",
                ],
                "report_workflow_smoke_results_available": True,
                "report_workflow_smoke_results": [
                    "PASS create workflow -> workflow-e2e status=planning_required",
                    "PASS GET /export/snapshot -> 200 export_version=decisiondoc_report_workflow_snapshot.v1",
                    "Report workflow smoke completed workflow_id=workflow-e2e slide_count=2",
                ],
            },
            {
                "file": "post-deploy-20260414T031000Z.json",
                "status": "failed",
                "base_url": "https://admin.decisiondoc.kr",
                "started_at": "2026-04-14T03:09:00+00:00",
                "finished_at": "2026-04-14T03:10:00+00:00",
                "skip_smoke": True,
                "error": "docker compose ps failed with exit code 17",
                "smoke_results_available": False,
                "report_workflow_smoke_results_available": False,
            },
        ],
    }
    with open(os.path.join(report_path, "latest.json"), "w", encoding="utf-8") as handle:
        json.dump(latest_payload, handle)
    with open(os.path.join(report_path, "post-deploy-20260414T041000Z.json"), "w", encoding="utf-8") as handle:
        json.dump(latest_payload, handle)
    with open(os.path.join(report_path, "post-deploy-20260414T031000Z.json"), "w", encoding="utf-8") as handle:
        json.dump(previous_payload, handle)
    with open(os.path.join(report_path, "index.json"), "w", encoding="utf-8") as handle:
        json.dump(index_payload, handle)


@pytest.fixture(scope="session")
def live_server(tmp_path_factory):
    """Session-scoped fixture: starts uvicorn on a free localhost port with mock provider."""
    tmp = tmp_path_factory.mktemp("e2e_data")
    report_dir = tmp / "reports" / "post-deploy"
    _seed_post_deploy_reports(str(report_dir))
    os.environ.update(
        {
            "DECISIONDOC_PROVIDER": "mock",
            "DECISIONDOC_PROVIDER_GENERATION": "",
            "DECISIONDOC_PROVIDER_ATTACHMENT": "",
            "DECISIONDOC_PROVIDER_VISUAL": "",
            "DATA_DIR": str(tmp),
            "DECISIONDOC_ENV": "dev",
            "DECISIONDOC_MAINTENANCE": "0",
            "DECISIONDOC_API_KEYS": "e2e-global-api-key",
            "DECISIONDOC_OPS_KEY": "ops-secret",
            "DECISIONDOC_POST_DEPLOY_REPORT_DIR": str(report_dir),
            "DECISIONDOC_PROCUREMENT_COPILOT_ENABLED": "1",
            "JWT_SECRET_KEY": "e2e-test-secret-key-32chars-minimum!!",
        }
    )
    os.environ.pop("DECISIONDOC_API_KEY", None)

    from app.main import create_app

    port = _reserve_local_port()
    config = uvicorn.Config(
        create_app(),
        host="127.0.0.1",
        port=port,
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

    base_url = f"http://127.0.0.1:{port}"
    auth = _bootstrap_e2e_user(base_url)

    yield {"base_url": base_url, "auth": auth, "ops_key": "ops-secret"}

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
