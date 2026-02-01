import asyncio
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Implements the Circuit Breaker pattern to prevent cascading failures.
    
    This component monitors the health of external calls and "trips" (opens) the circuit
    when failures exceed a threshold. This allows the system to fail fast and preventing
    resource exhaustion during outages.
    
    State Machine:
    - CLOSED: Normal operation. Execution allowed.
    - OPEN: Fails immediately. Active during the recovery timeout.
    - HALF_OPEN: Probation period. Allows one trial call to check connectivity.
    """
    def __init__(
        self, 
        failure_threshold: int = 5, 
        recovery_timeout: int = 30,
        expected_exception: type[Exception] = Exception
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitState.CLOSED
        self._lock = asyncio.Lock()

    async def call(self, func, *args, **kwargs):
        """
        Executes a function with circuit protection.
        
        Logic:
        1. Checks Circuit state (Fail Fast if OPEN).
        2. Executes the function.
        3. Success -> Resets failure count (CLOSED).
        4. Failure -> Increments count, potentially tripping the circuit (OPEN).
        
        Thread Safety: uses asyncio.Lock to ensure atomic state transitions.
        """
        async with self._lock:
            await self._before_call()
            
        if self.state == CircuitState.OPEN:
            raise Exception("Circuit is OPEN")

        try:
            result = await func(*args, **kwargs)
            async with self._lock:
                self._on_success()
            return result
        except self.expected_exception as e:
            async with self._lock:
                self._on_failure()
            raise e

    async def _before_call(self):
        if self.state == CircuitState.OPEN:
            if self.last_failure_time and (time.time() - self.last_failure_time) > self.recovery_timeout:
                logger.info("Circuit Breaker moving to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
            else:
                return

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit Breaker moving to CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            logger.warning(f"Circuit Breaker moving to OPEN (failures: {self.failure_count})")
            self.state = CircuitState.OPEN
