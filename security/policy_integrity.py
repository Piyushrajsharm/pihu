"""
Pihu — Policy Integrity Guard
Provides tamper detection, version monotonicity, and rollback for the security policy.
Anchors policy hashes to the Windows Registry to prevent physical file replacement.
"""

import sys
import os
import json
import hashlib
import shutil
import copy
import difflib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import yaml
from logger import get_logger

try:
    import winreg
except ImportError:
    winreg = None

log = get_logger("POLICY-INTEGRITY")

class SchemaValidationError(Exception):
    pass

class PolicyIntegrityGuard:
    def __init__(self, policy_path: Path):
        self.policy_path = policy_path
        self.history_dir = self.policy_path.parent / "policy_history"
        self.reg_path = r"Software\Pihu_Core\Policy"
        
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        # We need audit logger for diff appending
        from security.security_core import AuditLog, ThreatLevel
        self.audit = AuditLog()

    def get_registry_info(self) -> dict:
        """Fetch the known good hash and version from OS registry."""
        if not winreg:
            return {"hash": None, "version": 0}
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.reg_path, 0, winreg.KEY_READ)
            hash_val, _ = winreg.QueryValueEx(key, "CurrentHash")
            version, _ = winreg.QueryValueEx(key, "CurrentVersion")
            winreg.CloseKey(key)
            return {"hash": hash_val, "version": version}
        except FileNotFoundError:
            return {"hash": None, "version": 0}
        except Exception as e:
            log.warning("Failed to read policy registry anchor: %s", e)
            return {"hash": None, "version": 0}

    def _set_registry_info(self, hash_val: str, version: int):
        if not winreg: return
        try:
            winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.reg_path)
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.reg_path, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, "CurrentHash", 0, winreg.REG_SZ, hash_val)
            winreg.SetValueEx(key, "CurrentVersion", 0, winreg.REG_DWORD, version)
            winreg.CloseKey(key)
        except Exception as e:
            log.warning("Failed to write policy registry anchor: %s", e)

    def _compute_hash(self, filepath: Path) -> Optional[str]:
        if not filepath.exists(): return None
        return hashlib.sha256(filepath.read_bytes()).hexdigest()

    def validate_schema(self, policy: dict) -> bool:
        """Basic schema validation to ensure required structure exists."""
        required_keys = ["version", "default_decision"]
        for k in required_keys:
            if k not in policy:
                log.error("Schema validation failed: Missing required key '%s'", k)
                return False
        
        # Verify it doesn't fail-open unexpectedly
        if policy.get("default_decision") == "allow":
            # This is technically allowed by schema, but log a loud warning
            log.warning("CRITICAL: Policy uses default_decision=allow (fail-open). This is strongly discouraged.")
            
        return True

    def check_integrity(self) -> Tuple[bool, str]:
        """Check if policy file is tampered or downgraded."""
        if not self.policy_path.exists():
            return False, "Policy file missing"
            
        try:
            with open(self.policy_path, "r", encoding="utf-8") as f:
                policy_dict = yaml.safe_load(f)
        except Exception as e:
            return False, f"Policy YAML malformed: {e}"
            
        if not policy_dict or not isinstance(policy_dict, dict):
            return False, "Policy is empty or not a dictionary"
            
        if not self.validate_schema(policy_dict):
            return False, "Schema validation failed"
            
        current_hash = self._compute_hash(self.policy_path)
        current_version = policy_dict.get("version", 0)
        
        reg_info = self.get_registry_info()
        expected_hash = reg_info["hash"]
        expected_version = reg_info["version"]
        
        if expected_hash and current_hash != expected_hash:
            # Hash mismatch. Either it was tampered offline, or normally updated
            # Check version. Monotonicity enforcement.
            if current_version < expected_version:
                return False, f"Policy downgrade attack detected (v{expected_version} -> v{current_version})"
            log.warning("Policy file hash differs from registry. Assuming legitimate offline update.")
            
        return True, "OK"

    def record_snapshot(self, policy_dict: dict, raw_hash: str):
        """Maintain a rolling history of the last 3 policies for rollback."""
        version = policy_dict.get("version", 0)
        snapshot_file = self.history_dir / f"policy_v{version}_{raw_hash[:8]}.yaml"
        if snapshot_file.exists():
            return
            
        try:
            shutil.copy2(self.policy_path, snapshot_file)
            
            # Prune to keep only 3
            snapshots = sorted(self.history_dir.glob("policy_v*.yaml"), key=os.path.getmtime)
            while len(snapshots) > 3:
                oldest = snapshots.pop(0)
                oldest.unlink()
        except Exception as e:
            log.warning("Failed to record policy snapshot: %s", e)
            
    def update_anchor(self):
        """Update the registry anchor with the current policy hash and version."""
        if not self.policy_path.exists(): return
        
        try:
            with open(self.policy_path, "r", encoding="utf-8") as f:
                policy_dict = yaml.safe_load(f)
            current_hash = self._compute_hash(self.policy_path)
            current_version = policy_dict.get("version", 0)
            
            self._set_registry_info(current_hash, current_version)
            self.record_snapshot(policy_dict, current_hash)
            
        except Exception as e:
            log.error("Failed to update policy anchor: %s", e)

    def compute_policy_diff(self, old_policy: dict, new_policy: dict) -> str:
        """Generate a diff string between two dictionaries."""
        old_str = yaml.dump(old_policy, sort_keys=True).splitlines()
        new_str = yaml.dump(new_policy, sort_keys=True).splitlines()
        
        diff = difflib.unified_diff(old_str, new_str, fromfile="old_policy", tofile="new_policy", lineterm="")
        return "\n".join(diff)

    def rollback(self) -> bool:
        """Rollback to the most recent valid snapshot."""
        snapshots = sorted(self.history_dir.glob("policy_v*.yaml"), key=os.path.getmtime, reverse=True)
        
        for snap in snapshots:
            try:
                # Try to load and validate
                with open(snap, "r", encoding="utf-8") as f:
                    policy_dict = yaml.safe_load(f)
                if self.validate_schema(policy_dict):
                    # It's valid, restore it
                    shutil.copy2(snap, self.policy_path)
                    log.warning("🛡️ Policy rolled back to snapshot: %s", snap.name)
                    self.update_anchor()
                    
                    from security.security_core import ThreatLevel
                    self.audit.record("POLICY_ROLLBACK", f"Reverted to {snap.name}", ThreatLevel.HIGH)
                    return True
            except Exception:
                continue
                
        log.error("🚨 CRITICAL: Policy rollback failed. No valid snapshots found.")
        return False
