# Event-Driven Workflow Engine

A production-grade Directed Acyclic Graph (DAG) orchestration engine designed for high-throughput, distributed task execution. This system parses JSON workflow definitions, resolves dependencies, and orchestrates concurrent execution using Redis Streams and Python asyncio.

It demonstrates mastery of **Clean Architecture**, **Hexagonal (Ports & Adapters) Patterns**, and **Distributed Systems Design**.

## Setup Instructions

### Prerequisites
*   **Docker & Docker Compose**: The entire environment is containerized.
*   **Ports**: Ensure ports `8000` (API), `5432` (Postgres), and `6379` (Redis) are available or adjusted in `docker-compose.yml`.

### Quick Start
1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd workflow-engine
    ```

2.  **Start Services**:
    This command builds the images and starts the API, Orchestrator, Worker Cluster, Redis, and PostgreSQL.
    ```bash
    docker compose up -d --build
    ```

3.  **Verify System Health**:
    Check that all containers are in the `Up` state.
    ```bash
    docker compose ps
    ```
    *   `api`: The REST gateway.
    *   `orchestrator`: The event processor.
    *   `worker`: The task execution nodes.
    *   `redis`: The high-speed message broker.
    *   `postgres`: The persistent storage.

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

### 1. Submit a Workflow
Submit a JSON payload to the API. This example submits a workflow with parallel branches.

```bash
# Submit the 'Parallel Execution' test case
curl -X POST http://localhost:8000/workflow \
  -H "Content-Type: application/json" \
  -d @payloads/parallel_api_fetcher.json
```
**Response**:
```json
{"execution_id": "550e8400-e29b-41d4-a716-446655440000"}
```

### 2. Trigger Execution
Once submitted, the workflow is in a `PENDING` state. Use the returned ID to start it.

```bash
curl -X POST http://localhost:8000/workflow/trigger/550e8400-e29b-41d4-a716-446655440000
```

### 3. Monitor Status
The execution happens asynchronously. Poll the status endpoint to watch the graph state evolve.

```bash
curl http://localhost:8000/workflows/550e8400-e29b-41d4-a716-446655440000
```
*Tip: Use `jq` to format the JSON output: `curl ... | jq`*

### Automated Verification Script
For a complete system test, run the provided script. It acts as an integration test suite, verifying:
1.  Input validation (Cycle rejection).
2.  Complex DAG execution (Fan-in/Fan-out).
3.  Resilience features (Cancellation, State recovery).

```bash
bash scripts/test_api.sh http://localhost:8000
```

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

---

## License

MIT
