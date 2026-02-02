# Event-Driven Workflow Engine

A production-grade DAG orchestration engine for high-throughput, distributed task execution using Redis Streams and Python asyncio.

**Key Features**: Cycle detection, parallel execution, data templating, idempotency, distributed locking, resilience patterns (DLQ, circuit breaker, exponential backoff, zombie recovery), and rate limiting.

---
**Built with**: Clean Architecture, Hexagonal Patterns, Event-Driven Design

## ⚡ Quick Start (3 Steps)

### Step 1: Clone
```bash
git clone https://github.com/amgad01/workflow-orchestrator.git && cd workflow-orchestrator
```

### Step 2: Initialize (everything automated)
```bash
bash scripts/init.sh
```

This script handles:
- ✅ Docker verification
- ✅ Environment setup
- ✅ Container build & start
- ✅ Service health checks
- ✅ Database migrations
- ✅ Complete validation

### Step 3: Test (fully automated)
```bash
bash scripts/test_api.sh http://localhost:8000
```

This comprehensive test validates cycle detection, parallel execution, data templating, resilience features, rate limiting, and generates a full report.

---

## Documentation

For detailed information, see:

- [**Architecture**](docs/ARCHITECTURE.md) - System design, data flow, component roles
- [**Algorithms**](docs/ALGORITHMS.md) - Kahn's cycle detection, distributed locking (SETNX), template resolution, exponential backoff, zombie recovery
- [**Testing & Resilience**](docs/TESTING_RESILIENCE.md) - Five-layer failure recovery, manual testing, load testing, local development

---

## What This System Does

1. **Accepts JSON workflow definitions** (Directed Acyclic Graphs)
2. **Validates structure** (cycle detection in O(V+E) time)
3. **Orchestrates execution** with Redis-based state management
4. **Resolves dependencies** using reactive event-driven choreography
5. **Handles failures** with 5 layers of resilience
6. **Provides observability** via logs and metrics

---

## System Requirements

- **Docker & Docker Compose** (entire stack containerized)
- **Ports Available**: 8000 (API), 5432 (PostgreSQL), 6379 (Redis)

---

## Architecture at a Glance

```
Client ──→ API ──→ PostgreSQL (DAG storage)
              ↓
            Redis Streams (event broker & hot state)
              ↑           ↓
          Reaper ←─ Orchestrator ─→ Worker Cluster
```

**Hot Path (Redis)**: Sub-millisecond reads/writes for real-time execution state  
**Cold Path (PostgreSQL)**: ACID-compliant storage for workflow definitions and history  
**Result**: ~10x higher throughput vs. database-only approaches

---

## Example Workflow

```bash
# Submit workflow
curl -X POST http://localhost:8000/api/v1/workflow \
  -H "Content-Type: application/json" \
  -d @payloads/parallel_api_fetcher.json

# Response
{"execution_id": "550e8400-e29b-41d4-a716-446655440000"}

# Trigger execution
curl -X POST http://localhost:8000/api/v1/workflow/trigger/550e8400-e29b-41d4-a716-446655440000

# Monitor status
curl http://localhost:8000/api/v1/workflow/550e8400-e29b-41d4-a716-446655440000 | jq
```

---

## Resilience Layers (Automatic Failure Recovery)

1. **Idempotency** (sub-second) - Redis-based deduplication
2. **Exponential Backoff** (1-30s) - Retry with jitter
3. **Circuit Breaker** (immediate) - Fail fast on cascading failures
4. **Dead Letter Queue** (minutes) - Manual inspection & retry
5. **The Reaper** (30s) - Automatic zombie task recovery

---

## Performance

Targets **35+ workflows/sec** on commodity hardware via:
- Polyglot persistence (Redis hot + PostgreSQL cold)
- Redis Streams with Consumer Groups
- Distributed locking for race-condition prevention
- Fully reactive event-driven architecture

Load testing: `./scripts/run_load_test.sh http://localhost:8000`

---

## Development

For detailed testing, local development, and advanced usage, see [Testing & Resilience](docs/TESTING_RESILIENCE.md).
