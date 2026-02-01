import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from src.main import app
from src.adapters.primary.api.dto import WorkflowSubmitResponse, WorkflowStatusResponse, WorkflowResultsResponse
from src.adapters.primary.api.dependencies import (
    get_submit_workflow_use_case,
    get_workflow_status_use_case,
    get_workflow_results_use_case,
    get_cancel_workflow_use_case,
)
from src.domain.resilience.value_objects.rate_limit_result import RateLimitResult


class TestApiRoutes:
    @pytest.fixture
    def mock_submit(self):
        return AsyncMock()

    @pytest.fixture
    def mock_status(self):
        return AsyncMock()

    @pytest.fixture
    def mock_results(self):
        return AsyncMock()

    @pytest.fixture
    def mock_cancel(self):
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_submit, mock_status, mock_results, mock_cancel):
        # Override dependencies
        app.dependency_overrides[get_submit_workflow_use_case] = lambda: mock_submit
        app.dependency_overrides[get_workflow_status_use_case] = lambda: mock_status
        app.dependency_overrides[get_workflow_results_use_case] = lambda: mock_results
        app.dependency_overrides[get_cancel_workflow_use_case] = lambda: mock_cancel
        
        from src.shared.config import settings
        old_rl_enabled = settings.RATE_LIMIT_ENABLED
        old_cb_enabled = settings.CIRCUIT_BREAKER_ENABLED
        settings.RATE_LIMIT_ENABLED = False
        settings.CIRCUIT_BREAKER_ENABLED = False
        
        # Mock Rate Limiter to return allowed
        mock_rl_result = RateLimitResult(allowed=True, remaining=99, limit=100)
        mock_rate_limiter = AsyncMock()
        mock_rate_limiter.check_rate_limit.return_value = mock_rl_result
        
        # Mock the infrastructure to avoid connection errors
        try:
            with patch("src.main.redis_client", AsyncMock()), \
                 patch("src.main.engine", AsyncMock()), \
                 patch("src.shared.redis_client.redis_client", AsyncMock(ping=AsyncMock())), \
                 patch("src.adapters.primary.api.routes.health.redis_client", AsyncMock(ping=AsyncMock())), \
                 patch("src.adapters.primary.api.routes.health.engine", MagicMock()), \
                 patch("src.adapters.primary.api.middleware.rate_limit_middleware.RedisRateLimiter", return_value=mock_rate_limiter):
                
                # Setup health check engine mock
                import src.adapters.primary.api.routes.health as health_mod
                mock_engine = health_mod.engine
                mock_conn = AsyncMock()
                mock_cm = AsyncMock()
                mock_cm.__aenter__.return_value = mock_conn
                mock_engine.connect.return_value = mock_cm

                with TestClient(app) as c:
                    yield c
        finally:
            # Clear overrides and restore settings after test
            app.dependency_overrides = {}
            settings.RATE_LIMIT_ENABLED = old_rl_enabled
            settings.CIRCUIT_BREAKER_ENABLED = old_cb_enabled

    def test_submit_workflow_success(self, client, mock_submit):
        mock_submit.execute.return_value = ("wf-123", "exec-456")
        
        response = client.post(
            "/api/v1/workflow",
            json={
                "name": "Test Workflow",
                "dag": {"nodes": [{"id": "n1", "handler": "h1"}]}
            }
        )
        
        assert response.status_code == 201
        assert response.json()["workflow_id"] == "wf-123"
        assert response.json()["execution_id"] == "exec-456"

    def test_get_workflow_status_success(self, client, mock_status):
        mock_status.execute.return_value = {
            "execution_id": "exec-456",
            "workflow_id": "wf-123",
            "status": "RUNNING",
            "node_statuses": {"n1": "RUNNING"}
        }
        
        response = client.get("/api/v1/workflow/exec-456")
        
        assert response.status_code == 200
        assert response.json()["status"] == "RUNNING"

    def test_get_workflow_results_success(self, client, mock_results):
        mock_results.execute.return_value = {
            "execution_id": "exec-456", 
            "workflow_id": "wf-123", 
            "outputs": {"n1": {"output": "data"}}
        }
        
        response = client.get("/api/v1/workflow/exec-456/results")
        
        assert response.status_code == 200
        assert response.json()["outputs"]["n1"]["output"] == "data"

    def test_get_workflow_results_alias_success(self, client, mock_results):
        # Test the /workflows/{id}/results alias
        mock_results.execute.return_value = {
            "execution_id": "exec-456", 
            "workflow_id": "wf-123", 
            "outputs": {"n1": {"output": "data"}}
        }
        
        response = client.get("/api/v1/workflow/exec-456/results")
        
        assert response.status_code == 200
        assert response.json()["outputs"]["n1"]["output"] == "data"

    def test_cancel_workflow_success(self, client, mock_cancel):
        mock_cancel.execute.return_value = None
        
        response = client.delete("/api/v1/workflow/exec-456")
        
        assert response.status_code == 200
        assert "cancelled" in response.json()["message"]

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
