"""
Pihu — OpenClaw Universal Orchestrator (Security-Hardened)
The command hub that routes ANY user intent to the right sub-system.
ALL commands pass through SecurityManager (threat assessment, rate limiting, audit).

Architecture:
    User Command → SecurityManager (assess) → Route → Execute → Audit
"""

import time
from logger import get_logger
from security.security_core import SecurityManager, ThreatLevel

log = get_logger("OPENCLAW")


class OpenClawBridge:
    """Security-hardened universal command orchestrator."""

    def __init__(self, swarm_agent=None, automation=None, groq_llm=None):
        self.swarm = swarm_agent
        self.automation = automation
        self.groq = groq_llm

        # Initialize Security Manager
        self.security = SecurityManager()

        status = self.security.get_status()
        log.info("🔧 OpenClaw Orchestrator initialized | Security=ACTIVE | Vault=%d secrets | Audit=%d entries",
                 status["vault_secrets"], status["audit_entries"])

    def execute(self, command: str, dry_run: bool = False) -> str:
        """Execute any command through the secured OpenClaw pipeline.

        Pipeline:
            1. Threat Assessment (block critical commands)
            2. Rate Limiting (prevent automation abuse)
            3. Route to correct sub-system
            4. Execute with vision verification
            5. Audit trail recording
        """
        t0 = time.time()
        log.info("🔧 OpenClaw received: %s", command[:80])

        # ─── SECURITY GATE ───
        can_exec, reason = self.security.can_execute(command)
        if not can_exec:
            log.warning("🚫 BLOCKED by security: %s", reason)
            return f"🛡️ Security blocked this command: {reason}"

        threat = self.security.assess_command(command)

        # High-risk confirmation warning
        if threat.requires_confirmation and not threat.blocked:
            log.warning("⚠️ HIGH RISK command detected: %s", threat.risks)

        # ─── ROUTE & EXECUTE ───
        try:
            result = self._route_command(command, dry_run=dry_run)

            # ─── AUDIT ───
            elapsed = time.time() - t0
            self.security.record_action(
                action="EXECUTE",
                command=command,
                threat_level=threat.level,
                result=f"OK ({elapsed:.1f}s)",
            )

            return result

        except Exception as e:
            self.security.record_action(
                action="ERROR",
                command=command,
                threat_level=threat.level,
                result=f"FAILED: {str(e)[:100]}",
            )
            log.error("OpenClaw execution failed: %s", e)
            return f"❌ Execution failed: {e}"

    def _route_command(self, command: str, dry_run: bool = False) -> str:
        """Determines the correct sub-system for execution."""
        cmd_lower = command.lower()

        # 1. Browser specific
        if any(kw in cmd_lower for kw in ["browser", "website", "google", "search online"]):
            if self.swarm: return self.swarm.perform_task(command, dry_run=dry_run)
            return "Swarm agent offline — browser task aborted."

        # 2. Prediction specific
        if any(kw in cmd_lower for kw in ["predict", "forecast", "simulation"]):
            if self.swarm: return self.swarm.perform_task(command, dry_run=dry_run)
            return "Swarm agent offline — prediction task aborted."

        # 3. Automation / OS Commands (Agentic)
        if self.swarm:
            return self.swarm.perform_task(command, dry_run=dry_run)
        elif self.automation:
            return self.automation.execute_natural(command)
        else:
            return f"❌ No execution engine available"

    def emergency_stop(self) -> str:
        """KILL SWITCH — stop all automation immediately."""
        self.security.emergency_stop("User triggered emergency stop")
        return "🚨 EMERGENCY STOP — All automation halted!"

    def resume(self) -> str:
        """Resume automation after emergency stop."""
        self.security.resume()
        return "✅ Automation resumed"

    def get_status(self) -> dict:
        """Get full system status."""
        status = self.security.get_status()
        status.update({
            "openclaw": "✅ Active",
            "swarm": "✅" if self.swarm else "❌",
            "automation": "✅" if self.automation else "❌",
            "godmode": "✅" if self.swarm and self.swarm.godmode else "❌",
            "mirofish": "✅" if self.swarm and self.swarm.mirofish else "❌",
            "groq": "✅" if self.groq and self.groq.is_available else "❌",
        })
        return status

    def audit_report(self, last_n: int = 10) -> str:
        """Get recent audit trail entries."""
        from pathlib import Path
        from config import LOGS_DIR
        log_file = Path(LOGS_DIR) / "audit_trail.jsonl"
        if not log_file.exists():
            return "No audit entries yet"

        import json
        lines = log_file.read_text().strip().split("\n")
        recent = lines[-last_n:]

        report = "📜 Audit Trail (last %d):\n" % len(recent)
        for line in recent:
            entry = json.loads(line)
            report += f"  [{entry['threat_level']}] {entry['timestamp'][:19]} | {entry['action']}: {entry['command'][:40]}\n"

        chain_ok, count = self.security.audit.verify_chain()
        report += f"\n🔗 Chain integrity: {'✅ VALID' if chain_ok else '🚨 BROKEN'} ({count} entries)"
        return report
