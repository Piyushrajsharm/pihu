"""
Pihu SaaS — Observability Matrix
SLO definitions, error budget tracking, trace correlation IDs,
per-endpoint latency histograms, and model cost tracking.
"""

import os
import uuid
import time
from contextlib import contextmanager
from datetime import datetime
from fastapi import Request, Response
from logger import get_logger

log = get_logger("OBSERVABILITY")

# ──────────────────────────────────────────
# OPTIONAL DEPENDENCY IMPORTS
# ──────────────────────────────────────────

# OpenTelemetry (optional)
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False
    log.warning("opentelemetry SDK not installed — tracing disabled")

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    _HAS_FASTAPI_INSTRUMENTOR = True
except ImportError:
    _HAS_FASTAPI_INSTRUMENTOR = False

# Prometheus (optional)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    _HAS_PROMETHEUS = True
except ImportError:
    _HAS_PROMETHEUS = False
    log.warning("prometheus_client not installed — metrics disabled")

    # No-op stubs so metric recording calls don't crash
    class _NoOpMetric:
        def labels(self, **kw): return self
        def inc(self, val=1): pass
        def observe(self, val): pass
        def set(self, val): pass

    def _noop_factory(*a, **kw): return _NoOpMetric()
    Counter = Histogram = Gauge = _noop_factory
    def generate_latest(): return b""
    CONTENT_TYPE_LATEST = "text/plain"


# ──────────────────────────────────────────
# OPENTELEMETRY SETUP
# ──────────────────────────────────────────

if _HAS_OTEL:
    provider = TracerProvider()
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer(__name__)
else:
    tracer = None


# ──────────────────────────────────────────
# SLO DEFINITIONS
# ──────────────────────────────────────────

SLOS = {
    "chat_latency_p95": {
        "target": 2.0,         # seconds
        "description": "95th percentile chat response latency",
        "window": "30d",
    },
    "prediction_latency_p95": {
        "target": 5.0,         # seconds
        "description": "95th percentile prediction latency",
        "window": "30d",
    },
    "availability": {
        "target": 0.995,       # 99.5% uptime
        "description": "API availability (non-5xx responses)",
        "window": "30d",
    },
    "error_rate": {
        "target": 0.01,        # < 1% error rate
        "description": "Percentage of requests resulting in 5xx",
        "window": "1h",
    },
}


# ──────────────────────────────────────────
# PROMETHEUS METRICS
# ──────────────────────────────────────────

# Per-endpoint request counts
REQUEST_COUNT = Counter(
    "pihu_requests_total",
    "Total requests by endpoint and status",
    ["endpoint", "method", "status", "tenant_id"]
)

