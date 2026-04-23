from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "cd.yml"


def _load_cd_workflow() -> dict:
    return yaml.safe_load(CD_WORKFLOW.read_text(encoding="utf-8"))


def test_cd_production_tag_deploy_does_not_depend_on_staging_job():
    workflow = _load_cd_workflow()
    deploy_production = workflow["jobs"]["deploy-production"]

    assert deploy_production["needs"] == "build-and-push"
    assert deploy_production["if"] == "startsWith(github.ref, 'refs/tags/v')"


def test_cd_staging_deploy_remains_main_branch_only_and_optional():
    workflow = _load_cd_workflow()
    deploy_staging = workflow["jobs"]["deploy-staging"]
    step_names = [step.get("name", "") for step in deploy_staging["steps"]]

    assert deploy_staging["needs"] == "build-and-push"
    assert deploy_staging["if"] == "github.ref == 'refs/heads/main'"
    assert "Check staging deploy configuration" in step_names


def test_cd_remote_deploy_scripts_sync_server_checkout_before_compose():
    workflow = _load_cd_workflow()

    staging_script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["deploy-staging"]["steps"]
        if step.get("name") == "Deploy to staging server"
    )
    production_script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["deploy-production"]["steps"]
        if step.get("name") == "Deploy to production"
    )

    assert "git fetch --prune origin" in staging_script
    assert "git -c advice.detachedHead=false checkout --force ${{ github.sha }}" in staging_script
    assert "git fetch --prune origin" in production_script
    assert "git -c advice.detachedHead=false checkout --force ${{ github.sha }}" in production_script


def test_cd_staging_uses_branch_image_tag_that_metadata_action_publishes():
    workflow = _load_cd_workflow()
    staging_script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["deploy-staging"]["steps"]
        if step.get("name") == "Deploy to staging server"
    )

    assert "tr '[:upper:]' '[:lower:]'" in staging_script
    assert 'export DOCKER_IMAGE="${IMAGE_REPO}:main"' in staging_script
    assert "sha-${{ github.sha }}" not in staging_script


def test_cd_remote_deploy_scripts_fail_fast_and_use_prod_env_file():
    workflow = _load_cd_workflow()

    staging_script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["deploy-staging"]["steps"]
        if step.get("name") == "Deploy to staging server"
    )
    production_script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["deploy-production"]["steps"]
        if step.get("name") == "Deploy to production"
    )

    for script in (staging_script, production_script):
        assert script.startswith("set -eu\n")
        assert "tr '[:upper:]' '[:lower:]'" in script
        assert "docker compose --env-file .env.prod -f docker-compose.prod.yml pull" in script
        assert "docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --remove-orphans" in script
        assert "docker compose -f docker-compose.prod.yml" not in script


def test_cd_production_uses_release_tag_from_lowercase_image_repository():
    workflow = _load_cd_workflow()
    production_script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["deploy-production"]["steps"]
        if step.get("name") == "Deploy to production"
    )

    assert 'IMAGE_TAG="${{ github.ref_name }}"' in production_script
    assert 'IMAGE_TAG="${IMAGE_TAG#v}"' in production_script
    assert 'export DOCKER_IMAGE="${IMAGE_REPO}:${IMAGE_TAG}"' in production_script
    assert "ghcr.io/${{ github.repository }}:${{ github.ref_name }}" not in production_script


def test_cd_production_backup_uses_writable_repo_local_default():
    workflow = _load_cd_workflow()
    production_script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["deploy-production"]["steps"]
        if step.get("name") == "Deploy to production"
    )

    assert 'BACKUP_DIR="${DECISIONDOC_BACKUP_DIR:-./backups}"' in production_script
    assert 'mkdir -p "$BACKUP_DIR"' in production_script
    assert "mkdir -p /backup" not in production_script
    assert "tar czf /backup" not in production_script
