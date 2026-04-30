"""
Pihu — Phase D & E Trust Model Tests
Tests cryptographic verification of plugins and system updates.
"""
import sys
import os
import json
import pytest
import zipfile
import base64
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from security.plugin_trust import PluginTrustManager
from security.update_trust import UpdateTrustManager

@pytest.fixture(scope="module")
def trust_env(tmp_path_factory):
    """Setup an environment with a valid Ed25519 keypair for signing test artifacts."""
    env_dir = tmp_path_factory.mktemp("pihu_trust_env")
    
    # Generate Ed25519 keypair
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Hex encode public key for manager configuration
    pub_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    ).hex()

    def sign_payload(payload: bytes) -> str:
        sig = private_key.sign(payload)
        return base64.b64encode(sig).decode("utf-8")
        
    return {
        "dir": env_dir,
        "pub_hex": pub_hex,
        "sign": sign_payload
    }

class TestPluginTrust:
    def test_signed_plugin_evaluates(self, trust_env):
        d = trust_env["dir"]
        
        # 1. Create a valid plugin manifest
        manifest = {
            "id": "my_plugin_1",
            "version": "1.0",
            "author": "Test",
            "profile_mapping": "plugin_sandbox",
            "permissions": ["read_file"]
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        sig_b64 = trust_env["sign"](manifest_bytes)
        
        # 2. Package it into a zip
        zip_path = d / "test_plugin.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("manifest.json", manifest_bytes)
            zf.writestr("signature.sig", sig_b64.encode("utf-8"))
            
        # 3. Evaluate
        manager = PluginTrustManager(data_dir=str(d / "security"))
        ok, reason, extracted_manifest = manager.evaluate_plugin_archive(zip_path, public_key_hex=trust_env["pub_hex"])
        
        # Note: Will return False because APPROVAL_REQUIRED!
        assert not ok
        assert "APPROVAL_REQUIRED" in reason
        assert extracted_manifest["id"] == "my_plugin_1"
        
        # 4. Approve and evaluate again
        import hashlib
        m_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manager.approve_plugin("my_plugin_1", m_hash)
        
        ok, reason, extracted_manifest = manager.evaluate_plugin_archive(zip_path, public_key_hex=trust_env["pub_hex"])
        assert ok
        assert reason == "OK"

    def test_tampered_plugin_rejected(self, trust_env):
        d = trust_env["dir"]
        
        manifest = {
            "id": "my_plugin_tampered",
            "version": "1.0",
            "author": "Test",
            "profile_mapping": "plugin_sandbox",
            "permissions": ["read_file"]
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        sig_b64 = trust_env["sign"](manifest_bytes)
        
        # TAMPER: change permissions!
        tampered_manifest = {**manifest, "permissions": ["shell_exec"]}
        tampered_bytes = json.dumps(tampered_manifest).encode("utf-8")
        
        zip_path = d / "test_plugin_tampered.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("manifest.json", tampered_bytes) # Tampered
            zf.writestr("signature.sig", sig_b64.encode("utf-8")) # Original signature
            
        manager = PluginTrustManager(data_dir=str(d / "security"))
        ok, reason, _ = manager.evaluate_plugin_archive(zip_path, public_key_hex=trust_env["pub_hex"])
        
        assert not ok
        assert "validation failed" in reason

class TestUpdateTrust:
    def test_valid_update_lifecycle(self, trust_env):
        d = trust_env["dir"]
        
        # Mock install dir
        install_dir = d / "pihu_install"
        install_dir.mkdir()
        (install_dir / "core.py").write_text("old_code")
        
        # Create update zip
        update_dir = d / "update_build"
        update_dir.mkdir()
        
        # Create new files
        core_py_new = b"new_code"
        import hashlib
        core_hash = hashlib.sha256(core_py_new).hexdigest()
        
        manifest = {
            "version": "1.5.0",
            "channel": "stable",
            "min_compatible_version": "1.0.0",
            "file_hashes": {
                "core.py": core_hash
            }
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        sig_b64 = trust_env["sign"](manifest_bytes)
        
        zip_path = d / "update.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("release_manifest.json", manifest_bytes)
            zf.writestr("release_manifest.sig", sig_b64.encode("utf-8"))
            zf.writestr("core.py", core_py_new)
            
        # Run update
        manager = UpdateTrustManager(install_dir=str(install_dir))
        manager.official_public_key_hex = trust_env["pub_hex"]
        
        ok, reason = manager.apply_update(zip_path, "1.4.0")
        assert ok
        assert reason == "Update applied successfully"
        assert (install_dir / "core.py").read_text() == "new_code"

    def test_tampered_update_file_rolled_back(self, trust_env):
        d = trust_env["dir"]
        
        install_dir = d / "pihu_install2"
        install_dir.mkdir()
        (install_dir / "core.py").write_text("old_code")
        
        manifest = {
            "version": "1.6.0",
            "channel": "stable",
            "min_compatible_version": "1.0.0",
            "file_hashes": {
                "core.py": "abc" # Fake hash, won't match what's in the zip
            }
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        sig_b64 = trust_env["sign"](manifest_bytes)
        
        zip_path = d / "update2.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            zf.writestr("release_manifest.json", manifest_bytes)
            zf.writestr("release_manifest.sig", sig_b64.encode("utf-8"))
            zf.writestr("core.py", b"evil_code")
            
        manager = UpdateTrustManager(install_dir=str(install_dir))
        manager.official_public_key_hex = trust_env["pub_hex"]
        
        ok, reason = manager.apply_update(zip_path, "1.5.0")
        assert not ok
        assert "Hash mismatch" in reason
        
        # Verify rollback worked
        assert (install_dir / "core.py").read_text() == "old_code"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
