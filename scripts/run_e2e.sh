#!/usr/bin/env bash
set -euo pipefail

compose_cmd="docker compose"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

cleanup() {
  echo -e "${YELLOW}[ACK] Cleaning up Docker services...${NC}"
  ${compose_cmd} down
  echo -e "${GREEN}[ACK] Cleanup done${NC}"
}

trap cleanup EXIT

echo -e "${BLUE}[ACK] Starting Docker build and services...${NC}"
${compose_cmd} up -d --build
echo -e "${GREEN}[ACK] Docker services started${NC}"

echo -e "\n${BLUE}[ACK] Waiting for API to become ready...${NC}"
ready=false
for _ in {1..30}; do
  if curl -fsS http://localhost:8000/health >/dev/null; then
    echo -e "${GREEN}[ACK] API is ready${NC}"
    ready=true
    break
  fi
  sleep 1
done

if [[ "$ready" != "true" ]]; then
  echo -e "${RED}[FAILURE] API did not become ready in time${NC}"
  exit 1
fi

echo -e "\n${BLUE}[ACK] Running database migrations...${NC}"
if ${compose_cmd} exec -T api alembic upgrade head > /dev/null 2>&1; then
  echo -e "${GREEN}[ACK] Database migrations done${NC}"
else
  echo -e "${RED}[FAILURE] Database migrations failed${NC}"
  exit 1
fi

echo -e "\n${BLUE}[ACK] Running e2e tests...${NC}"
if poetry run pytest tests/e2e/ -v; then
  echo -e "\n${GREEN}════════════════════════════════════════════════════════${NC}"
  echo -e "${GREEN}[SUCCESS] All e2e tests passed${NC}"
  echo -e "${GREEN}════════════════════════════════════════════════════════${NC}"
  exit 0
else
  echo -e "\n${RED}════════════════════════════════════════════════════════${NC}"
  echo -e "${RED}[FAILURE] Some e2e tests failed${NC}"
  echo -e "${RED}════════════════════════════════════════════════════════${NC}"
  exit 1
fi
