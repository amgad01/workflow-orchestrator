#!/bin/bash

# Workflow Orchestrator - Initialization Script
# This script automates the complete setup: environment setup, Docker build/start, and database initialization

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}  Workflow Orchestrator - Initialization${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"

# Get the repository root directory
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo -e "${YELLOW}📍 Repository root: $REPO_ROOT${NC}"

# Step 1: Check prerequisites
echo -e "\n${BLUE}Step 1: Checking prerequisites...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker found${NC}"

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}✗ Docker Compose is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Docker Compose found${NC}"

# Step 2: Create .env file if it doesn't exist
echo -e "\n${BLUE}Step 2: Setting up environment...${NC}"

if [ -f .env ]; then
    echo -e "${YELLOW}⚠ .env file already exists, skipping creation${NC}"
else
    if [ ! -f .env.example ]; then
        echo -e "${RED}✗ .env.example not found${NC}"
        exit 1
    fi
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env from .env.example${NC}"
fi

# Step 3: Start Docker services
echo -e "\n${BLUE}Step 3: Starting Docker services...${NC}"
echo -e "${YELLOW}Building images and starting containers (this may take a minute)...${NC}"

docker compose up -d --build > /dev/null 2>&1 || {
    echo -e "${RED}✗ Failed to start Docker services${NC}"
    exit 1
}
echo -e "${GREEN}✓ Docker services started${NC}"

# Step 4: Wait for services to be healthy
echo -e "\n${BLUE}Step 4: Waiting for services to be ready...${NC}"

MAX_ATTEMPTS=60
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ API service is healthy${NC}"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo -n "."
    sleep 1
done

if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
    echo -e "\n${RED}✗ Timeout waiting for API service to become healthy${NC}"
    echo -e "${YELLOW}Check logs with: docker compose logs api${NC}"
    exit 1
fi

# Step 5: Run database migrations
echo -e "\n${BLUE}Step 5: Initializing database schema...${NC}"

if docker compose exec -T api alembic upgrade head > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Database migrations applied successfully${NC}"
else
    echo -e "${RED}✗ Database migration failed${NC}"
    echo -e "${YELLOW}Check logs with: docker compose logs api${NC}"
    exit 1
fi

# Step 6: Verify the complete setup
echo -e "\n${BLUE}Step 6: Verifying setup...${NC}"

SERVICES_OK=true

# Check API
if ! curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo -e "${RED}✗ API service is not healthy${NC}"
    SERVICES_OK=false
else
    echo -e "${GREEN}✓ API service is healthy${NC}"
fi

# Check all containers are running
RUNNING=$(docker compose ps | grep -c "Up " || echo 0)
TOTAL=$(docker compose config --services | wc -l)

if [ "$RUNNING" -ge "$((TOTAL - 1))" ]; then
    echo -e "${GREEN}✓ All services are running ($RUNNING/$TOTAL)${NC}"
else
    echo -e "${YELLOW}⚠ Some services may still be starting ($RUNNING/$TOTAL)${NC}"
fi

if [ "$SERVICES_OK" = false ]; then
    exit 1
fi

# Final summary
echo -e "\n${BLUE}════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Initialization complete!${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "  1. ${YELLOW}Submit a workflow:${NC}"
echo -e "     curl -X POST http://localhost:8000/api/v1/workflow \\"
echo -e "       -H 'Content-Type: application/json' \\"
echo -e "       -d @payloads/parallel_api_fetcher.json"
echo ""
echo -e "  2. ${YELLOW}Run the test suite:${NC}"
echo -e "     bash scripts/test_api.sh http://localhost:8000"
echo ""
echo -e "  3. ${YELLOW}View logs:${NC}"
echo -e "     docker compose logs -f api"
echo ""
echo -e "${BLUE}API is running at: http://localhost:8000${NC}"
echo -e "${BLUE}Health check: http://localhost:8000/health${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
