from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(module_name: str, relative_path: str):
    path = REPO_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class _FakeResponse:
    def __init__(self, payload: str):
        self._payload = payload.encode("utf-8")

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        _ = exc_type, exc, tb


def _health_payload(
    *,
    status: str = "ok",
    provider: str = "openai",
    default_route: str = "openai",
    generation_route: str = "openai",
    attachment_route: str = "openai",
    visual_route: str = "openai",
    default_route_status: str = "ok",
    generation_route_status: str = "ok",
    attachment_route_status: str = "ok",
    visual_route_status: str = "ok",
    provider_check_status: str = "ok",
    quality_first_status: str = "degraded",
    quality_first_issues: list[str] | None = None,
) -> str:
    return json.dumps(
        {
            "status": status,
            "provider": provider,
            "checks": {
                "provider": provider_check_status,
                "provider_generation": generation_route_status,
                "provider_attachment": attachment_route_status,
                "provider_visual": visual_route_status,
            },
            "provider_routes": {
                "default": default_route,
                "generation": generation_route,
                "attachment": attachment_route,
                "visual": visual_route,
            },
            "provider_route_checks": {
                "default": default_route_status,
                "generation": generation_route_status,
                "attachment": attachment_route_status,
                "visual": visual_route_status,
            },
            "provider_policy_checks": {
                "quality_first": quality_first_status,
            },
            "provider_policy_issues": {
                "quality_first": quality_first_issues
                if quality_first_issues is not None
                else ["default route must include claude, gemini, openai for quality-first readiness"],
            },
        }
    )


def test_post_deploy_check_runs_health_nginx_and_smoke(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_default", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text(
        "\n".join(
            [
                "ALLOWED_ORIGINS=https://admin.decisiondoc.kr",
                "DECISIONDOC_API_KEYS=runtime-key-1",
                "DECISIONDOC_PROVIDER=openai",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    calls: list[list[str]] = []

    def _fake_urlopen(url: str, timeout: float = 0.0):
        assert url == "https://admin.decisiondoc.kr/health"
        assert timeout == 10.0
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check, kwargs
        calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    result = checker.run_post_deploy_check(
        env_file=env_file,
        compose_file=compose_file,
        app_service="app",
        nginx_service="nginx",
    )

    assert result == 0
    assert calls == [
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "ps",
        ],
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "exec",
            "-T",
            "nginx",
            "nginx",
            "-t",
        ],
        [
            checker.sys.executable,
            "scripts/run_deployed_smoke.py",
            "--env-file",
            str(env_file),
            "--base-url",
            "https://admin.decisiondoc.kr",
            "--preflight",
        ],
        [
            checker.sys.executable,
            "scripts/run_deployed_smoke.py",
            "--env-file",
            str(env_file),
            "--compose-file",
            str(compose_file),
            "--service",
            "app",
            "--base-url",
            "https://admin.decisiondoc.kr",
        ],
    ]


def test_post_deploy_check_writes_json_report(tmp_path: Path, monkeypatch, capsys) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_report", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    report_file = tmp_path / "reports" / "post-deploy.json"

    def _fake_urlopen(url: str, timeout: float = 0.0):
        assert url == "https://admin.decisiondoc.kr/health"
        assert timeout == 10.0
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check, kwargs
        command_list = list(command)
        if command_list[:2] == [checker.sys.executable, "scripts/run_deployed_smoke.py"] and "--preflight" not in command_list:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "GET /health -> 200 request_id=req-1\n"
                    "POST /generate/with-attachments (no key) -> 401\n"
                    "POST /generate/with-attachments (auth) -> 200 request_id=req-2 bundle_id=bundle-1 files=1 docs=4\n"
                ),
                stderr="",
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    result = checker.main(
        [
            "--env-file",
            str(env_file),
            "--compose-file",
            str(compose_file),
            "--report-file",
            str(report_file),
        ]
    )

    captured = capsys.readouterr().out
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert result == 0
    assert "PASS report written" in captured
    assert payload["status"] == "passed"
    assert payload["base_url"] == "https://admin.decisiondoc.kr"
    assert payload["checks"][0]["name"] == "health"
    assert payload["checks"][1]["name"] == "health provider routing"
    assert payload["checks"][-1]["name"] == "deployed smoke"


