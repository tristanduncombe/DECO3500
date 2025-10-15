# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Install uv and build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential libgl1 libglib2.0-0 libpq5 libsm6 libxrender1 libxext6 \
 && rm -rf /var/lib/apt/lists/* \
 && curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy project metadata first for better layer caching
COPY pyproject.toml uv.lock* ./

# Sync dependencies with uv (use lockfile if present)
RUN if [ -f uv.lock ]; then uv sync --frozen --no-dev; else uv sync --no-dev; fi

# Copy application code
COPY . .

EXPOSE 8000

# Run using uv-managed environment
CMD ["uv", "run", "fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]
