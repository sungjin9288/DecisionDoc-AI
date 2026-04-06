from __future__ import annotations

from pathlib import Path
from scripts.check_procurement_stale_share_demo import DemoVerificationResult
from scripts.playtest_procurement_stale_share_demo import DemoUIPlaytestResult
from scripts.seed_procurement_stale_share_demo import DemoSeedResult

from scripts import run_procurement_stale_share_demo as runner


class _FakeProcess:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.returncode = 0
        return 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def test_run_procurement_stale_share_demo_starts_server_and_runs_seed_and_verify(
    tmp_path: Path,
    monkeypatch,
) -> None:
    launched: list[dict[str, object]] = []
    waited: list[str] = []
    manifests: list[dict[str, object]] = []
    opened_urls: list[list[str]] = []
    playtest_calls: list[dict[str, object]] = []
    fake_process = _FakeProcess()
    seed_result = DemoSeedResult(
        data_dir=tmp_path / "demo-data",
        base_url="http://127.0.0.1:8878",
        username="stale_demo_admin",
        password="DemoPass123!",
        project_id="project-1",
        project_name="거점 stale share 데모 프로젝트",
        shared_bundle_id="proposal_kr",
        shared_project_document_id="doc-proposal-1",
        decision_project_document_id="doc-bid-1",
        proposal_project_document_id="doc-proposal-1",
        decision_council_session_id="session-1",
        decision_council_session_revision=1,
        internal_tenant_review_url="http://127.0.0.1:8878/?location_procurement_tenant=system&location_procurement_activity_actions=share.create",
        internal_focused_review_url="http://127.0.0.1:8878/?location_procurement_tenant=system&location_procurement_activity_actions=share.create&location_procurement_focus_project=project-1",
        public_share_url="http://127.0.0.1:8878/shared/share-1",
        share_id="share-1",
    )
    verification_result = DemoVerificationResult(
        tenant_id="system",
        project_id="project-1",
        share_id="share-1",
        bundle_id="proposal_kr",
        public_share_url="http://127.0.0.1:8878/shared/share-1",
        internal_tenant_review_url="http://127.0.0.1:8878/?location_procurement_tenant=system&location_procurement_activity_actions=share.create",
        internal_focused_review_url="http://127.0.0.1:8878/?location_procurement_tenant=system&location_procurement_activity_actions=share.create&location_procurement_focus_project=project-1",
        stale_status_copy="현재 procurement 대비 이전 council 기준",
    )
    playtest_result = DemoUIPlaytestResult(
        bundle_id="proposal_kr",
        project_id="project-1",
        share_id="share-1",
        focused_review_url=verification_result.internal_focused_review_url,
        public_share_url=verification_result.public_share_url,
        focused_review_screenshot=str(tmp_path / "focused-review.png"),
        public_share_screenshot=str(tmp_path / "public-share.png"),
    )

    def _fake_popen(command, cwd=None, env=None):
        launched.append(
            {
                "command": list(command),
                "cwd": cwd,
                "env": dict(env or {}),
            }
        )
        return fake_process

    def _fake_run_child(command, *, env):
        child_commands.append((list(command), dict(env)))

    def _fake_wait(
        base_url: str,
        *,
        process=None,
        timeout_seconds: float = 20.0,
        interval_seconds: float = 0.5,
    ):
        waited.append(base_url)
        assert process is fake_process

    def _fake_seed(*, data_dir: Path, base_url: str):
        assert data_dir == tmp_path / "demo-data"
        assert base_url == "http://127.0.0.1:8878"
        return seed_result

    def _fake_verify(*, base_url: str, tenant_id: str = "system", username: str = "stale_demo_admin", password: str = "DemoPass123!", client=None):
        assert base_url == "http://127.0.0.1:8878"
        return verification_result

    def _fake_write_manifest(*, data_dir: Path, base_url: str, seed_result: DemoSeedResult, verification_result: DemoVerificationResult):
        manifests.append(
            {
                "data_dir": data_dir,
                "base_url": base_url,
                "seed_result": seed_result,
                "verification_result": verification_result,
            }
        )
        return data_dir / runner.DEFAULT_MANIFEST_NAME

    def _fake_open_browser(urls):
        opened_urls.append(list(urls))

    def _fake_playtest_ui(*, data_dir: Path, base_url: str, headed: bool = False, slow_mo_ms: int = 0):
        playtest_calls.append(
            {
                "data_dir": data_dir,
                "base_url": base_url,
                "headed": headed,
                "slow_mo_ms": slow_mo_ms,
            }
        )
        return playtest_result

    monkeypatch.setattr(runner.subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(runner, "_wait_for_health", _fake_wait)
    monkeypatch.setattr(runner, "seed_procurement_stale_share_demo", _fake_seed)
    monkeypatch.setattr(runner, "verify_procurement_stale_share_demo", _fake_verify)
    monkeypatch.setattr(runner, "_write_demo_manifest", _fake_write_manifest)
    monkeypatch.setattr(runner, "_open_browser_urls", _fake_open_browser)
    monkeypatch.setattr(runner, "playtest_procurement_stale_share_demo", _fake_playtest_ui)

    result = runner.run_procurement_stale_share_demo(
        data_dir=tmp_path / "demo-data",
        port=8878,
        exit_after_verify=True,
        open_browser=True,
        playtest_ui=True,
        playtest_headed=True,
        playtest_slow_mo_ms=120,
    )

    assert result == 0
    assert len(launched) == 1
    server_command = launched[0]["command"]
    assert server_command[:3] == [runner.sys.executable, "-m", "uvicorn"]
    assert "app.main:app" in server_command
    assert "--port" in server_command
    assert "8878" in server_command

    env = launched[0]["env"]
    assert env["DATA_DIR"] == str(tmp_path / "demo-data")
    assert env["DECISIONDOC_PROCUREMENT_COPILOT_ENABLED"] == "1"
    assert env["DECISIONDOC_PROVIDER"] == "mock"

    assert waited == ["http://127.0.0.1:8878"]
    assert len(manifests) == 1
    assert manifests[0]["data_dir"] == tmp_path / "demo-data"
    assert manifests[0]["base_url"] == "http://127.0.0.1:8878"
    assert manifests[0]["seed_result"] is seed_result
    assert manifests[0]["verification_result"] is verification_result
    assert opened_urls == [[seed_result.internal_focused_review_url, seed_result.public_share_url]]
    assert playtest_calls == [
        {
            "data_dir": tmp_path / "demo-data",
            "base_url": "http://127.0.0.1:8878",
            "headed": True,
            "slow_mo_ms": 120,
        }
    ]
    assert fake_process.terminated is True
