FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY scripts/ scripts/

RUN pip install --no-cache-dir .

EXPOSE 8000

# Secrets injected via environment variables at runtime:
# LYCHEE_WEBHOOK_SECRET, LYCHEE_APP_ID, LYCHEE_PRIVATE_KEY_PATH
# ANTHROPIC_API_KEY

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "-m", "scripts.run_server"]
