"""
Pihu — Deterministic Policy Engine v2
The core authorization layer. Evaluates every tool request against
versioned policy rules. The LLM can PROPOSE. It cannot AUTHORIZE.

Policy evaluation order:
  1. Action enabled check (scope_controls)
  2. Session trust level check
  3. Content trust origin check
  4. Rate limit check
  5. Directory allowlist enforcement
  6. Protected path enforcement (FilesystemGuard)
  7. Workspace boundary enforcement (FilesystemGuard)
  8. Command classification (CommandClassifier)
  9. Network policy (NetworkGuard)
  10. Resource budget enforcement
  11. Execution scope overrides (approval/sandbox/dry-run)
  12. Default decision

All decisions are logged to the audit trail.
"""

import os
import time
import uuid
import fnmatch
import yaml
from enum import Enum
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any

from logger import get_logger

log = get_logger("POLICY")


# ──────────────────────────────────────────────
# DATA TYPES
# ──────────────────────────────────────────────

class ActionType(Enum):
    """Classified action types for policy evaluation."""
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    DELETE_FILE = "delete_file"
    LIST_DIR = "list_dir"
    RUN_PYTHON = "run_python"
    SHELL_EXEC = "shell_exec"
    OPEN_BROWSER = "open_browser"
    CALL_API = "call_api"
    WEB_SEARCH = "web_search"
    VISION_CAPTURE = "vision_capture"
    MEMORY_WRITE = "memory_write"
    MEMORY_READ = "memory_read"
    PLUGIN_LOAD = "plugin_load"
    SYSTEM_INFO = "system_info"
    CHAT = "chat"
    PLUGIN_EXEC = "plugin_exec"


