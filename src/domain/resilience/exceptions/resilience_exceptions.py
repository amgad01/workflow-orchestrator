class ResilienceException(Exception):
    pass


class RateLimitExceededException(ResilienceException):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Rate limit exceeded. Retry after {retry_after_seconds} seconds.")


class CircuitOpenException(ResilienceException):
    def __init__(self, circuit_name: str, reset_timeout_seconds: int):
        self.circuit_name = circuit_name
        self.reset_timeout_seconds = reset_timeout_seconds
        super().__init__(
            f"Circuit '{circuit_name}' is OPEN. Service unavailable. "
            f"Retry after {reset_timeout_seconds} seconds."
        )
