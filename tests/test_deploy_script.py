from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "scripts" / "deploy.sh"


def _deploy_script_text() -> str:
    return DEPLOY_SCRIPT.read_text(encoding="utf-8")


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