class Verdict(Enum):
    """Policy decision outcomes."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    REQUIRE_SANDBOX = "require_sandbox"
    REQUIRE_DRY_RUN = "require_dry_run"


class UserRole(Enum):
    """Semantic user roles for RBAC."""
    ADMIN = "admin"       # Full control, bypasses most limits
    SYSTEM = "system"     # Automated system processes
    USER = "user"         # Standard interacting user
    GUEST = "guest"       # read-only interaction

@dataclass
class Subject:
    """Who is making the request."""
    user_id: str = "pihu_user"
    role: UserRole = UserRole.SYSTEM
    trust_level: int = 1     # maps to session_trust.TrustLevel
    session_mode: str = "interactive"  # interactive, automated, batch


@dataclass
class Resource:
    """What is being accessed."""
    path: Optional[str] = None
    url: Optional[str] = None
    plugin_id: Optional[str] = None
    command: Optional[str] = None
    description: str = ""


@dataclass
class PolicyContext:
    """Contextual information for policy evaluation."""
    workspace_roots: list[str] = field(default_factory=list)
    is_offline: bool = False
    prior_denials: int = 0
    risk_score: float = 0.0
    request_chain_depth: int = 0     # nested tool calls
    correlation_id: str = ""


@dataclass
class PolicyRequest:
    """A complete policy evaluation request."""
    subject: Subject
    action: ActionType
    resource: Resource
    context: PolicyContext
    
    def __post_init__(self):
        if not self.context.correlation_id:
            self.context.correlation_id = str(uuid.uuid4())[:8]


@dataclass
class PolicyDecision:
    """The result of policy evaluation."""
    verdict: Verdict
    reason: str
    matched_rules: list[str]
    risk_score: float
    correlation_id: str
    requires_user_prompt: bool = False
    prompt_message: str = ""
    metadata: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# TRUST LEVEL REQUIREMENTS PER ACTION
# ──────────────────────────────────────────────

# Minimum trust level required for each action type
ACTION_TRUST_REQUIREMENTS = {
    ActionType.CHAT: 0,                # TrustLevel.OBSERVE
    ActionType.SYSTEM_INFO: 0,
    ActionType.MEMORY_READ: 1,         # TrustLevel.ASSIST
    ActionType.READ_FILE: 1,
    ActionType.LIST_DIR: 1,
    ActionType.WEB_SEARCH: 1,
    ActionType.MEMORY_WRITE: 2,        # TrustLevel.EDIT_WORKSPACE
    ActionType.WRITE_FILE: 2,
    ActionType.DELETE_FILE: 2,
    ActionType.RUN_PYTHON: 3,          # TrustLevel.EXECUTE_SANDBOXED
    ActionType.VISION_CAPTURE: 3,
    ActionType.SHELL_EXEC: 4,          # TrustLevel.HIGH_RISK
    ActionType.OPEN_BROWSER: 4,
    ActionType.CALL_API: 4,
    ActionType.PLUGIN_LOAD: 4,
}

# Maximum request chain depth (prevents infinite tool recursion)
MAX_CHAIN_DEPTH = 10

# Rate limits per action type (per minute)
DEFAULT_RATE_LIMITS = {
    ActionType.SHELL_EXEC: 10,
    ActionType.RUN_PYTHON: 20,
    ActionType.CALL_API: 30,
    ActionType.WRITE_FILE: 50,
    ActionType.DELETE_FILE: 10,
    ActionType.WEB_SEARCH: 20,
    ActionType.PLUGIN_LOAD: 5,
}


class PolicyEngine:
    """
    Deterministic policy evaluator (v2).
    
    Every request is evaluated against a chain of rules.
    First matching DENY wins. If no deny, first matching ALLOW wins.
    If nothing matches, the default decision applies.
    
    Reads scope_controls, directory_allowlists, tool_profiles,
    and network_policy from a versioned YAML policy file.
    """

    def __init__(self, policy_path: str = None):
        from config import DATA_DIR
        
        self.policy_path = Path(policy_path or DATA_DIR / "security" / "policy.yaml")
        
        # ── Phase A: Policy Integrity Enforcements ──
        from security.policy_integrity import PolicyIntegrityGuard
        self.integrity_guard = PolicyIntegrityGuard(self.policy_path)
        
        ok, reason = self.integrity_guard.check_integrity()
        if not ok:
            log.warning("🚨 Policy integrity check failed: %s", reason)
            log.info("Attempting policy rollback...")
            if not self.integrity_guard.rollback():
                log.error("Rollback failed! Falling back to safe hardcoded _default_policy()")
                self.policy = self._default_policy()
            else:
                self.policy = self._load_policy()
        else:
            self.policy = self._load_policy()
            self.integrity_guard.update_anchor() # Update anchor in case of legitimate offline edits
            
        self.policy_version = self.policy.get("version", 1)
        
        # Parse rich schema sections
        self.scope_controls: dict = self.policy.get("scope_controls", {})
        self.directory_allowlists: dict = self.policy.get("directory_allowlists", {})
        self.tool_profiles: dict = self.policy.get("tool_profiles", {})
        net_policy: dict = self.policy.get("network_policy", {})
        
        # Rate tracking
        self._action_timestamps: dict[str, list[float]] = {}  # action -> timestamps
        # Per-request tool call counter
        self._request_tool_counts: dict[str, int] = {}
        
        # Import guards
        from security.filesystem_guard import FilesystemGuard
        from security.command_classifier import CommandClassifier
        from security.network_guard import NetworkGuard, NetworkClass
        from security.session_trust import TrustLevel
        
        workspace_roots = self.policy.get("workspace_roots", [])
        protected_paths = self.policy.get("extra_protected_paths", [])
        
        self.fs_guard = FilesystemGuard(
            workspace_roots=workspace_roots,
            extra_protected=protected_paths,
        )
        self.cmd_classifier = CommandClassifier()
        
        # Network policy — prefer nested network_policy block, fall back to top-level keys
        allowed_domains = net_policy.get("allowed_domains",
                            self.policy.get("allowed_domains", [
                                "integrate.api.nvidia.com",
                                "serpapi.com",
                                "google.com",
                            ]))
        blocked_domains = net_policy.get("blocked_domains",
                            self.policy.get("blocked_domains", []))
        allow_localhost = net_policy.get("allow_localhost",
                            self.policy.get("allow_localhost", False))
        allow_private = net_policy.get("allow_private_network",
                          self.policy.get("allow_private_network", False))
        
        self.net_guard = NetworkGuard(
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
            default_class=NetworkClass.APPROVED_APIS_ONLY,
            allow_localhost=allow_localhost,
            allow_private_network=allow_private,
            max_download_bytes=net_policy.get("max_download_bytes", 50 * 1024 * 1024),
        )
        
        log.info("⚖️ PolicyEngine v%d initialized | schema=%s | workspace_roots=%d | "
                 "scope_controls=%d | tool_profiles=%d | policy_path=%s",
                 self.policy_version,
                 self.policy.get("schema_version", "1.0"),
                 len(workspace_roots),
                 len(self.scope_controls),
                 len(self.tool_profiles),
                 self.policy_path)

    def _load_policy(self) -> dict:
        """Load policy from YAML file, or create default."""
        if self.policy_path.exists():
            try:
                with open(self.policy_path, "r", encoding="utf-8") as f:
                    policy = yaml.safe_load(f) or {}
                log.info("📋 Policy loaded from %s (version %d)", 
                         self.policy_path.name, policy.get("version", 0))
                return policy
            except Exception as e:
                log.error("Failed to load policy file: %s. Using defaults.", e)
        
        # Create default policy
        default = self._default_policy()
        self._save_policy(default)
        return default

    def _save_policy(self, policy: dict):
        """Persist policy to YAML."""
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.policy_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(policy, f, default_flow_style=False, sort_keys=False)
            log.info("📋 Policy saved to %s", self.policy_path)
        except Exception as e:
            log.error("Failed to save policy: %s", e)

    @staticmethod
    def _default_policy() -> dict:
        """Generate the default secure-by-default policy."""
        return {
            "version": 1,
            "default_decision": "deny",
            "workspace_roots": [
                "d:/JarvisProject",
            ],
            "allowed_domains": [
                "integrate.api.nvidia.com",
                "serpapi.com",
            ],
            "blocked_domains": [],
            "allow_localhost": False,
            "allow_private_network": False,
            "extra_protected_paths": [],
            "max_chain_depth": MAX_CHAIN_DEPTH,
            "rate_limits": {
                "shell_exec": 10,
                "run_python": 20,
                "call_api": 30,
                "write_file": 50,
                "delete_file": 10,
            },
            "blocked_shell_metacharacters": True,
            "require_sandbox_for_python": True,
            "require_approval_for_delete": True,
            "require_approval_for_shell": True,
            "require_approval_for_network": True,
        }

    # ──────────────────────────────────────────────
    # DIRECTORY ALLOWLIST HELPERS
    # ──────────────────────────────────────────────

    def _get_scope_control(self, action: ActionType) -> dict:
        """Retrieve the scope_controls entry for an action type."""
        return self.scope_controls.get(action.value, {})

    def _check_directory_allowlist(self, path: str, operation: str) -> tuple[bool, str]:
        """
        Check if a normalized path is within the directory allowlist
        for the given operation (read, write, delete, execute).
        Returns (allowed, reason).
        """
        allowlist = self.directory_allowlists.get(operation, [])
        if not allowlist:
            return True, ""  # No allowlist → fall through to workspace check

        # Fix traversal vulnerability by fully resolving the path first
        try:
            resolved_path = str(Path(path).resolve())
        except Exception:
            resolved_path = path

        normalized = resolved_path.replace("\\", "/")
        if os.name == "nt":
            normalized = normalized.lower()

        for pattern in allowlist:
            norm_pattern = pattern.replace("\\", "/")
            if os.name == "nt":
                norm_pattern = norm_pattern.lower()
            if fnmatch.fnmatch(normalized, norm_pattern):
                return True, f"Path matches {operation} allowlist: '{pattern}'"

        return False, f"Path '{path}' is not in the {operation} directory allowlist"

    def _check_tool_profile_directory(self, path: str, profile: dict) -> tuple[bool, str]:
        """
        Check if a path is within a tool profile's allowed/blocked directories.
        Returns (allowed, reason).
        """
        try:
            resolved_path = str(Path(path).resolve())
        except Exception:
            resolved_path = path

        normalized = resolved_path.replace("\\", "/")
        if os.name == "nt":
            normalized = normalized.lower()

        # Check blocked directories first
        for pattern in profile.get("blocked_directories", []):
            norm_pattern = pattern.replace("\\", "/")
            if os.name == "nt":
                norm_pattern = norm_pattern.lower()
            if fnmatch.fnmatch(normalized, norm_pattern):
                return False, f"Path blocked by tool profile: '{pattern}'"

        # Check allowed directories
        allowed_dirs = profile.get("allowed_directories", [])
        if allowed_dirs:
            for pattern in allowed_dirs:
                norm_pattern = pattern.replace("\\", "/")
                if os.name == "nt":
                    norm_pattern = norm_pattern.lower()
                if fnmatch.fnmatch(normalized, norm_pattern):
                    return True, f"Path allowed by tool profile: '{pattern}'"
            return False, "Path not in tool profile's allowed_directories"

        return True, ""  # No restrictions in profile

    def _find_tool_profile(self, action: ActionType) -> Optional[dict]:
        """Find the most specific tool profile matching this action."""
        for profile_name, profile in self.tool_profiles.items():
            allowed_actions = profile.get("allowed_actions", [])
            if action.value in allowed_actions:
                return profile
        return None

    # ──────────────────────────────────────────────
    # MAIN EVALUATION
    # ──────────────────────────────────────────────

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        """
        Evaluate a policy request through the full rule chain.
        Returns a deterministic PolicyDecision.
        """
        matched_rules = []
        risk_score = request.context.risk_score
        cid = request.context.correlation_id
        scope = self._get_scope_control(request.action)
        
        # ── Rule 0: Action enabled check ──
        if scope and not scope.get("enabled", True):
            matched_rules.append("action_disabled")
            return PolicyDecision(
                verdict=Verdict.DENY,
                reason=f"Action '{request.action.value}' is disabled in policy",
                matched_rules=matched_rules,
                risk_score=1.0,
                correlation_id=cid,
            )
        # ── Rule 0.5: RBAC Role Binding Check ──
        role_bindings = self.policy.get("role_bindings", {})
        if role_bindings:
            role_str = request.subject.role.value
            role_allowed_actions = role_bindings.get(role_str, [])
            # Admin can do everything, or if '*' is in allowed actions
            if request.subject.role != UserRole.ADMIN and "*" not in role_allowed_actions:
                if request.action.value not in role_allowed_actions:
                    matched_rules.append("rbac_role_denied")
                    return PolicyDecision(
                        verdict=Verdict.DENY,
                        reason=f"RBAC Denied: Role '{role_str}' is not permitted to perform action '{request.action.value}'",
                        matched_rules=matched_rules,
                        risk_score=0.9,
                        correlation_id=cid,
                    )
        # ── Rule 1: Chain depth limit ──
        max_depth = self.policy.get("max_chain_depth", MAX_CHAIN_DEPTH)
        if request.context.request_chain_depth > max_depth:
            matched_rules.append("chain_depth_exceeded")
            return PolicyDecision(
                verdict=Verdict.DENY,
                reason=f"Request chain depth {request.context.request_chain_depth} exceeds maximum {max_depth}",
                matched_rules=matched_rules,
                risk_score=1.0,
                correlation_id=cid,
            )
        
        # ── Rule 2: Trust level check ──
        # Prefer scope_controls.min_trust_level over the hardcoded map
        if scope and "min_trust_level" in scope:
            required_trust = scope["min_trust_level"]
        else:
            required_trust = ACTION_TRUST_REQUIREMENTS.get(request.action, 4)
        
        if request.subject.trust_level < required_trust:
            matched_rules.append("insufficient_trust_level")
            from security.session_trust import TrustLevel, TRUST_DESCRIPTIONS
            required_name = TrustLevel(required_trust).name
            current_name = TrustLevel(request.subject.trust_level).name
            
            return PolicyDecision(
                verdict=Verdict.REQUIRE_APPROVAL,
                reason=f"Action '{request.action.value}' requires trust level {required_name}, "
                       f"current session is {current_name}",
                matched_rules=matched_rules,
                risk_score=0.5,
                correlation_id=cid,
                requires_user_prompt=True,
                prompt_message=f"Escalate to {required_name} to perform '{request.action.value}'?",
            )
        
        # ── Rule 3: Rate limit check ──
        # Prefer scope_controls.max_per_minute, fall back to policy rate_limits, then defaults
        rate_limit = None
        if scope and "max_per_minute" in scope:
            rate_limit = scope["max_per_minute"]
        else:
            policy_rates = self.policy.get("rate_limits", {})
            rate_limit = policy_rates.get(request.action.value,
                           DEFAULT_RATE_LIMITS.get(request.action))
        
        if rate_limit:
            rate_key = f"{request.subject.user_id}:{request.action.value}"
            if not self._check_rate(rate_key, rate_limit):
                matched_rules.append("rate_limited")
                return PolicyDecision(
                    verdict=Verdict.DENY,
                    reason=f"Rate limit exceeded for '{request.action.value}': max {rate_limit}/minute",
                    matched_rules=matched_rules,
                    risk_score=0.3,
                    correlation_id=cid,
                )
        
        # ── Rule 4: Directory allowlist enforcement ──
        if request.resource.path and request.action in (
            ActionType.READ_FILE, ActionType.WRITE_FILE, ActionType.DELETE_FILE,
            ActionType.LIST_DIR, ActionType.RUN_PYTHON,
        ):
            op_map = {
                ActionType.READ_FILE: "read",
                ActionType.LIST_DIR: "read",
                ActionType.WRITE_FILE: "write",
                ActionType.DELETE_FILE: "delete",
                ActionType.RUN_PYTHON: "execute",
            }
            dir_op = op_map.get(request.action, "read")
            allowed, reason = self._check_directory_allowlist(request.resource.path, dir_op)
            if not allowed:
                matched_rules.append("directory_allowlist_denied")
                return PolicyDecision(
                    verdict=Verdict.DENY,
                    reason=f"Directory allowlist denied: {reason}",
                    matched_rules=matched_rules,
                    risk_score=0.8,
                    correlation_id=cid,
                )
        
        # ── Rule 4.5: Tool profile directory check ──
        profile = self._find_tool_profile(request.action)
        if profile and request.resource.path:
            prof_allowed, prof_reason = self._check_tool_profile_directory(
                request.resource.path, profile
            )
            if not prof_allowed:
                matched_rules.append("tool_profile_directory_denied")
                return PolicyDecision(
                    verdict=Verdict.DENY,
                    reason=f"Tool profile denied: {prof_reason}",
                    matched_rules=matched_rules,
                    risk_score=0.8,
                    correlation_id=cid,
                )
        
        # ── Rule 5: Filesystem checks (FilesystemGuard) ──
        if request.resource.path and request.action in (
            ActionType.READ_FILE, ActionType.WRITE_FILE, ActionType.DELETE_FILE, ActionType.LIST_DIR
        ):
            from security.filesystem_guard import FileOperation
            
            op_map = {
                ActionType.READ_FILE: FileOperation.READ,
                ActionType.WRITE_FILE: FileOperation.MODIFY,
                ActionType.DELETE_FILE: FileOperation.DELETE,
                ActionType.LIST_DIR: FileOperation.LIST,
            }
            fs_op = op_map.get(request.action, FileOperation.READ)
            assessment = self.fs_guard.assess(request.resource.path, fs_op)
            
            if not assessment.allowed:
                matched_rules.append("filesystem_denied")
                return PolicyDecision(
                    verdict=Verdict.DENY,
                    reason=f"Filesystem guard denied: {'; '.join(assessment.reasons)}",
                    matched_rules=matched_rules,
                    risk_score=0.9,
                    correlation_id=cid,
                )
            
            if assessment.requires_approval:
                matched_rules.append("filesystem_requires_approval")
                return PolicyDecision(
                    verdict=Verdict.REQUIRE_APPROVAL,
                    reason=f"Filesystem operation requires approval: {'; '.join(assessment.reasons)}",
                    matched_rules=matched_rules,
                    risk_score=0.6,
                    correlation_id=cid,
                    requires_user_prompt=True,
                    prompt_message=f"Allow {request.action.value} on '{request.resource.path}'?",
                )
            
            risk_score += 0.1 if not assessment.is_in_workspace else 0.0
        
        # ── Rule 6: Command classification ──
        if request.resource.command and request.action in (ActionType.SHELL_EXEC,):
            cmd_assessment = self.cmd_classifier.classify(request.resource.command)
            
            if cmd_assessment.blocked:
                matched_rules.append("command_blocked")
                return PolicyDecision(
                    verdict=Verdict.DENY,
                    reason=f"Command blocked: {cmd_assessment.explanation}",
                    matched_rules=matched_rules,
                    risk_score=1.0,
                    correlation_id=cid,
                    metadata={"command_flags": cmd_assessment.flags},
                )
                
            has_metachars = any("METACHAR" in f for f in cmd_assessment.flags)
            if has_metachars and self.policy.get("blocked_shell_metacharacters", False):
                matched_rules.append("metacharacters_blocked")
                return PolicyDecision(
                    verdict=Verdict.DENY,
                    reason="Shell metacharacters (chaining, redirection, substitution) are blocked by policy.",
                    matched_rules=matched_rules,
                    risk_score=0.9,
                    correlation_id=cid,
                    metadata={"command_flags": cmd_assessment.flags},
                )
            
            if cmd_assessment.requires_approval:
                matched_rules.append("command_requires_approval")
                if self.policy.get("require_approval_for_shell", True):
                    return PolicyDecision(
                        verdict=Verdict.REQUIRE_APPROVAL,
                        reason=f"Shell command requires approval:\n{cmd_assessment.explanation}",
                        matched_rules=matched_rules,
                        risk_score=cmd_assessment.risk / 5.0,
                        correlation_id=cid,
                        requires_user_prompt=True,
                        prompt_message=(
                            f"Execute shell command?\n"
                            f"  Command: {cmd_assessment.original[:80]}\n"
                            f"  Risk: {cmd_assessment.risk_label}\n"
                            f"  Factors: {', '.join(cmd_assessment.flags[:3])}"
                        ),
                    )
            
            if cmd_assessment.requires_sandbox:
                matched_rules.append("command_sandbox")
                risk_score += cmd_assessment.risk / 5.0
        
        # ── Rule 7: Network policy ──
        if request.resource.url and request.action in (ActionType.CALL_API, ActionType.WEB_SEARCH, ActionType.OPEN_BROWSER):
            from security.network_guard import NetworkClass
            
            net_assessment = self.net_guard.assess(request.resource.url)
            
            if net_assessment.blocked:
                matched_rules.append("network_blocked")
                return PolicyDecision(
                    verdict=Verdict.DENY,
                    reason=f"Network access denied: {'; '.join(net_assessment.reasons)}",
                    matched_rules=matched_rules,
                    risk_score=0.8,
                    correlation_id=cid,
                )
            
            if net_assessment.requires_approval:
                matched_rules.append("network_requires_approval")
                return PolicyDecision(
                    verdict=Verdict.REQUIRE_APPROVAL,
                    reason=f"Network access requires approval: {'; '.join(net_assessment.reasons)}",
                    matched_rules=matched_rules,
                    risk_score=0.5,
                    correlation_id=cid,
                    requires_user_prompt=True,
                    prompt_message=f"Allow network access to '{net_assessment.domain}'?",
                )
        
        # ── Rule 8: Scope control overrides (sandbox / approval / dry-run) ──
        # These check the scope_controls section of the YAML
        if scope.get("require_sandbox", False):
            matched_rules.append("scope_sandbox_required")
            return PolicyDecision(
                verdict=Verdict.REQUIRE_SANDBOX,
                reason=f"Action '{request.action.value}' requires sandbox execution (scope_controls)",
                matched_rules=matched_rules,
                risk_score=risk_score + 0.3,
                correlation_id=cid,
            )
        
        if scope.get("require_dry_run", False):
            matched_rules.append("scope_dry_run_required")
            return PolicyDecision(
                verdict=Verdict.REQUIRE_DRY_RUN,
                reason=f"Action '{request.action.value}' requires dry-run (scope_controls)",
                matched_rules=matched_rules,
                risk_score=risk_score + 0.1,
                correlation_id=cid,
            )
        
        if scope.get("require_approval", False):
            matched_rules.append("scope_approval_required")
            return PolicyDecision(
                verdict=Verdict.REQUIRE_APPROVAL,
                reason=f"Action '{request.action.value}' requires approval (scope_controls)",
                matched_rules=matched_rules,
                risk_score=risk_score + 0.2,
                correlation_id=cid,
                requires_user_prompt=True,
                prompt_message=f"Allow '{request.action.value}' on '{request.resource.description}'?",
            )
        
        # ── Rule 9: Legacy hard gates (backward compat with v1 policy) ──
        if request.action == ActionType.RUN_PYTHON:
            if self.policy.get("require_sandbox_for_python", True):
                matched_rules.append("python_sandbox_required")
                return PolicyDecision(
                    verdict=Verdict.REQUIRE_SANDBOX,
                    reason="Python execution must run in Docker sandbox",
                    matched_rules=matched_rules,
                    risk_score=risk_score + 0.3,
                    correlation_id=cid,
                )
        
        if request.action == ActionType.DELETE_FILE:
            if self.policy.get("require_approval_for_delete", True):
                matched_rules.append("delete_requires_approval")
                return PolicyDecision(
                    verdict=Verdict.REQUIRE_APPROVAL,
                    reason="File deletion requires explicit approval",
                    matched_rules=matched_rules,
                    risk_score=risk_score + 0.4,
                    correlation_id=cid,
                    requires_user_prompt=True,
                    prompt_message=f"Delete file '{request.resource.path}'?",
                )
        
        # ── Rule 10: Auto-allow safe actions ──
        if scope.get("auto_allow", False):
            matched_rules.append("scope_auto_allow")
            return PolicyDecision(
                verdict=Verdict.ALLOW,
                reason=f"Action '{request.action.value}' auto-allowed by scope_controls",
                matched_rules=matched_rules,
                risk_score=risk_score,
                correlation_id=cid,
            )
        
        if request.action in (ActionType.CHAT, ActionType.SYSTEM_INFO, ActionType.MEMORY_READ):
            matched_rules.append("safe_action_default_allow")
            return PolicyDecision(
                verdict=Verdict.ALLOW,
                reason=f"Action '{request.action.value}' is safe by default",
                matched_rules=matched_rules,
                risk_score=risk_score,
                correlation_id=cid,
            )
        
        # ── Default decision from policy ──
        default = self.policy.get("default_decision", "deny")
        if default == "allow":
            matched_rules.append("default_allow")
            return PolicyDecision(
                verdict=Verdict.ALLOW,
                reason="No rule matched — default policy is ALLOW",
                matched_rules=matched_rules,
                risk_score=risk_score,
                correlation_id=cid,
            )
        
        # Default DENY
        matched_rules.append("default_deny")
        return PolicyDecision(
            verdict=Verdict.REQUIRE_APPROVAL,
            reason=f"No explicit rule matched for '{request.action.value}' — "
                   f"default policy requires approval",
            matched_rules=matched_rules,
            risk_score=risk_score + 0.2,
            correlation_id=cid,
            requires_user_prompt=True,
            prompt_message=f"Allow '{request.action.value}' on '{request.resource.description}'?",
        )

    def _check_rate(self, key: str, limit: int) -> bool:
        """Check if action is within rate limit (per minute)."""
        now = time.time()
        timestamps = self._action_timestamps.get(key, [])
        
        # Prune old entries
        timestamps = [t for t in timestamps if now - t < 60.0]
        
        if len(timestamps) >= limit:
            return False
        
        timestamps.append(now)
        self._action_timestamps[key] = timestamps
        return True

    def reload(self):
        """Hot-reload policy from YAML without restarting."""
        old_version = self.policy_version
        old_policy = self.policy
        
        ok, reason = self.integrity_guard.check_integrity()
        if not ok:
            log.error("🚨 Reload aborted. Policy integrity check failed: %s", reason)
            return
            
        self.policy = self._load_policy()
        
        # Policy diff audit
        diff = self.integrity_guard.compute_policy_diff(old_policy, self.policy)
        if diff:
            from security.security_core import ThreatLevel
            self.integrity_guard.audit.record(
                "POLICY_RELOAD", 
                f"Policy version v{old_version} -> v{self.policy.get('version', 1)}\nDiff:\n{diff}", 
                ThreatLevel.SAFE
            )
            
        self.integrity_guard.update_anchor()

        self.policy_version = self.policy.get("version", 1)
        self.scope_controls = self.policy.get("scope_controls", {})
        self.directory_allowlists = self.policy.get("directory_allowlists", {})
        self.tool_profiles = self.policy.get("tool_profiles", {})

        # Rebuild guards with new config
        net_policy = self.policy.get("network_policy", {})
        workspace_roots = self.policy.get("workspace_roots", [])
        protected_paths = self.policy.get("extra_protected_paths", [])

        from security.filesystem_guard import FilesystemGuard
        from security.network_guard import NetworkGuard, NetworkClass

        self.fs_guard = FilesystemGuard(
            workspace_roots=workspace_roots,
            extra_protected=protected_paths,
        )

        allowed_domains = net_policy.get("allowed_domains",
                            self.policy.get("allowed_domains", []))
        blocked_domains = net_policy.get("blocked_domains",
                            self.policy.get("blocked_domains", []))

        self.net_guard = NetworkGuard(
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
            default_class=NetworkClass.APPROVED_APIS_ONLY,
            allow_localhost=net_policy.get("allow_localhost", False),
            allow_private_network=net_policy.get("allow_private_network", False),
            max_download_bytes=net_policy.get("max_download_bytes", 50 * 1024 * 1024),
        )

        # Reset rate counters on reload
        self._action_timestamps.clear()

        log.info("🔄 Policy reloaded v%d → v%d | scope_controls=%d | tool_profiles=%d",
                 old_version, self.policy_version,
                 len(self.scope_controls), len(self.tool_profiles))

    def get_policy_summary(self) -> dict:
        """Return human-readable policy summary."""
        net_policy = self.policy.get("network_policy", {})
        return {
            "version": self.policy_version,
            "schema_version": self.policy.get("schema_version", "1.0"),
            "default_decision": self.policy.get("default_decision", "deny"),
            "workspace_roots": self.policy.get("workspace_roots", []),
            "allowed_domains": net_policy.get("allowed_domains",
                                self.policy.get("allowed_domains", [])),
            "scope_controls_count": len(self.scope_controls),
            "tool_profiles_count": len(self.tool_profiles),
            "directory_allowlists": {
                k: len(v) for k, v in self.directory_allowlists.items()
            },
            "sandbox_python": self.policy.get("require_sandbox_for_python", True),
            "approval_for_delete": self.policy.get("require_approval_for_delete", True),
            "approval_for_shell": self.policy.get("require_approval_for_shell", True),
            "max_chain_depth": self.policy.get("max_chain_depth", MAX_CHAIN_DEPTH),
        }
