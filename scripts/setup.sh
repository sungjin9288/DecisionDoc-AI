#!/bin/bash
# First-time setup for DecisionDoc AI
set -euo pipefail

echo "DecisionDoc AI Setup"

# Check prerequisites
for cmd in docker openssl python3; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "ERROR: Required: $cmd"
        exit 1
    fi
done

# Generate secrets
echo "Generating secrets..."
JWT_SECRET=$(openssl rand -hex 32)

# Create .env if not exists
if [[ ! -f ".env" ]]; then
    cp .env.example .env
    # Replace placeholder with generated secret
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s/your-secret-key-here/$JWT_SECRET/g" .env
    else
        sed -i "s/your-secret-key-here/$JWT_SECRET/g" .env
    fi
    echo "Created .env (please review and update)"
else
    echo "INFO: .env already exists — skipping"
fi

# Create directories
mkdir -p data nginx/ssl

# Generate self-signed SSL for development
if [[ ! -f "nginx/ssl/cert.pem" ]]; then
    echo "Generating self-signed SSL certificate..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout nginx/ssl/key.pem \
        -out nginx/ssl/cert.pem \
        -subj "/C=KR/ST=Seoul/L=Seoul/O=DecisionDoc/CN=localhost" \
        2>/dev/null
    echo "SSL certificate generated (nginx/ssl/)"
fi

# Generate PWA icons
echo "Generating PWA icons..."
python3 scripts/generate_icons.py 2>/dev/null || echo "INFO: Icon generation skipped"

echo ""
echo "Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys"
echo "  2. docker compose up -d"
echo "  3. Open http://localhost:3300"
