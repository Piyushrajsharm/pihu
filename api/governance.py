"""
Pihu SaaS — Governance Policy Engine
Per-tool permission scopes, allow/deny lists, policy versioning,
step-up approval thresholds, and blocked-action audit trail.
"""

import json
import os
from datetime import datetime
from typing import Optional
from fastapi import HTTPException
from logger import get_logger

log = get_logger("GOVERNANCE")

PIHU_ENV = os.getenv("PIHU_ENV", "development")

# ──────────────────────────────────────────
# DEFAULT POLICY TEMPLATE
# ──────────────────────────────────────────

DEFAULT_POLICY = {
    "version": 1,
    "max_session_budget": 20_000,
    "max_single_task_cost": 5_000,

    # Per-tool permission scopes: which roles can use which tools
    "tool_permissions": {
        "chat": ["member", "admin", "owner", "service"],
        "web_search": ["member", "admin", "owner"],
        "system_command": ["admin", "owner"],
        "code_execution": ["admin", "owner"],
        "vision": ["member", "admin", "owner"],
        "prediction": ["member", "admin", "owner"],
        "file_write": ["admin", "owner"],
        "browser_automation": ["admin", "owner"],
    },

    # Domain allowlist (empty = allow all)
    "allowed_domains": [],

    # Command deny list — always blocked regardless of role
    "denied_commands": [
        "rm -rf /", "format c:", "del /s /q", "mkfs", "shred",
        "drop database", "truncate table", "shutdown /s",
        "net user", "reg delete", "diskpart",
    ],

    # Step-up approval: actions above this cost require explicit confirmation
    "step_up_threshold": 2_000,

    # Rate limits per tool per hour
    "tool_rate_limits": {
        "system_command": 20,
        "code_execution": 30,
        "browser_automation": 10,
        "prediction": 50,
    },
}


# ──────────────────────────────────────────
# POLICY ENGINE
# ──────────────────────────────────────────

