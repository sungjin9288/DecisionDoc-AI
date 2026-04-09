#!/bin/bash
# SSL certificate setup using Let's Encrypt (Certbot)
# Usage: ./scripts/setup_ssl.sh your-domain.com admin@your-domain.com
set -euo pipefail

DOMAIN=${1:-""}
EMAIL=${2:-""}
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$APP_DIR/docker-compose.prod.yml"
ENV_FILE="$APP_DIR/.env.prod"

if [[ -z "$DOMAIN" || -z "$EMAIL" ]]; then
  echo "Usage: $0 <domain> <email>"
  echo "Example: $0 decisiondoc.company.kr admin@company.kr"
  exit 1
fi

echo "SSL Setup for $DOMAIN"

# Install certbot if needed
if ! command -v certbot &>/dev/null; then
  echo "Installing certbot..."
  apt-get update -q && apt-get install -y certbot python3-certbot-nginx
fi

# Issue certificate
certbot certonly --standalone \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  --domains "$DOMAIN" \
  --pre-hook "cd $APP_DIR && docker compose --env-file $ENV_FILE -f $COMPOSE_FILE stop nginx 2>/dev/null || true" \
  --post-hook "cd $APP_DIR && docker compose --env-file $ENV_FILE -f $COMPOSE_FILE start nginx 2>/dev/null || true"

# Copy to nginx ssl directory
mkdir -p "$APP_DIR/nginx/ssl"
cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$APP_DIR/nginx/ssl/cert.pem"
cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$APP_DIR/nginx/ssl/key.pem"
chmod 600 "$APP_DIR/nginx/ssl/key.pem"

# Update nginx.conf with actual domain
sed -i "s/server_name _;/server_name $DOMAIN;/" "$APP_DIR/nginx/nginx.conf"

# Setup auto-renewal cron
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --post-hook 'cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $APP_DIR/nginx/ssl/cert.pem && cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $APP_DIR/nginx/ssl/key.pem && cd $APP_DIR && docker compose --env-file $ENV_FILE -f $COMPOSE_FILE exec nginx nginx -s reload'") | crontab -

echo "SSL configured for $DOMAIN"
echo "   Certificate: nginx/ssl/cert.pem"
echo "   Auto-renewal: daily cron (3AM)"
