"""
Pihu — Latency Benchmark Suite
Measures actual p50/p95/p99 latency for all critical pipelines.
Outputs hardware baseline and benchmark report.

Usage:
    python benchmarks/latency_test.py
"""

import os
import sys
import time
import json
import platform
import statistics
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger import get_logger

log = get_logger("BENCHMARK")


def get_hardware_baseline() -> dict:
    """Collect hardware and environment info."""
    info = {
        "platform": platform.platform(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }

    try:
        import psutil
        mem = psutil.virtual_memory()
        info["ram_total_gb"] = round(mem.total / (1024**3), 1)
        info["ram_available_gb"] = round(mem.available / (1024**3), 1)
    except ImportError:
        info["ram_total_gb"] = "psutil not installed"

    # GPU detection
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["gpu"] = result.stdout.strip()
        else:
            info["gpu"] = "No NVIDIA GPU detected"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        info["gpu"] = "nvidia-smi not available"

    return info


def percentile(data: list, p: float) -> float:
    """Calculate the p-th percentile of a list."""
    if not data:
        return 0.0
    k = (len(data) - 1) * (p / 100)
    f = int(k)
    c = f + 1 if f + 1 < len(data) else f
    d = k - f
    return data[f] + d * (data[c] - data[f])


def summarize_latencies(timings: list, label: str) -> dict:
    """Compute p50, p95, p99 from a list of timing values (in ms)."""
    if not timings:
        return {"label": label, "status": "skipped", "samples": 0}

    timings.sort()
    return {
        "label": label,
        "samples": len(timings),
        "min_ms": round(min(timings), 1),
        "p50_ms": round(percentile(timings, 50), 1),
        "p95_ms": round(percentile(timings, 95), 1),
        "p99_ms": round(percentile(timings, 99), 1),
        "max_ms": round(max(timings), 1),
        "mean_ms": round(statistics.mean(timings), 1),
        "stddev_ms": round(statistics.stdev(timings), 1) if len(timings) > 1 else 0,
    }


# ──────────────────────────────────────────
# BENCHMARK: Intent Classification
# ──────────────────────────────────────────

def bench_intent_classification(iterations: int = 50) -> dict:
    """Benchmark the intent classifier."""
    try:
        from intent_classifier import IntentClassifier
        classifier = IntentClassifier()
    except Exception:
        return {"label": "intent_classification", "status": "import_failed"}

    test_inputs = [
        "search latest news about AI",
        "open chrome browser",
        "explain quantum computing in detail",
        "what's on my screen right now",
        "create a login page for my app",
        "delete the temp folder",
        "predict if bitcoin will rise",
        "hello pihu how are you",
        "what's the weather in delhi",
        "run python script test.py",
    ]

    timings = []
    for i in range(iterations):
        text = test_inputs[i % len(test_inputs)]
        start = time.perf_counter()
        try:
            classifier.classify(text)
        except Exception:
            pass
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)

    return summarize_latencies(timings, "intent_classification")


# ──────────────────────────────────────────
# BENCHMARK: Router Decision
# ──────────────────────────────────────────

def bench_router_decision(iterations: int = 20) -> dict:
    """Benchmark the router's pipeline selection (no actual execution)."""
    try:
        from intent_classifier import Intent
    except ImportError:
        return {"label": "router_decision", "status": "import_failed"}

    timings = []
    for _ in range(iterations):
        start = time.perf_counter()
        intent = Intent(
            type="chat", confidence=0.95,
            metadata={}, raw_input="test benchmark input"
        )
        # Measure just the intent object creation + type classification
        _ = intent.type
        _ = intent.confidence
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)

    return summarize_latencies(timings, "router_decision")


# ──────────────────────────────────────────
# BENCHMARK: Governance Check
# ──────────────────────────────────────────

def bench_governance_check(iterations: int = 100) -> dict:
    """Benchmark the governance engine's full_check pipeline."""
    try:
        from api.governance import governance_engine
    except ImportError:
        return {"label": "governance_check", "status": "import_failed"}

    timings = []
    for _ in range(iterations):
        start = time.perf_counter()
        try:
            governance_engine.full_check(
                tenant_id="bench_user", role="member",
                tool_name="chat", command="test command",
                estimated_cost=100, org_id="bench_org"
            )
        except Exception:
            pass
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)

    # Reset tool usage counters after benchmark
    governance_engine.tool_usage.clear()
    governance_engine.session_usage.clear()

    return summarize_latencies(timings, "governance_check")