class GovernanceEngine:
    """Enforces execution budgets, per-tool RBAC, command filtering,
    and step-up approval with full audit trail."""

    def __init__(self):
        self.session_usage = {}         # tenant_id -> current tokens
        self.tool_usage = {}            # tenant_id:tool -> count this hour
        self.blocked_log = []           # Audit trail of blocked actions
        self._org_policies = {}         # org_id -> policy dict

    def get_policy(self, org_id: str) -> dict:
        """Get the active policy for an org, or return default."""
        return self._org_policies.get(org_id, DEFAULT_POLICY)

    def set_policy(self, org_id: str, policy: dict, updated_by: str) -> dict:
        """Update the policy for an organization. Returns versioned record."""
        current = self.get_policy(org_id)
        new_version = current.get("version", 0) + 1
        policy["version"] = new_version
        policy["updated_at"] = datetime.utcnow().isoformat()
        policy["updated_by"] = updated_by
        self._org_policies[org_id] = policy

        log.info("📋 Policy updated for org '%s' → v%d by %s", org_id, new_version, updated_by)
        return {"org_id": org_id, "version": new_version}

    # ──────────────────────────────────────────
    # BUDGET ENFORCEMENT
    # ──────────────────────────────────────────

    def check_execution_budget(self, tenant_id: str, estimated_cost: int, org_id: str = "default"):
        """Enforce per-session budget cap."""
        policy = self.get_policy(org_id)
        max_budget = policy.get("max_session_budget", 20_000)
        max_single = policy.get("max_single_task_cost", 5_000)

        # Single task cost check
        if estimated_cost > max_single:
            self._log_blocked(tenant_id, "budget_single_task",
                              f"Task cost {estimated_cost} exceeds single-task limit {max_single}")
            raise HTTPException(
                status_code=403,
                detail=f"Task cost ({estimated_cost}) exceeds single-task limit ({max_single})"
            )

        # Session budget check
        current = self.session_usage.get(tenant_id, 0)
        if current + estimated_cost > max_budget:
            self._log_blocked(tenant_id, "budget_session",
                              f"Session budget exhausted: {current}/{max_budget}")
            raise HTTPException(
                status_code=403,
                detail=f"Session budget exhausted ({current}/{max_budget} tokens)"
            )

        self.session_usage[tenant_id] = current + estimated_cost

    # ──────────────────────────────────────────
    # TOOL PERMISSION CHECK
    # ──────────────────────────────────────────

    def check_tool_permission(self, tool_name: str, role: str, org_id: str = "default"):
        """Verify the user's role has access to the requested tool."""
        policy = self.get_policy(org_id)
        tool_perms = policy.get("tool_permissions", {})

        allowed_roles = tool_perms.get(tool_name, ["member", "admin", "owner"])
        if role not in allowed_roles:
            self._log_blocked(
                f"role:{role}", "tool_access",
                f"Role '{role}' denied access to tool '{tool_name}'"
            )
            raise HTTPException(
                status_code=403,
                detail=f"Your role '{role}' does not have access to '{tool_name}'. "
                       f"Allowed: {allowed_roles}"
            )

    # ──────────────────────────────────────────
    # COMMAND DENY LIST
    # ──────────────────────────────────────────

    def check_command_safety(self, command: str, org_id: str = "default") -> dict:
        """Check command against deny list. Returns safety assessment."""
        policy = self.get_policy(org_id)
        denied = policy.get("denied_commands", [])
        step_up = policy.get("step_up_threshold", 2_000)

        cmd_lower = command.lower().strip()

        # Hard deny
        for pattern in denied:
            if pattern.lower() in cmd_lower:
                self._log_blocked(
                    "system", "command_denied",
                    f"Denied command '{command[:60]}' matched pattern '{pattern}'"
                )
                raise HTTPException(
                    status_code=403,
                    detail=f"Command blocked by governance policy: '{pattern}' is denied"
                )

        # Domain allowlist check
        allowed_domains = policy.get("allowed_domains", [])
        if allowed_domains and any(d in cmd_lower for d in ["http://", "https://"]):
            domain_allowed = any(d in cmd_lower for d in allowed_domains)
            if not domain_allowed:
                self._log_blocked("system", "domain_blocked",
                                  f"Domain not in allowlist for command: {command[:60]}")
                raise HTTPException(
                    status_code=403,
                    detail="Command references a domain not in the organization's allowlist"
                )

        return {"safe": True, "command": command[:60]}

    # ──────────────────────────────────────────
    # STEP-UP APPROVAL
    # ──────────────────────────────────────────

    def check_step_up(self, estimated_cost: int, org_id: str = "default") -> dict:
        """Check if an action requires step-up (explicit) approval."""
        policy = self.get_policy(org_id)
        threshold = policy.get("step_up_threshold", 2_000)

        if estimated_cost >= threshold:
            return {
                "requires_approval": True,
                "reason": f"Estimated cost ({estimated_cost}) exceeds step-up threshold ({threshold})",
                "threshold": threshold,
            }
        return {"requires_approval": False}

    # ──────────────────────────────────────────
    # TOOL RATE LIMITING
    # ──────────────────────────────────────────

    def check_tool_rate(self, tenant_id: str, tool_name: str, org_id: str = "default"):
        """Per-tool, per-tenant rate limiting."""
        policy = self.get_policy(org_id)
        limits = policy.get("tool_rate_limits", {})
        limit = limits.get(tool_name)

        if not limit:
            return  # No rate limit for this tool

        key = f"{tenant_id}:{tool_name}"
        count = self.tool_usage.get(key, 0)
        if count >= limit:
            self._log_blocked(tenant_id, "tool_rate_limit",
                              f"Rate limit for '{tool_name}': {count}/{limit} per hour")
            raise HTTPException(
                status_code=429,
                detail=f"Tool rate limit reached for '{tool_name}': {count}/{limit} per hour"
            )
        self.tool_usage[key] = count + 1

    # ──────────────────────────────────────────
    # FULL GOVERNANCE CHECK (Convenience)
    # ──────────────────────────────────────────

    def full_check(
        self, tenant_id: str, role: str, tool_name: str,
        command: str = "", estimated_cost: int = 0, org_id: str = "default"
    ) -> dict:
        """Run all governance checks in sequence. Returns assessment."""
        self.check_tool_permission(tool_name, role, org_id)
        self.check_tool_rate(tenant_id, tool_name, org_id)
        if command:
            self.check_command_safety(command, org_id)
        if estimated_cost > 0:
            self.check_execution_budget(tenant_id, estimated_cost, org_id)
        step_up = self.check_step_up(estimated_cost, org_id)

        return {
            "approved": True,
            "step_up_required": step_up.get("requires_approval", False),
            "tool": tool_name,
            "cost": estimated_cost,
        }

    # ──────────────────────────────────────────
    # BLOCKED ACTION AUDIT TRAIL
    # ──────────────────────────────────────────

    def _log_blocked(self, actor: str, reason_type: str, details: str):
        """Record every blocked action for compliance audit."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "actor": actor,
            "reason_type": reason_type,
            "details": details,
        }
        self.blocked_log.append(entry)
        log.warning("🚫 GOVERNANCE BLOCK: [%s] %s — %s", reason_type, actor, details)

        # Keep last 500 entries
        if len(self.blocked_log) > 500:
            self.blocked_log = self.blocked_log[-300:]

    def get_blocked_log(self, limit: int = 50) -> list:
        """Return recent blocked action entries."""
        return self.blocked_log[-limit:]

    def get_policy_summary(self, org_id: str = "default") -> dict:
        """Return a summary of the active policy for an org."""
        policy = self.get_policy(org_id)
        return {
            "org_id": org_id,
            "version": policy.get("version", 1),
            "max_session_budget": policy.get("max_session_budget"),
            "tools_restricted": list(policy.get("tool_permissions", {}).keys()),
            "denied_commands_count": len(policy.get("denied_commands", [])),
            "step_up_threshold": policy.get("step_up_threshold"),
            "tool_rate_limits": policy.get("tool_rate_limits", {}),
        }


governance_engine = GovernanceEngine()
