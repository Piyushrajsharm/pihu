"""
Tests for api/telemetry.py — Audit logger, hash chaining, tamper evidence.
"""
import pytest
import os
import json
import tempfile

os.environ["PIHU_ENV"] = "testing"

from api.telemetry import AuditLogger


@pytest.fixture
def temp_audit_file():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    yield path
    os.remove(path)


@pytest.fixture
def audit_logger(monkeypatch, temp_audit_file):
    monkeypatch.setattr("api.telemetry.AUDIT_LOG_FILE", temp_audit_file)
    return AuditLogger()


class TestAuditLogger:
    def test_initialization(self, audit_logger):
        assert audit_logger._entry_count == 0
        assert audit_logger._prev_hash == "genesis"

    def test_log_event_creates_entry(self, audit_logger, temp_audit_file):
        record = audit_logger.log_event(
            tenant_id="t1", event_type="test_event", details={"foo": "bar"}
        )
        assert record["tenant_id"] == "t1"
        assert record["event_type"] == "test_event"
        assert record["sequence"] == 0
        assert "entry_hash" in record
        assert "timestamp" in record

        # Verify it was written to file
        with open(temp_audit_file, "r") as f:
            lines = f.readlines()
            assert len(lines) == 1
            written_record = json.loads(lines[0])
            assert written_record["entry_hash"] == record["entry_hash"]

    def test_hash_chaining(self, audit_logger):
        r1 = audit_logger.log_event("t1", "e1", {})
        r2 = audit_logger.log_event("t1", "e2", {})
        r3 = audit_logger.log_event("t1", "e3", {})

        assert r2["prev_hash"] == r1["entry_hash"]
        assert r3["prev_hash"] == r2["entry_hash"]
        assert audit_logger._prev_hash == r3["entry_hash"]
        assert audit_logger._entry_count == 3

    def test_verify_chain_intact(self, audit_logger):
        audit_logger.log_event("t1", "e1", {})
        audit_logger.log_event("t1", "e2", {})
        
        verification = audit_logger.verify_chain()
        assert verification["status"] == "intact"
        assert verification["entries_checked"] == 2

    def test_verify_chain_detects_tampering(self, audit_logger, temp_audit_file):
        audit_logger.log_event("t1", "e1", {})
        audit_logger.log_event("t1", "e2", {"sensitive": "data"})
        audit_logger.log_event("t1", "e3", {})

        # Tamper with the file (modify the second event)
        with open(temp_audit_file, "r") as f:
            lines = f.readlines()
        
        tampered_entry = json.loads(lines[1])
        tampered_entry["details"]["sensitive"] = "tampered"
        lines[1] = json.dumps(tampered_entry) + "\n"

        with open(temp_audit_file, "w") as f:
            f.writelines(lines)

        verification = audit_logger.verify_chain()
        assert verification["status"] == "broken"
        # It should break at entry 2 because the recomputed hash won't match stored hash
        assert "violation at entry 2" in verification["message"]

    def test_get_recent_entries(self, audit_logger):
        audit_logger.log_event("t1", "e1", {})
        audit_logger.log_event("t2", "e2", {})
        audit_logger.log_event("t1", "e3", {})

        entries = audit_logger.get_recent_entries(limit=10)
        assert len(entries) == 3
        # Should be in reverse chronological order
        assert entries[0]["event_type"] == "e3"
        assert entries[2]["event_type"] == "e1"

        # Filter by tenant
        t1_entries = audit_logger.get_recent_entries(tenant_id="t1")
        assert len(t1_entries) == 2
        assert all(e["tenant_id"] == "t1" for e in t1_entries)

    def test_get_chain_summary(self, audit_logger):
        audit_logger.log_event("t1", "e1", {})
        audit_logger.log_event("t1", "e2", {})
        
        summary = audit_logger.get_chain_summary()
        assert summary["total_entries"] == 2
        assert "first_entry" in summary
        assert "last_entry" in summary
        assert "last_hash" in summary
