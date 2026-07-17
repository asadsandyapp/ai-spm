FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

# Pip/PyPI downloads can flake (BrokenPipe on large wheels like cryptography).
# Retries + longer timeout keep `make up` usable on flaky networks.
ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_RETRIES=5

RUN pip install --upgrade pip \
 && ( \
      for i in 1 2 3 4 5; do \
        echo "=== pip install attempt $i/5 ==="; \
        pip install --no-cache-dir -e ".[dev]" && exit 0; \
        echo "pip install failed (attempt $i) — retrying in $((i * 5))s…"; \
        sleep $((i * 5)); \
      done; \
      echo "pip install failed after 5 attempts"; \
      exit 1; \
    )

ENV PYTHONPATH=/app/src
EXPOSE 8000

CMD ["uvicorn", "ai_spm.main:app", "--host", "0.0.0.0", "--port", "8000"]
