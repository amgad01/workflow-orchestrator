#!/usr/bin/env python3
"""
demo_reaper_dlq.py — Demonstrate the Reaper + Dead Letter Queue flow.

This script:
  1. Submits a workflow whose task deliberately fails (via `simulate_failure: true`)
     to exhaust the retry budget and land in the DLQ.
  2. Polls the execution status to show the failure path.
  3. Optionally shows how to inspect the DLQ stream in Redis.

Usage:
    python scripts/demo_reaper_dlq.py [--api-url http://localhost:8000] [--watch]

Environment:
  API_URL  — override the default API base URL (also settable via --api-url flag).
  REDIS_URL — inspected for DLQ contents (default: redis://localhost:6379/0).
"""

import argparse
import asyncio
import json
import os
import sys
import time

import httpx

# ---------------------------------------------------------------------------
# Defaults — can be overridden via CLI flags or env vars.
# ---------------------------------------------------------------------------
DEFAULT_API_URL = os.getenv("API_URL", "http://localhost:8000")
DEFAULT_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DLQ_STREAM_KEY = "workflow:dlq"  # must match STREAM_DLQ_KEY in config

# ---------------------------------------------------------------------------
# Demo payload: single task that signals a deliberate failure via
# `simulate_failure: true` — no URL magic strings needed.
# ---------------------------------------------------------------------------
DEMO_WORKFLOW = {
    "name": "demo-reaper-dlq",
    "dag": {
        "nodes": [
            {
                "id": "failing-task",
                "handler": "call_external_service",
                "dependencies": [],
                "config": {
                    "url": "http://example.com/api",
                    "simulate_failure": True,
                },
            }
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


async def wait_for_api(api_url: str, timeout: int = 30) -> None:
    """Block until the API health endpoint responds."""
    deadline = time.monotonic() + timeout
    async with httpx.AsyncClient(timeout=5) as client:
        while time.monotonic() < deadline:
            try:
                resp = await client.get(f"{api_url}/health")
                if resp.status_code == 200:
                    return
            except httpx.ConnectError:
                pass
            await asyncio.sleep(1)
    print(f"ERROR: API at {api_url} did not become ready within {timeout}s.", file=sys.stderr)
    sys.exit(1)


async def submit_workflow(api_url: str, payload: dict) -> str:
    """Submit the workflow definition and return the execution_id."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(f"{api_url}/api/v1/workflow", json=payload)
        resp.raise_for_status()
        data = resp.json()
    execution_id = data["execution_id"]
    print(f"  Submitted execution_id = {execution_id}")
    return execution_id


async def poll_status(api_url: str, execution_id: str, poll_interval: float = 2.0, max_polls: int = 30) -> dict:
    """Poll /executions/{id} until status is terminal or max polls reached."""
    terminal_states = {"COMPLETED", "FAILED", "TIMED_OUT"}
    async with httpx.AsyncClient(timeout=10) as client:
        for i in range(max_polls):
            resp = await client.get(f"{api_url}/api/v1/workflow/{execution_id}")
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "unknown")
            print(f"  [{i+1:02d}] status = {status}")
            if status.upper() in terminal_states:
                return data
            await asyncio.sleep(poll_interval)
    print("  Timed out waiting for terminal status.")
    return {}


async def inspect_dlq(redis_url: str, stream_key: str = DLQ_STREAM_KEY, count: int = 5) -> None:
    """Print the last `count` messages in the DLQ stream."""
    try:
        import redis.asyncio as aioredis  # only needed for this optional step
    except ImportError:
        print("  (redis-py not available; skipping DLQ inspection)")
        return

    client = aioredis.from_url(redis_url, decode_responses=True)
    try:
        messages = await client.xrevrange(stream_key, count=count)
        if not messages:
            print(f"  DLQ stream '{stream_key}' is empty.")
            return
        print(f"  Last {len(messages)} message(s) in '{stream_key}':")
        for msg_id, fields in messages:
            try:
                config = json.loads(fields.get("config", "{}"))
            except json.JSONDecodeError:
                config = fields.get("config", {})
            print(f"    stream_id={msg_id}  execution_id={fields.get('execution_id')}  "
                  f"node_id={fields.get('node_id')}  handler={fields.get('handler')}  "
                  f"simulate_failure={config.get('simulate_failure', False)}")
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(description="Demo: Reaper + DLQ flow")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Workflow API base URL")
    parser.add_argument("--redis-url", default=DEFAULT_REDIS_URL, help="Redis URL for DLQ inspection")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep polling status after submission (useful in CI / terminal demos)",
    )
    args = parser.parse_args()

    print_section("1. Waiting for API to be ready")
    await wait_for_api(args.api_url)
    print("  API is up.")

    print_section("2. Submitting deliberate-failure workflow")
    print(f"  Payload snippet: simulate_failure=true on node 'failing-task'")
    execution_id = await submit_workflow(args.api_url, DEMO_WORKFLOW)

    # Trigger execution
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(f"{args.api_url}/api/v1/workflow/trigger/{execution_id}")
    print(f"  Triggered execution {execution_id}")

    print_section("3. Polling execution status")
    result = await poll_status(
        args.api_url,
        execution_id,
        poll_interval=2.0,
        max_polls=30 if args.watch else 15,
    )
    if result:
        status = result.get("status", "unknown")
        print(f"\n  Final status: {status}")
        if status.lower() == "failed":
            print("  Task exhausted retries and was routed to the DLQ. [expected]")
        else:
            print(f"  Unexpected terminal status: {status}")

    print_section("4. Inspecting DLQ stream")
    await inspect_dlq(args.redis_url)

    print_section("Done")
    print("  To see the Reaper recover stalled tasks, kill a worker mid-execution")
    print("  and wait for REAPER_MIN_IDLE_SECONDS. The reaper will reclaim and")
    print("  re-publish the stuck task automatically.")


if __name__ == "__main__":
    asyncio.run(main())
