"""
Integration tests for resilience features.

Tests cover:
- Health check endpoint
- Metrics endpoint
- Rate limiting
- Dead Letter Queue endpoints
- Circuit breaker
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.shared.config import settings


@pytest.mark.asyncio
class TestHealthAndMonitoring:
    """Tests for health check and metrics endpoints."""

    @pytest.fixture(autouse=True)
    async def setup(self, monkeypatch):
        """Set up test fixtures with mocked infrastructure."""
        settings.RATE_LIMIT_ENABLED = True
        settings.CIRCUIT_BREAKER_ENABLED = True

        self.mock_redis = AsyncMock()
        self.mock_redis.ping = AsyncMock(return_value=True)
        self.mock_redis.zcount = AsyncMock(return_value=0)
        self.mock_redis.zcard = AsyncMock(return_value=0)
        self.mock_redis.zadd = AsyncMock(return_value=1)
        self.mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        self.mock_redis.expire = AsyncMock(return_value=True)

        monkeypatch.setattr("src.shared.redis_client.redis_client", self.mock_redis)
        monkeypatch.setattr(
            "src.adapters.primary.api.middleware.rate_limit_middleware.redis_client",
            self.mock_redis,
        )
        monkeypatch.setattr("src.adapters.primary.api.routes.health.redis_client", self.mock_redis)

        self.mock_engine = MagicMock()
        self.mock_conn = AsyncMock()
        self.mock_cm = AsyncMock()
        self.mock_cm.__aenter__.return_value = self.mock_conn
        self.mock_engine.connect.return_value = self.mock_cm
        monkeypatch.setattr("src.adapters.primary.api.routes.health.engine", self.mock_engine)

        self.app = app
        self.transport = ASGITransport(app=self.app)

    @pytest.fixture
    async def client(self):
        """Create async HTTP client for testing."""
        async with AsyncClient(transport=self.transport, base_url="http://test") as client:
            yield client

    async def test_health_check_returns_healthy(self, client: AsyncClient):
        """Health check should return healthy status when dependencies are available."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_metrics_endpoint_returns_prometheus_format(self, client: AsyncClient):
        """Metrics endpoint should return Prometheus-compatible format."""
        response = await client.get("/metrics")

        assert response.status_code == 200
        assert "# HELP" in response.text


@pytest.mark.asyncio
class TestRateLimiting:
    """Tests for rate limiting middleware."""

    @pytest.fixture(autouse=True)
    async def setup(self, monkeypatch):
        """Set up test fixtures with mocked infrastructure."""
        settings.RATE_LIMIT_ENABLED = True

        self.mock_redis = AsyncMock()
        self.mock_redis.ping = AsyncMock(return_value=True)
        self.mock_redis.zcount = AsyncMock(return_value=0)
        self.mock_redis.zcard = AsyncMock(return_value=0)
        self.mock_redis.zadd = AsyncMock(return_value=1)
        self.mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        self.mock_redis.expire = AsyncMock(return_value=True)

        monkeypatch.setattr("src.shared.redis_client.redis_client", self.mock_redis)
        monkeypatch.setattr(
            "src.adapters.primary.api.middleware.rate_limit_middleware.redis_client",
            self.mock_redis,
        )
        monkeypatch.setattr("src.adapters.primary.api.routes.health.redis_client", self.mock_redis)

        self.mock_engine = MagicMock()
        self.mock_conn = AsyncMock()
        self.mock_cm = AsyncMock()
        self.mock_cm.__aenter__.return_value = self.mock_conn
        self.mock_engine.connect.return_value = self.mock_cm
        monkeypatch.setattr("src.adapters.primary.api.routes.health.engine", self.mock_engine)

        self.app = app
        self.transport = ASGITransport(app=self.app)

    @pytest.fixture
    async def client(self):
        """Create async HTTP client for testing."""
        async with AsyncClient(transport=self.transport, base_url="http://test") as client:
            yield client

    @patch("src.adapters.secondary.redis.redis_rate_limiter.RedisRateLimiter.check_rate_limit")
    async def test_returns_429_when_rate_limited(self, mock_check, client: AsyncClient):
        """Requests exceeding rate limit should receive 429 with Retry-After header."""
        from src.domain.resilience.value_objects.rate_limit_result import RateLimitResult

        reset_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        mock_check.return_value = RateLimitResult(
            allowed=False, limit=300, remaining=0, reset_at=reset_at
        )

        payload = {
            "name": "RL Test",
            "dag": {"nodes": [{"id": "n1", "handler": "h1"}]},
        }
        response = await client.post("/api/v1/workflow", json=payload)

        assert response.status_code == 429
        assert "Retry-After" in response.headers


