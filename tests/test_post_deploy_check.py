from __future__ import annotations

import importlib.util
import io
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
        return _FakeResponse('{"status":"ok","provider":"openai"}')

    def _fake_run(command, cwd=None, check=False):
        _ = cwd, check
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
            "--compose-file",
            str(compose_file),
            "--service",
            "app",
            "--base-url",
            "https://admin.decisiondoc.kr",
        ],
    ]


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
        return _FakeResponse('{"status":"ok"}')

    def _fake_run(command, cwd=None, check=False):
        _ = cwd, check
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
        return _FakeResponse('{"status":"degraded"}')

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
