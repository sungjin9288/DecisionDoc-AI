#!/bin/bash
# HA health verification script
set -euo pipefail

COMPOSE_FILE=${1:-docker-compose.ha.yml}
EXPECTED_REPLICAS=${2:-3}

echo "HA Health Check"

# Resolve running containers for the app service
container_ids=$(docker compose -f "$COMPOSE_FILE" ps -q app)
running=$(printf '%s\n' "$container_ids" | sed '/^$/d' | wc -l | tr -d ' ')
echo "   App replicas running: $running / $EXPECTED_REPLICAS"

if [[ "$running" -lt "$EXPECTED_REPLICAS" ]]; then
  echo "Not enough replicas running"
  docker compose -f "$COMPOSE_FILE" ps app
  exit 1
fi

# Check container-level health for each replica
echo "   Checking container health..."
for container_id in $container_ids; do
  name=$(docker inspect -f '{{.Name}}' "$container_id" | sed 's#^/##')
  health=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")
  echo "   Replica $name -- $health"
  if [[ "$health" != "healthy" && "$health" != "running" ]]; then
    echo "Replica $name is not healthy"
    exit 1
  fi
done

# Check nginx
if curl -sf "http://localhost/health" >/dev/null 2>&1; then
  echo "   Nginx load balancer -- healthy"
else
  echo "   Nginx not responding"
  exit 1
fi

echo "   HA check complete -- all replicas healthy"
