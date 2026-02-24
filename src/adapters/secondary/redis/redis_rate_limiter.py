from datetime import datetime, timezone

import redis.asyncio as redis

from src.domain.resilience.value_objects.rate_limit_result import RateLimitResult
from src.ports.secondary.rate_limiter import IRateLimiter


class RedisRateLimiter(IRateLimiter):
    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        now = datetime.now(timezone.utc)
        window_start = int(now.timestamp()) // window_seconds * window_seconds
        redis_key = f"rate_limit:{key}:{window_start}"

        current_count = await self._redis.incr(redis_key)

        if current_count == 1:
            await self._redis.expire(redis_key, window_seconds)

        remaining = max(0, limit - current_count)
        reset_at = datetime.fromtimestamp(window_start + window_seconds, tz=timezone.utc)
        allowed = current_count <= limit

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            limit=limit,
            reset_at=reset_at,
        )

    async def reset(self, key: str) -> None:
        pattern = f"rate_limit:{key}:*"
        cursor = 0
        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
            if keys:
                await self._redis.delete(*keys)
            if cursor == 0:
                break
