"""
Tests for api/tenant_manager.py — Organization lifecycle and member management.
"""
import pytest
import os
import json

os.environ["PIHU_ENV"] = "testing"

from api.tenant_manager import TenantManager

@pytest.fixture
def manager():
    return TenantManager()

class MockResult:
    def __init__(self, data=None):
        self.data = data
    def scalar_one_or_none(self):
        return self.data
    def scalars(self):
        class MockScalars:
            def all(self):
                return self.data if hasattr(self, 'data') else []
        s = MockScalars()
        s.data = self.data if isinstance(self.data, list) else [self.data] if self.data else []
        return s

class MockDB:
    def __init__(self, existing_data=None):
        self.existing_data = existing_data or {}
        self.added = []
        self.deleted = []
        self.committed = False
    
    async def execute(self, query):
        # Very simple mock that just returns predefined data based on what's being queried
        # In a real test suite this would use a sqlite in-memory db or a more complex mock
        q_str = str(query).lower()
        if "organization" in q_str:
            return MockResult(self.existing_data.get("org"))
        elif "tenant" in q_str:
            return MockResult(self.existing_data.get("tenant"))
        elif "apikey" in q_str:
            return MockResult(self.existing_data.get("apikey"))
        return MockResult()
        
    def add(self, item):
        self.added.append(item)
        
    async def delete(self, item):
        self.deleted.append(item)
        
    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
class TestTenantManager:
    async def test_create_organization_success(self, manager):
        db = MockDB()
        result = await manager.create_organization("org1", "Test Org", "user1", db, tier="pro")
        
        assert result["org_id"] == "org1"
        assert result["owner"] == "user1"
        assert result["tier"] == "pro"
        assert len(db.added) == 2  # Org + Owner Tenant
        assert db.committed is True

    async def test_create_organization_duplicate_raises(self, manager):
        # Mock DB returns an existing org
        class ExistingOrg: pass
        db = MockDB(existing_data={"org": ExistingOrg()})
        
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await manager.create_organization("org1", "Test", "user1", db)
        assert exc_info.value.status_code == 409

    async def test_create_api_key(self, manager):
        db = MockDB()
        result = await manager.create_api_key("user1", "org1", "Test Key", ["read"], db)
        
        assert "key" in result
        assert result["key"].startswith("pk_test_")
        assert "prefix" in result
        assert len(db.added) == 1
        assert db.committed is True

    async def test_verify_tenant_access_success(self, manager):
        class MockTenant:
            def has_permission(self, p): return p == "read"
            
        db = MockDB(existing_data={"tenant": MockTenant()})
        
        result = await manager.verify_tenant_access("user1", "org1", "read", db)
        assert result is True

    async def test_verify_tenant_access_denied(self, manager):
        class MockTenant:
            def has_permission(self, p): return False
            
        db = MockDB(existing_data={"tenant": MockTenant()})
        
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await manager.verify_tenant_access("user1", "org1", "execute", db)
        assert exc_info.value.status_code == 403
        
    async def test_verify_tenant_access_not_found(self, manager):
        db = MockDB(existing_data={"tenant": None})
        
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await manager.verify_tenant_access("user1", "org1", "read", db)
        assert exc_info.value.status_code == 403
