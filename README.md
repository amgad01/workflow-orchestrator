# Event-Driven Workflow Engine

A production-grade Directed Acyclic Graph (DAG) orchestration engine designed for high-throughput, distributed task execution. This system parses JSON workflow definitions, resolves dependencies, and orchestrates concurrent execution using Redis Streams and Python asyncio.

It demonstrates mastery of **Clean Architecture**, **Hexagonal (Ports & Adapters) Patterns**, and **Distributed Systems Design**.

## ⚡ Quick Start (Automated)

The fastest way to get started is using the automated initialization script:

```bash
# 1. Clone the repository
git clone https://github.com/amgad01/workflow-orchestrator.git
cd workflow-orchestrator

# 2. Run the initialization script (handles everything: Docker setup + database initialization)
bash scripts/init.sh
```

That's it! The script will:
- ✅ Verify Docker is installed
- ✅ Create `.env` file from `.env.example`
- ✅ Build and start all Docker containers
- ✅ Wait for services to be healthy
- ✅ **Run database migrations automatically** ⚠️ *This step is critical!*
- ✅ Verify the complete setup

## Setup Instructions (Manual Alternative)

### Prerequisites
*   **Docker & Docker Compose**: The entire environment is containerized.
*   **Ports**: Ensure ports `8000` (API), `5432` (Postgres), and `6379` (Redis) are available or adjusted in `docker-compose.yml`.

### Manual Setup Steps

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/amgad01/workflow-orchestrator.git
    cd workflow-orchestrator
    ```

2.  **Create environment file**:
    ```bash
    cp .env.example .env
    ```

3.  **Start Services**:
    This command builds the images and starts the API, Orchestrator, Worker Cluster, Redis, and PostgreSQL.
    ```bash
    docker compose up -d --build
    ```

4.  **⚠️ CRITICAL: Initialize the database**:
    This step is **required** for the system to work. It creates the database schema:
    ```bash
    docker compose exec -T api alembic upgrade head
    ```
    
    Without this step, you'll get "relation 'workflows' does not exist" errors.

5.  **Verify System Health**:
    Check that all containers are in the `Up` state.
    ```bash
    docker compose ps
    ```
    You should see:
    *   `api`: The REST gateway (should be `healthy`)
    *   `orchestrator`: The event processor
    *   `worker`: The task execution nodes (3 instances)
    *   `redis`: The high-speed message broker
    *   `postgres`: The persistent storage

---

## Architecture Overview

The system follows a strict Hexagonal Architecture, ensuring business logic (`src/domain`, `src/application`) remains isolated from infrastructure concerns (`src/adapters`).

### High-Level Data Flow

```text
+----------+       +-----------+       +----------------+
|          | HTTP  |           | SQL   |                |
|  Client  +------->    API    +------->   PostgreSQL   |
|          |       |  Service  |       |  (Persistence) |
+----------+       +-----+-----+       +----------------+
                         |
                         | Publish (Submission Event)
                         v
                  +------+------+
                  |             |
+----------+      |    Redis    |      +----------------+
|          |      |   Streams   |      |                |
|  Reaper  +------>             +------>  Orchestrator  |
|          |      |  (Broker)   |      |                |
+----------+      +------+------+      +-------+--------+
                         ^                     |
                         | Consume / Publish   |
                         |                     |
                  +------+------+              |
                  |             |              |
                  |   Worker    | <------------+
                  |   Cluster   |
                  |             |
                  +-------------+
