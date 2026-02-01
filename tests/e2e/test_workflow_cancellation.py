"""
End-to-end tests for workflow cancellation.

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
class TestWorkflowCancellationE2E:
    """End-to-end tests for workflow cancellation functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self):
        """Set up test with server base URL."""
        self.base_url = "http://localhost:8000"

    async def test_cancellation_stops_workflow_execution(self):
        """
        Canceling a running workflow should stop it and prevent downstream execution.

        Test setup:
        1. Submit workflow with two sequential nodes (n1 takes 2s, n2 depends on n1)
        2. Trigger execution
        3. Cancel while n1 is running
        4. Verify status is CANCELLED and n2 never executed
        """
        async with AsyncClient(base_url=self.base_url) as client:
            dag = {
                "nodes": [
                    {"id": "n1", "handler": "delay", "config": {"seconds": 2}},
                    {
                        "id": "n2",
                        "handler": "echo",
                        "config": {"message": "unreachable"},
                        "dependencies": ["n1"],
                    },
                ]
            }

            # 1. Submit workflow
            resp = await client.post(
                "/workflow", json={"name": "test-cancellation", "dag": dag}
            )
            assert resp.status_code == 201
            execution_id = resp.json()["execution_id"]

            # 2. Trigger execution
            await client.post(f"/workflow/trigger/{execution_id}")

            # Wait for n1 to start
            await asyncio.sleep(0.5)

            # 3. Cancel the workflow
            resp = await client.delete(f"/workflow/{execution_id}")
            assert resp.status_code == 200
            assert resp.json()["status"] == "success"

            # 4. Wait for n1 to complete (but orchestrator should drop its completion)
            await asyncio.sleep(3)

            # 5. Verify final status
            resp = await client.get(f"/workflow/{execution_id}")
            status = resp.json()
            assert status["status"] == "CANCELLED"

            # Verify n2 was never executed - check results
            resp = await client.get(f"/workflow/{execution_id}/results")
            outputs = resp.json()["outputs"]
            assert "n2" not in outputs