# Per-endpoint latency histograms (p50, p90, p95, p99)
LATENCY_HISTOGRAM = Histogram(
    "pihu_request_duration_seconds",
    "Request duration in seconds per endpoint",
    ["endpoint", "tenant_id"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

# Token expenditure
TOKEN_USAGE = Counter(
    "pihu_tokens_consumed_total",
    "Total tokens consumed",
    ["tenant_id", "action_type"]
)

# Model inference cost (estimated USD)
MODEL_COST = Counter(
    "pihu_model_cost_usd_total",
    "Estimated model inference cost in USD",
    ["model", "tenant_id"]
)

# Celery queue backlog
QUEUE_BACKLOG = Gauge(
    "pihu_celery_queue_depth",
    "Number of pending tasks in Celery queue",
    ["queue_name"]
)

# Active connections
ACTIVE_CONNECTIONS = Gauge(
    "pihu_active_connections",
    "Number of active WebSocket/HTTP connections",
    ["connection_type"]
)

# Error budget burn rate
ERROR_BUDGET_REMAINING = Gauge(
    "pihu_error_budget_remaining_ratio",
    "Remaining error budget as a ratio (1.0 = full budget)",
    []
)

# Circuit breaker state
CIRCUIT_STATE = Gauge(
    "pihu_circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=half_open, 2=open)",
    ["circuit_name"]
)


# ──────────────────────────────────────────
# TRACE CORRELATION
# ──────────────────────────────────────────

def generate_trace_id() -> str:
    """Generate a unique trace ID for request correlation across services."""
    return f"trace-{uuid.uuid4().hex[:16]}"


def inject_trace_id(request: Request) -> str:
    """Extract or generate a trace ID from the incoming request."""
    trace_id = request.headers.get("X-Trace-ID")
    if not trace_id:
        trace_id = generate_trace_id()
    return trace_id


# ──────────────────────────────────────────
# ERROR BUDGET TRACKER
# ──────────────────────────────────────────

class ErrorBudgetTracker:
    """Tracks error budget consumption against SLO targets."""

    def __init__(self, target_availability: float = 0.995):
        self.target = target_availability
        self.total_requests = 0
        self.error_requests = 0
        self._window_start = time.time()
        self._window_size = 3600  # 1 hour rolling window

    def record(self, is_error: bool):
        """Record a request outcome."""
        self._maybe_reset_window()
        self.total_requests += 1
        if is_error:
            self.error_requests += 1
        self._update_gauge()

    def _maybe_reset_window(self):
        """Reset counters if the window has elapsed."""
        if time.time() - self._window_start > self._window_size:
            self.total_requests = 0
            self.error_requests = 0
            self._window_start = time.time()

    @property
    def current_error_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.error_requests / self.total_requests

    @property
    def budget_remaining(self) -> float:
        """How much of the error budget is left (1.0 = full, 0.0 = exhausted)."""
        allowed_error_rate = 1.0 - self.target
        if allowed_error_rate == 0:
            return 1.0 if self.error_requests == 0 else 0.0
        consumed = self.current_error_rate / allowed_error_rate
        return max(0.0, 1.0 - consumed)

    def _update_gauge(self):
        ERROR_BUDGET_REMAINING.labels().set(self.budget_remaining)

    def get_status(self) -> dict:
        return {
            "target_availability": f"{self.target * 100:.1f}%",
            "current_error_rate": f"{self.current_error_rate * 100:.2f}%",
            "budget_remaining": f"{self.budget_remaining * 100:.1f}%",
            "total_requests": self.total_requests,
            "error_requests": self.error_requests,
            "window": f"{self._window_size}s",
        }


error_budget = ErrorBudgetTracker()


# ──────────────────────────────────────────
# METRICS RECORDING HELPERS
# ──────────────────────────────────────────

def record_request(endpoint: str, method: str, status: int, tenant_id: str, duration: float):
    """Record complete request metrics."""
    REQUEST_COUNT.labels(
        endpoint=endpoint, method=method,
        status=str(status), tenant_id=tenant_id
    ).inc()
    LATENCY_HISTOGRAM.labels(endpoint=endpoint, tenant_id=tenant_id).observe(duration)
    error_budget.record(is_error=(status >= 500))


def record_token_usage(tenant_id: str, action_type: str, tokens: int):
    """Record token consumption."""
    TOKEN_USAGE.labels(tenant_id=tenant_id, action_type=action_type).inc(tokens)


def record_model_cost(model: str, tenant_id: str, estimated_usd: float):
    """Record estimated model inference cost."""
    MODEL_COST.labels(model=model, tenant_id=tenant_id).inc(estimated_usd)


def update_queue_backlog(queue_name: str, depth: int):
    """Update the Celery queue depth metric."""
    QUEUE_BACKLOG.labels(queue_name=queue_name).set(depth)


def update_circuit_state(circuit_name: str, state: str):
    """Update circuit breaker state metric."""
    state_map = {"closed": 0, "half_open": 1, "open": 2}
    CIRCUIT_STATE.labels(circuit_name=circuit_name).set(state_map.get(state, 0))


# ──────────────────────────────────────────
# INSTRUMENT APP
# ──────────────────────────────────────────

def instrument_app(app):
    """Integrate tracing, metrics, and SLO reporting into FastAPI."""
    if _HAS_FASTAPI_INSTRUMENTOR:
        FastAPIInstrumentor.instrument_app(app)
    else:
        log.warning("opentelemetry-instrumentation-fastapi not installed — skipping auto-instrumentation")

    @app.get("/metrics")
    def metrics():
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/api/v1/slos")
    def get_slos():
        return {
            "slo_definitions": SLOS,
            "error_budget": error_budget.get_status(),
        }


def record_chat_metrics(tenant_id: str, status: str, latency: float, tokens: int = 0):
    """Convenience wrapper used by app.py to record chat endpoint metrics."""
    status_code = 200 if status == "success" else 500
    record_request(
        endpoint="/api/v1/chat", method="POST",
        status=status_code, tenant_id=tenant_id, duration=latency
    )
    if tokens > 0:
        record_token_usage(tenant_id=tenant_id, action_type="chat", tokens=tokens)

