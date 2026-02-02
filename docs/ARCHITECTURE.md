# Architecture Overview

The Event-Driven Workflow Engine follows a strict **Hexagonal Architecture** (Ports & Adapters pattern), ensuring business logic remains isolated from infrastructure concerns.

## High-Level Data Flow

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

## Detailed Workflow Execution Flow

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

## Component Roles & Responsibilities

1. **API Service (`src/adapters/primary/api`)**: 
   - The Gateway: Validates DAG structure, persists definitions to PostgreSQL, initializes Redis state.
   - Characteristics: Stateless, Scalable, Rate-Limited.

2. **Redis (Broker & State)**: 
   - The Central Nervous System: Acts as the "Hot Store" for real-time execution state and message bus for task distribution.

3. **Orchestrator (`src/application/orchestrator`)**: 
   - The Brain: Consumes completion messages, evaluates DAG dependencies, resolves data templates, and dispatches new tasks.

4. **Worker Cluster (`src/workers`)**: 
   - The Muscle: Stateless consumers that execute business logic with exactly-once semantics via Consumer Groups.

5. **PostgreSQL (`src/adapters/persistence`)**: 
   - System of Record: Stores immutable workflow definitions and execution history.

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
