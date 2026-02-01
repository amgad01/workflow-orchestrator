import pytest
import asyncio
import time
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from src.adapters.secondary.redis.redis_rate_limiter import RedisRateLimiter
from src.domain.resilience.value_objects.rate_limit_result import RateLimitResult


class TestRateLimiterLoadPerformance:
    @pytest.fixture
    def mock_redis(self):
        redis = AsyncMock()
        redis.incr.return_value = 1
        redis.expire.return_value = True
        return redis

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        return RedisRateLimiter(mock_redis)

    @pytest.mark.asyncio
    async def test_concurrent_rate_limit_checks(self, rate_limiter, mock_redis):
        call_count = 0
        
        async def mock_incr(*args):
            nonlocal call_count
            call_count += 1
            return call_count
        
        mock_redis.incr = mock_incr
        
        tasks = [
            rate_limiter.check_rate_limit("user1", limit=100, window_seconds=60)
            for _ in range(50)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All requests should be allowed (under limit)
        allowed_count = sum(1 for r in results if r.allowed)
        assert allowed_count == 50

    @pytest.mark.asyncio
    async def test_high_volume_rate_limiting(self, rate_limiter, mock_redis):
        request_count = 0
        
        async def mock_incr(*args):
            nonlocal request_count
            request_count += 1
            return request_count
        
        mock_redis.incr = mock_incr
        
        # Simulate 100 requests with limit of 60
        results = []
        for _ in range(100):
            result = await rate_limiter.check_rate_limit("user1", limit=60, window_seconds=60)
            results.append(result)
        
        allowed = sum(1 for r in results if r.allowed)
        blocked = sum(1 for r in results if not r.allowed)
        
        assert allowed == 60
        assert blocked == 40

    @pytest.mark.asyncio
    async def test_multiple_users_independent_limits(self, rate_limiter, mock_redis):
        user_counts = {"user1": 0, "user2": 0}
        
        async def mock_incr(key):
            user = "user1" if "user1" in key else "user2"
            user_counts[user] += 1
            return user_counts[user]
        
        mock_redis.incr = mock_incr
        
        # Each user gets their own limit
        for _ in range(30):
            await rate_limiter.check_rate_limit("user1", limit=50, window_seconds=60)
            await rate_limiter.check_rate_limit("user2", limit=50, window_seconds=60)
        
        assert user_counts["user1"] == 30
        assert user_counts["user2"] == 30

    @pytest.mark.asyncio
    async def test_rate_limit_reset_functionality(self, rate_limiter, mock_redis):
        mock_redis.scan.return_value = (0, ["rate_limit:user1:12345"])
        mock_redis.delete.return_value = 1
        
        await rate_limiter.reset("user1")
        
        mock_redis.delete.assert_called()


class TestRateLimiterEdgeCases:
    @pytest.fixture
    def mock_redis(self):
        return AsyncMock()

    @pytest.fixture
    def rate_limiter(self, mock_redis):
        return RedisRateLimiter(mock_redis)

    @pytest.mark.asyncio
    async def test_first_request_sets_expiry(self, rate_limiter, mock_redis):
        mock_redis.incr.return_value = 1  # First request
        
        await rate_limiter.check_rate_limit("new_user", limit=10, window_seconds=60)
        
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_subsequent_request_no_expiry_reset(self, rate_limiter, mock_redis):
        mock_redis.incr.return_value = 5  # Not first request
        
        await rate_limiter.check_rate_limit("existing_user", limit=10, window_seconds=60)
        
        mock_redis.expire.assert_not_called()

    @pytest.mark.asyncio
    async def test_zero_limit_blocks_all(self, rate_limiter, mock_redis):
        mock_redis.incr.return_value = 1
        
        result = await rate_limiter.check_rate_limit("user", limit=0, window_seconds=60)
        
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_very_short_window(self, rate_limiter, mock_redis):
        mock_redis.incr.return_value = 1
        
        result = await rate_limiter.check_rate_limit("user", limit=10, window_seconds=1)
        
        assert result.allowed is True
        assert result.reset_at is not None


class TestRateLimiterConcurrency:
    @pytest.mark.asyncio
    async def test_race_condition_handling(self):
        mock_redis = AsyncMock()
        race_counter = {"value": 0, "lock": asyncio.Lock()}
        
        async def mock_incr_with_delay(key):
            async with race_counter["lock"]:
                await asyncio.sleep(0.001)  # Simulate network delay
                race_counter["value"] += 1
                return race_counter["value"]
        
        mock_redis.incr = mock_incr_with_delay
        mock_redis.expire.return_value = True
        
        rate_limiter = RedisRateLimiter(mock_redis)
        
        # Concurrent requests
        tasks = [
            rate_limiter.check_rate_limit("user", limit=5, window_seconds=60)
            for _ in range(10)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # First 5 should be allowed, rest blocked
        allowed = sum(1 for r in results if r.allowed)
        assert allowed == 5