```

### Detailed Workflow Execution Flow

This diagram shows how a DAG is executed from submission to completion:

```text
┌─────────────────────────────────────────────────────────────────┐
│                         USER SUBMISSION                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │ POST /api/v1/workflow (DAG JSON)
                     ▼
           ┌─────────────────────┐
           │   API Service       │
           │  - Validate DAG     │
           │  - Cycle Detection  │
           │  - Store Workflow   │
           └──────────┬──────────┘
                      │
         ┌────────────┴────────────┐
         ▼                         ▼
    PostgreSQL              Redis (Init State)
   (Workflow Def)           (Lock, Metadata)
                                   │
                     ┌─────────────┴──────────┐
                     │                        │
        Trigger Event Published               │
             (Task Stream)                    │
                     │                        │
                     ▼                        │
         ┌──────────────────────┐             │
         │   Orchestrator       │◄────────────┘
         │  - Consume Event     │
         │  - Read DAG (Cache)  │
         │  - Resolve Deps      │
         │  - Acquire Lock      │
         │  - Resolve Templates │
         └──────────┬───────────┘
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
   Ready Nodes?         Fan-In Lock?
         │              (SETNX)
         │                  │
    YES │                   ├─ GRANTED → Dispatch All Ready
         │                  │
         ▼                  └─ DENIED → Skip (Another instance handling)
   Publish Tasks
   (Task Stream)
         │
         ▼
   ┌─────────────────────────────────────┐
   │  Worker (Consumer Group)        │
   │ - Pop Task from Stream          │
   │ - Check Idempotency (Redis Set) │
   │ - Execute Handler               │
   │ - Publish Completion Event      │
   │ - ACK Message                   │
   └──────────┬──────────────────────┘
              │
         Completion
         Event Loop
              │
              └──────────► Back to Orchestrator
```

### Kahn's Algorithm: Cycle Detection

Visual representation of how cycle detection works:

```text
STEP 1: Calculate In-Degrees
┌─────┐    ┌─────┐    ┌─────┐
│  A  │───→│  B  │───→│  C  │
└─────┘    └─────┘    └─────┘
  In=0      In=1       In=1

STEP 2: Process Nodes with In-Degree 0
Queue: [A]
┌──────────────────────┐
│ Pop A                │
│ For each child:      │
│   In-degree--        │
│   If In=0: Add Queue │
└──────────────────────┘

STEP 3: Process B and C
Queue: [B] → [C] → []
Processed: [A, B, C]

STEP 4: Verify
If processed_count == total_nodes → NO CYCLE ✓
Else → CYCLE DETECTED ✗

Example with Cycle:
  A ←──┐
  │    │
  B ───┘

In-degrees: A=1, B=1
Queue: [] (empty!)
After loop: A and B still have in-degree > 0
→ CYCLE DETECTED ✗
```

### Fan-In Race Condition: SETNX Lock Solution

How distributed locking prevents duplicate execution:

```text
Scenario: Node C depends on A and B (both complete simultaneously)

╔════════════════════════════════════════════════════════════════╗
║                    TIME PROGRESS →                            ║
╚════════════════════════════════════════════════════════════════╝

Orchestrator 1               |            Orchestrator 2
                            |
Event: A Completed          |         Event: B Completed
│                           |         │
├─ Check C's Parents        |         ├─ Check C's Parents
│ (A=DONE, B=DONE)          |         │ (A=DONE, B=DONE)
│                           |         │
├─ Try: SETNX               |         ├─ Try: SETNX
│ key="lock:exec:C"         |         │ key="lock:exec:C"
│                           |         │
├─ GRANTED ✓◄───────────────┼────────┤─ DENIED ✗
│                           |         │
├─ Update C Status          |         ├─ Log & Abort
│ C = PENDING               |         │ (Skip dispatch)
│                           |         │
├─ Dispatch C Task          |         │
│ Publish(C, Message)       |         │
│                           |         │
├─ Release Lock             |         │
│ DEL lock:exec:C           |         │
│                           |         │
└─ Result: C executes ONCE  |         └─ Result: No duplicate


Lock Details:
┌────────────────────────────────────┐
│ SET lock:exec:C "1"                │
│ NX        (only if not exists)     │
│ EX 30     (auto-expire in 30s)     │
│           (prevents deadlock)      │
└────────────────────────────────────┘
```

### Data Passing: Template Resolution

How data flows between nodes via template substitution:

```text
Node A Output (stored in Redis):
┌──────────────────────────┐
│ {                        │
│   "user_id": "12345",    │
│   "email": "a@example"   │
│ }                        │
└──────────────────────────┘

Node B Config (BEFORE resolution):
┌──────────────────────────────────┐
│ {                                │
│   "url": "http://api/user/{{A.user_id}}"  │
│ }                                │
└──────────────────────────────────┘
         │
         │ Regex Match: {{A.user_id}}
         │ Lookup: A.outputs["user_id"]
         │ Replace: "12345"
         ▼
