"""
Tests for api/billing.py — Stripe integration, tiers, and quotas.
"""
import pytest
import os

os.environ["PIHU_ENV"] = "testing"

from api.billing import BillingEngine, TIER_CONFIG


class MockDB:
    def __init__(self, org=None, logs=None):
        self.org = org
        self.logs = logs or []
        self.added = []
        self.committed = False
        
    async def execute(self, query):
        class MockResult:
            def __init__(self, data): self.data = data
            def scalar_one_or_none(self): return self.data
            def scalars(self):
                class MockScalars:
                    def all(self, data): return data
                s = MockScalars()
                s.all = lambda: self.data
                return s
        
        q_str = str(query).lower()
        if "organization" in q_str:
            return MockResult(self.org)
        else:
            # Assume it's selecting TransactionLog.token_cost
            costs = [log.cost for log in self.logs] if self.logs else []
            return MockResult(costs)

    def add(self, item):
        self.added.append(item)
        
    async def flush(self):
        pass
        
    async def commit(self):
        self.committed = True


@pytest.fixture
def billing():
    return BillingEngine()


@pytest.mark.asyncio
class TestBillingEngine:
    async def test_tier_config_structure(self):
        assert "free" in TIER_CONFIG
        assert "pro" in TIER_CONFIG
        assert "enterprise" in TIER_CONFIG
        assert TIER_CONFIG["free"]["token_limit"] == 50_000

    async def test_log_transaction(self, billing):
        db = MockDB()
        await billing.log_transaction("u1", "org1", "chat", 150, db)
        
        assert len(db.added) == 1
        assert db.added[0].tenant_id == "u1"
        assert db.added[0].token_cost == 150
        assert db.committed is True

    async def test_verify_funding_free_tier_under_limit(self, billing):
        class MockOrg:
            subscription_tier = "free"
            token_limit = 50_000
            payment_status = "active"
            
        class MockLog:
            cost = 10_000
            
        db = MockDB(org=MockOrg(), logs=[MockLog(), MockLog()])  # Total: 20k
        
        result = await billing.verify_funding("u1", "org1", db)
        assert result["tier"] == "free"
        assert result["tokens_used"] == 20_000
        assert result["usage_percent"] == 40.0

    async def test_verify_funding_free_tier_over_limit_raises(self, billing):
        class MockOrg:
            subscription_tier = "free"
            token_limit = 50_000
            payment_status = "active"
            
        class MockLog:
            cost = 60_000
            
        db = MockDB(org=MockOrg(), logs=[MockLog()])
        
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await billing.verify_funding("u1", "org1", db)
        assert exc_info.value.status_code == 402  # Payment Required

    async def test_verify_funding_pro_tier_soft_limit_warning(self, billing):
        class MockOrg:
            subscription_tier = "pro"
            token_limit = 500_000
            payment_status = "active"
            
        class MockLog:
            cost = 600_000  # Over the soft limit, but pro tier allows overages
            
        db = MockDB(org=MockOrg(), logs=[MockLog()])
        
        result = await billing.verify_funding("u1", "org1", db)
        assert result["tokens_used"] == 600_000
        assert result["usage_percent"] == 120.0
        assert result["overage_allowed"] is True
        
    async def test_verify_funding_pro_tier_overage_allowed(self, billing):
        class MockOrg:
            subscription_tier = "pro"
            token_limit = 500_000
            payment_status = "active"
            
        class MockLog:
            cost = 2_000_000  # Pro overage
            
        db = MockDB(org=MockOrg(), logs=[MockLog()])
        
        result = await billing.verify_funding("u1", "org1", db)
        assert result["overage_allowed"] is True
        assert result["tokens_used"] == 2_000_000
