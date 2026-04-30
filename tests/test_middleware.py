"""
Tests for api/middleware.py — Circuit breaker, idempotency, degraded mode.
"""
import pytest
import os

os.environ["PIHU_ENV"] = "testing"

from api.middleware import CircuitBreaker, ReliabilityEngine


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker("test_service", failure_threshold=3, recovery_timeout=5)
        assert cb.state.value == "closed"

    def test_transitions_to_open_after_threshold(self):
        cb = CircuitBreaker("test_svc", failure_threshold=3, recovery_timeout=5)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state.value == "open"

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test_svc", failure_threshold=3, recovery_timeout=0, success_threshold=1)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        # Evaluate state to trigger transition to half_open since timeout is 0
        assert cb.state.value == "half_open"
        cb.record_success()
        assert cb._failure_count == 0
        assert cb.state.value == "closed"

    def test_open_circuit_blocks_requests(self):
        cb = CircuitBreaker("test_svc", failure_threshold=2, recovery_timeout=60)
        cb.record_failure()
        cb.record_failure()
        assert cb.state.value == "open"
        assert cb.allow_request() is False

    def test_closed_circuit_allows_requests(self):
        cb = CircuitBreaker("test_svc", failure_threshold=5, recovery_timeout=5)
        assert cb.allow_request() is True


class TestIdempotency:
    def test_none_key_passes(self):
        engine = ReliabilityEngine()
        engine.verify_idempotency(None)  # Should not raise

    def test_new_key_passes(self):
        engine = ReliabilityEngine()
        engine.verify_idempotency("unique-key-12345")  # Should not raise

    def test_duplicate_key_raises(self):
        from fastapi import HTTPException
        engine = ReliabilityEngine()
        engine.verify_idempotency("dup-key-1")
        with pytest.raises(HTTPException) as exc_info:
            engine.verify_idempotency("dup-key-1")
        assert exc_info.value.status_code == 409


class TestReliabilityEngine:
    def test_get_health_returns_dict(self):
        engine = ReliabilityEngine()
        status = engine.get_health()
        assert isinstance(status, dict)
        assert "circuits" in status
        assert "infrastructure" in status

    def test_circuit_breakers_exist_for_services(self):
        engine = ReliabilityEngine()
        assert "llm" in engine.circuits
        assert "database" in engine.circuits
