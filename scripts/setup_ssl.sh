#!/bin/bash
# SSL certificate setup using Let's Encrypt (Certbot)
# Usage: ./scripts/setup_ssl.sh your-domain.com admin@your-domain.com
set -euo pipefail

DOMAIN=${1:-""}
EMAIL=${2:-""}
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$APP_DIR/docker-compose.prod.yml"
ENV_FILE="$APP_DIR/.env.prod"
REFRESH_SCRIPT="$APP_DIR/scripts/refresh_ssl_certs.sh"

cleanup() {
  cd "$APP_DIR"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" start nginx 2>/dev/null || true
}

trap cleanup EXIT

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "Usage: $0 <domain> <email>"
  echo "Example: $0 decisiondoc.company.kr admin@company.kr"
  exit 1
fi

echo "SSL Setup for $DOMAIN"

# Install certbot if needed
if ! command -v certbot &>/dev/null; then
  echo "Installing certbot..."
  apt-get update -q && apt-get install -y certbot
fi

cd "$APP_DIR"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" stop nginx 2>/dev/null || true

# Issue certificate
certbot certonly --standalone \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  --domains "$DOMAIN"

"$REFRESH_SCRIPT" "$DOMAIN"

# Setup auto-renewal cron
CRON_CMD="0 3 * * * certbot renew --quiet --deploy-hook '$REFRESH_SCRIPT $DOMAIN' >> /var/log/decisiondoc-ssl-renew.log 2>&1"
(crontab -l 2>/dev/null | grep -v "decisiondoc-ssl-renew.log" | grep -v "refresh_ssl_certs.sh $DOMAIN" || true; echo "$CRON_CMD") | crontab -

echo "SSL configured for $DOMAIN"
echo "   Certificate: nginx/ssl/cert.pem"
echo "   Auto-renewal: daily cron (3AM) via scripts/refresh_ssl_certs.sh"
