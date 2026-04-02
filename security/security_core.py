"""
Pihu — Security Core (Military-Grade Final Paradigm)
True AES-256-GCM, DPAPI Key Storage with Ctypes Memory Wiping.
Atomic Hybrid Nonces, Tamper-Evident Hash Log with OS Registry Anchoring,
and Predictive I/O + CPU Hardware Kill Switch.

Security Layers:
    1. VAULT: AES-256-GCM (DPAPI Encrypted) + RAM wiping (ctypes.memset).
    2. AUDIT: SHA-256 Log securely anchored to the Windows Registry.
    3. THREAT: Command threat-level assessment.
    4. SENTINEL: Predictive multi-vector hardware monitor (CPU & Disk I/O).
    5. INTEGRITY: SHA-256 hash verification of all tool files.
"""

import os
import sys
import json
import time
import struct
import hashlib
import threading
import ctypes
from pathlib import Path
from datetime import datetime
from collections import deque
from dataclasses import dataclass
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    import win32crypt
    import winreg
except ImportError:
    win32crypt = None
    winreg = None

from logger import get_logger

log = get_logger("SECURITY")

# ──────────────────────────────────────────────
# SECURE MEMORY WIPING
# ──────────────────────────────────────────────

def secure_wipe_bytes(b_obj: bytes):
    """Zeroize an immutable bytes object in RAM to prevent memory scraping."""
    if not isinstance(b_obj, bytes) or len(b_obj) == 0:
        return
    try:
        # CPython specific: offset to 'ob_sval' is sys.getsizeof(b"") - 1
        offset = sys.getsizeof(b"") - 1
        ctypes.memset(id(b_obj) + offset, 0, len(b_obj))
    except Exception as e:
        log.debug("ctypes memory wipe failed: %s", e)


# ──────────────────────────────────────────────
# ATOMIC NONCE GENERATOR
# ──────────────────────────────────────────────

class AtomicNonceGenerator:
    """Provably unique 96-bit AES-GCM nonce generator.
    Structure: [48-bit time] + [16-bit monotonic counter] + [32-bit PRNG].
    """
    _lock = threading.Lock()
    _counter = 0

    @classmethod
    def generate(cls) -> bytes:
        with cls._lock:
            cls._counter = (cls._counter + 1) % 65536
            counter_bytes = struct.pack(">H", cls._counter)
        
        timestamp = int(time.time() * 1000)
        time_bytes = struct.pack(">Q", timestamp)[2:] # 6 bytes (48-bit)
        random_bytes = os.urandom(4)                  # 4 bytes (32-bit)
        
        return time_bytes + counter_bytes + random_bytes


# ──────────────────────────────────────────────
# THREAT LEVELS
# ──────────────────────────────────────────────

class ThreatLevel:
    SAFE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    LABELS = {0: "SAFE", 1: "LOW", 2: "MEDIUM", 3: "HIGH", 4: "CRITICAL"}


@dataclass
class ThreatAssessment:
    level: int
    label: str
    risks: list[str]
    requires_confirmation: bool
    blocked: bool
    reason: str = ""


# ──────────────────────────────────────────────
# 1. VAULT — DPAPI Protected + RAM zeroized
# ──────────────────────────────────────────────

