FROM python:3.10-slim AS base

WORKDIR /app

# Upgrade pip build tooling to latest to pick up any security patches
RUN pip install --upgrade pip setuptools wheel jaraco.context

RUN pip install poetry==1.8.4 && \
    poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./
RUN poetry install --no-interaction --no-ansi --no-root

COPY . .

FROM base AS development
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS production
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN poetry install --no-interaction --no-ansi --no-root --only main
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
