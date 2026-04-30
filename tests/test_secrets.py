"""
Tests for api/secrets.py — Secrets manager, key rotation, tenant isolation.
"""
import pytest
import os
import json

os.environ["PIHU_ENV"] = "testing"

from api.secrets import SecretsManager

@pytest.fixture
def secrets_manager():
    sm = SecretsManager()
    # Clear cache for tests
    sm._cache = {}
    return sm

class TestSecretsManager:
    def test_get_missing_secret_returns_none(self, secrets_manager):
        assert secrets_manager.get("nonexistent_key") is None

    def test_get_required_secret_raises_in_prod(self, monkeypatch):
        monkeypatch.setattr("api.secrets.PIHU_ENV", "production")
        sm = SecretsManager()
        with pytest.raises(RuntimeError):
            sm.get("MISSING_CRITICAL_KEY", required=True)

    def test_tenant_secret_isolation(self, secrets_manager):
        secrets_manager.store_tenant_secret("tenant1", "api_key", "secret1")
        secrets_manager.store_tenant_secret("tenant2", "api_key", "secret2")
        
        assert secrets_manager.get_tenant_secret("tenant1", "api_key") == "secret1"
        assert secrets_manager.get_tenant_secret("tenant2", "api_key") == "secret2"
        assert secrets_manager.get_tenant_secret("tenant3", "api_key") is None

    def test_delete_tenant_secrets(self, secrets_manager):
        secrets_manager.store_tenant_secret("tenant1", "key1", "val1")
        secrets_manager.store_tenant_secret("tenant1", "key2", "val2")
        secrets_manager.store_tenant_secret("tenant2", "key1", "val3")
        
        count = secrets_manager.delete_tenant_secrets("tenant1")
        assert count == 2
        assert secrets_manager.get_tenant_secret("tenant1", "key1") is None
        assert secrets_manager.get_tenant_secret("tenant2", "key1") == "val3"

    def test_rotate_secret(self, secrets_manager):
        # Initial store
        secrets_manager._cache["my_secret"] = "old_value"
        
        # Rotate
        rotation_info = secrets_manager.rotate_secret("my_secret", "new_value")
        
        assert secrets_manager.get("my_secret") == "new_value"
        assert rotation_info["version"] == 1
        assert "old_key_hash" in rotation_info
        assert "new_key_hash" in rotation_info
        
        # Rotate again
        rotation_info2 = secrets_manager.rotate_secret("my_secret", "newer_value")
        assert rotation_info2["version"] == 2

    def test_access_log_recording(self, secrets_manager):
        secrets_manager.get("some_key")
        secrets_manager.store_tenant_secret("t1", "k1", "v1")
        
        logs = secrets_manager.get_access_log()
        assert len(logs) == 2
        assert logs[0]["secret"] == "some_key"
        assert logs[0]["action"] == "read"
        assert logs[1]["secret"] == "tenant:t1:k1"
        assert logs[1]["action"] == "write"

    def test_production_readiness_check(self, secrets_manager):
        status = secrets_manager.check_production_readiness()
        assert isinstance(status, dict)
        assert "production_ready" in status
        assert status["environment"] == "testing"
