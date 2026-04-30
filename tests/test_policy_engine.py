"""
Pihu — PolicyEngine v2 Test Suite
Validates the full policy evaluation chain against the production policy.yaml.

Tests cover:
  - Policy loading and versioning
  - Scope controls (enabled/disabled, auto_allow)
  - Trust level enforcement
  - Rate limiting
  - Directory allowlist scoping (read/write/delete/execute)
  - Tool profile directory enforcement
  - Filesystem guard integration
  - Command classification
  - Network policy
  - Execution scope overrides (sandbox/approval/dry-run)
  - Default deny behavior
  - Hot-reload
"""

import sys
import os
import pytest

# Ensure pihu root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from security.policy_engine import (
    PolicyEngine, PolicyRequest, Subject, Resource, PolicyContext,
    ActionType, Verdict,
)


# ──────────────────────────────────────────────
# FIXTURES
# ──────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    """Load the production PolicyEngine once for the entire test module."""
    return PolicyEngine()


def _make_request(
    action: ActionType,
    trust: int = 4,
    path: str = None,
    url: str = None,
    command: str = None,
    description: str = "",
    chain_depth: int = 0,
) -> PolicyRequest:
    """Helper to build a PolicyRequest with defaults."""
    return PolicyRequest(
        subject=Subject(user_id="test_user", trust_level=trust),
        action=action,
        resource=Resource(
            path=path,
            url=url,
            command=command,
            description=description or action.value,
        ),
        context=PolicyContext(
            request_chain_depth=chain_depth,
        ),
    )


# ──────────────────────────────────────────────
# 1. POLICY LOADING
# ──────────────────────────────────────────────

class TestPolicyLoading:
    def test_policy_version(self, engine):
        assert engine.policy_version == 2

    def test_schema_version(self, engine):
        assert engine.policy.get("schema_version") == "2.0"

    def test_default_decision_is_deny(self, engine):
        assert engine.policy.get("default_decision") == "deny"

    def test_scope_controls_loaded(self, engine):
        assert len(engine.scope_controls) > 0
        assert "chat" in engine.scope_controls
        assert "shell_exec" in engine.scope_controls

    def test_tool_profiles_loaded(self, engine):
        assert len(engine.tool_profiles) > 0
        assert "file_reader" in engine.tool_profiles
        assert "python_sandbox" in engine.tool_profiles

    def test_directory_allowlists_loaded(self, engine):
        assert "read" in engine.directory_allowlists
        assert "write" in engine.directory_allowlists
        assert "delete" in engine.directory_allowlists
        assert "execute" in engine.directory_allowlists

    def test_policy_summary(self, engine):
        summary = engine.get_policy_summary()
        assert summary["version"] == 2
        assert summary["schema_version"] == "2.0"
        assert summary["default_decision"] == "deny"
        assert summary["scope_controls_count"] > 0
        assert summary["tool_profiles_count"] > 0


# ──────────────────────────────────────────────
# 2. SAFE ACTION AUTO-ALLOW
# ──────────────────────────────────────────────

class TestSafeActions:
    def test_chat_auto_allowed(self, engine):
        req = _make_request(ActionType.CHAT, trust=0)
        decision = engine.evaluate(req)
        assert decision.verdict in (Verdict.ALLOW,)

    def test_system_info_auto_allowed(self, engine):
        req = _make_request(ActionType.SYSTEM_INFO, trust=0)
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.ALLOW

    def test_memory_read_auto_allowed(self, engine):
        req = _make_request(ActionType.MEMORY_READ, trust=1)
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.ALLOW


# ──────────────────────────────────────────────
# 3. TRUST LEVEL ENFORCEMENT
# ──────────────────────────────────────────────

