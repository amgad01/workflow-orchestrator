#!/usr/bin/env bash
set -euo pipefail

compose_cmd="docker compose"

cleanup() {
  ${compose_cmd} down
}

trap cleanup EXIT

${compose_cmd} up -d --build

echo "Waiting for API to become ready..."
ready=false
for _ in {1..30}; do
  if curl -fsS http://localhost:8000/health >/dev/null; then
    echo "API is ready."
    ready=true
    break
  fi
  sleep 1
done

if [[ "$ready" != "true" ]]; then
  echo "API did not become ready in time."
  exit 1
fi

echo "Running database migrations..."
${compose_cmd} exec -T api alembic upgrade head

poetry run pytest tests/e2e/ -v
