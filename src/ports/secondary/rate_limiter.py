from abc import ABC, abstractmethod

from src.domain.resilience.value_objects.rate_limit_result import RateLimitResult


class IRateLimiter(ABC):
    @abstractmethod
    async def check_rate_limit(self, key: str, limit: int, window_seconds: int) -> RateLimitResult:
        pass

    @abstractmethod
    async def reset(self, key: str) -> None:
        pass
