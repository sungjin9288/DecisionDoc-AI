#!/bin/bash
# Refresh copied Let's Encrypt certs for nginx and reload the container.
# Usage: ./scripts/refresh_ssl_certs.sh <domain>

set -euo pipefail

export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

DOMAIN=${1:-""}
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$APP_DIR/docker-compose.prod.yml"
ENV_FILE="$APP_DIR/.env.prod"
LIVE_CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
NGINX_SSL_DIR="$APP_DIR/nginx/ssl"

if [[ -z "$DOMAIN" ]]; then
  echo "Usage: $0 <domain>"
  exit 1
fi

if [[ ! -f "$LIVE_CERT_DIR/fullchain.pem" || ! -f "$LIVE_CERT_DIR/privkey.pem" ]]; then
  echo "Certificate files not found for domain: $DOMAIN"
  exit 1
fi

mkdir -p "$NGINX_SSL_DIR"
cp "$LIVE_CERT_DIR/fullchain.pem" "$NGINX_SSL_DIR/cert.pem"
cp "$LIVE_CERT_DIR/privkey.pem" "$NGINX_SSL_DIR/key.pem"
chmod 600 "$NGINX_SSL_DIR/key.pem"

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d nginx >/dev/null 2>&1 || true
if ! docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T nginx nginx -s reload >/dev/null 2>&1; then
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" restart nginx >/dev/null 2>&1 || true
fi

echo "Refreshed nginx SSL certs for $DOMAIN"
