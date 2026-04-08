#!/bin/bash
# DecisionDoc AI deployment script
# Usage: ./scripts/deploy.sh [staging|production] [image_tag]
set -euo pipefail

ENVIRONMENT=${1:-staging}
IMAGE_TAG=${2:-latest}
COMPOSE_FILE="docker-compose.prod.yml"

echo "Deploying DecisionDoc AI"
echo "   Environment: $ENVIRONMENT"
echo "   Image: $IMAGE_TAG"

# Confirm production deploy
if [[ "$ENVIRONMENT" == "production" ]]; then
    echo "WARNING: Production deploy — confirmation required."
    read -p "Deploy to PRODUCTION? (yes/no): " confirm
    if [[ "$confirm" != "yes" ]]; then
        echo "Aborted."
        exit 0
    fi
fi

# Validate required env vars
required_vars=(JWT_SECRET_KEY ALLOWED_ORIGINS)
for var in "${required_vars[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: Required env var not set: $var"
        exit 1
    fi
done

# Backup data
echo "Backing up data..."
BACKUP_DIR="/backup/decisiondoc"
mkdir -p "$BACKUP_DIR"
if [[ -d "./data" ]]; then
    tar czf "$BACKUP_DIR/data-$(date +%Y%m%d-%H%M%S).tar.gz" ./data/
    echo "   Backup saved to $BACKUP_DIR"
fi

# Pull new image
export DOCKER_IMAGE="${DOCKER_IMAGE:-ghcr.io/sungjin9288/decisiondoc-ai:$IMAGE_TAG}"
echo "Pulling image: $DOCKER_IMAGE"
docker compose -f "$COMPOSE_FILE" pull

# Deploy
echo "Deploying..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Wait for health
echo "Waiting for health check..."
for i in {1..24}; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "Deploy successful!"
        docker compose -f "$COMPOSE_FILE" ps
        exit 0
    fi
    echo "   Attempt $i/24..."
    sleep 5
done

echo "ERROR: Health check failed after 120s"
exit 1
