from __future__ import annotations

import importlib.util
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


def test_deploy_compose_local_builds_and_rolls_out(tmp_path: Path, monkeypatch) -> None:
    deployer = _load_script_module("decisiondoc_deploy_compose_local_default", "scripts/deploy_compose_local.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("DECISIONDOC_ENV=prod\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    calls: list[tuple[list[str], dict[str, str]]] = []

    def _fake_run(command, cwd=None, env=None, check=False):
        _ = cwd, check
        calls.append((list(command), dict(env or {})))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deployer.subprocess, "run", _fake_run)

    result = deployer.deploy_compose_local(
        env_file=env_file,
        compose_file=compose_file,
        image="decisiondoc-admin-local",
        build_context=tmp_path,
    )

    assert result == 0
    assert calls[0][0] == ["docker", "build", "-t", "decisiondoc-admin-local", str(tmp_path)]
    assert calls[1][0] == [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
        "up",
        "-d",
        "--force-recreate",
    ]
    assert calls[1][1]["DOCKER_IMAGE"] == "decisiondoc-admin-local"


def test_deploy_compose_local_can_skip_build_and_run_post_check(tmp_path: Path, monkeypatch) -> None:
    deployer = _load_script_module("decisiondoc_deploy_compose_local_post", "scripts/deploy_compose_local.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("DECISIONDOC_ENV=prod\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    calls: list[tuple[list[str], dict[str, str]]] = []

    def _fake_run(command, cwd=None, env=None, check=False):
        _ = cwd, check
        calls.append((list(command), dict(env or {})))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deployer.subprocess, "run", _fake_run)

    result = deployer.main(
        [
            "--env-file",
            str(env_file),
            "--compose-file",
            str(compose_file),
            "--image",
            "decisiondoc-dawool-local",
            "--build-context",
            str(tmp_path),
            "--skip-build",
            "--post-check",
            "--base-url",
            "https://dawool.decisiondoc.kr",
            "--skip-smoke",
        ]
    )

    assert result == 0
    assert len(calls) == 2
    assert calls[0][0][:4] == ["docker", "compose", "--env-file", str(env_file)]
    assert calls[0][1]["DOCKER_IMAGE"] == "decisiondoc-dawool-local"
    assert calls[1][0] == [
        deployer.sys.executable,
        "scripts/post_deploy_check.py",
        "--env-file",
        str(env_file),
        "--compose-file",
        str(compose_file),
        "--base-url",
        "https://dawool.decisiondoc.kr",
        "--skip-smoke",
        "--report-dir",
        str(deployer.DEFAULT_POST_CHECK_REPORT_DIR),
    ]


def test_deploy_compose_local_allows_custom_report_path(tmp_path: Path, monkeypatch) -> None:
    deployer = _load_script_module("decisiondoc_deploy_compose_local_report", "scripts/deploy_compose_local.py")
    env_file = tmp_path / ".env.prod"
    env_file.write_text("DECISIONDOC_ENV=prod\n", encoding="utf-8")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    custom_report = tmp_path / "reports" / "custom-post-deploy.json"

    calls: list[tuple[list[str], dict[str, str]]] = []

    def _fake_run(command, cwd=None, env=None, check=False):
        _ = cwd, check
        calls.append((list(command), dict(env or {})))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deployer.subprocess, "run", _fake_run)

    result = deployer.deploy_compose_local(
        env_file=env_file,
        compose_file=compose_file,
        image="decisiondoc-custom-report-local",
        build_context=tmp_path,
        skip_build=True,
        post_check=True,
        report_file=custom_report,
    )

    assert result == 0
    assert calls[1][0][-2:] == ["--report-file", str(custom_report)]


def test_deploy_compose_local_requires_existing_env_file(tmp_path: Path) -> None:
    deployer = _load_script_module("decisiondoc_deploy_compose_local_missing", "scripts/deploy_compose_local.py")
    compose_file = tmp_path / "docker-compose.prod.yml"
    compose_file.write_text("services: {}\n", encoding="utf-8")

    try:
        deployer.deploy_compose_local(
            env_file=tmp_path / ".env.prod",
            compose_file=compose_file,
            image="decisiondoc-missing-env",
            build_context=tmp_path,
        )
    except SystemExit as exc:
        assert "Env file not found" in str(exc)
    else:
        raise AssertionError("Expected SystemExit for missing env file")