Node B Config (AFTER resolution):
┌──────────────────────────────────┐
│ {                                │
│   "url": "http://api/user/12345" │
│ }                                │
└──────────────────────────────────┘
```

### Exponential Backoff: Retry Strategy

How failed tasks are retried with increasing delays:

```text
Task Fails
│
├─ Retry Count = 1
│  Delay = min(1.0 * 2^0, 30) + jitter = ~1s
│  Wait 1 second, re-execute
│
├─ Retry Count = 2
│  Delay = min(1.0 * 2^1, 30) + jitter = ~2s
│  Wait 2 seconds, re-execute
│
├─ Retry Count = 3
│  Delay = min(1.0 * 2^2, 30) + jitter = ~4s
│  Wait 4 seconds, re-execute
│
├─ Retry Count = 4
│  Delay = min(1.0 * 2^3, 30) + jitter = ~8s
│  Wait 8 seconds, re-execute (MAX RETRIES EXCEEDED)
│
└─ Move to DLQ (Dead Letter Queue)
   Store for manual inspection & retry

Benefit: Prevents "Thundering Herd"
Without jitter:  All retries at exact same time → spike
With jitter:     Retries spread across time → smooth load
```

### The Reaper: Zombie Task Recovery

How the system automatically recovers from worker crashes:

```text
NORMAL EXECUTION:
┌──────────┐       ┌──────────────┐       ┌─────────────┐
│  Task    │──────→│   Worker     │──────→│  ACK in PEL │
│Published │       │  Processes   │       │   Removed   │
└──────────┘       │   (Success)  │       └─────────────┘
                   └──────────────┘
                   Task Completes in 5s


WORKER CRASH SCENARIO:
┌──────────┐       ┌──────────────┐       ✗ CRASH!
│  Task    │──────→│   Worker     │       (No ACK)
│Published │       │  Processing  │
└──────────┘       └──────────────┘
                         │
              Task sits in PEL (Pending Entry List)
              ┌──────────────────────────┐
              │ PEL[task_id] = {         │
              │   consumer: "worker-xyz" │
              │   timestamp: 10:00:00    │
              │   idle_ms: 0             │
              │ }                        │
              └──────────────────────────┘
                         │
                    (30 seconds pass)
                    idle_ms = 30,000ms
                         │
                         ▼
              ┌──────────────────────────┐
              │  REAPER (monitoring)     │
              │  - Polls PEL every 5s    │
              │  - Checks idle_ms > 25s? │
              │  - YES! Task is STALLED  │
              └──────────┬───────────────┘
                         │
           ┌─────────────┴─────────────┐
           │                           │
        XAUTOCLAIM:                   │
        "Give me idle tasks           │
         from this consumer group"    │
           │                           │
           ▼                           │
        ┌──────────────────┐          │
        │ Steal Message    │          │
        │ from worker-xyz  │          │
        │ Reassign to      │          │
        │ reaper consumer  │          │
        └────────┬─────────┘          │
                 │                    │
          ┌──────▼──────┐             │
          │ Re-publish  │◄────────────┘
          │ task to     │
          │ task_stream │
          └──────┬──────┘
                 │
                 ▼
        ┌──────────────────┐
        │ New worker picks │
        │ it up (tries     │
        │ again)           │
        └──────────────────┘