@pytest.mark.asyncio
class TestDeadLetterQueue:
    """Tests for Dead Letter Queue admin endpoints."""

    @pytest.fixture(autouse=True)
    async def setup(self, monkeypatch):
        settings.RATE_LIMIT_ENABLED = True

        self.mock_redis = AsyncMock()
        self.mock_redis.ping = AsyncMock(return_value=True)
        self.mock_redis.zcount = AsyncMock(return_value=0)
        self.mock_redis.zcard = AsyncMock(return_value=0)
        self.mock_redis.zadd = AsyncMock(return_value=1)
        self.mock_redis.zremrangebyscore = AsyncMock(return_value=0)
        self.mock_redis.expire = AsyncMock(return_value=True)

        monkeypatch.setattr("src.shared.redis_client.redis_client", self.mock_redis)
        monkeypatch.setattr(
            "src.adapters.primary.api.middleware.rate_limit_middleware.redis_client",
            self.mock_redis,
        )
        monkeypatch.setattr("src.adapters.primary.api.routes.health.redis_client", self.mock_redis)

        # Mock DLQ repository using FastAPI dependency override
        self.mock_dlq_repo = AsyncMock()
        self.mock_broker = AsyncMock()

        from src.adapters.primary.api.dlq_routes import get_dlq_repository

        app.dependency_overrides[get_dlq_repository] = lambda: self.mock_dlq_repo

        self.mock_engine = MagicMock()
        self.mock_conn = AsyncMock()
        self.mock_cm = AsyncMock()
        self.mock_cm.__aenter__.return_value = self.mock_conn
        self.mock_engine.connect.return_value = self.mock_cm
        monkeypatch.setattr("src.adapters.primary.api.routes.health.engine", self.mock_engine)

        self.app = app
        self.transport = ASGITransport(app=self.app)

        yield

        app.dependency_overrides.clear()

    @pytest.fixture
    async def client(self):
        """Create async HTTP client for testing."""
        async with AsyncClient(transport=self.transport, base_url="http://test") as client:
            yield client

    async def test_list_dlq_returns_empty_when_no_entries(self, client: AsyncClient):
        """DLQ list endpoint should return empty list with count 0."""
        self.mock_dlq_repo.list_entries.return_value = []
        self.mock_dlq_repo.count.return_value = 0

        resp = await client.get("/api/v1/admin/dlq")

        assert resp.status_code == 200
        assert resp.json()["count"] == 0


@pytest.mark.asyncio
class TestCircuitBreaker:
    """Tests for circuit breaker functionality."""

    @pytest.fixture(autouse=True)
    async def setup(self, monkeypatch):
        """Set up test fixtures."""
        settings.RATE_LIMIT_ENABLED = False
        settings.CIRCUIT_BREAKER_ENABLED = True

        self.mock_redis = AsyncMock()
        monkeypatch.setattr("src.shared.redis_client.redis_client", self.mock_redis)
        monkeypatch.setattr(
            "src.adapters.primary.api.middleware.rate_limit_middleware.redis_client",
            self.mock_redis,
        )

        self.app = app
        self.transport = ASGITransport(app=self.app)

    @pytest.fixture
    async def client(self):
        """Create async HTTP client for testing."""
        async with AsyncClient(transport=self.transport, base_url="http://test") as client:
            yield client

    @patch("src.application.workflow.use_cases.submit_workflow.SubmitWorkflowUseCase.execute")
    async def test_workflow_with_external_service_handler(self, mock_submit, client: AsyncClient):
        """Workflow with external service handler should be accepted."""
        mock_submit.return_value = ("wf-1", "ex-1")

        payload = {
            "name": "External Service Test",
            "dag": {
                "nodes": [
                    {
                        "id": "external",
                        "handler": "call_external_service",
                        "config": {"url": "http://api.example.com"},
                    }
                ]
            },
        }
        resp = await client.post("/api/v1/workflow", json=payload)

        assert resp.status_code == 201
