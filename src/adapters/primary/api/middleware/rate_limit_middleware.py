from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.adapters.secondary.redis.redis_rate_limiter import RedisRateLimiter
from src.shared.config import settings
from src.shared.logger import get_logger
from src.shared.redis_client import redis_client

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limiter: RedisRateLimiter = None):
        super().__init__(app)
        self._rate_limiter = rate_limiter or RedisRateLimiter(redis_client)

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Only rate limit workflow submission
        if request.method != "POST" or not request.url.path.endswith("/workflow"):
            return await call_next(request)

        # Use client IP as rate limit key
        client_ip = request.client.host if request.client else "unknown"
        rate_limit_key = f"workflow_submit:{client_ip}"

        result = await self._rate_limiter.check_rate_limit(
            key=rate_limit_key,
            limit=settings.RATE_LIMIT_REQUESTS_PER_MINUTE,
            window_seconds=60,
        )

        if not result.allowed:
            logger.warning(f"Rate limit exceeded for {client_ip}")
            return Response(
                content=f'{{"detail": "Rate limit exceeded. Retry after {result.retry_after_seconds} seconds."}}',
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": str(result.retry_after_seconds),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": str(result.remaining),
                },
            )

        response = await call_next(request)
        
        # Add rate limit headers to successful responses
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        
        return response
