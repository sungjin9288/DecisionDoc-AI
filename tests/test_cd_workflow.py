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
    assert deploy_production["permissions"]["contents"] == "read"
    assert deploy_production["if"] == "startsWith(github.ref, 'refs/tags/v')"


def test_cd_production_tag_must_point_to_main_history():
    workflow = _load_cd_workflow()
    production_steps = workflow["jobs"]["deploy-production"]["steps"]
    checkout_step = next(step for step in production_steps if step.get("name") == "Checkout release tag with full history")
    source_step = next(step for step in production_steps if step.get("name") == "Validate production release source")
    deploy_step = next(step for step in production_steps if step.get("name") == "Deploy to production")

    assert checkout_step["uses"] == "actions/checkout@v6"
    assert checkout_step["with"]["fetch-depth"] == 0
    assert source_step["id"] == "production_release_source"
    assert "git fetch --no-tags --prune origin +refs/heads/main:refs/remotes/origin/main" in source_step["run"]
    assert 'git merge-base --is-ancestor "$GITHUB_SHA" refs/remotes/origin/main' in source_step["run"]
    assert 'echo "main_ancestor=true" >> "$GITHUB_OUTPUT"' in source_step["run"]
    assert 'echo "main_ancestor=false" >> "$GITHUB_OUTPUT"' in source_step["run"]
    assert "Production release tags must point to commits reachable from origin/main." in source_step["run"]
    assert (
        deploy_step["if"]
        == "steps.production_release_source.outputs.main_ancestor == 'true' && steps.production_config.outputs.configured == 'true'"
    )


def test_cd_staging_deploy_remains_main_branch_only_and_optional():
    workflow = _load_cd_workflow()
    deploy_staging = workflow["jobs"]["deploy-staging"]
    step_names = [step.get("name", "") for step in deploy_staging["steps"]]

    assert deploy_staging["needs"] == "build-and-push"
    assert deploy_staging["if"] == "github.ref == 'refs/heads/main'"
    assert "Check staging deploy configuration" in step_names
    assert "Summarize staging deploy decision" in step_names


def test_cd_staging_summary_records_skip_reason_for_unconfigured_secrets():
    workflow = _load_cd_workflow()
    summary_step = next(
        step
        for step in workflow["jobs"]["deploy-staging"]["steps"]
        if step.get("name") == "Summarize staging deploy decision"
    )

    assert summary_step["if"] == "always()"
    assert summary_step["env"]["STAGING_CONFIGURED"] == "${{ steps.staging_config.outputs.configured }}"
    assert "## Staging deployment" in summary_step["run"]
    assert 'echo "- status: skipped"' in summary_step["run"]
    assert 'echo "- reason: staging secrets are not configured."' in summary_step["run"]
    assert "STAGING_HOST, STAGING_USER, STAGING_SSH_KEY" in summary_step["run"]
    assert '>> "$GITHUB_STEP_SUMMARY"' in summary_step["run"]


def test_cd_production_summary_records_secret_preflight_result():
    workflow = _load_cd_workflow()
    production_steps = workflow["jobs"]["deploy-production"]["steps"]
    validate_step = next(step for step in production_steps if step.get("name") == "Validate production deploy secrets")
    summary_step = next(step for step in production_steps if step.get("name") == "Summarize production deploy decision")

    assert validate_step["id"] == "production_config"
    assert 'echo "configured=true" >> "$GITHUB_OUTPUT"' in validate_step["run"]
    assert 'echo "configured=false" >> "$GITHUB_OUTPUT"' in validate_step["run"]
    assert "::error::Missing production secret: PROD_HOST" in validate_step["run"]
    assert "::error::Missing production secret: PROD_USER" in validate_step["run"]
    assert "::error::Missing production secret: PROD_SSH_KEY" in validate_step["run"]
    assert summary_step["if"] == "always()"
    assert summary_step["env"]["RELEASE_SOURCE_OK"] == "${{ steps.production_release_source.outputs.main_ancestor }}"
    assert summary_step["env"]["PROD_CONFIGURED"] == "${{ steps.production_config.outputs.configured }}"
    assert "## Production deployment" in summary_step["run"]
    assert "release tag does not point to a commit reachable from origin/main" in summary_step["run"]
    assert 'echo "- status: configured"' in summary_step["run"]
    assert 'echo "- status: blocked"' in summary_step["run"]
    assert "PROD_HOST, PROD_USER, PROD_SSH_KEY" in summary_step["run"]
    assert '>> "$GITHUB_STEP_SUMMARY"' in summary_step["run"]


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


def test_cd_production_runs_authenticated_post_deploy_check_after_health():
    workflow = _load_cd_workflow()
    production_script = next(
        step["with"]["script"]
        for step in workflow["jobs"]["deploy-production"]["steps"]
        if step.get("name") == "Deploy to production"
    )

    assert "Production local health check passed" in production_script
    assert 'export SMOKE_TIMEOUT_SEC="${SMOKE_TIMEOUT_SEC:-180}"' in production_script
    assert "python3 scripts/post_deploy_check.py" in production_script
    assert "--env-file .env.prod" in production_script
    assert "--compose-file docker-compose.prod.yml" in production_script
    assert "--base-url https://admin.decisiondoc.kr" in production_script
    assert "--report-dir ./reports/post-deploy" in production_script
    assert production_script.index("curl -sf http://localhost:8000/health") < production_script.index(
        "python3 scripts/post_deploy_check.py"
    )
