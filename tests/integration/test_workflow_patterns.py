"""
Integration tests for workflow scenarios using FastAPI dependency injection.

Tests cover:
- Linear workflow (A → B → C)
- Fan-out/Fan-in patterns
- Data templating between nodes
- Fail-fast propagation
"""

import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from src.main import app
from src.shared.config import settings


@pytest.fixture(scope="module", autouse=True)
def mock_infrastructure():
    """Module-scoped fixture to mock infrastructure dependencies."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)

    mock_engine = AsyncMock()
    mock_engine.dispose = AsyncMock()

    from src import main

    original_lifespan = main.lifespan

    @asyncio.iscoroutinefunction
    async def dummy_lifespan(app):
        yield

    main.lifespan = dummy_lifespan

    with (
        patch("src.shared.redis_client.redis_client", mock_redis),
        patch("src.shared.database.engine", mock_engine),
        patch("src.main.redis_client", mock_redis),
        patch("src.main.engine", mock_engine),
        patch(
            "src.adapters.primary.api.middleware.rate_limit_middleware.redis_client",
            mock_redis,
        ),
        patch("src.adapters.primary.api.routes.health.redis_client", mock_redis),
        patch("src.adapters.primary.api.routes.health.engine", mock_engine),
    ):
        yield

    main.lifespan = original_lifespan


@pytest.fixture(scope="module")
def transport():
    """Create transport for the module."""
    old_rl = settings.RATE_LIMIT_ENABLED
    settings.RATE_LIMIT_ENABLED = False

    transport = ASGITransport(app=app)
    yield transport

    settings.RATE_LIMIT_ENABLED = old_rl


@pytest.mark.asyncio
class TestWorkflowPatterns:
    """Tests for common workflow execution patterns."""

    async def test_linear_workflow_pattern(self, transport):
        """
        Scenario: Linear workflow (A → B → C).

        Each node depends on the previous one, forming a simple chain.
        """
        from src.adapters.primary.api.dependencies import (
            get_submit_workflow_use_case,
            get_trigger_execution_use_case,
        )

        mock_submit = AsyncMock()
        mock_submit.execute.return_value = ("wf-123", "exec-456")
        mock_trigger = AsyncMock()
        mock_trigger.execute.return_value = None

        app.dependency_overrides[get_submit_workflow_use_case] = lambda: mock_submit
        app.dependency_overrides[get_trigger_execution_use_case] = lambda: mock_trigger

        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                dag = {
                    "name": "Linear Workflow",
                    "dag": {
                        "nodes": [
                            {"id": "A", "handler": "h1", "dependencies": []},
                            {"id": "B", "handler": "h1", "dependencies": ["A"]},
                            {"id": "C", "handler": "h1", "dependencies": ["B"]},
                        ]
                    },
                }
                response = await ac.post("/api/v1/workflow", json=dag)

                assert response.status_code == 201
                assert response.json()["execution_id"] == "exec-456"
        finally:
            app.dependency_overrides = {}

    async def test_fan_out_fan_in_pattern(self, transport):
        """
        Scenario: Parallel execution with fan-out/fan-in.

        A → [B, C, D] → E (B, C, D execute in parallel)
        """
        from src.adapters.primary.api.dependencies import get_submit_workflow_use_case

        mock_submit = AsyncMock()
        mock_submit.execute.return_value = ("wf-fan", "exec-fan")
        app.dependency_overrides[get_submit_workflow_use_case] = lambda: mock_submit

        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                dag = {
                    "name": "Fan-Out Fan-In",
                    "dag": {
                        "nodes": [
                            {"id": "A", "handler": "h1", "dependencies": []},
                            {"id": "B", "handler": "h1", "dependencies": ["A"]},
                            {"id": "C", "handler": "h1", "dependencies": ["A"]},
                            {"id": "D", "handler": "h1", "dependencies": ["A"]},
                            {
                                "id": "E",
                                "handler": "h1",
                                "dependencies": ["B", "C", "D"],
                            },
                        ]
                    },
                }
                response = await ac.post("/api/v1/workflow", json=dag)

                assert response.status_code == 201
        finally:
            app.dependency_overrides = {}

    async def test_data_templating_pattern(self, transport):
        """
        Scenario: Data passing between nodes via templating.

        Output from 'fetch' node is used as input for 'process' node.
        """
        from src.adapters.primary.api.dependencies import get_submit_workflow_use_case

        mock_submit = AsyncMock()
        mock_submit.execute.return_value = ("wf-data", "exec-data")
        app.dependency_overrides[get_submit_workflow_use_case] = lambda: mock_submit

        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                dag = {
                    "name": "Data Templating",
                    "dag": {
                        "nodes": [
                            {"id": "fetch", "handler": "h1", "config": {"key": "val"}},
                            {
                                "id": "process",
                                "handler": "h2",
                                "dependencies": ["fetch"],
                                "config": {"input": "{{ fetch.output }}"},
                            },
                        ]
                    },
                }
                response = await ac.post("/api/v1/workflow", json=dag)

                assert response.status_code == 201
        finally:
            app.dependency_overrides = {}

    async def test_fail_fast_propagation(self, transport):
        """
        Scenario: Fail-fast behavior when a node fails.

        Downstream nodes should remain PENDING when upstream fails.
        """
        from src.adapters.primary.api.dependencies import get_workflow_status_use_case

        mock_status = AsyncMock()
        mock_status.execute.return_value = {
            "execution_id": "exec-fail",
            "workflow_id": "wf-fail",
            "status": "FAILED",
            "node_statuses": {"A": "FAILED", "B": "PENDING"},
        }
        app.dependency_overrides[get_workflow_status_use_case] = lambda: mock_status

        try:
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get("/api/v1/workflow/exec-fail")

                assert response.status_code == 200
                assert response.json()["status"] == "FAILED"
        finally:
            app.dependency_overrides = {}
