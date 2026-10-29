"""Budget Enforcer with Redis atomic operations"""

import logging

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class BudgetExceededError(Exception):
    """Raised when budget limit would be exceeded"""


class BudgetEnforcer:
    """Hard budget enforcement with Redis atomic operations"""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def create_budget(self, user_id: str, period: str, limit_usd: float):
        """Create budget pool with limit"""
        if limit_usd <= 0:
            raise ValueError("Limit must be positive")

        key = f"budget:{user_id}:{period}"
        limit_key = f"{key}:limit"

        await self.redis.set(key, 0)
        await self.redis.set(limit_key, limit_usd)

        # Set expiry
        ttl = {"daily": 86400, "weekly": 604800, "monthly": 2592000}[period]
        await self.redis.expire(key, ttl)
        await self.redis.expire(limit_key, ttl)

        logger.info("Created $%s %s budget for %s", limit_usd, period, user_id)

    async def check_budget(self, user_id: str, period: str, cost: float) -> bool:
        """Check if cost can be deducted without exceeding limit"""
        key = f"budget:{user_id}:{period}"
        current = float(await self.redis.get(key) or 0)
        limit = float(await self.redis.get(f"{key}:limit") or 0)

        if limit == 0:  # No limit set
            return True

        return (current + cost) <= limit

    async def deduct_budget(self, user_id: str, period: str, cost: float):
        """Atomically deduct cost with budget check"""
        key = f"budget:{user_id}:{period}"

        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    current = float(await pipe.get(key) or 0)
                    limit = float(await pipe.get(f"{key}:limit") or 0)

                    if 0 < limit < current + cost:
                        raise BudgetExceededError(
                            f"Budget exceeded: ${current:.4f} + ${cost:.4f} > ${limit:.4f}"
                        )

                    pipe.multi()
                    pipe.incrbyfloat(key, cost)
                    await pipe.execute()
                    break
                except redis.WatchError:
                    continue  # Retry on concurrent modification

        logger.debug("Deducted $%.6f from %s %s budget", cost, user_id, period)

    async def get_status(self, user_id: str, period: str) -> dict:
        """Get budget status"""
        key = f"budget:{user_id}:{period}"
        current = float(await self.redis.get(key) or 0)
        limit = float(await self.redis.get(f"{key}:limit") or 0)

        return {
            "current_spend": current,
            "limit": limit,
            "remaining": max(0, limit - current),
            "utilization": (current / limit * 100) if limit > 0 else 0,
        }
