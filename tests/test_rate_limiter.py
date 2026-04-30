"""
Tests for api/rate_limiter.py — Redis sliding window limiter.
"""
import pytest
import os

os.environ["PIHU_ENV"] = "testing"

from api.rate_limiter import RateLimiter, MAX_REQUESTS_PER_MINUTE


@pytest.mark.asyncio
class TestRateLimiter:
    async def test_fail_open_when_redis_none(self):
        # When Redis is unavailable, it should not raise any exceptions
        limiter = RateLimiter()
        limiter.redis = None  # Simulate no redis
        
        # Should pass without raising HTTPException
        await limiter.check_rate_limit("user1")
        
    async def test_rate_limit_exceeded(self, monkeypatch):
        # We need to mock the Redis async client
        limiter = RateLimiter()
        
        class MockRedis:
            def __init__(self):
                self.counts = {}
            
            async def incr(self, key):
                self.counts[key] = self.counts.get(key, 0) + 1
                return self.counts[key]
                
            async def expire(self, key, seconds):
                pass
                
        limiter.redis = MockRedis()
        
        # Make MAX_REQUESTS_PER_MINUTE requests (should pass)
        for _ in range(MAX_REQUESTS_PER_MINUTE):
            await limiter.check_rate_limit("user1")
            
        # The next request should fail
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await limiter.check_rate_limit("user1")
        assert exc_info.value.status_code == 429
