"""
Pihu — Session Trust Manager
Manages session trust levels — the LLM never decides permissions.

Trust levels control what operations are allowed without explicit user approval.
Sessions start at ASSIST by default and require explicit escalation.
"""

import time
from enum import IntEnum
from dataclasses import dataclass
from typing import Optional

from logger import get_logger

log = get_logger("TRUST")


class TrustLevel(IntEnum):
    """Session trust levels — higher = more dangerous capabilities unlocked."""
    OBSERVE = 0          # Read-only, no tool execution
    ASSIST = 1           # Chat + safe reads inside workspace
    EDIT_WORKSPACE = 2   # File writes in workspace
    EXECUTE_SANDBOXED = 3  # Code execution in Docker sandbox
    HIGH_RISK = 4        # Shell, network, system modifications


# Human-readable descriptions for the CLI approval prompt
TRUST_DESCRIPTIONS = {
    TrustLevel.OBSERVE: "👁️  OBSERVE — Read-only mode, no tool execution",
    TrustLevel.ASSIST: "💬 ASSIST — Chat + safe file reads in workspace",
    TrustLevel.EDIT_WORKSPACE: "✏️  EDIT — File writes allowed in workspace",
    TrustLevel.EXECUTE_SANDBOXED: "🐳 EXECUTE — Code execution in Docker sandbox",
    TrustLevel.HIGH_RISK: "⚠️  HIGH-RISK — Shell, network, system modifications",
}


@dataclass
class SessionState:
    """Current session security state."""
    trust_level: TrustLevel
    escalated_at: Optional[float]  # timestamp of last escalation
    inactivity_timeout_s: float
    last_activity: float
    escalation_count: int
    user_id: str


class SessionTrustManager:
    """Manages session trust levels with escalation, timeout, and consent."""

    def __init__(
        self,
        default_level: TrustLevel = TrustLevel.ASSIST,
        inactivity_timeout_s: float = 900.0,  # 15 minutes
        user_id: str = "pihu_user",
    ):
        self.state = SessionState(
            trust_level=default_level,
            escalated_at=None,
            inactivity_timeout_s=inactivity_timeout_s,
            last_activity=time.time(),
            escalation_count=0,
            user_id=user_id,
        )
        
        log.info("🔒 SessionTrust initialized | level=%s | timeout=%ds",
                 self.state.trust_level.name, int(inactivity_timeout_s))

    @property
    def current_level(self) -> TrustLevel:
        """Get current trust level, checking for timeout first."""
        self._check_timeout()
        return self.state.trust_level

    def touch(self):
        """Record activity to reset inactivity timer."""
        self.state.last_activity = time.time()

    def _check_timeout(self):
        """If inactivity exceeded, drop back to ASSIST."""
        if self.state.trust_level > TrustLevel.ASSIST:
            elapsed = time.time() - self.state.last_activity
            if elapsed > self.state.inactivity_timeout_s:
                old_level = self.state.trust_level
                self.state.trust_level = TrustLevel.ASSIST
                self.state.escalated_at = None
                log.warning("⏰ Trust level dropped %s → ASSIST (inactivity timeout: %.0fs)",
                            old_level.name, elapsed)

    def can_perform(self, required_level: TrustLevel) -> bool:
        """Check if current session trust level allows the operation."""
        self._check_timeout()
        return self.state.trust_level >= required_level

    def escalate(self, target_level: TrustLevel) -> bool:
        """
        Escalate session trust level.
        
        In a real deployment, this would prompt the user for confirmation.
        Here we record the escalation for the ToolBroker to use.
        
        Returns True if escalation is accepted.
        """
        if target_level <= self.state.trust_level:
            return True  # Already at or above target
        
        self.state.trust_level = target_level
        self.state.escalated_at = time.time()
        self.state.last_activity = time.time()
        self.state.escalation_count += 1
        
        log.info("⬆️ Trust escalated to %s (escalation #%d)",
                 target_level.name, self.state.escalation_count)
        return True

    def deescalate(self, target_level: TrustLevel = TrustLevel.ASSIST):
        """Drop trust level back down."""
        old = self.state.trust_level
        self.state.trust_level = target_level
        self.state.escalated_at = None
        log.info("⬇️ Trust de-escalated %s → %s", old.name, target_level.name)

    def request_escalation_prompt(self, required_level: TrustLevel) -> str:
        """Generate a human-readable escalation prompt for CLI display."""
        current_desc = TRUST_DESCRIPTIONS.get(self.state.trust_level, "Unknown")
        target_desc = TRUST_DESCRIPTIONS.get(required_level, "Unknown")
        
        return (
            f"\n{'='*60}\n"
            f"🔐 TRUST ESCALATION REQUIRED\n"
            f"{'='*60}\n"
            f"Current: {current_desc}\n"
            f"Required: {target_desc}\n"
            f"\nThis action requires elevated permissions.\n"
            f"Do you want to escalate? (y/n): "
        )

    def get_status(self) -> dict:
        """Return current session trust state."""
        self._check_timeout()
        return {
            "trust_level": self.state.trust_level.name,
            "trust_value": int(self.state.trust_level),
            "escalated_at": self.state.escalated_at,
            "inactivity_timeout_s": self.state.inactivity_timeout_s,
            "seconds_since_activity": time.time() - self.state.last_activity,
            "escalation_count": self.state.escalation_count,
            "user_id": self.state.user_id,
        }
