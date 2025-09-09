# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

WORKDIR /app

# Install build deps (if any needed for future extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata first for better layer caching
COPY pyproject.toml uv.lock* ./

# Use uv (fast Python package installer) if lock present; fallback to pip
RUN pip install --upgrade pip
# If uv is required specifically, you could: pip install uv
# Install deps (FastAPI + SQLModel)
RUN pip install fastapi fastapi-cli sqlmodel uvicorn[standard] psycopg[binary]

# Copy application code
COPY . .

EXPOSE 8000

# Run with reload disabled (prod). For dev: add --reload and mount volume in compose override
CMD ["fastapi", "run", "main.py", "--port", "8000"]
