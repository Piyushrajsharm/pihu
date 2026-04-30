"""
Pihu SaaS — Telemetry & Audit Trail
Hash-chained, tamper-evident audit logging with trace correlation.
Designed for compliance-aligned auditing (SOC 2 Type II alignment).

Note: This provides the cryptographic structure for tamper-evident logs.
Full SOC 2 certification requires external audit, policy documentation,
and continuous monitoring — which are organizational processes, not code.
"""

import os
import json
import hashlib
from datetime import datetime
from typing import Optional
from logger import get_logger

log = get_logger("AUDIT_TRAIL")

PIHU_ENV = os.getenv("PIHU_ENV", "development")
AUDIT_LOG_FILE = os.getenv(
    "AUDIT_LOG_FILE",
    os.path.join(os.path.dirname(__file__), "..", "data", "audit_chain.jsonl")
)
os.makedirs(os.path.dirname(os.path.abspath(AUDIT_LOG_FILE)), exist_ok=True)


class AuditLogger:
    """
    Tamper-evident audit logger using hash chaining.
    Each entry includes a SHA-256 hash of the previous entry,
    forming an append-only integrity chain. If any entry is modified
    or deleted, the chain breaks — detectable by verify_chain().
    """

    def __init__(self):
        self._prev_hash = self._load_last_hash()
        self._entry_count = 0

    def _load_last_hash(self) -> str:
        """Load the hash of the last entry from the log file on startup."""
        try:
            if os.path.exists(AUDIT_LOG_FILE):
                with open(AUDIT_LOG_FILE, "r") as f:
                    lines = f.readlines()
                    if lines:
                        last = json.loads(lines[-1].strip())
                        return last.get("entry_hash", "genesis")
        except Exception as e:
            log.warning("Could not load previous audit hash: %s", e)
        return "genesis"

    def log_event(
        self, tenant_id: str, event_type: str, details: dict,
        org_id: str = None, trace_id: str = None
    ) -> dict:
        """
        Append a tamper-evident audit entry to the log.
        Each entry is hash-chained to its predecessor.
        """
        timestamp = datetime.utcnow().isoformat() + "Z"

        record = {
            "timestamp": timestamp,
            "tenant_id": tenant_id,
            "org_id": org_id or "unknown",
            "event_type": event_type,
            "details": details,
            "trace_id": trace_id,
            "prev_hash": self._prev_hash,
            "sequence": self._entry_count,
        }

        # Compute hash of this entry (includes prev_hash for chaining)
        hash_input = json.dumps(record, sort_keys=True, default=str)
        entry_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        record["entry_hash"] = entry_hash

        # Write to log file
        try:
            with open(AUDIT_LOG_FILE, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
            self._prev_hash = entry_hash
            self._entry_count += 1
        except Exception as e:
            log.error("Failed to write audit entry: %s", e)

        return record

    def verify_chain(self, max_entries: int = 10000) -> dict:
        """
        Verify the integrity of the audit log hash chain.
        Returns a verification report indicating whether the chain is intact.
        """
        if not os.path.exists(AUDIT_LOG_FILE):
            return {"status": "empty", "message": "No audit log found"}

        try:
            with open(AUDIT_LOG_FILE, "r") as f:
                lines = f.readlines()

            if not lines:
                return {"status": "empty", "entries": 0}

            entries_checked = 0
            prev_hash = "genesis"
            broken_at = None

            for i, line in enumerate(lines[:max_entries]):
                try:
                    entry = json.loads(line.strip())
                except json.JSONDecodeError:
                    return {
                        "status": "corrupted",
                        "message": f"Malformed JSON at line {i + 1}",
                        "entries_checked": entries_checked,
                    }

                # Verify chain link
                if entry.get("prev_hash") != prev_hash:
                    broken_at = i + 1
                    break

                # Recompute hash
                stored_hash = entry.pop("entry_hash", None)
                recomputed_input = json.dumps(entry, sort_keys=True, default=str)
                recomputed_hash = hashlib.sha256(recomputed_input.encode()).hexdigest()

                if stored_hash != recomputed_hash:
                    broken_at = i + 1
                    break

                prev_hash = stored_hash
                entries_checked += 1

            if broken_at:
                return {
                    "status": "broken",
                    "message": f"Hash chain integrity violation at entry {broken_at}",
                    "entries_checked": entries_checked,
                    "total_entries": len(lines),
                }

            return {
                "status": "intact",
                "entries_checked": entries_checked,
                "total_entries": len(lines),
                "last_hash": prev_hash,
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_recent_entries(self, limit: int = 50, tenant_id: str = None) -> list:
        """Retrieve recent audit entries, optionally filtered by tenant."""
        entries = []
        try:
            if os.path.exists(AUDIT_LOG_FILE):
                with open(AUDIT_LOG_FILE, "r") as f:
                    lines = f.readlines()
                for line in reversed(lines):
                    try:
                        entry = json.loads(line.strip())
                        if tenant_id and entry.get("tenant_id") != tenant_id:
                            continue
                        entries.append(entry)
                        if len(entries) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            log.error("Failed to read audit entries: %s", e)
        return entries

    def get_chain_summary(self) -> dict:
        """Return a summary of the audit log for monitoring."""
        try:
            if not os.path.exists(AUDIT_LOG_FILE):
                return {"total_entries": 0, "file": AUDIT_LOG_FILE}

            with open(AUDIT_LOG_FILE, "r") as f:
                lines = f.readlines()

            if not lines:
                return {"total_entries": 0, "file": AUDIT_LOG_FILE}

            first = json.loads(lines[0].strip())
            last = json.loads(lines[-1].strip())

            return {
                "total_entries": len(lines),
                "first_entry": first.get("timestamp"),
                "last_entry": last.get("timestamp"),
                "last_hash": last.get("entry_hash", "unknown"),
                "file": AUDIT_LOG_FILE,
            }
        except Exception as e:
            return {"error": str(e)}


# ──────────────────────────────────────────
# CONVENIENCE EVENT HELPERS
# ──────────────────────────────────────────

audit_logger = AuditLogger()


def audit_auth_event(tenant_id: str, action: str, success: bool, details: dict = None):
    """Log an authentication event."""
    audit_logger.log_event(
        tenant_id=tenant_id,
        event_type=f"auth.{action}",
        details={"success": success, **(details or {})},
    )


def audit_execution_event(tenant_id: str, tool: str, command: str, org_id: str = None, trace_id: str = None):
    """Log a tool/command execution event."""
    audit_logger.log_event(
        tenant_id=tenant_id,
        org_id=org_id,
        event_type="execution",
        details={"tool": tool, "command": command[:200]},
        trace_id=trace_id,
    )


def audit_governance_event(tenant_id: str, action: str, result: str, details: dict = None):
    """Log a governance decision (approved or blocked)."""
    audit_logger.log_event(
        tenant_id=tenant_id,
        event_type=f"governance.{result}",
        details={"action": action, **(details or {})},
    )
