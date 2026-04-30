"""
Pihu — Update Trust Model
Provides secure, cryptographically verified mechanism for updating the core system.
Prevents downgrade attacks, malicious updates, and validates every file hash against 
a signed release manifest before applying any changes.
"""
import os
import json
import shutil
import hashlib
import zipfile
import base64
from pathlib import Path
from typing import Dict, Tuple

from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

from sandbox.snapshot_engine import SnapshotEngine
from logger import get_logger

log = get_logger("UPDATE-TRUST")

class UpdateTrustManager:
    def __init__(self, install_dir: str = "."):
        self.install_dir = Path(install_dir).absolute()
        self.snapshot_engine = SnapshotEngine()
        
        # Pihu Official Releases Public Key (Hardcoded for Ring-0 security)
        self.official_public_key_hex = "f" * 64

    def verify_signature(self, payload: bytes, signature_base64: str, public_key_hex: str) -> bool:
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            sig_bytes = base64.b64decode(signature_base64)
            public_key.verify(sig_bytes, payload)
            return True
        except (ValueError, InvalidSignature, TypeError):
            return False

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        try:
            with open(path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            return h.hexdigest()
        except OSError:
            return ""

    def evaluate_update_archive(self, update_zip_path: Path) -> Tuple[bool, str, dict]:
        """
        Verify the update archive's cryptographic trust before any extraction.
        Returns (is_safe, reason, manifest_data)
        """
        if not update_zip_path.exists():
            return False, "Update archive not found.", {}
            
        try:
            with zipfile.ZipFile(update_zip_path, 'r') as zf:
                if "release_manifest.json" not in zf.namelist():
                    return False, "Archive missing release_manifest.json", {}
                if "release_manifest.sig" not in zf.namelist():
                    return False, "Archive missing release_manifest.sig. Unsigned updates blocked.", {}
                    
                manifest_bytes = zf.read("release_manifest.json")
                signature_b64 = zf.read("release_manifest.sig").decode("utf-8").strip()
                
                if not self.verify_signature(manifest_bytes, signature_b64, self.official_public_key_hex):
                    return False, "Update signature validation failed. Archive is tampered or from an untrusted source.", {}
                    
                manifest = json.loads(manifest_bytes)
                
        except Exception as e:
            return False, f"Failed to read update archive: {e}", {}
            
        required_fields = ["version", "channel", "min_compatible_version", "file_hashes"]
        for f in required_fields:
            if f not in manifest:
                return False, f"Manifest missing required field: {f}", {}
                
        return True, "OK", manifest

    def apply_update(self, update_zip_path: Path, current_version: str) -> Tuple[bool, str]:
        """
        Safely applies the update.
        1. Verifies archive trust
        2. Validates compatibility and downgrade protection
        3. Takes a system-wide rollback snapshot
        4. Extracts files to a staging dir and verifies every single hash
        5. Swaps files
        """
        ok, reason, manifest = self.evaluate_update_archive(update_zip_path)
        if not ok:
            return False, f"Update rejected: {reason}"
            
        new_version = manifest["version"]
        
        # Primitive semantic-versionish downgrade protection
        if new_version < current_version and "downgrade" not in manifest.get("flags", []):
             return False, f"Downgrade attack detected. V{new_version} is older than V{current_version}."
             
        log.info("Starting trusted update: v%s -> v%s (Channel: %s)", current_version, new_version, manifest["channel"])
        
        # 1. Take a snapshot of the current installation
        snapshot_path = self.snapshot_engine.take_snapshot(self.install_dir)
        if not snapshot_path:
            return False, "Failed to create pre-update safety snapshot. Update aborted."
            
        staging_dir = self.install_dir / ".update_staging"
        shutil.rmtree(staging_dir, ignore_errors=True)
        staging_dir.mkdir()
        
        try:
            # 2. Extract out to staging
            with zipfile.ZipFile(update_zip_path, 'r') as zf:
                # Do not extract the signatures
                extract_members = [m for m in zf.namelist() if m not in ("release_manifest.json", "release_manifest.sig")]
                zf.extractall(path=staging_dir, members=extract_members)
                
            # 3. Verify EVERY file's hash matches the signed manifest
            expected_hashes: dict = manifest["file_hashes"]
            
            for file_rel_path, expected_hash in expected_hashes.items():
                staged_file = staging_dir / file_rel_path
                if not staged_file.exists():
                    raise ValueError(f"CRITICAL: Signed file {file_rel_path} is missing from archive.")
                    
                actual_hash = self._hash_file(staged_file)
                if actual_hash != expected_hash:
                    raise ValueError(f"CRITICAL: Hash mismatch for {file_rel_path}. Expected {expected_hash}, got {actual_hash}.")
                    
            # 4. Copy verified files over
            for file_rel_path in expected_hashes.keys():
                src = staging_dir / file_rel_path
                dst = self.install_dir / file_rel_path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                
            log.info("✅ Update v%s successfully applied.", new_version)
            
            # Clean up snapshot on success
            self.snapshot_engine.cleanup(snapshot_path)
            shutil.rmtree(staging_dir, ignore_errors=True)
            
            # Trigger audit log
            from security.security_core import AuditLog, ThreatLevel
            AuditLog().record("SYSTEM_UPDATE", f"Successfully authenticated and applied update v{new_version}", ThreatLevel.SAFE)
            return True, "Update applied successfully"
            
        except Exception as e:
            log.error("Update failed during application: %s. Initiating emergency rollback.", e)
            self.snapshot_engine.rollback(self.install_dir, snapshot_path)
            shutil.rmtree(staging_dir, ignore_errors=True)
            return False, f"Update failed, system rolled back securely. Reason: {e}"
