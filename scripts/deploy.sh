#!/bin/bash
# DecisionDoc AI deployment script
# Usage: ./scripts/deploy.sh [staging|production] [image_tag_or_ref]
set -euo pipefail

ENVIRONMENT=${1:-staging}
IMAGE_INPUT=${2:-latest}
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"
POST_DEPLOY_REPORT_DIR="./reports/post-deploy"
PROVIDER_PROFILE=${DECISIONDOC_DEPLOY_PROVIDER_PROFILE:-standard}
IS_RELEASE_TAG_INPUT=false

if [[ "$ENVIRONMENT" == "production" ]]; then
    ENV_FILE=".env.prod"
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Env file not found: $ENV_FILE"
    exit 1
fi

if [[ "$IMAGE_INPUT" != *"/"* && "$IMAGE_INPUT" != *":"* && "$IMAGE_INPUT" =~ ^v[0-9]+[.][0-9]+[.][0-9]+$ ]]; then
    IS_RELEASE_TAG_INPUT=true
fi

if [[ "$ENVIRONMENT" == "production" && "$IMAGE_INPUT" != *"/"* && "$IMAGE_INPUT" != *":"* && "$IMAGE_INPUT" =~ ^v && "$IS_RELEASE_TAG_INPUT" != "true" ]]; then
    echo "ERROR: Production release tag input must match vMAJOR.MINOR.PATCH, for example v1.2.3."
    echo "       For non-semver rollback images, pass the full image ref, for example ghcr.io/...:rollback-tag."
    exit 1
fi

if [[ "$IMAGE_INPUT" == *"/"* || "$IMAGE_INPUT" == *":"* ]]; then
    IMAGE_REF="$IMAGE_INPUT"
else
    IMAGE_TAG="$IMAGE_INPUT"
    if [[ "$ENVIRONMENT" == "production" && "$IS_RELEASE_TAG_INPUT" == "true" ]]; then
        IMAGE_TAG="${IMAGE_INPUT#v}"
    fi
    IMAGE_REF="ghcr.io/sungjin9288/decisiondoc-ai:$IMAGE_TAG"
fi

echo "Deploying DecisionDoc AI"
echo "   Environment: $ENVIRONMENT"
echo "   Env file: $ENV_FILE"
echo "   Image: $IMAGE_REF"
echo "   Provider profile: $PROVIDER_PROFILE"

if [[ "$ENVIRONMENT" == "production" ]]; then
    echo "WARNING: Production deploy — confirmation required."
    read -r -p "Deploy to PRODUCTION? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Aborted."
        exit 0
    fi

    if [[ "$IS_RELEASE_TAG_INPUT" == "true" ]]; then
        echo "Running release tag source preflight..."
        python3 scripts/check_release_tag_source.py "$IMAGE_INPUT"
    else
        echo "Skipping release tag source preflight (image input is not a vMAJOR.MINOR.PATCH release tag)."
    fi

    echo "Running production env preflight..."
    python3 scripts/check_prod_env.py --env-file "$ENV_FILE" --provider-profile "$PROVIDER_PROFILE"
fi

if [[ -x "./scripts/backup.sh" && -d "./data" ]]; then
    echo "Running pre-deploy backup..."
    ./scripts/backup.sh
else
    echo "Skipping pre-deploy backup (host data directory not found)."
fi

echo "Rolling out image..."
DOCKER_IMAGE="$IMAGE_REF" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --force-recreate

if [[ "$ENVIRONMENT" == "production" ]]; then
    echo "Running post-deploy verification..."
    python3 scripts/post_deploy_check.py --env-file "$ENV_FILE" --report-dir "$POST_DEPLOY_REPORT_DIR"
    echo "Post-deploy report history saved under: $POST_DEPLOY_REPORT_DIR"
else
    echo "Running staging health check..."
    curl -sf http://localhost:8000/health > /dev/null
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
    echo "Deploy successful!"
fi