Benefits:
- No manual intervention needed
- Automatic recovery from crashes
- Configurable idle threshold (25s default)
- Task completes despite worker failure
```

### Resilience Mechanisms: Complete Picture

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

### Component Roles & Responsibilities

1.  **API Service (`src/adapters/primary/api`)**: 
    *   **Role**: The Gateway.
    *   **Functions**: Validates DAG structure (Cycle Detection), persists definitions to PostgreSQL, initializes Redis state, and returns an Execution ID.
    *   **Characteristics**: Stateless, Scalable, Rate-Limited.

2.  **Redis (Broker & State)**: 
    *   **Role**: The Central Nervous System.
    *   **Functions**: Acts as the "Hot Store" for real-time execution state (Node Status, Locks) and the message bus (Redis Streams) for task distribution.

3.  **Orchestrator (`src/application/orchestrator`)**: 
    *   **Role**: The Brain.
    *   **Functions**: Consumes `CompletionMessages`, updates node state, evaluates DAG dependencies (Fan-In/Fan-Out logic), resolves data templates, and dispatches new `TaskMessages`.

4.  **Worker Cluster (`src/workers`)**: 
    *   **Role**: The Muscle.
    *   **Functions**: Stateless consumers that execute business logic. They leverage **Consumer Groups** for load balancing and check **Idempotency** keys to ensure exactly-once execution.

5.  **PostgreSQL (`src/adapters/persistence`)**: 
    *   **Role**: System of Record.
    *   **Functions**: Securely stores immutable workflow definitions and the final history of every execution.

---

## How to Trigger Test Workflows

The system includes a suite of payloads to demonstrate different capabilities.

### Option 1: Automated Test Suite (Recommended)

Run the comprehensive test suite that validates all features:

```bash
bash scripts/test_api.sh http://localhost:8000
```

This script:
- Tests cycle detection (rejects invalid DAGs)
- Tests parallel execution (fan-out/fan-in)
- Tests data templating
- Tests resilience features (DLQ, circuit breaker, retries)
- Tests rate limiting
- Generates a full test report

### Option 2: Manual Testing

#### 1. Submit a Workflow
Submit a JSON payload to the API. This example submits a workflow with parallel branches.

```bash
curl -X POST http://localhost:8000/api/v1/workflow \
  -H "Content-Type: application/json" \
  -d @payloads/parallel_api_fetcher.json
```
**Response**:
```json
{"execution_id": "550e8400-e29b-41d4-a716-446655440000"}
```

#### 2. Trigger Execution
Once submitted, the workflow is in a `PENDING` state. Use the returned ID to start it.

```bash
curl -X POST http://localhost:8000/api/v1/workflow/trigger/550e8400-e29b-41d4-a716-446655440000
```

#### 3. Monitor Status
The execution happens asynchronously. Poll the status endpoint to watch the graph state evolve.

```bash
curl http://localhost:8000/api/v1/workflow/550e8400-e29b-41d4-a716-446655440000
```
*Tip: Use `jq` to format the JSON output: `curl ... | jq`*

---

## Testing

The project includes a comprehensive test suite organized by scope:

```bash
# Run all unit and integration tests
poetry run pytest tests/ --ignore=tests/e2e/ -v

# Run specific test categories
poetry run pytest tests/unit/ -v          # Unit tests
poetry run pytest tests/integration/ -v   # Integration tests
poetry run pytest tests/domain/ -v        # Domain logic tests
```

**E2E Tests** require a running server:
```bash
docker compose up -d
poetry run pytest tests/e2e/ -v
```

You can also run E2E tests end-to-end with Docker using the helper script:
```bash
./scripts/run_e2e.sh
```

---

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

---

## Observability

- **Logs**: `docker compose logs -f api orchestrator worker`
- **Metrics**: Prometheus endpoint at `GET /metrics`

---

## Performance Notes

Run the load-test harness against a running stack:
```bash
./scripts/run_load_test.sh http://localhost:8000
```

---

## Key Features

| Feature | Description |
|---------|-------------|
| **DAG Validation** | Cycle detection using Kahn's algorithm with O(V+E) complexity |
| **Parallel Execution** | Fan-out/Fan-in patterns with distributed locking |
| **Data Templating** | Dynamic variable resolution between nodes using `${node.output.field}` syntax |
| **Idempotency** | Exactly-once execution semantics via Redis-based deduplication |
| **Resilience** | Dead Letter Queue, automatic task reclamation, and graceful cancellation |
| **Rate Limiting** | Sliding window algorithm protecting API endpoints |

---

## Project Structure

```
src/
├── domain/           # Business entities and rules (DAG, Execution, Node)
├── application/      # Use cases and orchestration logic
├── adapters/
│   ├── primary/      # Inbound (API routes, middleware)
│   └── secondary/    # Outbound (Redis, PostgreSQL repositories)
├── ports/            # Interface definitions (repository contracts)
└── shared/           # Configuration, utilities, common infrastructure
```
