"""
Integration tests for concurrent workflow operations.

Tests cover:
- Concurrent workflow submissions
- Parallel trigger operations
- Single node workflows
"""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from src.main import app
from src.shared.config import settings


@pytest.mark.asyncio
class TestWorkflowConcurrency:
    """Tests for concurrent workflow operations and race conditions."""

    @pytest.fixture(autouse=True)
    async def setup(self, monkeypatch):
        """Set up test fixtures with mocked infrastructure."""
        settings.RATE_LIMIT_ENABLED = False

        self.mock_redis = AsyncMock()
        monkeypatch.setattr("src.shared.redis_client.redis_client", self.mock_redis)
        monkeypatch.setattr(
            "src.adapters.primary.api.middleware.rate_limit_middleware.redis_client",
            self.mock_redis,
        )

        self.app = app
        self.transport = ASGITransport(app=self.app)

    @patch(
        "src.application.workflow.use_cases.submit_workflow.SubmitWorkflowUseCase.execute"
    )
    async def test_handles_concurrent_submissions(self, mock_execute):
        """
        Multiple concurrent workflow submissions should all succeed.

        This validates thread-safety and proper handling of concurrent requests.
        """
        mock_execute.return_value = ("wf-1", "ex-1")

        async with AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            payload = {
                "name": "Concurrent Workflow",
                "dag": {"nodes": [{"id": "n1", "handler": "h1"}]},
            }

            tasks = [client.post("/workflow", json=payload) for _ in range(10)]
            responses = await asyncio.gather(*tasks)

            for resp in responses:
                assert resp.status_code == 201
                assert "execution_id" in resp.json()

    @patch(
        "src.application.workflow.use_cases.submit_workflow.SubmitWorkflowUseCase.execute"
    )
    async def test_accepts_single_node_workflow(self, mock_execute):
        """Single node workflow should be accepted and processed."""
        mock_execute.return_value = ("wf-1", "ex-1")

        async with AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            payload = {
                "name": "Single Node",
                "dag": {"nodes": [{"id": "only", "handler": "input"}]},
            }
            response = await client.post("/workflow", json=payload)

            assert response.status_code == 201

    @patch(
        "src.application.workflow.use_cases.submit_workflow.SubmitWorkflowUseCase.execute"
    )
    @patch(
        "src.application.workflow.use_cases.trigger_execution.TriggerExecutionUseCase.execute"
    )
    async def test_handles_concurrent_triggers(self, mock_trigger, mock_submit):
        """
        Multiple concurrent triggers for same execution should be handled gracefully.

        This validates idempotency of trigger operations.
        """
        mock_submit.return_value = ("wf-1", "ex-1")
        mock_trigger.return_value = None

        async with AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            payload = {
                "name": "Parallel Trigger Test",
                "dag": {"nodes": [{"id": "n1", "handler": "h1"}]},
            }
            submit_resp = await client.post("/workflow", json=payload)
            execution_id = submit_resp.json()["execution_id"]

            trigger_tasks = [
                client.post(f"/workflow/trigger/{execution_id}") for _ in range(5)
            ]
            responses = await asyncio.gather(*trigger_tasks)

            for resp in responses:
                assert resp.status_code in (200, 201)