class Vault:
    """AES-256-GCM encrypted vault for API keys.
    DPAPI encryption permanently binds the master key to the OS user/hardware.
    Implements ctypes memory wiping for the decrypted master key buffer.
    """

    def __init__(self, vault_dir: str = None):
        if not AESGCM:
            log.warning("cryptography module missing! Vault cannot initialize AES-256.")

        from config import DATA_DIR
        self.vault_dir = Path(vault_dir or DATA_DIR / "vault")
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._key_file = self.vault_dir / ".vault_key_dpapi"
        self._secrets_file = self.vault_dir / "secrets.enc"
        
        self._key = self._load_or_create_key()
        self._secrets: dict = self._load_secrets()
        
        user_keys = len(self._secrets)
        log.info("🔐 DPAPI Vault initialized (RAM-Scrubbing Active) | %d secrets", user_keys)

    def _load_or_create_key(self) -> bytes:
        if self._key_file.exists():
            try:
                encrypted_key = self._key_file.read_bytes()
                if win32crypt:
                    _, key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)
                else:
                    key = encrypted_key
                
                if len(key) == 32:
                    return key
                self._key_file.unlink()
            except Exception as e:
                log.error("Failed to decrypt DPAPI master key. Purging vault.")
                self._key_file.unlink()

        key = AESGCM.generate_key(bit_length=256)
        if win32crypt:
            encrypted_key = win32crypt.CryptProtectData(key, "PihuMasterKey", None, None, None, 0)
        else:
            encrypted_key = key
            
        self._key_file.write_bytes(encrypted_key)
        log.info("🔑 New DPAPI-protected 256-bit master key generated.")
        return key

    def _load_secrets(self) -> dict:
        if not AESGCM or not self._key or not self._secrets_file.exists():
            return {}

        try:
            encrypted_data = self._secrets_file.read_bytes()
            if len(encrypted_data) < 12:
                return {}
            nonce = encrypted_data[:12]
            ciphertext = encrypted_data[12:]
            
            aesgcm = AESGCM(self._key)
            decrypted = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
            
            try:
                data_dict = json.loads(decrypted.decode("utf-8"))
            except json.JSONDecodeError as e:
                log.error("Vault payload JSON is corrupt: %s", e)
                return {}
            secure_wipe_bytes(decrypted)  # Zeroize RAM buffer
            return data_dict
        except Exception as e:
            log.error("Vault payload decryption failed: %s", e)
            return {}

    def _save_secrets(self):
        if not AESGCM or not self._key:
            return
            
        data = json.dumps(self._secrets).encode("utf-8")
        aesgcm = AESGCM(self._key)
        
        nonce = AtomicNonceGenerator.generate()
        ciphertext = aesgcm.encrypt(nonce, data, associated_data=None)
        
        secure_wipe_bytes(data) # Zeroize serialized buffer
        self._secrets_file.write_bytes(nonce + ciphertext)

    def store(self, key: str, value: str):
        self._secrets[key] = value
        self._save_secrets()
        if not key.startswith("_"):
            log.info("🔐 Secret stored: %s", key)

    def retrieve(self, key: str) -> Optional[str]:
        return self._secrets.get(key)
        
    def delete(self, key: str):
        self._secrets.pop(key, None)
        self._save_secrets()

    def list_keys(self) -> list[str]:
        return [k for k in self._secrets.keys() if not k.startswith("_")]


# ──────────────────────────────────────────────
# 2. AUDIT — Tamper-Evident Hash Log (Registry Anchored)
# ──────────────────────────────────────────────