def test_post_deploy_check_writes_report_history_and_latest(tmp_path: Path, monkeypatch, capsys) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_report_dir", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    report_dir = tmp_path / "reports" / "post-deploy"

    def _fake_urlopen(url: str, timeout: float = 0.0):
        assert url == "https://admin.decisiondoc.kr/health"
        assert timeout == 10.0
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check, kwargs
        command_list = list(command)
        if command_list[:2] == [checker.sys.executable, "scripts/run_deployed_smoke.py"] and "--preflight" not in command_list:
            return SimpleNamespace(
                returncode=0,
                stdout=(
                    "GET /health -> 200 request_id=req-1\n"
                    "POST /generate/with-attachments (no key) -> 401\n"
                    "POST /generate/with-attachments (auth) -> 200 request_id=req-2 bundle_id=bundle-1 files=1 docs=4\n"
                ),
                stderr="",
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    result = checker.main(
        [
            "--env-file",
            str(env_file),
            "--compose-file",
            str(compose_file),
            "--report-dir",
            str(report_dir),
        ]
    )

    captured = capsys.readouterr().out
    history_reports = sorted(report_dir.glob("post-deploy-*.json"))
    latest_report = report_dir / "latest.json"
    index_report = report_dir / "index.json"
    assert result == 0
    assert "PASS report written" in captured
    assert "PASS latest report updated" in captured
    assert len(history_reports) == 1
    assert latest_report.exists()
    assert index_report.exists()
    history_payload = json.loads(history_reports[0].read_text(encoding="utf-8"))
    latest_payload = json.loads(latest_report.read_text(encoding="utf-8"))
    index_payload = json.loads(index_report.read_text(encoding="utf-8"))
    assert history_payload["status"] == "passed"
    assert latest_payload["status"] == "passed"
    assert history_payload["checks"][-1]["name"] == "deployed smoke"
    assert latest_payload["checks"][-1]["name"] == "deployed smoke"
    assert history_payload["checks"][-1]["smoke_results"] == [
        "GET /health -> 200 request_id=req-1",
        "POST /generate/with-attachments (no key) -> 401",
        "POST /generate/with-attachments (auth) -> 200 request_id=req-2 bundle_id=bundle-1 files=1 docs=4",
    ]
    assert latest_payload["smoke_results"] == history_payload["checks"][-1]["smoke_results"]
    assert history_payload["checks"][1]["name"] == "health provider routing"
    assert index_payload["reports"][0]["provider_routes"]["generation"] == "openai"
    assert index_payload["reports"][0]["provider_route_checks"]["visual"] == "ok"
    assert index_payload["reports"][0]["provider_policy_checks"]["quality_first"] == "degraded"
    assert index_payload["reports"][0]["provider_policy_issues"]["quality_first"][0].startswith("default route must include")
    assert index_payload["reports"][0]["smoke_results"][1] == "POST /generate/with-attachments (no key) -> 401"
    assert index_payload["latest"] == "latest.json"
    assert index_payload["latest_report"] == history_reports[0].name
    assert index_payload["reports"][0]["file"] == history_reports[0].name
    assert index_payload["reports"][0]["status"] == "passed"


def test_post_deploy_check_updates_index_with_newest_report_first(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_report_index", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    report_dir = tmp_path / "reports" / "post-deploy"
    initial_report = report_dir / "post-deploy-20260414T010000Z.json"
    initial_index = report_dir / "index.json"
    report_dir.mkdir(parents=True, exist_ok=True)
    initial_report.write_text(
        json.dumps({"status": "passed", "started_at": "2026-04-14T01:00:00+00:00", "finished_at": "2026-04-14T01:01:00+00:00"}),
        encoding="utf-8",
    )
    initial_index.write_text(
        json.dumps(
            {
                "updated_at": "2026-04-14T01:01:00+00:00",
                "latest": "latest.json",
                "latest_report": initial_report.name,
                "reports": [
                    {
                        "file": initial_report.name,
                        "status": "passed",
                        "base_url": "https://admin.decisiondoc.kr",
                        "started_at": "2026-04-14T01:00:00+00:00",
                        "finished_at": "2026-04-14T01:01:00+00:00",
                        "skip_smoke": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def _fake_urlopen(url: str, timeout: float = 0.0):
        assert url == "https://admin.decisiondoc.kr/health"
        assert timeout == 10.0
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check, kwargs
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    result = checker.main(
        [
            "--env-file",
            str(env_file),
            "--compose-file",
            str(compose_file),
            "--report-dir",
            str(report_dir),
        ]
    )

    history_reports = sorted(report_dir.glob("post-deploy-*.json"))
    index_payload = json.loads((report_dir / "index.json").read_text(encoding="utf-8"))
    assert result == 0
    assert len(history_reports) == 2
    assert index_payload["reports"][0]["file"] == index_payload["latest_report"]
    assert index_payload["reports"][1]["file"] == initial_report.name


def test_post_deploy_check_writes_failure_report(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_report_fail", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    report_file = tmp_path / "reports" / "post-deploy-fail.json"

    def _fake_urlopen(url: str, timeout: float = 0.0):
        _ = url, timeout
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check, kwargs
        if list(command)[-1] == "ps":
            return SimpleNamespace(returncode=17)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    try:
        checker.main(
            [
                "--env-file",
                str(env_file),
                "--compose-file",
                str(compose_file),
                "--report-file",
                str(report_file),
            ]
        )
    except SystemExit as exc:
        assert "docker compose ps failed with exit code 17" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for failing compose ps")

    payload = json.loads(report_file.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["error"] == "docker compose ps failed with exit code 17"
    assert payload["checks"][-1]["name"] == "docker compose ps"
    assert payload["checks"][-1]["status"] == "failed"


def test_post_deploy_check_captures_deployed_smoke_failure_details(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_smoke_fail_details", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    report_file = tmp_path / "reports" / "post-deploy-smoke-fail.json"

    def _fake_urlopen(url: str, timeout: float = 0.0):
        _ = url, timeout
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check
        if list(command)[:2] == [checker.sys.executable, "scripts/run_deployed_smoke.py"]:
            if "--preflight" in list(command):
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            return SimpleNamespace(
                returncode=1,
                stdout="GET /health -> 200 request_id=req-1\n",
                stderr=(
                    "POST /generate (auth) expected 200, got 503 "
                    "(code=PROVIDER_FAILED; "
                    "message=AI provider quota is exhausted. 운영 키 또는 과금 한도를 확인하세요.; "
                    "provider_error_code=insufficient_quota)\n"
                ),
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    try:
        checker.main(
            [
                "--env-file",
                str(env_file),
                "--compose-file",
                str(compose_file),
                "--report-file",
                str(report_file),
            ]
        )
    except SystemExit as exc:
        assert str(exc) == (
            "deployed smoke failed with exit code 1 "
            "(smoke_response_code=PROVIDER_FAILED; provider_error_code=insufficient_quota)"
        )
    else:
        raise AssertionError("Expected SystemExit for failing deployed smoke")

    payload = json.loads(report_file.read_text(encoding="utf-8"))
    smoke_check = payload["checks"][-1]
    assert payload["status"] == "failed"
    assert payload["error"] == (
        "deployed smoke failed with exit code 1 "
        "(smoke_response_code=PROVIDER_FAILED; provider_error_code=insufficient_quota)"
    )
    assert smoke_check["name"] == "deployed smoke"
    assert smoke_check["status"] == "failed"
    assert smoke_check["smoke_response_code"] == "PROVIDER_FAILED"
    assert smoke_check["provider_error_code"] == "insufficient_quota"
    assert smoke_check["smoke_message"] == "AI provider quota is exhausted. 운영 키 또는 과금 한도를 확인하세요."
    assert smoke_check["failure_line"].startswith("POST /generate (auth) expected 200, got 503")
    assert smoke_check["stdout"] == "GET /health -> 200 request_id=req-1\n"
    assert "provider_error_code=insufficient_quota" in smoke_check["stderr"]
    assert payload["checks"][-1]["smoke_response_code"] == "PROVIDER_FAILED"
    assert smoke_check["smoke_results"] == ["GET /health -> 200 request_id=req-1"]


def test_post_deploy_check_indexes_smoke_failure_summary(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_smoke_index", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    report_dir = tmp_path / "reports" / "post-deploy"

    def _fake_urlopen(url: str, timeout: float = 0.0):
        _ = url, timeout
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check, kwargs
        command_list = list(command)
        if command_list[:2] == [checker.sys.executable, "scripts/run_deployed_smoke.py"] and "--preflight" not in command_list:
            return SimpleNamespace(
                returncode=1,
                stdout="GET /health -> 200 request_id=req-1\n",
                stderr=(
                    "POST /generate (auth) expected 200, got 503 "
                    "(code=PROVIDER_FAILED; message=AI provider quota is exhausted. 운영 키 또는 과금 한도를 확인하세요.; "
                    "provider_error_code=insufficient_quota)\n"
                ),
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    try:
        checker.main(
            [
                "--env-file",
                str(env_file),
                "--compose-file",
                str(compose_file),
                "--report-dir",
                str(report_dir),
            ]
        )
    except SystemExit:
        pass
    else:
        raise AssertionError("Expected failing deployed smoke")

    index_payload = json.loads((report_dir / "index.json").read_text(encoding="utf-8"))
    assert index_payload["reports"][0]["smoke_response_code"] == "PROVIDER_FAILED"
    assert index_payload["reports"][0]["provider_error_code"] == "insufficient_quota"
    assert index_payload["reports"][0]["smoke_results"] == ["GET /health -> 200 request_id=req-1"]


def test_post_deploy_check_captures_deployed_smoke_timeout_summary(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_smoke_timeout", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    report_file = tmp_path / "reports" / "post-deploy-smoke-timeout.json"

    def _fake_urlopen(url: str, timeout: float = 0.0):
        _ = url, timeout
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check, kwargs
        command_list = list(command)
        if command_list[:2] == [checker.sys.executable, "scripts/run_deployed_smoke.py"] and "--preflight" not in command_list:
            return SimpleNamespace(
                returncode=1,
                stdout="GET /health -> 200 request_id=req-1\nPOST /generate/from-documents (no key) -> 401\n",
                stderr="httpx.ReadTimeout: The read operation timed out\n",
            )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    try:
        checker.main(
            [
                "--env-file",
                str(env_file),
                "--compose-file",
                str(compose_file),
                "--report-file",
                str(report_file),
            ]
        )
    except SystemExit as exc:
        assert str(exc) == "deployed smoke failed with exit code 1 (smoke_exception_type=httpx.ReadTimeout)"
    else:
        raise AssertionError("Expected failing deployed smoke timeout")

    payload = json.loads(report_file.read_text(encoding="utf-8"))
    smoke_check = payload["checks"][-1]
    assert payload["error"] == "deployed smoke failed with exit code 1 (smoke_exception_type=httpx.ReadTimeout)"
    assert smoke_check["smoke_exception_type"] == "httpx.ReadTimeout"
    assert smoke_check["smoke_results"] == [
        "GET /health -> 200 request_id=req-1",
        "POST /generate/from-documents (no key) -> 401",
    ]


def test_post_deploy_check_rejects_report_file_and_report_dir_together(tmp_path: Path) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_report_conflict", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    report_dir = tmp_path / "reports" / "post-deploy"
    report_file = tmp_path / "reports" / "post-deploy.json"

    try:
        checker.run_post_deploy_check(
            env_file=env_file,
            compose_file=compose_file,
            app_service="app",
            nginx_service="nginx",
            report_file=report_file,
            report_dir=report_dir,
        )
    except SystemExit as exc:
        assert "either --report-file or --report-dir" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for conflicting report targets")


def test_post_deploy_check_skips_smoke_when_requested(tmp_path: Path, monkeypatch, capsys) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_skip", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://dawool.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    calls: list[list[str]] = []

    def _fake_urlopen(url: str, timeout: float = 0.0):
        assert url == "https://dawool.decisiondoc.kr/health"
        assert timeout == 10.0
        return _FakeResponse(_health_payload())

    def _fake_run(command, cwd=None, check=False, **kwargs):
        _ = cwd, check, kwargs
        calls.append(list(command))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(checker.subprocess, "run", _fake_run)

    result = checker.main(
        [
            "--env-file",
            str(env_file),
            "--compose-file",
            str(compose_file),
            "--skip-smoke",
        ]
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert "PASS deployed smoke preflight" not in captured
    assert "PASS post-deploy check completed." in captured
    assert len(calls) == 2


def test_post_deploy_check_rejects_non_ok_health(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_bad_health", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    def _fake_urlopen(url: str, timeout: float = 0.0):
        _ = url, timeout
        return _FakeResponse(_health_payload(status="degraded", provider_check_status="degraded"))

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)

    try:
        checker.run_post_deploy_check(
            env_file=env_file,
            compose_file=compose_file,
            app_service="app",
            nginx_service="nginx",
        )
    except SystemExit as exc:
        assert "non-ok status" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for degraded health response")


def test_post_deploy_check_rejects_missing_provider_route_metadata(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script_module("decisiondoc_post_deploy_check_bad_provider_routes", "scripts/post_deploy_check.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("ALLOWED_ORIGINS=https://admin.decisiondoc.kr\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    def _fake_urlopen(url: str, timeout: float = 0.0):
        _ = url, timeout
        return _FakeResponse('{"status":"ok","provider":"openai","checks":{"provider":"ok"}}')

    monkeypatch.setattr(checker.request, "urlopen", _fake_urlopen)

    try:
        checker.run_post_deploy_check(
            env_file=env_file,
            compose_file=compose_file,
            app_service="app",
            nginx_service="nginx",
        )
    except SystemExit as exc:
        assert "provider_routes" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for missing provider route metadata")
