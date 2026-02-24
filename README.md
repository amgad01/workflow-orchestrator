# Workflow Orchestrator

A production-grade DAG orchestration engine for high-throughput, distributed task execution using Redis Streams and Python asyncio.

**Key Features**: Cycle detection, parallel execution, data templating, idempotency, distributed locking, resilience patterns (DLQ, circuit breaker, exponential backoff, zombie recovery), and rate limiting.

---

**Built with**: Clean Architecture, Hexagonal Patterns, Event-Driven Design

## Quick Start

### 1. Clone

```bash
git clone https://github.com/amgad01/workflow-orchestrator.git && cd workflow-orchestrator
```

### 2. Initialize

```bash
bash scripts/init.sh
```

Handles Docker verification, `.env` setup, container build, health checks, and database migrations.

### 3. Validate

```bash
bash scripts/test_api.sh http://localhost:8000
```

Runs cycle detection, parallel execution, data templating, resilience features, rate limiting, and generates a full report.

---

## Architecture

```
Submission Phase (POST /api/v1/workflow)
┌────────────────────────────────────────────────────────────────┐
Client ──→ API ──→ Use Case ──→ DAG (Kahn's validation) ──→ PostgreSQL
└────────────────────────────────────────────────────────────────┘

Execution Phase (POST /api/v1/workflow/trigger/{id})
┌────────────────────────────────────────────────────────────────┐
API ──→ Redis Streams (root task dispatch) ────┐
              ↓                                  ↓
        Orchestrator (dependency resolution) ──→ Worker Cluster
              ↑                                  ↓
           Reaper ←───────────────────────── Task Results
└────────────────────────────────────────────────────────────────┘
```

**Submission (Cold Path)**: DAG validation via Kahn's algorithm O(V+E), persisted to PostgreSQL.
**Execution (Hot Path)**: Redis Streams manages real-time task dispatch with sub-millisecond latency.
**Two-Phase Design**: Decouples validation (synchronous) from execution (asynchronous).

### Container Topology

| Service | Role | Replicas |
|---|---|---|
| `api` | REST API (FastAPI), handles submissions and status queries | 1 |
| `worker` | Task execution (LLM, API calls, decisions) | 3 |
| `orchestrator` | Dependency resolution and task dispatch | 2 |
| `reaper` | Zombie task recovery from Redis PEL | 1 |
| `redis` | Streams, state store, distributed locks | 1 |
| `postgres` | Workflow definitions and execution audit trail | 1 |

### Key Queue Dynamics

| Queue | Consumer | Publisher | Function |
|---|---|---|---|
| `workflow:tasks` | Workers (competing) | API + Orchestrator | Task dispatch |
| `workflow:completions` | Orchestrators (competing) | Workers | Task results |
| `workflow:dlq` | Operator (manual) | Workers (on failure) | Failed task parking |

---

## API Reference

### Workflow Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/workflow` | Submit a workflow DAG |
| `POST` | `/api/v1/workflow/trigger/{execution_id}` | Trigger execution |
| `GET` | `/api/v1/workflow/{execution_id}` | Get execution status |
| `GET` | `/api/v1/workflow/{execution_id}/results` | Get execution results |
| `DELETE` | `/api/v1/workflow/{execution_id}` | Cancel execution |

### Admin Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/admin/dlq` | List dead letter queue entries |
| `POST` | `/api/v1/admin/dlq/{entry_id}/retry` | Retry a DLQ entry |
| `DELETE` | `/api/v1/admin/dlq/{entry_id}` | Delete a DLQ entry |

### Operational Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check (Redis + PostgreSQL) |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/docs` | Swagger UI |

---

## Example Usage

```bash
# Submit a workflow
curl -X POST http://localhost:8000/api/v1/workflow \
  -H "Content-Type: application/json" \
  -d @payloads/parallel_api_fetcher.json

# Trigger execution
curl -X POST http://localhost:8000/api/v1/workflow/trigger/{execution_id}

# Poll status
curl http://localhost:8000/api/v1/workflow/{execution_id}

# Get results
curl http://localhost:8000/api/v1/workflow/{execution_id}/results
```

---

## Resilience Layers

1. **Idempotency** — Redis-based task deduplication prevents double-processing.
2. **Exponential Backoff** — Retry with jitter (configurable base, max, and jitter via env).
3. **Circuit Breaker** — Fail fast on cascading downstream failures.
4. **Dead Letter Queue** — Tasks exceeding max retries are parked for manual inspection.
5. **Reaper (Zombie Recovery)** — Background service reclaims stuck tasks from Redis PEL.

### Fault Tolerance

```
Worker crashes:
  → Task stays in Redis PEL (not ACK'd)
  → Reaper detects idle task after REAPER_MIN_IDLE_SECONDS
  → XAUTOCLAIM transfers ownership, task is re-published
  → Healthy worker picks it up

Orchestrator crashes:
  → Completion message stays in PEL
  → Another orchestrator instance processes it
  → Idempotency prevents duplicate dispatch
```

---

## Configuration

All settings are centralized in `src/shared/config.py` and can be overridden via environment variables or `.env` file. See `.env.example` for the full list.

Key configuration groups:
- **Application**: `APP_NAME`, `APP_VERSION`
- **Database**: `DATABASE_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`
- **Redis**: `REDIS_URL`
- **Worker**: Batch size, delays, retry/backoff settings, handler defaults
- **Orchestrator**: Batch size, block time, timeout check interval
- **Reaper**: Check interval, min idle time, batch size
- **Streams**: Key names, consumer group names, max length
- **Resilience**: Rate limiting, circuit breaker, DLQ settings

---

## Scaling

```bash
# Default: 3 workers, 2 orchestrators
docker compose up -d

# Scale to 30 workers, 5 orchestrators
docker compose up -d --scale worker=30 --scale orchestrator=5
```

Redis Streams consumer groups handle distribution automatically — no coordinator needed.

---

## Testing

### Unit Tests

```bash
cd workflow-orchestrator
poetry run pytest tests/ -v -m "not e2e"
```

### End-to-End Tests

```bash
bash scripts/run_e2e.sh
```

### Load Testing

```bash
bash scripts/run_load_test.sh http://localhost:8000
```

### Demo: Reaper + DLQ

```bash
python scripts/demo_reaper_dlq.py --api-url http://localhost:8000 --watch
```

---

## Development

```bash
# Install dependencies
poetry install

# Start infrastructure
docker compose up -d redis postgres

# Run API locally
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

# Run worker
python -m src.worker

# Run orchestrator
python -m src.orchestrator
```

---

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — System design, data flow, component roles
- [Algorithms](docs/ALGORITHMS.md) — Kahn's cycle detection, distributed locking, template resolution, exponential backoff, zombie recovery
- [Testing & Resilience](docs/TESTING_RESILIENCE.md) — Five-layer failure recovery, manual testing, load testing

---

## System Requirements

- **Docker & Docker Compose**
- **Ports**: 8000 (API), 5432 (PostgreSQL), 6379 (Redis)
