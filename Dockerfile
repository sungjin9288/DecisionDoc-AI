# ── Stage 1: Builder ──────────────────────────────────
FROM python:3.12-slim AS builder
WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libldap2-dev libsasl2-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ──────────────────────────────────
FROM python:3.12-slim AS runtime
WORKDIR /app

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap-common libsasl2-2 libssl3 curl \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# Install Playwright with chromium for PDF/G2B scraping
RUN pip install --no-cache-dir playwright \
    && playwright install chromium --with-deps \
    && rm -rf /tmp/*

# Copy Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Generate PWA icons
RUN python scripts/generate_icons.py

# Create data directory with proper permissions
RUN mkdir -p /app/data && chmod 755 /app/data

# Create non-root user for security
RUN groupadd -r decisiondoc && useradd -r -g decisiondoc -d /app decisiondoc \
    && chown -R decisiondoc:decisiondoc /app

USER decisiondoc

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production

CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
