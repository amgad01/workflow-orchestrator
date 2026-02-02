# Resilience & Testing

## Resilience Mechanisms: Complete Picture

Five layers of failure recovery working together:

```text
FAILURE RECOVERY LAYERS (from fast to slow):

┌──────────────────────────────────────────────────────┐
│ Layer 1: IDEMPOTENCY (Sub-second)                   │
│ ┌────────────────────────────────────────────────┐  │
│ │ Redis Set: idempotency:{task_id} = 1           │  │
│ │ Check before execution: "Have I seen this?"   │  │
│ │ Prevents duplicate processing from retries     │  │
│ └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────┐
│ Layer 2: EXPONENTIAL BACKOFF (1-30 seconds)         │
│ ┌────────────────────────────────────────────────┐  │
│ │ Formula: min(1.0 * 2^(retry-1), 30) + jitter  │  │
│ │ Retry up to 4 times with increasing delays    │  │
│ │ Prevents thundering herd on cascading failures │  │
│ └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────┐
│ Layer 3: CIRCUIT BREAKER (Immediate)                │
│ ┌────────────────────────────────────────────────┐  │
│ │ State: CLOSED → (failures) → OPEN             │  │
│ │ When OPEN: Fail fast, don't call service      │  │
│ │ After timeout: HALF_OPEN → test with 1 call  │  │
│ │ Prevents cascading failures across services   │  │
│ └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────┐
│ Layer 4: DLQ - DEAD LETTER QUEUE (Minutes)          │
│ ┌────────────────────────────────────────────────┐  │
│ │ Capture poison pills after max retries         │  │
│ │ Store: {error, config, retry_count}           │  │
│ │ Manual retry via API: POST /admin/dlq/retry   │  │
│ │ Operators can debug and fix issues            │  │
│ └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                         ▼
┌──────────────────────────────────────────────────────┐
│ Layer 5: THE REAPER - ZOMBIE RECOVERY (30s)         │
│ ┌────────────────────────────────────────────────┐  │
│ │ Monitor Redis PEL for stalled messages         │  │
│ │ If idle > 25s: Re-publish to queue             │  │
│ │ New worker picks up and retries                │  │
│ │ Handles worker crashes transparently           │  │
│ └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘

Example Failure Journey:
External API fails
       ↓
Layer 1: Idempotency check (prevents dups)
       ↓
Layer 2: Retry with backoff (up to 4 times)
       ↓
Layer 3: Circuit breaker (fail fast after 5 failures)
       ↓
Layer 4: DLQ entry (operator reviews & retries)
       ↓
Layer 5: Reaper (catches stalled messages)
       ↓
Complete audit trail for debugging
```

## Testing

### Automated Test Suite (Recommended)

```bash
bash scripts/test_api.sh http://localhost:8000
```

This comprehensive test validates:
- Cycle detection (rejects invalid DAGs)
- Parallel execution (fan-out/fan-in)
- Data templating
- Resilience features (DLQ, circuit breaker, retries)
- Rate limiting
- Full test report generation

### Running Test Categories

```bash
# All unit and integration tests
poetry run pytest tests/ --ignore=tests/e2e/ -v

# Specific categories
poetry run pytest tests/unit/ -v          # Unit tests
poetry run pytest tests/integration/ -v   # Integration tests
poetry run pytest tests/domain/ -v        # Domain logic tests

# E2E Tests (requires running server)
docker compose up -d
poetry run pytest tests/e2e/ -v
```

### Load Testing

Run the load-test harness against a running stack:

```bash
./scripts/run_load_test.sh http://localhost:8000
```

## Manual Testing

### 1. Submit a Workflow

```bash
curl -X POST http://localhost:8000/api/v1/workflow \
  -H "Content-Type: application/json" \
  -d @payloads/parallel_api_fetcher.json
```

**Response**:
```json
{"execution_id": "550e8400-e29b-41d4-a716-446655440000"}
```

### 2. Trigger Execution

```bash
curl -X POST http://localhost:8000/api/v1/workflow/trigger/550e8400-e29b-41d4-a716-446655440000
```

### 3. Monitor Status

```bash
curl http://localhost:8000/api/v1/workflow/550e8400-e29b-41d4-a716-446655440000 | jq
```

## Local Development (without Docker)

```bash
poetry install
poetry run uvicorn src.main:app --reload
```

In separate terminals:
```bash
poetry run python -m src.orchestrator
poetry run python -m src.worker
```

## Observability

- **Logs**: `docker compose logs -f api orchestrator worker`
- **Metrics**: Prometheus endpoint at `GET /metrics`
