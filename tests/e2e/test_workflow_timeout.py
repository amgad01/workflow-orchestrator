"""
End-to-end tests for workflow timeout functionality.

These tests require:
- Running server at localhost:8000
- Running Redis and PostgreSQL instances
- Running orchestrator and worker processes

To run: docker-compose up -d && pytest tests/e2e/ -v
"""

import asyncio
import pytest
from httpx import AsyncClient


@pytest.mark.e2e
@pytest.mark.asyncio
class TestWorkflowTimeout:
    """End-to-end tests for workflow timeout behavior."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Set up test with server base URL."""
        self.base_url = "http://localhost:8000"

    async def test_workflow_times_out_with_short_timeout(self):
        """
        Workflow with short timeout should fail when node exceeds timeout.

        Test setup:
        - Workflow with 0.1s timeout
        - Node that takes 1-2s to complete
        - Expected: FAILED status due to timeout
        """
        async with AsyncClient(base_url=self.base_url) as client:
            payload = {
                "name": "Timeout Test",
                "timeout_seconds": 0.1,
                "dag": {
                    "nodes": [
                        {
                            "id": "n1",
                            "handler": "call_external_service",
                            "dependencies": [],
                        }
                    ]
                },
            }

            resp = await client.post("/workflow", json=payload)
            assert resp.status_code == 201
            execution_id = resp.json()["execution_id"]

            # Trigger execution
            await client.post(f"/workflow/trigger/{execution_id}")

            # Wait for orchestrator to detect timeout
            await asyncio.sleep(4)

            resp = await client.get(f"/workflow/{execution_id}")
            assert resp.json()["status"] == "FAILED"
            assert resp.json()["node_statuses"]["n1"] == "FAILED"


@pytest.mark.e2e
@pytest.mark.asyncio
class TestCircuitBreakerE2E:
    """End-to-end tests for circuit breaker with real external service calls."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Set up test with server base URL."""
        self.base_url = "http://localhost:8000"

    async def test_circuit_breaker_opens_on_failures(self):
        """
        Circuit breaker should open after repeated failures.

        Test setup:
        - Multiple nodes calling a failing external URL
        - Expected: FAILED status after circuit opens
        """
        async with AsyncClient(base_url=self.base_url) as client:
            payload = {
                "name": "Circuit Breaker Test",
                "dag": {
                    "nodes": [
                        {
                            "id": "f1",
                            "handler": "call_external_service",
                            "dependencies": [],
                            "config": {"url": "http://fail.com"},
                        },
                        {
                            "id": "f2",
                            "handler": "call_external_service",
                            "dependencies": [],
                            "config": {"url": "http://fail.com"},
                        },
                        {
                            "id": "f3",
                            "handler": "call_external_service",
                            "dependencies": [],
                            "config": {"url": "http://fail.com"},
                        },
                    ]
                },
            }

            resp = await client.post("/workflow", json=payload)
            assert resp.status_code == 201
            execution_id = resp.json()["execution_id"]

            await client.post(f"/workflow/trigger/{execution_id}")

            # Wait for failures and circuit breaker to trigger
            await asyncio.sleep(10)

            resp = await client.get(f"/workflow/{execution_id}")
            assert resp.json()["status"] == "FAILED"
