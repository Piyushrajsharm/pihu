"""
Tests for api/auth.py — JWT, permissions, roles, demo mode.
"""
import pytest
import os
import time

os.environ["PIHU_ENV"] = "testing"

from api.auth import (
    create_jwt_token, validate_jwt_token,
    require_permission, require_role, handle_login, verify_jwt_token,
    ROLE_PERMISSIONS, ALL_PERMISSIONS,
    JWT_SECRET, JWT_ALGORITHM,
)


class TestJWTCreation:
    def test_create_token_returns_string(self):
        token = create_jwt_token(user_id="u1", org_id="org1", role="admin")
        assert isinstance(token, str)
        assert len(token) > 20

    def test_create_token_with_custom_permissions(self):
        token = create_jwt_token(
            user_id="u1", org_id="org1", role="viewer",
            permissions=["read", "predict"]
        )
        claims = validate_jwt_token(token)
        assert "read" in claims["permissions"]
        assert "predict" in claims["permissions"]

    def test_create_token_default_permissions_from_role(self):
        token = create_jwt_token(user_id="u1", org_id="org1", role="member")
        claims = validate_jwt_token(token)
        assert set(claims["permissions"]) == set(ROLE_PERMISSIONS["member"])


class TestJWTValidation:
    def test_valid_token_roundtrip(self):
        token = create_jwt_token(user_id="test_user", org_id="org1", role="admin")
        claims = validate_jwt_token(token)
        assert claims["sub"] == "test_user"
        assert claims["org_id"] == "org1"
        assert claims["role"] == "admin"

    def test_invalid_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt_token("this.is.not.a.valid.token")
        assert exc_info.value.status_code == 401

    def test_empty_token_raises(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            validate_jwt_token("")

    def test_expired_token_raises(self):
        import jwt
        payload = {
            "sub": "user1", "org_id": "org1", "role": "admin",
            "permissions": [], "exp": int(time.time()) - 3600
        }
        expired_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            validate_jwt_token(expired_token)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_credentials_do_not_demo_bypass_by_default(self, monkeypatch):
        import api.auth as auth_module
        from fastapi import HTTPException

        monkeypatch.setattr(auth_module, "DEMO_MODE_ENABLED", False)
        with pytest.raises(HTTPException) as exc_info:
            await verify_jwt_token(None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_handle_login_requires_configured_admin_secret(self, monkeypatch):
        import hashlib

        monkeypatch.setenv("PIHU_ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("PIHU_ADMIN_PASSWORD_SHA256", hashlib.sha256(b"correct-password").hexdigest())
        result = await handle_login("admin@example.com", "correct-password")

        assert result["role"] == "admin"
        assert result["tenant_id"] == "tenant_admin"
        assert validate_jwt_token(result["token"])["sub"] == "tenant_admin"


class TestPermissions:
    def _make_claims(self, role="admin", permissions=None):
        return {
            "sub": "user1", "org_id": "org1", "role": role,
            "permissions": permissions or ROLE_PERMISSIONS.get(role, [])
        }

    def test_require_permission_passes(self):
        claims = self._make_claims(role="admin")
        require_permission(claims, "read")  # Should not raise

    def test_require_permission_fails(self):
        from fastapi import HTTPException
        claims = self._make_claims(role="viewer")  # Only has "read"
        with pytest.raises(HTTPException) as exc_info:
            require_permission(claims, "execute")
        assert exc_info.value.status_code == 403

    def test_require_role_passes(self):
        claims = self._make_claims(role="admin")
        require_role(claims, "admin")  # Should not raise

    def test_require_role_fails(self):
        from fastapi import HTTPException
        claims = self._make_claims(role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            require_role(claims, "admin")
        assert exc_info.value.status_code == 403

    def test_all_roles_have_read(self):
        for role, perms in ROLE_PERMISSIONS.items():
            assert "read" in perms, f"Role '{role}' missing 'read' permission"

    def test_owner_has_all_permissions(self):
        assert set(ROLE_PERMISSIONS["owner"]) == set(ALL_PERMISSIONS)
