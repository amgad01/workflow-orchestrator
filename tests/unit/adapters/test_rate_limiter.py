from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.adapters.secondary.redis.redis_rate_limiter import RedisRateLimiter
from src.domain.resilience.value_objects.rate_limit_result import RateLimitResult


class TestRedisRateLimiter:
    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        return RedisRateLimiter(mock_redis)

    @pytest.mark.asyncio
    async def test_rate_limit_allows_under_threshold(self, rate_limiter, mock_redis):
        mock_redis.incr.return_value = 5
        
        result = await rate_limiter.check_rate_limit(
            key="test_user",
            limit=10,
            window_seconds=60,
        )
        
        assert result.allowed is True
        assert result.remaining == 5
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_threshold(self, rate_limiter, mock_redis):
        mock_redis.incr.return_value = 11
        
        result = await rate_limiter.check_rate_limit(
            key="test_user",
            limit=10,
            window_seconds=60,
        )
        
        assert result.allowed is False
        assert result.remaining == 0
        assert result.retry_after_seconds is not None

    @pytest.mark.asyncio
    async def test_rate_limit_exact_at_threshold(self, rate_limiter, mock_redis):
        mock_redis.incr.return_value = 10
        
        result = await rate_limiter.check_rate_limit(
            key="test_user",
            limit=10,
            window_seconds=60,
        )
        
        assert result.allowed is True
        assert result.remaining == 0

    @pytest.mark.asyncio
    async def test_sets_expire_on_first_request(self, rate_limiter, mock_redis):
        mock_redis.incr.return_value = 1
        
        await rate_limiter.check_rate_limit(
            key="test_user",
            limit=10,
            window_seconds=60,
        )
        
        mock_redis.expire.assert_called_once()


class TestRateLimitResult:
    def test_retry_after_returns_none_when_allowed(self):
        result = RateLimitResult(
            allowed=True,
            remaining=5,
            limit=10,
            reset_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        
        assert result.retry_after_seconds is None

    def test_retry_after_returns_seconds_when_blocked(self):
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=10,
            reset_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        
        retry_after = result.retry_after_seconds
        assert retry_after is not None
        assert 25 <= retry_after <= 30  # Allow some tolerance

    def test_retry_after_returns_none_without_reset_at(self):
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            limit=10,
            reset_at=None,
        )
        
        assert result.retry_after_seconds is None
