
from src.domain.resilience.entities.circuit_breaker import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    def test_circuit_breaker_starts_closed(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.can_execute() is True

    def test_circuit_opens_after_threshold_failures(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_execute() is False

    def test_success_resets_failure_count_in_closed_state(self):
        cb = CircuitBreaker(name="test", failure_threshold=3)
        
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2
        
        cb.record_success()
        assert cb.failure_count == 0

    def test_circuit_transitions_to_half_open_after_timeout(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, reset_timeout_seconds=0)
        
        # Open the circuit
        for _ in range(3):
            cb.record_failure()
        
        assert cb.state == CircuitState.OPEN
        
        # With 0 timeout, should immediately transition to HALF_OPEN
        assert cb.can_execute() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_circuit_closes_on_successful_half_open_requests(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, reset_timeout_seconds=0)
        
        for _ in range(3):
            cb.record_failure()
        
        # Transition to HALF_OPEN
        cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN
        
        # Two successes should close
        cb.record_success()
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_circuit_reopens_on_half_open_failure(self):
        cb = CircuitBreaker(name="test", failure_threshold=3, reset_timeout_seconds=0)
        
        for _ in range(3):
            cb.record_failure()
        
        cb.can_execute()
        assert cb.state == CircuitState.HALF_OPEN
        
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_to_dict_serialization(self):
        cb = CircuitBreaker(name="test_circuit", failure_threshold=5, reset_timeout_seconds=60)
        cb.record_failure()
        
        data = cb.to_dict()
        
        assert data["name"] == "test_circuit"
        assert data["state"] == "CLOSED"
        assert data["failure_count"] == 1
        assert data["failure_threshold"] == 5
        assert data["reset_timeout_seconds"] == 60