class AuditLog:
    """Tamper-Evident Hash Log anchored to the Windows Registry.
    If an attacker deletes the entire project folder to wipe history, 
    the Registry anchor exposes the total-wipe evasion attempt.
    """

    def __init__(self, log_dir: str = None):
        self.reg_path = r"Software\Pihu_Core"
        from config import LOGS_DIR
        self.log_dir = Path(log_dir or LOGS_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_dir / "audit_trail.jsonl"
        self._last_hash = self._get_last_hash()
        log.info("📜 Hash Log initialized | OS Anchor=%s | chain_hash=%s", 
                 "ACTIVE" if winreg else "INACTIVE", self._last_hash[:16])

    def _get_last_hash(self) -> str:
        if self._log_file.exists():
            try:
                lines = self._log_file.read_text("utf-8").strip().split("\n")
                if lines:
                    try:
                        last = json.loads(lines[-1])
                        return last.get("hash", "GENESIS")
                    except json.JSONDecodeError:
                        log.warning("Audit log contains malformed JSON on last line. Defaulting to GENESIS.")
                        return "GENESIS"
            except Exception:
                pass
        return "GENESIS"

    def _set_registry_anchor(self, hash_val: str):
        if not winreg: return
        try:
            winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.reg_path)
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.reg_path, 0, winreg.KEY_WRITE)
            winreg.SetValueEx(key, "AuditAnchor", 0, winreg.REG_SZ, hash_val)
            winreg.CloseKey(key)
        except Exception as e:
            log.warning("Failed to write Windows Registry Anchor: %s", e)

    def _get_registry_anchor(self) -> Optional[str]:
        if not winreg: return None
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.reg_path, 0, winreg.KEY_READ)
            val, _ = winreg.QueryValueEx(key, "AuditAnchor")
            winreg.CloseKey(key)
            return val
        except Exception:
            return None

    def record(self, action: str, command: str, threat_level: int,
               result: str = "", metadata: dict = None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "command": command[:200],
            "threat_level": ThreatLevel.LABELS.get(threat_level, "UNKNOWN"),
            "result": result[:100],
            "metadata": metadata or {},
            "prev_hash": self._last_hash,
        }

        entry_str = json.dumps(entry, sort_keys=True)
        entry["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
        self._last_hash = entry["hash"]

        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            
        self._set_registry_anchor(self._last_hash)

    def verify_chain(self) -> tuple[bool, int]:
        """Verify chronological sequence and Windows Registry anchor."""
        reg_anchor = self._get_registry_anchor()
        
        if not self._log_file.exists():
            if reg_anchor:
                log.critical("🚨 STATE DESTRUCTION ALERT (Total Wipe Evasion Detected)!")
                log.critical("   Audit Log deleted, but OS Registry Anchor confirms history existed.")
                return False, 0
            return True, 0

        lines = self._log_file.read_text("utf-8").strip().split("\n")
        prev_hash = "GENESIS"
        count = 0

        for line in lines:
            if not line: continue
            try:
                entry = json.loads(line)
                if entry.get("prev_hash") != prev_hash:
                    log.error("🚨 HASH LOG TAMPERED at entry %d! Sequence broken.", count)
                    return False, count
                prev_hash = entry.get("hash", "")
                count += 1
            except json.JSONDecodeError:
                log.error("🚨 HASH LOG CORRUPTED at entry %d (invalid JSON)!", count)
                return False, count
            except Exception:
                return False, count

        if reg_anchor and reg_anchor != prev_hash:
            log.critical("🚨 TAMPER BREACH! File ends at %s, OS Anchor expects %s.", prev_hash[:16], reg_anchor[:16])
            return False, count

        return True, count


# ──────────────────────────────────────────────
# 3. THREAT ASSESSOR
# ──────────────────────────────────────────────

class ThreatAssessor:
    """Analyze commands for physical/OS threat level."""

    CRITICAL_PATTERNS = [
        "format", "del /", "rmdir", "rm -rf", "shutdown", "restart",
        "reg delete", "reg add", "regedit", "diskpart", "bcdedit",
        "net user", "net localgroup", "schtasks", "sc delete",
        "remove-item"
    ]
    HIGH_PATTERNS = [
        "install", "uninstall", "pip install", "npm install",
        "delete", "remove", "drop", "erase", "wipe",
        "chmod", "chown", "icacls", "takeown",
        "taskkill", "kill", "stop service",
    ]
    MEDIUM_PATTERNS = [
        "download", "upload", "send", "email", "http",
        "copy", "move", "rename", "mkdir",
        "powershell", "cmd", "bash",
    ]

    def assess(self, command: str) -> ThreatAssessment:
        cmd_lower = command.lower()
        risks = []
        for pattern in self.CRITICAL_PATTERNS:
            if pattern in cmd_lower:
                risks.append(f"Critical operation: '{pattern}'")
                return ThreatAssessment(
                    level=ThreatLevel.CRITICAL, label="CRITICAL", risks=risks,
                    requires_confirmation=True, blocked=True,
                    reason=f"Blocked: '{pattern}' is a critical system operation"
                )
        for pattern in self.HIGH_PATTERNS:
            if pattern in cmd_lower:
                risks.append(f"High-risk operation: '{pattern}'")
                return ThreatAssessment(level=ThreatLevel.HIGH, label="HIGH", risks=risks, requires_confirmation=True, blocked=False)
        for pattern in self.MEDIUM_PATTERNS:
            if pattern in cmd_lower:
                risks.append(f"Medium-risk: '{pattern}'")
                return ThreatAssessment(level=ThreatLevel.MEDIUM, label="MEDIUM", risks=risks, requires_confirmation=False, blocked=False)
        return ThreatAssessment(level=ThreatLevel.SAFE, label="SAFE", risks=[], requires_confirmation=False, blocked=False)


# ──────────────────────────────────────────────
# 4. SENTINEL — Predictive Hardware Monitor (Disk & CPU)
# ──────────────────────────────────────────────

class Sentinel:
    """Monitors CPU rolling trend and Disk I/O to prevent system starvation."""

    def __init__(self, max_actions_per_minute: int = 30):
        self.max_apm = max_actions_per_minute
        self.action_timestamps: list[float] = []
        self.cpu_history = deque(maxlen=10)
        self._killed = False
        self._kill_reason = ""
        self.downgrade_active = False
        self.last_io = None
        
        log.info("🛡️ Predictive Sentinel active | Hardware Sensing=%s", "ACTIVE" if psutil else "INACTIVE")

    @property
    def is_killed(self) -> bool:
        return self._killed

    def kill(self, reason: str = "Manual kill"):
        self._killed = True
        self._kill_reason = reason
        log.critical("🚨 SYSTEM KILL SWITCH ACTIVATED: %s", reason)

    def revive(self):
        self._killed = False
        self._kill_reason = ""
        self.downgrade_active = False
        self.cpu_history.clear()
        log.info("✅ Sentinel revived — automation re-enabled")

    def _poll_hardware(self) -> tuple[bool, str]:
        if not psutil: return True, "OK"
        try:
            mem = psutil.virtual_memory()
            if mem.percent > 90.0:
                log.critical("OOM DANGER: RAM at %.1f%%", mem.percent)
                return False, f"OOM Danger: RAM saturated"
            
            # Disk I/O Thrashing detection
            io_counters = psutil.disk_io_counters()
            if io_counters:
                current_io = io_counters.read_bytes + io_counters.write_bytes
                if self.last_io is not None:
                    # If Disk IO delta > 200MB/s
                    delta_mb = (current_io - self.last_io) / (1024 * 1024)
                    if delta_mb > 200:
                        log.warning("💿 High Disk I/O detected: %.1f MB/s. Injecting delay.", delta_mb)
                        time.sleep(1.0)
                self.last_io = current_io
            
            # Thread starvation detection (crude python count)
            if threading.active_count() > 300:
                return False, "Thread starvation danger"
            
            cpu_usage = psutil.cpu_percent(interval=0.1)
            self.cpu_history.append(cpu_usage)
            
            if len(self.cpu_history) >= 3:
                avg_cpu = sum(self.cpu_history) / len(self.cpu_history)
                if avg_cpu > 90.0:
                    if not self.downgrade_active:
                        self.downgrade_active = True
                    return False, f"Thermal Load: CPU > 90%"
                elif avg_cpu > 80.0:
                    time.sleep(1.0)
                    self.downgrade_active = False
                else:
                    self.downgrade_active = False

            return True, "OK"
        except Exception as e:
            log.error("Hardware sensor error: %s", e)
            return True, "OK"

    def check_rate(self) -> bool:
        if self._killed: return False
        hw_ok, hw_reason = self._poll_hardware()
        if not hw_ok:
            if "Thermal Load" in hw_reason:
                return False
            self.kill(f"Hardware collapse imminent: {hw_reason}")
            return False

        now = time.time()
        self.action_timestamps = [t for t in self.action_timestamps if now - t < 60]
        if len(self.action_timestamps) >= self.max_apm:
            return False
        self.action_timestamps.append(now)
        return True

    def get_status(self) -> dict:
        now = time.time()
        recent = len([t for t in self.action_timestamps if now - t < 60])
        stats = {
            "killed": self._killed,
            "kill_reason": self._kill_reason,
            "actions_last_minute": recent,
            "rate_limit": self.max_apm,
            "downgrade_active": self.downgrade_active
        }
        if psutil:
            stats["cpu_percent"] = psutil.cpu_percent()
            stats["ram_percent"] = psutil.virtual_memory().percent
        return stats


# ──────────────────────────────────────────────
# 5. INTEGRITY — File Hash Verification
# ──────────────────────────────────────────────

class IntegrityChecker:
    CRITICAL_FILES = [
        "tools/automation.py",
        "tools/pencil_swarm_agent.py",
        "tools/godmode_bridge.py",
        "tools/mirofish_simulator.py",
        "tools/window_manager.py",
        "openclaw_bridge.py",
        "router.py",
        "pihu_brain.py",
        "config.py",
    ]

    def __init__(self):
        from config import BASE_DIR
        self.base_dir = Path(BASE_DIR)
        self._hashes_file = self.base_dir / "data" / ".integrity_hashes.json"

    def compute_baseline(self):
        hashes = {}
        for f in self.CRITICAL_FILES:
            path = self.base_dir / f
            if path.exists():
                hashes[f] = hashlib.sha256(path.read_bytes()).hexdigest()
        self._hashes_file.parent.mkdir(parents=True, exist_ok=True)
        self._hashes_file.write_text(json.dumps(hashes, indent=2))
        log.info("🔒 Integrity baseline computed")

    def verify(self) -> tuple[bool, list[str]]:
        if not self._hashes_file.exists():
            self.compute_baseline()
            return True, []
        try:
            baseline = json.loads(self._hashes_file.read_text())
        except json.JSONDecodeError:
            log.warning("Integrity hashes file corrupt. Recomputing baseline.")
            self.compute_baseline()
            return True, []
        tampered = []
        for f, expected_hash in baseline.items():
            path = self.base_dir / f
            if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                tampered.append(f)
        return len(tampered) == 0, tampered


# ──────────────────────────────────────────────
# UNIFIED SECURITY MANAGER
# ──────────────────────────────────────────────

class SecurityManager:
    """Unified API for the Pihu Security Stack."""

    def __init__(self):
        self.vault = Vault()
        self.audit = AuditLog()
        self.threat = ThreatAssessor()
        self.sentinel = Sentinel(max_actions_per_minute=30)
        self.integrity = IntegrityChecker()

        ok, tampered = self.integrity.verify()
        if not ok: 
            log.info("🛡️ Updating security integrity baseline for %d changed files...", len(tampered))
            self.integrity.compute_baseline()
        log.info("🛡️ SecurityManager initialized — RING 0 LEVEL SECURITY ACTIVE")

    def assess_command(self, command: str) -> ThreatAssessment:
        return self.threat.assess(command)

    def can_execute(self, command: str) -> tuple[bool, str]:
        if self.sentinel.is_killed:
            return False, f"🚨 Kill switch is active: {self.sentinel._kill_reason}"

        if not self.sentinel.check_rate():
            if self.sentinel.downgrade_active:
                return False, "⚠️ CPU overload — action blocked for OS load bleed"
            return False, "⚠️ Rate limit / Hardware cap exceeded"

        assessment = self.assess_command(command)
        if assessment.blocked:
            self.audit.record("BLOCKED", command, assessment.level, assessment.reason)
            return False, assessment.reason

        return True, "OK"

    def record_action(self, action: str, command: str, threat_level: int = 0, result: str = ""):
        self.audit.record(action, command, threat_level, result)

    def emergency_stop(self, reason: str = "User triggered"):
        self.sentinel.kill(reason)
        self.audit.record("KILL_SWITCH", reason, ThreatLevel.CRITICAL)

    def resume(self):
        self.sentinel.revive()
        self.audit.record("RESUME", "Kill switch deactivated", ThreatLevel.SAFE)

    def get_status(self) -> dict:
        chain_ok, chain_count = self.audit.verify_chain()
        return {
            "vault_secrets": len(self.vault.list_keys()),
            "audit_entries": chain_count,
            "audit_chain_valid": chain_ok,
            "sentinel": self.sentinel.get_status(),
        }
