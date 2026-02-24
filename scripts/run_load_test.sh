#!/bin/bash
# Workflow Orchestrator: Load Test Runner
# Ensures the environment is ready and triggers the load test logic.

set -e

BASE_URL="${1:-http://localhost:8000}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}============================================${NC}"
echo -e "${YELLOW}  Workflow Orchestrator: Load Test Runner    ${NC}"
echo -e "${YELLOW}  Target: $BASE_URL                         ${NC}"
echo -e "${YELLOW}============================================${NC}"

# Logic to ensure the environment is running
check_health() {
    curl -s "$BASE_URL/health" | grep -q "healthy"
}

if ! check_health; then
    echo -e "${YELLOW}⚠ Host is not responding. Attempting to start services...${NC}"
    ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    if [ -f "$ENGINE_DIR/docker-compose.yml" ]; then
        cd "$ENGINE_DIR"
        docker compose up -d
        echo -e "${YELLOW}⏳ Waiting for services to become healthy...${NC}"
        
        MAX_RETRIES=30
        RETRY_COUNT=0
        until check_health || [ $RETRY_COUNT -eq $MAX_RETRIES ]; do
            sleep 1
            RETRY_COUNT=$((RETRY_COUNT + 1))
            echo -n "."
        done
        echo ""
        
        if ! check_health; then
            echo -e "${RED}✗ ERROR: Services failed to start.${NC}"
            exit 1
        fi
        echo -e "${GREEN}✓ Services are up and healthy!${NC}"
    else
        echo -e "${RED}✗ ERROR: Cannot find docker-compose.yml at $ENGINE_DIR.${NC}"
        exit 1
    fi
fi

echo -e "${YELLOW}⏳ Running database migrations...${NC}"
ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ENGINE_DIR" && docker compose exec -T api alembic upgrade head

echo -e "\n${YELLOW}=== Starting Load Test (via Docker) ===${NC}"
ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Run inside the 'api' container where dependencies are already installed.
# We use 'http://localhost:8000' because the script is now running local to the API.
docker compose exec api python3 scripts/load_test.py

echo -e "\n${YELLOW}============================================${NC}"
echo -e "${GREEN}Load test session concluded.${NC}"
echo -e "${YELLOW}============================================${NC}"
