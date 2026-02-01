import asyncio
import random

from src.adapters.secondary.workers.base_worker import BaseWorker
from src.ports.secondary.message_broker import TaskMessage
from src.shared.circuit_breaker import CircuitBreaker
from src.shared.config import settings


class ExternalServiceWorker(BaseWorker):
    def __init__(self):
        self._circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10)

    @property
    def handler_name(self) -> str:
        return "call_external_service"

    async def process(self, task: TaskMessage) -> dict:
        return await self._circuit_breaker.call(self._do_process, task)

    async def _do_process(self, task: TaskMessage) -> dict:
        # Simulate external service call with configurable delay
        if settings.WORKER_ENABLE_DELAYS:
            delay = random.uniform(
                settings.WORKER_EXTERNAL_MIN_MS / 1000,
                settings.WORKER_EXTERNAL_MAX_MS / 1000
            )
            await asyncio.sleep(delay)

        url = task.config.get("url", "http://example.com/api")
        
        # Simulate occasional failures to test circuit breaker
        # In a real app, this would be an actual HTTP call
        if "fail" in url:
            raise Exception(f"External service at {url} failed")

        return {
            "status_code": 200,
            "url": url,
            "data": {
                "id": random.randint(1, 1000),
                "result": f"Mock response from {url}",
                "timestamp": asyncio.get_event_loop().time(),
            },
        }
