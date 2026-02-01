"""
Integration tests for workflow API error handling.

Tests cover:
- Pydantic validation errors
- Execution not found errors
- Workflow cancellation errors
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from src.main import app
from src.shared.config import settings


@pytest.mark.asyncio
class TestWorkflowApiErrors:

    @pytest.fixture(autouse=True)
    async def setup(self, monkeypatch):
        settings.RATE_LIMIT_ENABLED = False
        settings.CIRCUIT_BREAKER_ENABLED = False

        self.mock_redis = AsyncMock()
        monkeypatch.setattr("src.shared.redis_client.redis_client", self.mock_redis)
        monkeypatch.setattr(
            "src.adapters.primary.api.dependencies.redis_client", self.mock_redis
        )
        monkeypatch.setattr(
            "src.adapters.primary.api.middleware.rate_limit_middleware.redis_client",
            self.mock_redis,
        )
        monkeypatch.setattr(
            "src.adapters.primary.api.routes.health.redis_client", self.mock_redis
        )
        monkeypatch.setattr("src.shared.database.engine", AsyncMock())

        self.mock_engine = AsyncMock()
        monkeypatch.setattr(
            "src.adapters.primary.api.routes.health.engine", self.mock_engine
        )

        self.mock_session = AsyncMock()
        monkeypatch.setattr(
            "src.adapters.primary.api.dependencies.async_session_factory",
            lambda: self.mock_session,
        )
        monkeypatch.setattr(
            "src.shared.database.async_session_factory", lambda: self.mock_session
        )

        self.app = app
        self.transport = ASGITransport(app=self.app)

    @pytest.fixture
    async def client(self):
        """Create async HTTP client for testing."""
        async with AsyncClient(
            transport=self.transport, base_url="http://test"
        ) as client:
            yield client

    async def test_returns_422_for_missing_required_fields(self, client: AsyncClient):
        """Missing required DAG field should return 422 Pydantic validation error."""
        payload = {"name": "No DAG"}
        response = await client.post("/workflow", json=payload)

        assert response.status_code == 422 

    @patch(
        "src.application.workflow.use_cases.get_workflow_status.GetWorkflowStatusUseCase.execute"
    )
    async def test_returns_404_for_non_existent_execution(
        self, mock_execute, client: AsyncClient
    ):
        """Requesting status of non-existent execution should return 404."""
        from src.domain.workflow.exceptions import ExecutionNotFoundError

        mock_execute.side_effect = ExecutionNotFoundError("non-existent-id")

        response = await client.get("/workflow/non-existent-id")

        assert response.status_code == 404
        data = response.json()
        assert data["error"]["error_code"] == "EXECUTION_NOT_FOUND"

    @patch(
        "src.application.workflow.use_cases.cancel_workflow.CancelWorkflowUseCase.execute"
    )
    async def test_returns_404_for_cancel_non_existent_execution(
        self, mock_cancel, client: AsyncClient
    ):
        """Canceling non-existent execution should return 404."""
        from src.domain.workflow.exceptions import ExecutionNotFoundError

        mock_cancel.side_effect = ExecutionNotFoundError("unknown")

        response = await client.delete("/workflow/unknown")

        assert response.status_code == 404
        assert response.json()["error"]["error_code"] == "EXECUTION_NOT_FOUND"

    @patch(
        "src.application.workflow.use_cases.submit_workflow.SubmitWorkflowUseCase.execute"
    )
    async def test_accepts_workflow_with_unknown_handler(
        self, mock_execute, client: AsyncClient
    ):
        """
        Workflow with unknown handler is accepted at submission.

        Handler validation happens at execution time, not submission.
        """
        mock_execute.return_value = ("wf-1", "ex-1")

        payload = {
            "name": "Invalid Handler",
            "dag": {"nodes": [{"id": "n1", "handler": "invalid"}]},
        }
        response = await client.post("/workflow", json=payload)

        assert response.status_code == 201
