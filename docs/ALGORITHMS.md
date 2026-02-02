# Key Algorithms & Patterns

## 1. Dependency Resolution (Kahn's Algorithm)

Ensures DAGs are acyclic and produces topological sort in O(V+E) time.

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
```

## 2. Fan-In Race Condition: Distributed Locking (Redlock Pattern)

Prevents duplicate execution when a node has multiple parents completing simultaneously.

```text
Scenario: Node C depends on A and B (both complete at same millisecond)

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


Lock Configuration:
SET lock:exec:C "1" NX EX 30
  NX:        Only set if key doesn't exist
  EX 30:     Auto-expire in 30s (prevents deadlock)
```

## 3. Data Passing: Template Resolution

Dynamic variable resolution between nodes using regex pattern matching.

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

## 4. Exponential Backoff: Retry Strategy

Failed tasks are retried with increasing delays to prevent thundering herd.

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

## 5. The Reaper: Zombie Task Recovery

Automatically recovers from worker crashes by monitoring the Redis Pending Entry List (PEL).

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
