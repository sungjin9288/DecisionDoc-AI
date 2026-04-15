from __future__ import annotations

from fastapi.testclient import TestClient


class _FakeOpsService:
    def __init__(self, *, should_block: bool = False) -> None:
        self.should_block = should_block

    def run_post_deploy_check(self, *, skip_smoke: bool) -> dict:
        if self.should_block:
            raise PermissionError("Post-deploy run is disabled.")
        return {
            "run_id": "run-123",
            "status": "passed" if not skip_smoke else "failed",
            "exit_code": 0 if not skip_smoke else 17,
            "started_at": "2026-04-15T00:00:00Z",
            "finished_at": "2026-04-15T00:10:00Z",
            "report_dir": "/tmp/reports/post-deploy",
            "report_file": "post-deploy-20260415T001000Z.json",
            "report_path": "/tmp/reports/post-deploy/post-deploy-20260415T001000Z.json",
            "stdout_tail": ["PASS post-deploy check completed."],
            "stderr_tail": [],
            "command": "python3 scripts/post_deploy_check.py",
        }


def _create_client(monkeypatch, *, ops_service) -> TestClient:
    monkeypatch.setenv("DECISIONDOC_PROVIDER", "mock")
    monkeypatch.setenv("DATA_DIR", "/tmp/ops_run_test")
    monkeypatch.setenv("DECISIONDOC_TEMPLATE_VERSION", "v1")
    monkeypatch.setenv("DECISIONDOC_ENV", "dev")
    monkeypatch.setenv("DECISIONDOC_MAINTENANCE", "0")
    monkeypatch.setenv("DECISIONDOC_OPS_KEY", "ops-secret")
    monkeypatch.delenv("DECISIONDOC_API_KEY", raising=False)
    monkeypatch.delenv("DECISIONDOC_API_KEYS", raising=False)

    import app.main as main_module

    monkeypatch.setattr(main_module, "get_ops_service", lambda: ops_service)
    return TestClient(main_module.create_app())


def test_ops_post_deploy_run_requires_ops_key(monkeypatch) -> None:
    client = _create_client(monkeypatch, ops_service=_FakeOpsService())

    response = client.post("/ops/post-deploy/run", json={})

    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_ops_post_deploy_run_returns_payload(monkeypatch) -> None:
    client = _create_client(monkeypatch, ops_service=_FakeOpsService())

    response = client.post(
        "/ops/post-deploy/run",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
        json={"skip_smoke": False},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "run-123"
    assert body["status"] == "passed"
    assert body["exit_code"] == 0
    assert body["report_file"] == "post-deploy-20260415T001000Z.json"
    assert "post_deploy_check.py" in body["command"]


def test_ops_post_deploy_run_returns_403_when_disabled(monkeypatch) -> None:
    client = _create_client(monkeypatch, ops_service=_FakeOpsService(should_block=True))

    response = client.post(
        "/ops/post-deploy/run",
        headers={"X-DecisionDoc-Ops-Key": "ops-secret"},
        json={"skip_smoke": True},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Post-deploy runner is disabled."
