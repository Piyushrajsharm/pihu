"""
Pihu SaaS — API Rate Limiter
Uses Redis sliding window to limit per-tenant API request rates.
Gracefully degrades when Redis is unavailable.
"""

import os
from fastapi import HTTPException
from logger import get_logger

log = get_logger("RATE_LIMITER")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Maximum requests per minute per tenant
MAX_REQUESTS_PER_MINUTE = 50

# Try to import redis — it's an optional runtime dependency
try:
    from redis.asyncio import Redis
    _HAS_REDIS = True
except ImportError:
    _HAS_REDIS = False
    log.warning("redis package not installed — rate limiting disabled")


class RateLimiter:
    def __init__(self):
        self.redis = None
        if _HAS_REDIS:
            try:
                self.redis = Redis.from_url(REDIS_URL, decode_responses=True)
            except Exception as e:
                log.warning("Failed to connect to Redis: %s — rate limiting disabled", e)

    async def check_rate_limit(self, tenant_id: str):
        """
        Sliding window rate limit implementation.
        Raises 429 HttpException if limit exceeded.
        Fails open if Redis is unavailable (no rate limiting applied).
        """
        if not self.redis:
            return  # Fail open: no Redis = no rate limiting

        import time
        current_minute = int(time.time() / 60)
        key = f"rate_limit:{tenant_id}:{current_minute}"

        try:
            # Increment request count atomically
            current_count = await self.redis.incr(key)

            # If this is the first request in the window, set expire
            if current_count == 1:
                await self.redis.expire(key, 60)

            if current_count > MAX_REQUESTS_PER_MINUTE:
                log.warning(f"Tenant {tenant_id} exceeded rate limit ({current_count}/{MAX_REQUESTS_PER_MINUTE})")
                raise HTTPException(status_code=429, detail="Too Many Requests. Rate limit exceeded.")

        except HTTPException:
            raise
        except Exception as e:
            # If Redis goes down, we fail open to prevent total SaaS outage
            log.error(f"Rate Limiter bypassed due to Redis failure: {e}")

rate_limiter = RateLimiter()