class TestTrustLevels:
    def test_shell_exec_requires_trust_4(self, engine):
        req = _make_request(ActionType.SHELL_EXEC, trust=1, command="echo hi")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.REQUIRE_APPROVAL
        assert "insufficient_trust_level" in decision.matched_rules

    def test_write_file_requires_trust_2(self, engine):
        req = _make_request(
            ActionType.WRITE_FILE, trust=1,
            path="d:/JarvisProject/pihu/outputs/test.txt"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.REQUIRE_APPROVAL
        assert "insufficient_trust_level" in decision.matched_rules

    def test_shell_exec_passes_with_trust_4(self, engine):
        """Should not be blocked by trust level when trust=4."""
        req = _make_request(ActionType.SHELL_EXEC, trust=4, command="echo hello")
        decision = engine.evaluate(req)
        # Even with trust=4, shell_exec may require approval via other rules
        assert "insufficient_trust_level" not in decision.matched_rules


# ──────────────────────────────────────────────
# 4. CHAIN DEPTH LIMIT
# ──────────────────────────────────────────────

class TestChainDepth:
    def test_chain_depth_exceeded(self, engine):
        max_depth = engine.policy.get("max_chain_depth", 10)
        req = _make_request(ActionType.CHAT, trust=4, chain_depth=max_depth + 1)
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "chain_depth_exceeded" in decision.matched_rules

    def test_chain_depth_within_limit(self, engine):
        req = _make_request(ActionType.CHAT, trust=0, chain_depth=5)
        decision = engine.evaluate(req)
        assert decision.verdict != Verdict.DENY or "chain_depth_exceeded" not in decision.matched_rules


# ──────────────────────────────────────────────
# 5. DIRECTORY ALLOWLIST
# ──────────────────────────────────────────────

class TestDirectoryAllowlist:
    def test_read_inside_workspace_allowed(self, engine):
        req = _make_request(
            ActionType.READ_FILE, trust=4,
            path="d:/JarvisProject/pihu/config.py"
        )
        decision = engine.evaluate(req)
        assert decision.verdict != Verdict.DENY or "directory_allowlist_denied" not in decision.matched_rules

    def test_write_outside_allowlist_denied(self, engine):
        """Writing to a path outside the write allowlist should be denied."""
        req = _make_request(
            ActionType.WRITE_FILE, trust=4,
            path="c:/Windows/System32/evil.txt"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY

    def test_write_inside_outputs_allowed(self, engine):
        """Writing to outputs/ should pass the directory allowlist check."""
        req = _make_request(
            ActionType.WRITE_FILE, trust=4,
            path="d:/JarvisProject/pihu/outputs/result.txt"
        )
        decision = engine.evaluate(req)
        # Should not be denied by directory allowlist
        assert "directory_allowlist_denied" not in decision.matched_rules

    def test_delete_outside_allowlist_denied(self, engine):
        """Deleting outside the delete allowlist should be denied."""
        req = _make_request(
            ActionType.DELETE_FILE, trust=4,
            path="d:/JarvisProject/pihu/config.py"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY


# ──────────────────────────────────────────────
# 6. TOOL PROFILE DIRECTORY ENFORCEMENT
# ──────────────────────────────────────────────

class TestToolProfiles:
    def test_file_reader_blocked_vault(self, engine):
        """file_reader profile blocks reads from vault/."""
        req = _make_request(
            ActionType.READ_FILE, trust=4,
            path="d:/JarvisProject/pihu/data/vault/secrets.enc"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "tool_profile_directory_denied" in decision.matched_rules

    def test_file_writer_blocked_security(self, engine):
        """file_writer profile blocks writes to security/."""
        req = _make_request(
            ActionType.WRITE_FILE, trust=4,
            path="d:/JarvisProject/pihu/data/security/policy.yaml"
        )
        decision = engine.evaluate(req)
        # Should be denied by either directory allowlist or tool profile
        assert decision.verdict == Verdict.DENY


# ──────────────────────────────────────────────
# 7. SCOPE CONTROL OVERRIDES
# ──────────────────────────────────────────────

class TestScopeControls:
    def test_run_python_requires_sandbox(self, engine):
        req = _make_request(ActionType.RUN_PYTHON, trust=3)
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.REQUIRE_SANDBOX

    def test_shell_exec_requires_approval(self, engine):
        """shell_exec has require_approval=true in scope_controls."""
        req = _make_request(ActionType.SHELL_EXEC, trust=4, command="echo test")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.REQUIRE_APPROVAL

    def test_delete_requires_approval(self, engine):
        req = _make_request(
            ActionType.DELETE_FILE, trust=4,
            path="d:/JarvisProject/pihu/outputs/temp.txt"
        )
        decision = engine.evaluate(req)
        assert decision.verdict in (Verdict.REQUIRE_APPROVAL, Verdict.DENY)


# ──────────────────────────────────────────────
# 8. COMMAND CLASSIFICATION
# ──────────────────────────────────────────────

class TestCommandClassification:
    def test_destructive_command_blocked(self, engine):
        req = _make_request(
            ActionType.SHELL_EXEC, trust=4,
            command="rm -rf /"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "command_blocked" in decision.matched_rules

    def test_safe_command_not_blocked(self, engine):
        req = _make_request(
            ActionType.SHELL_EXEC, trust=4,
            command="echo hello world"
        )
        decision = engine.evaluate(req)
        assert "command_blocked" not in decision.matched_rules


# ──────────────────────────────────────────────
# 9. NETWORK POLICY
# ──────────────────────────────────────────────

class TestNetworkPolicy:
    def test_approved_domain_allowed(self, engine):
        req = _make_request(
            ActionType.CALL_API, trust=4,
            url="https://integrate.api.nvidia.com/v1/chat"
        )
        decision = engine.evaluate(req)
        assert "network_blocked" not in decision.matched_rules

    def test_blocked_domain_denied(self, engine):
        req = _make_request(
            ActionType.CALL_API, trust=4,
            url="https://pastebin.com/raw/abc123"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "network_blocked" in decision.matched_rules

    def test_unknown_domain_blocked(self, engine):
        """Unknown domains should be blocked under APPROVED_APIS_ONLY."""
        req = _make_request(
            ActionType.CALL_API, trust=4,
            url="https://evil-c2-server.com/exfiltrate"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY


# ──────────────────────────────────────────────
# 10. DEFAULT DENY
# ──────────────────────────────────────────────

class TestDefaultDeny:
    def test_unknown_action_gets_approval_required(self, engine):
        """Plugin loading with trust=4 should require approval."""
        req = _make_request(ActionType.PLUGIN_LOAD, trust=4)
        decision = engine.evaluate(req)
        assert decision.verdict in (Verdict.REQUIRE_APPROVAL, Verdict.DENY)


# ──────────────────────────────────────────────
# 11. HOT RELOAD
# ──────────────────────────────────────────────

class TestReload:
    def test_reload_preserves_version(self, engine):
        engine.reload()
        assert engine.policy_version == 2
        assert len(engine.scope_controls) > 0
        assert len(engine.tool_profiles) > 0

    def test_reload_clears_rate_limits(self, engine):
        # Pollute rate tracking
        engine._action_timestamps["test:fake"] = [1.0, 2.0, 3.0]
        engine.reload()
        assert "test:fake" not in engine._action_timestamps


# ──────────────────────────────────────────────
# 12. FILESYSTEM GUARD INTEGRATION
# ──────────────────────────────────────────────

class TestFilesystemGuard:
    def test_protected_path_write_denied(self, engine):
        """Writing to a protected path (security/) should be denied."""
        req = _make_request(
            ActionType.WRITE_FILE, trust=4,
            path="d:/JarvisProject/pihu/security/policy_engine.py"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY

    def test_windows_system_path_denied(self, engine):
        req = _make_request(
            ActionType.WRITE_FILE, trust=4,
            path="C:/Windows/System32/test.dll"
        )
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY

# ──────────────────────────────────────────────
# 13. RBAC ROLE BINDING ENFORCEMENT
# ──────────────────────────────────────────────

class TestRBAC:
    def test_admin_bypasses_rbac_restrictions(self, engine):
        # Inject custom RBAC policy
        engine.policy["role_bindings"] = {
            "guest": ["read_file", "chat"],
            "user": ["read_file", "write_file", "chat", "web_search"]
        }
        
        req = _make_request(ActionType.DELETE_FILE)
        from security.policy_engine import UserRole
        req.subject.role = UserRole.ADMIN
        
        decision = engine.evaluate(req)
        assert "rbac_role_denied" not in decision.matched_rules
        
    def test_guest_blocked_from_unauthorized_action(self, engine):
        engine.policy["role_bindings"] = {
            "guest": ["read_file", "chat"]
        }
        
        req = _make_request(ActionType.DELETE_FILE)
        from security.policy_engine import UserRole
        req.subject.role = UserRole.GUEST
        
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "rbac_role_denied" in decision.matched_rules


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
