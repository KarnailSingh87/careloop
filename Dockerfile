# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# Install system utilities (curl for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY pyproject.toml .

# Install dependencies into system Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Copy application code, simulator UI, and scripts
COPY careloop/ ./careloop/
COPY scripts/ ./scripts/

# Default environment configuration
ENV PYTHONUNBUFFERED=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    STORAGE_BACKEND=dynamodb \
    DYNAMODB_TABLE_NAME=CareLoopData \
    NOTIFIER_TYPE=sns \
    AWS_REGION=us-east-1 \
    BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0 \
    CLOCK_MODE=system \
    ESCALATION_TICK_INTERVAL_SECONDS=60.0

EXPOSE 8000

# Docker healthcheck querying FastMCP health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health || exit 1

# Launch CareLoop FastMCP Streamable HTTP server
ENTRYPOINT ["python", "-m", "careloop.server"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--storage", "dynamodb"]
