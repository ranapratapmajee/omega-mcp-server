# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

WORKDIR /app

# Install uv from official distroless image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 1. Install dependencies first (layer caching)
COPY pyproject.toml uv.lock* ./
RUN uv venv /app/.venv && \
    uv pip install --no-cache -r pyproject.toml

# 2. Copy source code and package files
COPY src/ /app/src/
COPY README.md ./

# Install project package into the venv
RUN uv pip install --no-cache --no-deps -e .

# 3. Security: Run container as non-root user
RUN groupadd -g 1001 mcpuser && \
    useradd -u 1001 -g mcpuser -s /bin/bash -m mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

EXPOSE 8080

CMD ["python", "-m", "mcp_server.server"]