import asyncio
import random

from src.adapters.secondary.workers.base_worker import BaseWorker
from src.domain.resilience.entities.circuit_breaker import CircuitBreaker
from src.domain.resilience.exceptions.resilience_exceptions import CircuitOpenException
from src.ports.secondary.message_broker import TaskMessage
from src.shared.config import settings


class ExternalServiceWorker(BaseWorker):
    def __init__(self):
        self._circuit_breaker = CircuitBreaker(
            name="external_service",
            failure_threshold=settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            reset_timeout_seconds=settings.CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS,
            half_open_max_calls=settings.CIRCUIT_BREAKER_HALF_OPEN_MAX_CALLS,
        )

    @property
    def handler_name(self) -> str:
        return "call_external_service"

    async def process(self, task: TaskMessage) -> dict:
        if not self._circuit_breaker.can_execute():
            raise CircuitOpenException(
                self._circuit_breaker.name,
                self._circuit_breaker.reset_timeout_seconds,
            )

        try:
            result = await self._do_process(task)
            self._circuit_breaker.record_success()
            return result
        except Exception:
            self._circuit_breaker.record_failure()
            raise

    async def _do_process(self, task: TaskMessage) -> dict:
        # Simulate external service call with configurable delay
        if settings.WORKER_ENABLE_DELAYS:
            delay = random.uniform(
                settings.WORKER_EXTERNAL_MIN_MS / 1000,
                settings.WORKER_EXTERNAL_MAX_MS / 1000
            )
            await asyncio.sleep(delay)

        url = task.config.get("url", settings.WORKER_DEFAULT_EXTERNAL_URL)

        # Failure simulation for testing
        if task.config.get("simulate_failure", False):
            raise Exception(f"Simulated failure for external service at {url}")

        return {
            "status_code": 200,
            "url": url,
            "data": {
                "id": random.randint(1, 1000),
                "result": f"Mock response from {url}",
                "timestamp": asyncio.get_event_loop().time(),
            },
        }
