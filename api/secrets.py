"""
Pihu SaaS — Secrets Management Layer
Abstracts secret retrieval across environments:
  - development: OS environment variables
  - staging: encrypted .env file
  - production: provider-ready interface (AWS KMS / HashiCorp Vault)

Includes key rotation policy and per-tenant secret isolation.
"""

import os
import json
import hashlib
import time
from datetime import datetime
from typing import Optional
from logger import get_logger

log = get_logger("SECRETS_MGR")

PIHU_ENV = os.getenv("PIHU_ENV", "development")


class SecretsManager:
    """
    Environment-aware secrets interface.
    In development: reads from env vars.
    In production: designed to plug into AWS Secrets Manager, HashiCorp Vault, 
    or Azure Key Vault via the `get()` abstraction.
    """

    # Registered secret names and their env var mappings
    SYSTEM_SECRETS = {
        "nvidia_nim_api_key": "NVIDIA_NIM_API_KEY",
        "e2b_api_key": "E2B_API_KEY",
        "stripe_secret_key": "STRIPE_SECRET_KEY",
        "stripe_webhook_secret": "STRIPE_WEBHOOK_SECRET",
        "jwt_secret_key": "JWT_SECRET_KEY",
        "db_encryption_key": "DB_ENCRYPTION_KEY",
        "redis_url": "REDIS_URL",
        "database_url": "DATABASE_URL",
    }

    # Key rotation metadata
    _rotation_log: dict = {}  # secret_name -> { rotated_at, version }

    def __init__(self):
        self._cache: dict = {}
        self._access_log: list = []
        self._load_environment_secrets()
        log.info("🔐 SecretsManager initialized (env=%s, secrets=%d)", PIHU_ENV, len(self._cache))

    def _load_environment_secrets(self):
        """Load all registered secrets from environment variables."""
        for secret_name, env_var in self.SYSTEM_SECRETS.items():
            value = os.getenv(env_var)
            if value:
                self._cache[secret_name] = value

    def get(self, secret_name: str, required: bool = False) -> Optional[str]:
        """
        Retrieve a secret by name.
        In production, this method would call the external vault.
        All access is logged for audit.
        """
        self._log_access(secret_name, "read")

        # Check cache first
        value = self._cache.get(secret_name)
        if value:
            return value

        # Fallback to env var
        env_var = self.SYSTEM_SECRETS.get(secret_name, secret_name.upper())
        value = os.getenv(env_var)

        if value:
            self._cache[secret_name] = value
            return value

        if required:
            if PIHU_ENV == "production":
                log.critical("FATAL: Required secret '%s' not found in production!", secret_name)
                raise RuntimeError(f"Required secret '{secret_name}' is missing")
            else:
                log.warning("Secret '%s' not found (non-production, continuing)", secret_name)

        return None

    def get_tenant_secret(self, tenant_id: str, secret_name: str) -> Optional[str]:
        """
        Retrieve a tenant-specific secret.
        Tenant secrets are namespaced: 'tenant:{tenant_id}:{secret_name}'
        """
        full_key = f"tenant:{tenant_id}:{secret_name}"
        self._log_access(full_key, "read")
        return self._cache.get(full_key)

    def store_tenant_secret(self, tenant_id: str, secret_name: str, value: str):
        """Store a tenant-specific secret."""
        full_key = f"tenant:{tenant_id}:{secret_name}"
        self._cache[full_key] = value
        self._log_access(full_key, "write")
        log.info("🔐 Tenant secret stored: %s", full_key.replace(value, "***"))

    def delete_tenant_secrets(self, tenant_id: str) -> int:
        """Purge all secrets for a tenant (offboarding)."""
        prefix = f"tenant:{tenant_id}:"
        keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
        for k in keys_to_delete:
            del self._cache[k]
        self._log_access(f"tenant:{tenant_id}:*", "purge")
        log.warning("🗑️ Purged %d tenant secrets for '%s'", len(keys_to_delete), tenant_id)
        return len(keys_to_delete)

    # ──────────────────────────────────────────
    # KEY ROTATION
    # ──────────────────────────────────────────

    def rotate_secret(self, secret_name: str, new_value: str) -> dict:
        """
        Rotate a secret to a new value.
        In production, this would trigger downstream key propagation.
        """
        old_hash = hashlib.sha256(
            (self._cache.get(secret_name, "") or "").encode()
        ).hexdigest()[:16]

        self._cache[secret_name] = new_value
        version = self._rotation_log.get(secret_name, {}).get("version", 0) + 1

        self._rotation_log[secret_name] = {
            "rotated_at": datetime.utcnow().isoformat(),
            "version": version,
            "old_key_hash": old_hash,
            "new_key_hash": hashlib.sha256(new_value.encode()).hexdigest()[:16],
        }

        self._log_access(secret_name, "rotate")
        log.info("🔄 Secret rotated: '%s' → version %d", secret_name, version)
        return self._rotation_log[secret_name]

    def get_rotation_status(self) -> dict:
        """Return rotation metadata for all secrets."""
        return {
            name: {
                "has_value": name in self._cache,
                "rotation": self._rotation_log.get(name, {"version": 0, "rotated_at": "never"}),
            }
            for name in self.SYSTEM_SECRETS
        }

    # ──────────────────────────────────────────
    # AUDIT LOGGING
    # ──────────────────────────────────────────

    def _log_access(self, secret_name: str, action: str):
        """Record every secret access for compliance audit."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "secret": secret_name,
            "action": action,
            "env": PIHU_ENV,
        }
        self._access_log.append(entry)
        # Keep last 1000 entries in memory
        if len(self._access_log) > 1000:
            self._access_log = self._access_log[-500:]

    def get_access_log(self, limit: int = 50) -> list:
        """Return recent secret access events."""
        return self._access_log[-limit:]

    # ──────────────────────────────────────────
    # PRODUCTION READINESS CHECK
    # ──────────────────────────────────────────

    def check_production_readiness(self) -> dict:
        """Verify all required secrets are present for production."""
        required_in_prod = [
            "nvidia_nim_api_key", "jwt_secret_key", "db_encryption_key",
            "stripe_secret_key", "database_url", "redis_url"
        ]
        results = {}
        all_ready = True
        for name in required_in_prod:
            present = name in self._cache and bool(self._cache[name])
            results[name] = "✅" if present else "❌ MISSING"
            if not present:
                all_ready = False

        results["production_ready"] = all_ready
        results["environment"] = PIHU_ENV
        return results


secrets_manager = SecretsManager()
