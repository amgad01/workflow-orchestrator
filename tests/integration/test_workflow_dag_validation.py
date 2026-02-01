"""
Integration tests for DAG validation in workflow submission.

Tests cover:
- Cycle detection
- Invalid node references
- Empty workflows
- Duplicate node IDs
- Disconnected graphs (valid case)
- Deeply nested DAGs
"""

import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from src.main import app
from src.shared.config import settings


@pytest.mark.asyncio
class TestWorkflowDagValidation:
    """Tests for validating DAG structure during workflow submission."""

    @pytest.fixture(autouse=True)
    async def setup(self, monkeypatch):
        """Set up test fixtures with mocked infrastructure."""
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

        self.mock_session = MagicMock()
        self.mock_session.add = MagicMock()
        self.mock_session.commit = AsyncMock()
        self.mock_session.execute = AsyncMock()

        class DummySessionContext:
            async def __aenter__(self_inner):
                return self.mock_session

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        monkeypatch.setattr(
            "src.adapters.primary.api.dependencies.async_session_factory",
            lambda: DummySessionContext(),
        )
        monkeypatch.setattr(
            "src.shared.database.async_session_factory",
            lambda: DummySessionContext(),
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

    async def test_rejects_cyclic_dag(self, client: AsyncClient):
        """Workflow with cyclic dependencies should be rejected with CYCLIC_DEPENDENCY error."""
        payload = {
            "name": "Cycle Workflow",
            "dag": {
                "nodes": [
                    {"id": "n1", "handler": "h1", "dependencies": ["n2"]},
                    {"id": "n2", "handler": "h1", "dependencies": ["n1"]},
                ]
            },
        }
        response = await client.post("/workflow", json=payload)

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["error_code"] == "CYCLIC_DEPENDENCY"

    async def test_rejects_invalid_node_reference(self, client: AsyncClient):
        """Workflow referencing non-existent node should be rejected with INVALID_NODE_REFERENCE error."""
        payload = {
            "name": "Missing Dep Workflow",
            "dag": {
                "nodes": [{"id": "n1", "handler": "h1", "dependencies": ["nonexistent"]}]
            },
        }
        response = await client.post("/workflow", json=payload)

        assert response.status_code == 400
        data = response.json()
        assert data["error"]["error_code"] == "INVALID_NODE_REFERENCE"

    async def test_rejects_empty_dag(self, client: AsyncClient):
        """Workflow with no nodes should be rejected with EMPTY_WORKFLOW error."""
        payload = {"name": "Empty Workflow", "dag": {"nodes": []}}
        response = await client.post("/workflow", json=payload)

        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "EMPTY_WORKFLOW"

    async def test_rejects_duplicate_node_ids(self, client: AsyncClient):
        """Workflow with duplicate node IDs should be rejected with DUPLICATE_NODE_ID error."""
        payload = {
            "name": "Duplicate ID",
            "dag": {
                "nodes": [
                    {"id": "n1", "handler": "input"},
                    {"id": "n1", "handler": "input"},
                ]
            },
        }
        response = await client.post("/workflow", json=payload)

        assert response.status_code == 400
        assert response.json()["error"]["error_code"] == "DUPLICATE_NODE_ID"

    async def test_accepts_disconnected_graph(self, client: AsyncClient):
        """
        Disconnected graph (parallel independent nodes) should be accepted.

        The engine supports multiple independent DAG islands for parallel execution.
        """
        payload = {
            "name": "Disconnected",
            "dag": {
                "nodes": [
                    {"id": "n1", "handler": "input"},
                    {"id": "n2", "handler": "input"},
                ]
            },
        }
        response = await client.post("/workflow", json=payload)

        assert response.status_code == 201

    @patch(
        "src.application.workflow.use_cases.submit_workflow.SubmitWorkflowUseCase.execute"
    )
    async def test_accepts_deeply_nested_dag(
        self, mock_execute, client: AsyncClient
    ):
        """
        Deeply nested linear DAG (50 nodes) should be accepted.

        This tests the engine's ability to handle complex dependency chains.
        """
        mock_execute.return_value = ("wf-deep", "ex-deep")

        nodes = [
            {
                "id": f"n{i}",
                "handler": "h1",
                "dependencies": [f"n{i-1}"] if i > 0 else [],
            }
            for i in range(50)
        ]
        payload = {"name": "Deep DAG", "dag": {"nodes": nodes}}

        response = await client.post("/workflow", json=payload)
        assert response.status_code == 201
