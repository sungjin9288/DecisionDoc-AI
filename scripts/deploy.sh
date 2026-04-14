#!/bin/bash
# DecisionDoc AI deployment script
# Usage: ./scripts/deploy.sh [staging|production] [image_tag_or_ref]
set -euo pipefail

ENVIRONMENT=${1:-staging}
IMAGE_INPUT=${2:-latest}
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"
POST_DEPLOY_REPORT_DIR="./reports/post-deploy"

if [[ "$ENVIRONMENT" == "production" ]]; then
    ENV_FILE=".env.prod"
fi

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: Env file not found: $ENV_FILE"
    exit 1
fi

if [[ "$IMAGE_INPUT" == *"/"* || "$IMAGE_INPUT" == *":"* ]]; then
    IMAGE_REF="$IMAGE_INPUT"
else
    IMAGE_REF="ghcr.io/sungjin9288/decisiondoc-ai:$IMAGE_INPUT"
fi

echo "Deploying DecisionDoc AI"
echo "   Environment: $ENVIRONMENT"
echo "   Env file: $ENV_FILE"
echo "   Image: $IMAGE_REF"

if [[ "$ENVIRONMENT" == "production" ]]; then
    echo "WARNING: Production deploy — confirmation required."
    read -r -p "Deploy to PRODUCTION? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Aborted."
        exit 0
    fi

    echo "Running production env preflight..."
    python3 scripts/check_prod_env.py --env-file "$ENV_FILE"
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
