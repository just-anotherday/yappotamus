# =============================================================
# YapVibes Stocks Backend - Production Dockerfile
# Target: Railway deployment
# Base: Python 3.12 slim
# =============================================================

FROM python:3.12-slim AS base

# Prevent Python from creating .pyc files and enable buffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

# Install system dependencies (asyncpg needs libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend ./backend
COPY alembic.ini .
COPY alembic ./alembic
COPY run.py .

 # Expose port (default to 8000; Railway injects PORT env var dynamically)
 ENV PORT=8000
 EXPOSE ${PORT}

 # Process-only health check; database readiness is exposed separately at /health.
 HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
     CMD python -c "import os, urllib.request; urllib.request.urlopen('http://localhost:' + os.getenv('PORT', '8000') + '/health/live')" || exit 1

 # Use run.py which handles production detection + dynamic PORT reading
 CMD ["python", "run.py"]
