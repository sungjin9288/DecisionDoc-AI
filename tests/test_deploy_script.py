from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy.sh"


def _deploy_script_text() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _copy_deploy_fixture(tmp_path: Path) -> Path:
    fixture_root = tmp_path / "deploy-fixture"
    scripts_dir = fixture_root / "scripts"
    bin_dir = fixture_root / "bin"
    scripts_dir.mkdir(parents=True)
    bin_dir.mkdir()

    shutil.copy2(DEPLOY_SCRIPT, scripts_dir / "deploy.sh")
    (fixture_root / ".env.prod").write_text("DECISIONDOC_ENV=prod\n", encoding="utf-8")
    _write_executable(
        bin_dir / "python3",
        """#!/bin/sh
printf 'python3 %s\\n' "$*" >> "$PYTHON_CALL_LOG"
exit 0
""",
    )
    _write_executable(
        bin_dir / "docker",
        """#!/bin/sh
printf 'DOCKER_IMAGE=%s docker %s\\n' "$DOCKER_IMAGE" "$*" >> "$DOCKER_CALL_LOG"
exit 0
""",
    )
    return fixture_root


def _run_production_deploy_fixture(tmp_path: Path, image_input: str) -> tuple[subprocess.CompletedProcess[str], str, str]:
    fixture_root = _copy_deploy_fixture(tmp_path)
    python_log = fixture_root / "python.log"
    docker_log = fixture_root / "docker.log"
    env = os.environ.copy()
    env["PATH"] = f"{fixture_root / 'bin'}{os.pathsep}{env['PATH']}"
    env["PYTHON_CALL_LOG"] = str(python_log)
    env["DOCKER_CALL_LOG"] = str(docker_log)

    completed = subprocess.run(
        ["bash", "scripts/deploy.sh", "production", image_input],
        cwd=fixture_root,
        input="yes\n",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return (
        completed,
        python_log.read_text(encoding="utf-8") if python_log.exists() else "",
        docker_log.read_text(encoding="utf-8") if docker_log.exists() else "",
    )


def test_deploy_script_runs_release_tag_source_preflight_for_production_release_tags() -> None:
    text = _deploy_script_text()

    assert 'IS_RELEASE_TAG_INPUT=false' in text
    assert '[[ "$IMAGE_INPUT" != *"/"* && "$IMAGE_INPUT" != *":"* && "$IMAGE_INPUT" =~ ^v' in text
    assert 'echo "Running release tag source preflight..."' in text
    assert 'python3 scripts/check_release_tag_source.py "$IMAGE_INPUT"' in text
    assert 'echo "Running production env preflight..."' in text
    assert text.index('python3 scripts/check_release_tag_source.py "$IMAGE_INPUT"') < text.index(
        'python3 scripts/check_prod_env.py --env-file "$ENV_FILE" --provider-profile "$PROVIDER_PROFILE"'
    )


def test_deploy_script_strips_v_prefix_for_production_semver_image_tags() -> None:
    text = _deploy_script_text()

    assert 'if [[ "$ENVIRONMENT" == "production" && "$IS_RELEASE_TAG_INPUT" == "true" ]]; then' in text
    assert 'IMAGE_TAG="${IMAGE_INPUT#v}"' in text
    assert 'IMAGE_REF="ghcr.io/sungjin9288/decisiondoc-ai:$IMAGE_TAG"' in text
    assert 'IMAGE_REF="ghcr.io/sungjin9288/decisiondoc-ai:$IMAGE_INPUT"' not in text


def test_deploy_script_allows_full_image_refs_without_release_tag_preflight() -> None:
    text = _deploy_script_text()

    assert 'if [[ "$IMAGE_INPUT" == *"/"* || "$IMAGE_INPUT" == *":"* ]]; then' in text
    assert 'IMAGE_REF="$IMAGE_INPUT"' in text
    assert 'Skipping release tag source preflight (image input is not a v*.*.* release tag).' in text


def test_deploy_script_executes_release_tag_preflight_before_prod_env_check(tmp_path: Path) -> None:
    completed, python_log, docker_log = _run_production_deploy_fixture(tmp_path, "v9.8.7")

    assert completed.returncode == 0, completed.stderr
    assert "python3 scripts/check_release_tag_source.py v9.8.7" in python_log
    assert "python3 scripts/check_prod_env.py --env-file .env.prod --provider-profile standard" in python_log
    assert python_log.index("scripts/check_release_tag_source.py") < python_log.index("scripts/check_prod_env.py")
    assert "python3 scripts/post_deploy_check.py --env-file .env.prod --report-dir ./reports/post-deploy" in python_log
    assert "DOCKER_IMAGE=ghcr.io/sungjin9288/decisiondoc-ai:9.8.7 docker compose" in docker_log


def test_deploy_script_executes_full_image_ref_without_release_tag_preflight(tmp_path: Path) -> None:
    image_ref = "ghcr.io/example/decisiondoc-ai:rollback-20260429"
    completed, python_log, docker_log = _run_production_deploy_fixture(tmp_path, image_ref)

    assert completed.returncode == 0, completed.stderr
    assert "scripts/check_release_tag_source.py" not in python_log
    assert "python3 scripts/check_prod_env.py --env-file .env.prod --provider-profile standard" in python_log
    assert f"DOCKER_IMAGE={image_ref} docker compose" in docker_log