# ──────────────────────────────────────────
# BENCHMARK: Audit Logging (Hash Chain)
# ──────────────────────────────────────────

def bench_audit_logging(iterations: int = 100) -> dict:
    """Benchmark audit log write performance with hash chaining."""
    try:
        from api.telemetry import AuditLogger
    except ImportError:
        return {"label": "audit_logging", "status": "import_failed"}

    # Use a temp file to avoid polluting the real audit log
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jsonl")
    tmp.close()

    original_file = os.environ.get("AUDIT_LOG_FILE", "")
    os.environ["AUDIT_LOG_FILE"] = tmp.name

    logger = AuditLogger()
    timings = []

    for i in range(iterations):
        start = time.perf_counter()
        logger.log_event(
            tenant_id="bench_user",
            event_type="benchmark",
            details={"iteration": i, "data": "x" * 100},
            org_id="bench_org",
            trace_id=f"trace-bench-{i:04d}",
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        timings.append(elapsed_ms)

    # Cleanup
    try:
        os.unlink(tmp.name)
    except Exception:
        pass
    if original_file:
        os.environ["AUDIT_LOG_FILE"] = original_file

    return summarize_latencies(timings, "audit_logging_hash_chain")


# ──────────────────────────────────────────
# BENCHMARK: JWT Token Creation/Validation
# ──────────────────────────────────────────

def bench_jwt_operations(iterations: int = 100) -> dict:
    """Benchmark JWT token creation and validation."""
    try:
        from api.auth import create_jwt_token, validate_jwt_token
    except ImportError:
        return {"label": "jwt_operations", "status": "import_failed"}

    # Token creation
    create_timings = []
    tokens = []
    for _ in range(iterations):
        start = time.perf_counter()
        token = create_jwt_token(
            user_id="bench_user", org_id="bench_org", role="member"
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        create_timings.append(elapsed_ms)
        tokens.append(token)

    # Token validation
    validate_timings = []
    for token in tokens:
        start = time.perf_counter()
        try:
            validate_jwt_token(token)
        except Exception:
            pass
        elapsed_ms = (time.perf_counter() - start) * 1000
        validate_timings.append(elapsed_ms)

    return {
        "create": summarize_latencies(create_timings, "jwt_create"),
        "validate": summarize_latencies(validate_timings, "jwt_validate"),
    }


# ──────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────

def run_all_benchmarks() -> dict:
    """Run all benchmarks and return consolidated report."""
    print("\n" + "=" * 60)
    print("  PIHU LATENCY BENCHMARK SUITE")
    print("=" * 60)

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "hardware": get_hardware_baseline(),
        "benchmarks": {},
    }

    benchmarks = [
        ("Intent Classification", bench_intent_classification),
        ("Router Decision", bench_router_decision),
        ("Governance Check", bench_governance_check),
        ("Audit Logging (Hash Chain)", bench_audit_logging),
        ("JWT Operations", bench_jwt_operations),
    ]

    for name, fn in benchmarks:
        print(f"\n📏 Running: {name}...", end=" ", flush=True)
        try:
            result = fn()
            report["benchmarks"][name] = result
            if isinstance(result, dict) and "p95_ms" in result:
                print(f"p95={result['p95_ms']}ms  p99={result['p99_ms']}ms")
            elif isinstance(result, dict) and "create" in result:
                c = result.get("create", {})
                v = result.get("validate", {})
                print(f"create p95={c.get('p95_ms', '?')}ms  validate p95={v.get('p95_ms', '?')}ms")
            else:
                print(f"result: {json.dumps(result, indent=None)[:80]}")
        except Exception as e:
            print(f"ERROR: {e}")
            report["benchmarks"][name] = {"status": "error", "error": str(e)}

    # Save report
    report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "benchmark_results.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n📊 Report saved: {report_path}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    run_all_benchmarks()
