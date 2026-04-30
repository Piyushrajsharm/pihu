"""
Tests for api/observability.py — Metrics, SLOs, and auto-instrumentation.
"""
import pytest
import os

os.environ["PIHU_ENV"] = "testing"

from api.observability import (
    error_budget, 
    record_request, 
    record_token_usage,
    record_chat_metrics,
    _HAS_PROMETHEUS
)


class TestErrorBudget:
    def test_initial_budget(self):
        eb = error_budget
        eb.total_requests = 0
        eb.error_requests = 0
        
        status = eb.get_status()
        assert status["budget_remaining"] == "100.0%"

    def test_budget_burning(self):
        eb = error_budget
        eb.total_requests = 100
        eb.error_requests = 20  # 20% error rate (target is < 1%)
        
        status = eb.get_status()
        assert status["budget_remaining"] == "0.0%"

    def test_record_updates_counters(self):
        eb = error_budget
        initial_total = eb.total_requests
        initial_errors = eb.error_requests
        
        eb.record(is_error=False)
        eb.record(is_error=True)
        
        assert eb.total_requests == initial_total + 2
        assert eb.error_requests == initial_errors + 1


class TestMetricsRecording:
    # We mainly test that these don't crash when called, 
    # as the underlying prometheus client handles the actual counting
    
    def test_record_request(self):
        # Should not raise
        record_request(
            endpoint="/api/v1/chat", 
            method="POST", 
            status=200, 
            tenant_id="t1", 
            duration=0.5
        )

    def test_record_token_usage(self):
        # Should not raise
        record_token_usage(tenant_id="t1", action_type="chat", tokens=150)

    def test_record_chat_metrics_success(self):
        # Should not raise
        record_chat_metrics(tenant_id="t1", status="success", latency=1.2, tokens=100)

    def test_record_chat_metrics_failure(self):
        # Should not raise
        record_chat_metrics(tenant_id="t1", status="error", latency=0.1, tokens=0)
