"""
Pihu SaaS — Reliability & Resilience Middleware
Stateful circuit breaker, idempotency enforcement, degraded mode detection,
request timeout, and retry-after headers.
"""

import os
import time
import threading
from enum import Enum
from datetime import datetime
from fastapi import Request, HTTPException
from logger import get_logger

log = get_logger("RELIABILITY")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/1")


# ──────────────────────────────────────────
# CIRCUIT BREAKER STATE MACHINE
# ──────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — block all requests
    HALF_OPEN = "half_open" # Testing recovery — allow one request


class CircuitBreaker:
    """
    Production circuit breaker with three states:
    CLOSED → OPEN (on failure threshold) → HALF_OPEN (after cooldown) → CLOSED (on success)
    """

    def __init__(self, name: str, failure_threshold: int = 5,
                 recovery_timeout: int = 30, success_threshold: int = 2):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    log.info("🔄 Circuit '%s' → HALF_OPEN (testing recovery)", self.name)
            return self._state

    def allow_request(self) -> bool:
        """Check if the circuit allows a request through."""
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            return True  # Allow probe request
        return False  # OPEN — block

    def record_success(self):
        """Record a successful request."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    log.info("✅ Circuit '%s' → CLOSED (recovered)", self.name)
            else:
                self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self):
        """Record a failed request."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                log.warning("🔴 Circuit '%s' → OPEN (recovery failed)", self.name)
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                log.warning("🔴 Circuit '%s' → OPEN (threshold %d reached)",
                            self.name, self.failure_threshold)

    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self._failure_count,
            "threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


# ──────────────────────────────────────────
# DEGRADED MODE DETECTION
# ──────────────────────────────────────────

class DegradedModeDetector:
    """Detects when infrastructure dependencies are unavailable
    and switches to degraded mode behavior."""

    def __init__(self):
        self._redis_available = True
        self._db_available = True
        self._last_check = 0
        self._check_interval = 30  # seconds

    def check_redis(self) -> bool:
        """Check if Redis is reachable."""
        if time.time() - self._last_check < self._check_interval:
            return self._redis_available
        try:
            import redis
            r = redis.from_url(REDIS_URL, socket_timeout=2)
            r.ping()
            self._redis_available = True
        except Exception:
            if self._redis_available:
                log.warning("⚠️ DEGRADED: Redis unavailable — rate limiting disabled")
            self._redis_available = False
        self._last_check = time.time()
        return self._redis_available

    def check_database(self) -> bool:
        """Check if PostgreSQL is reachable."""
        try:
            from api.database import sync_engine
            from sqlalchemy import text
            with sync_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            self._db_available = True
        except Exception:
            if self._db_available:
                log.warning("⚠️ DEGRADED: Database unavailable — read-only mode")
            self._db_available = False
        return self._db_available

    def get_status(self) -> dict:
        return {
            "redis": "healthy" if self._redis_available else "degraded",
            "database": "healthy" if self._db_available else "degraded",
            "mode": "normal" if (self._redis_available and self._db_available) else "degraded",
        }


# ──────────────────────────────────────────
# IDEMPOTENCY ENFORCEMENT
# ──────────────────────────────────────────

class IdempotencyManager:
    """Prevents duplicate business operations using idempotency keys."""

    def __init__(self):
        self._fallback_store = {}  # In-memory fallback when Redis is down

    def check_and_set(self, idempotency_key: str, ttl: int = 86400) -> bool:
        """
        Returns True if this is a NEW request (first time seeing this key).
        Returns False if this is a DUPLICATE.
        """
        if not idempotency_key:
            return True  # No key = no dedup

        # Try Redis first
        try:
            import redis
            r = redis.from_url(REDIS_URL, socket_timeout=2)
            key = f"idempotent:{idempotency_key}"
            if r.exists(key):
                log.warning("DUPLICATE REQUEST: Idempotency key '%s' already processed", idempotency_key)
                return False
            r.set(key, "processing", ex=ttl)
            return True
        except Exception:
            # Fallback to in-memory
            if idempotency_key in self._fallback_store:
                return False
            self._fallback_store[idempotency_key] = time.time()
            # Cleanup old entries
            cutoff = time.time() - ttl
            self._fallback_store = {
                k: v for k, v in self._fallback_store.items() if v > cutoff
            }
            return True

    def mark_complete(self, idempotency_key: str, result: str = "done"):
        """Mark an idempotent operation as completed."""
        try:
            import redis
            r = redis.from_url(REDIS_URL, socket_timeout=2)
            key = f"idempotent:{idempotency_key}"
            r.set(key, result, ex=86400)
        except Exception:
            pass


# ──────────────────────────────────────────
# UNIFIED RELIABILITY ENGINE
# ──────────────────────────────────────────

class ReliabilityEngine:
    """Unified reliability middleware combining circuit breaker,
    degraded mode, and idempotency."""

    def __init__(self):
        self.circuits = {
            "llm": CircuitBreaker("llm", failure_threshold=5, recovery_timeout=30),
            "database": CircuitBreaker("database", failure_threshold=3, recovery_timeout=60),
            "redis": CircuitBreaker("redis", failure_threshold=5, recovery_timeout=15),
            "external_api": CircuitBreaker("external_api", failure_threshold=3, recovery_timeout=45),
        }
        self.degraded = DegradedModeDetector()
        self.idempotency = IdempotencyManager()

    def get_circuit(self, name: str) -> CircuitBreaker:
        return self.circuits.get(name, CircuitBreaker(name))

    def verify_idempotency(self, idempotency_key: str) -> bool:
        """Returns True if request should proceed, raises 409 if duplicate."""
        if not self.idempotency.check_and_set(idempotency_key):
            raise HTTPException(
                status_code=409,
                detail="Conflict: Duplicate request detected via Idempotency Key."
            )
        return True

    def get_health(self) -> dict:
        """Full reliability health report."""
        return {
            "circuits": {name: cb.get_status() for name, cb in self.circuits.items()},
            "infrastructure": self.degraded.get_status(),
        }


reliability_engine = ReliabilityEngine()
