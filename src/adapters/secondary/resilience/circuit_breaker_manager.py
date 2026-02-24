import json
from collections.abc import Callable
from datetime import datetime
from typing import TypeVar

import redis.asyncio as redis

from src.domain.resilience.entities.circuit_breaker import CircuitBreaker, CircuitState
from src.domain.resilience.exceptions.resilience_exceptions import CircuitOpenException
from src.shared.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitBreakerManager:
    REDIS_KEY_PREFIX = "circuit_breaker:"

    def __init__(
        self,
        redis_client: redis.Redis,
        failure_threshold: int = 5,
        reset_timeout_seconds: int = 60,
    ):
        self._redis = redis_client
        self._failure_threshold = failure_threshold
        self._reset_timeout_seconds = reset_timeout_seconds
        self._local_circuits: dict[str, CircuitBreaker] = {}

    def _get_or_create_circuit(self, name: str) -> CircuitBreaker:
        if name not in self._local_circuits:
            self._local_circuits[name] = CircuitBreaker(
                name=name,
                failure_threshold=self._failure_threshold,
                reset_timeout_seconds=self._reset_timeout_seconds,
            )
        return self._local_circuits[name]

    async def _sync_from_redis(self, circuit: CircuitBreaker) -> None:
        key = f"{self.REDIS_KEY_PREFIX}{circuit.name}"
        data = await self._redis.get(key)
        if data:
            try:
                state_dict = json.loads(data)
                circuit.state = CircuitState(state_dict.get("state", "CLOSED"))
                circuit.failure_count = state_dict.get("failure_count", 0)
                last_failure = state_dict.get("last_failure_time")
                if last_failure:
                    circuit.last_failure_time = datetime.fromisoformat(last_failure)
            except (json.JSONDecodeError, ValueError):
                pass

    async def _sync_to_redis(self, circuit: CircuitBreaker) -> None:
        key = f"{self.REDIS_KEY_PREFIX}{circuit.name}"
        state_dict = {
            "state": circuit.state.value,
            "failure_count": circuit.failure_count,
            "last_failure_time": circuit.last_failure_time.isoformat()
            if circuit.last_failure_time
            else None,
        }
        await self._redis.set(key, json.dumps(state_dict), ex=self._reset_timeout_seconds * 2)

    async def execute(
        self,
        circuit_name: str,
        operation: Callable[[], T],
        fallback: Callable[[], T] | None = None,
    ) -> T:
        circuit = self._get_or_create_circuit(circuit_name)
        await self._sync_from_redis(circuit)

        if not circuit.can_execute():
            logger.warning(f"Circuit '{circuit_name}' is OPEN, rejecting request")
            if fallback:
                return fallback()
            raise CircuitOpenException(circuit_name, self._reset_timeout_seconds)

        try:
            result = await operation()
            circuit.record_success()
            await self._sync_to_redis(circuit)

            if circuit.state == CircuitState.CLOSED:
                logger.debug(f"Circuit '{circuit_name}' request succeeded")
            else:
                logger.info(f"Circuit '{circuit_name}' transitioning toward CLOSED after success")

            return result
        except Exception:
            circuit.record_failure()
            await self._sync_to_redis(circuit)

            if circuit.state == CircuitState.OPEN:
                logger.error(
                    f"Circuit '{circuit_name}' opened after {self._failure_threshold} failures"
                )
            else:
                logger.warning(
                    f"Circuit '{circuit_name}' recorded failure ({circuit.failure_count}/{self._failure_threshold})"
                )

            raise

    async def get_status(self, circuit_name: str) -> dict:
        circuit = self._get_or_create_circuit(circuit_name)
        await self._sync_from_redis(circuit)
        return circuit.to_dict()

    async def get_all_statuses(self) -> list[dict]:
        cursor = 0
        circuits = []
        while True:
            cursor, keys = await self._redis.scan(
                cursor, match=f"{self.REDIS_KEY_PREFIX}*", count=100
            )
            for key in keys:
                name = key.replace(self.REDIS_KEY_PREFIX, "")
                circuits.append(await self.get_status(name))
            if cursor == 0:
                break
        return circuits

    async def reset_circuit(self, circuit_name: str) -> None:
        if circuit_name in self._local_circuits:
            del self._local_circuits[circuit_name]
        key = f"{self.REDIS_KEY_PREFIX}{circuit_name}"
        await self._redis.delete(key)
        logger.info(f"Circuit '{circuit_name}' manually reset")
