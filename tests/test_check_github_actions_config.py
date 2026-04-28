from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check-github-actions-config.sh"


def _write_env_file(
    path: Path,
    *,
    stage: str = "dev",
    include_g2b: bool = True,
    include_target: bool = False,
    include_deploy: bool = False,
    partial_deploy: bool = False,
) -> None:
    stage_upper = stage.upper()
    deploy_prefix = "STAGING" if stage == "dev" else "PROD"
    lines = [
        "AWS_REGION=ap-northeast-2",
        "DECISIONDOC_API_KEY=repo-api-key",
        "DECISIONDOC_OPS_KEY=repo-ops-key",
        f"AWS_ROLE_ARN_{stage_upper}=arn:aws:iam::123456789012:role/{stage}",
        f"DECISIONDOC_S3_BUCKET_{stage_upper}=decisiondoc-{stage}",
        f"DECISIONDOC_PROCUREMENT_COPILOT_ENABLED_{stage_upper}=1",
    ]
    if include_g2b:
        lines.append(f"G2B_API_KEY_{stage_upper}={stage}-g2b-key")
    if include_target:
        lines.append(f"PROCUREMENT_SMOKE_URL_OR_NUMBER_{stage_upper}=20260405001-00")
    if include_deploy:
        lines.extend(
            [
                f"{deploy_prefix}_HOST={stage}.decisiondoc.internal",
                f"{deploy_prefix}_USER=ubuntu",
                f"{deploy_prefix}_SSH_KEY=test-private-key",
            ]
        )
    if partial_deploy:
        lines.append(f"{deploy_prefix}_HOST={stage}.decisiondoc.internal")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_check_github_actions_config_allows_procurement_smoke_without_fixed_target(tmp_path: Path) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_env_file(env_file, include_g2b=True, include_target=False)

    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--stage", "dev", "--env-file", str(env_file), "--procurement-smoke"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "OK     G2B_API_KEY_DEV" in completed.stdout
    assert "EMPTY  PROCUREMENT_SMOKE_URL_OR_NUMBER_DEV" in completed.stdout
    assert "All required entries are present." in completed.stdout


def test_check_github_actions_config_requires_g2b_key_for_procurement_smoke(tmp_path: Path) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_env_file(env_file, include_g2b=False, include_target=False)

    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--stage", "dev", "--env-file", str(env_file), "--procurement-smoke"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "MISSING G2B_API_KEY_DEV" in completed.stdout
    assert "EMPTY  PROCUREMENT_SMOKE_URL_OR_NUMBER_DEV" in completed.stdout
    assert "Missing required entries (1):" in completed.stdout
    assert "  - G2B_API_KEY_DEV" in completed.stdout


def test_check_github_actions_config_requires_docker_deploy_secrets_when_enabled(tmp_path: Path) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_env_file(env_file)

    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--stage", "dev", "--env-file", str(env_file), "--docker-deploy"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "MISSING STAGING_HOST" in completed.stdout
    assert "MISSING STAGING_USER" in completed.stdout
    assert "MISSING STAGING_SSH_KEY" in completed.stdout


def test_check_github_actions_config_accepts_docker_deploy_secrets_when_enabled(tmp_path: Path) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_env_file(env_file, include_deploy=True)

    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--stage", "dev", "--env-file", str(env_file), "--docker-deploy"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "OK     STAGING_HOST" in completed.stdout
    assert "OK     STAGING_USER" in completed.stdout
    assert "OK     STAGING_SSH_KEY" in completed.stdout


def test_check_github_actions_config_accepts_prod_docker_deploy_secrets_when_enabled(tmp_path: Path) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_env_file(env_file, stage="prod", include_deploy=True)

    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--stage", "prod", "--env-file", str(env_file), "--docker-deploy"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "OK     PROD_HOST" in completed.stdout
    assert "OK     PROD_USER" in completed.stdout
    assert "OK     PROD_SSH_KEY" in completed.stdout


def test_check_github_actions_config_rejects_partial_docker_deploy_secrets_when_optional(tmp_path: Path) -> None:
    env_file = tmp_path / "github-actions.env"
    _write_env_file(env_file, partial_deploy=True)

    completed = subprocess.run(
        ["bash", str(SCRIPT_PATH), "--stage", "dev", "--env-file", str(env_file)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    assert "INVALID STAGING_*" in completed.stdout
    assert "set STAGING_HOST, STAGING_USER, and STAGING_SSH_KEY together" in completed.stdout
