"""
Pihu — Plugin Trust Model
Verifies cryptographic signatures, manifest permissions, and revocations
before allowing any external plugin to load into the Engine.
"""
import json
import base64
import os
import zipfile
from pathlib import Path
from typing import Dict, Any, Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from logger import get_logger

log = get_logger("PLUGIN-TRUST")

class PluginTrustManager:
    def __init__(self, data_dir: str = ".pihu/data/security"):
        self.security_dir = Path(data_dir).absolute()
        self.security_dir.mkdir(parents=True, exist_ok=True)
        
        self.revocations_file = self.security_dir / "revoked_plugins.json"
        if not self.revocations_file.exists():
            self.revocations_file.write_text("[]")
            
        self.approvals_file = self.security_dir / "approved_plugins.json"
        if not self.approvals_file.exists():
            self.approvals_file.write_text("{}")
            
        # Pihu Official Plugins Public Key (Hardcoded for ring-0 security)
        # In a real deployment, this would be the actual Ed25519 public key in HEX
        # For this roadmap, we use a placeholder that will validate test signatures
        self.official_public_key_hex = "f" * 64
        
        # Mapping of plugin ID -> parsed Manifest rules
        self.active_plugins: Dict[str, dict] = {}
        
    def _is_revoked(self, plugin_id: str) -> bool:
        try:
            revoked = json.loads(self.revocations_file.read_text())
            return plugin_id in revoked
        except json.JSONDecodeError:
            log.error("Revocations file corrupted!")
            return True # Fail closed
            
    def _check_approval(self, plugin_id: str, manifest_hash: str) -> bool:
        try:
            approvals = json.loads(self.approvals_file.read_text())
            return approvals.get(plugin_id) == manifest_hash
        except json.JSONDecodeError:
            log.error("Approvals file corrupted!")
            return False

    def revoke_plugin(self, plugin_id: str):
        revoked = json.loads(self.revocations_file.read_text())
        if plugin_id not in revoked:
            revoked.append(plugin_id)
            self.revocations_file.write_text(json.dumps(revoked, indent=2))
            log.warning("Plugin %s permanently revoked.", plugin_id)

    def approve_plugin(self, plugin_id: str, manifest_hash: str):
        approvals = json.loads(self.approvals_file.read_text())
        approvals[plugin_id] = manifest_hash
        self.approvals_file.write_text(json.dumps(approvals, indent=2))
        log.info("Plugin %s approved by user.", plugin_id)

    def verify_signature(self, payload: bytes, signature_base64: str, public_key_hex: str) -> bool:
        """Verify an Ed25519 signature."""
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            sig_bytes = base64.b64decode(signature_base64)
            public_key.verify(sig_bytes, payload)
            return True
        except (ValueError, InvalidSignature, TypeError):
            return False
            
    def evaluate_plugin_archive(self, zip_path: Path, public_key_hex: str = None) -> Tuple[bool, str, dict]:
        """
        Evaluate a plugin ZIP archive file.
        Returns: (is_safe, reason, manifest_dict)
        """
        if not zip_path.exists():
            return False, "Plugin archive not found", {}
            
        pub_key = public_key_hex or self.official_public_key_hex
            
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if "manifest.json" not in zf.namelist():
                    return False, "Archive missing manifest.json", {}
                if "signature.sig" not in zf.namelist():
                    return False, "Archive missing signature.sig. Unsigned plugins are blocked.", {}
                    
                manifest_bytes = zf.read("manifest.json")
                signature_b64 = zf.read("signature.sig").decode("utf-8").strip()
                
                # Check signature
                if not self.verify_signature(manifest_bytes, signature_b64, pub_key):
                    return False, "Cryptographic signature validation failed. Archive tampered or untrusted source.", {}
                    
                manifest = json.loads(manifest_bytes)
        except Exception as e:
            return False, f"Failed to read archive: {e}", {}
            
        # Parse manifest rules
        required_fields = ["id", "version", "author", "permissions", "profile_mapping"]
        for f in required_fields:
            if f not in manifest:
                return False, f"Manifest missing required field: {f}", {}
                
        plugin_id = manifest["id"]
        
        # Check revocation
        if self._is_revoked(plugin_id):
            return False, f"Plugin '{plugin_id}' is securely revoked and cannot be loaded.", {}
            
        import hashlib
        m_hash = hashlib.sha256(manifest_bytes).hexdigest()
        
        # Check approval
        if not self._check_approval(plugin_id, m_hash):
            # Needs approval! The UI or CLI must prompt the user showing the permissions.
            return False, f"APPROVAL_REQUIRED: Plugin '{plugin_id}' (v{manifest['version']}) requires manual installation approval.", manifest
            
        return True, "OK", manifest

    def register_plugin_permissions(self, manifest: dict, policy_engine):
        """
        Validates the plugin's requested profile mapping against the global policy.
        """
        plugin_id = manifest["id"]
        mapping = manifest["profile_mapping"] # e.g. "plugin_sandbox" or "python_sandbox"
        requested_actions = manifest["permissions"] 
        
        # Read the existing profile from global policy
        profile = policy_engine.tool_profiles.get(mapping)
        if not profile:
            raise ValueError(f"Plugin '{plugin_id}' requested unknown profile '{mapping}'")
            
        # Ensure plugin isn't asking for actions that its profile doesn't allow
        profile_actions = profile.get("allowed_actions", [])
        for action in requested_actions:
            if action not in profile_actions and "*" not in profile_actions:
                raise ValueError(f"Plugin '{plugin_id}' requests permission '{action}' which is blocked by profile '{mapping}'")
                
        self.active_plugins[plugin_id] = manifest
        log.info("Trust validated and loaded for Plugin: %s", plugin_id)

    def is_plugin_action_allowed(self, plugin_id: str, action_name: str) -> bool:
        """Check if an active plugin is authorized to perform a specific action."""
        manifest = self.active_plugins.get(plugin_id)
        if not manifest:
            return False
            
        return action_name in manifest["permissions"]
