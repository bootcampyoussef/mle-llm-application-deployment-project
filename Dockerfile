
FROM python:3.13.18-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /usr/local/bin/

WORKDIR /app

# Python and environment settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    MODEL_PROVIDER=dry

# Install locked dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Copy our application
COPY app/ ./app/

# Run as non-root user
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

# Lightweight health check
HEALTHCHECK --interval=30s --timeout=5s \
    --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3)"

# Compatible with local Docker and Render PORT
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
