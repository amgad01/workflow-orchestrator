from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.adapters.secondary.resilience.circuit_breaker_manager import CircuitBreakerManager
from src.domain.resilience.exceptions.resilience_exceptions import CircuitOpenException


class TestCircuitBreakerManager:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.get.return_value = None
        redis.set.return_value = True
        redis.scan.return_value = (0, [])
        redis.delete.return_value = True
        return redis

    @pytest.fixture
    def manager(self, mock_redis):
        return CircuitBreakerManager(
            redis_client=mock_redis,
            failure_threshold=3,
            reset_timeout_seconds=30,
        )

    @pytest.mark.asyncio
    async def test_execute_success(self, manager):
        async def success_operation():
            return "success"

        result = await manager.execute("test_circuit", success_operation)
        assert result == "success"

    @pytest.mark.asyncio
    async def test_execute_failure_increments_count(self, manager, mock_redis):
        async def failing_operation():
            raise ValueError("Simulated failure")

        with pytest.raises(ValueError):
            await manager.execute("test_circuit", failing_operation)

        # Should have synced state to Redis
        mock_redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self, manager, mock_redis):
        async def failing_operation():
            raise ValueError("Simulated failure")

        # Fail 3 times to open circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await manager.execute("test_circuit", failing_operation)

        # Next call should raise CircuitOpenException
        with pytest.raises(CircuitOpenException):
            await manager.execute("test_circuit", failing_operation)

    @pytest.mark.asyncio
    async def test_execute_with_fallback(self, manager, mock_redis):
        # First, open the circuit
        async def failing_operation():
            raise ValueError("Simulated failure")

        for _ in range(3):
            with pytest.raises(ValueError):
                await manager.execute("test_circuit", failing_operation)

        # Now call with fallback
        def fallback():
            return "fallback_result"

        result = await manager.execute("test_circuit", failing_operation, fallback=fallback)
        assert result == "fallback_result"

    @pytest.mark.asyncio
    async def test_get_status(self, manager, mock_redis):
        status = await manager.get_status("test_circuit")

        assert "name" in status
        assert "state" in status
        assert status["name"] == "test_circuit"
        assert status["state"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_reset_circuit(self, manager, mock_redis):
        # Create a circuit
        async def success_op():
            return "ok"

        await manager.execute("test_circuit", success_op)

        # Reset it
        await manager.reset_circuit("test_circuit")

        mock_redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_sync_from_redis_restores_state(self, manager, mock_redis):
        # Simulate Redis having OPEN circuit state
        import json

        mock_redis.get.return_value = json.dumps(
            {
                "state": "OPEN",
                "failure_count": 5,
                "last_failure_time": datetime.now(timezone.utc).isoformat(),
            }
        )

        async def some_operation():
            return "ok"

        # Should raise CircuitOpenException because Redis state is OPEN
        with pytest.raises(CircuitOpenException):
            await manager.execute("synced_circuit", some_operation)

    @pytest.mark.asyncio
    async def test_get_all_statuses(self, manager, mock_redis):
        mock_redis.scan.return_value = (0, ["circuit_breaker:test1", "circuit_breaker:test2"])
        mock_redis.get.return_value = None

        statuses = await manager.get_all_statuses()

        assert isinstance(statuses, list)
