"""
Redis Cost Tracker - Real-time cost tracking with atomic operations

This module provides real-time cost tracking using Redis with atomic increment
operations and automatic expiry for daily/weekly/monthly budget periods.

Usage:
    from cost.redis_tracker import RedisCostTracker

    tracker = RedisCostTracker(redis_client)
    await tracker.track_cost(user_id="user123", tier=1, cost=0.000074)
    total = await tracker.get_total_cost(user_id="user123", period="daily")
"""

import logging
from typing import Any, Callable, Dict, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisCostTracker:
    """
    Real-time cost tracking using Redis with atomic operations.

    Features:
    - Atomic increment operations (INCRBYFLOAT)
    - Automatic expiry for budget periods
    - Per-user and per-tier tracking
    - <5ms latency per operation
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize cost tracker.

        Args:
            redis_client: Redis async client
        """
        self.redis = redis_client

    async def track_cost(
        self, user_id: str, tier: int, cost: float, period: str = "daily"
    ) -> float:
        """
        Track cost for a user and tier.

        Args:
            user_id: User identifier
            tier: LLM tier (0-4)
            cost: Cost in USD
            period: Budget period ("daily", "weekly", "monthly")

        Returns:
            New total cost for the period

        Raises:
            ValueError: If tier is invalid or cost is negative
        """
        if not 0 <= tier <= 4:
            raise ValueError(f"Tier must be 0-4, got {tier}")
        if cost < 0:
            raise ValueError(f"Cost must be non-negative, got {cost}")

        # Keys
        user_key = f"cost:{period}:{user_id}"
        tier_key = f"cost:{period}:tier:{tier}"
        global_key = f"cost:{period}:total"

        # Increment costs atomically
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incrbyfloat(user_key, cost)
            pipe.incrbyfloat(tier_key, cost)
            pipe.incrbyfloat(global_key, cost)

            # Set expiry if key is new
            ttl = self._get_ttl(period)
            pipe.expire(user_key, ttl, nx=True)
            pipe.expire(tier_key, ttl, nx=True)
            pipe.expire(global_key, ttl, nx=True)

            results = await pipe.execute()

        new_user_total = results[0]
        logger.debug(
            "Tracked $%.6f for user=%s, tier=%s, period=%s. New total: $%.6f",
            cost,
            user_id,
            tier,
            period,
            new_user_total,
        )

        return new_user_total

    async def get_total_cost(self, user_id: str, period: str = "daily") -> float:
        """
        Get total cost for a user in a period.

        Args:
            user_id: User identifier
            period: Budget period ("daily", "weekly", "monthly")

        Returns:
            Total cost in USD
        """
        key = f"cost:{period}:{user_id}"
        value = await self.redis.get(key)
        return float(value) if value else 0.0

    async def get_cost_by_tier(self, period: str = "daily") -> Dict[int, float]:
        """
        Get cost breakdown by tier.

        Args:
            period: Budget period ("daily", "weekly", "monthly")

        Returns:
            Dict mapping tier to cost, e.g., {0: 0.0, 1: 12.34, 3: 45.67}
        """
        pattern = f"cost:{period}:tier:*"
        costs = {}

        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)

            for key in keys:
                # Extract tier from key: "cost:daily:tier:1" -> 1
                tier_str = key.decode().split(":")[-1]
                tier = int(tier_str)

                value = await self.redis.get(key)
                costs[tier] = float(value) if value else 0.0

            if cursor == 0:
                break

        return costs

    async def get_global_cost(self, period: str = "daily") -> float:
        """
        Get total cost across all users and tiers.

        Args:
            period: Budget period ("daily", "weekly", "monthly")

        Returns:
            Total cost in USD
        """
        key = f"cost:{period}:total"
        value = await self.redis.get(key)
        return float(value) if value else 0.0

    async def reset_user_cost(self, user_id: str, period: str = "daily") -> None:
        """
        Reset cost for a user (e.g., manual budget reset).

        Args:
            user_id: User identifier
            period: Budget period ("daily", "weekly", "monthly")
        """
        key = f"cost:{period}:{user_id}"
        await self.redis.delete(key)
        logger.info("Reset cost for user=%s, period=%s", user_id, period)

    async def get_top_spenders(
        self, period: str = "daily", limit: int = 10
    ) -> list[tuple[str, float]]:
        """
        Get top N spenders for a period.

        Args:
            period: Budget period ("daily", "weekly", "monthly")
            limit: Number of top spenders to return

        Returns:
            List of (user_id, cost) tuples sorted by cost descending
        """
        pattern = f"cost:{period}:*"
        spenders = []

        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)

            for key in keys:
                key_str = key.decode()

                # Skip tier and total keys
                if ":tier:" in key_str or ":total" in key_str:
                    continue

                # Extract user_id: "cost:daily:user123" -> "user123"
                user_id = key_str.split(":")[-1]

                value = await self.redis.get(key)
                if value:
                    spenders.append((user_id, float(value)))

            if cursor == 0:
                break

        # Sort by cost descending and return top N
        spenders.sort(key=lambda x: x[1], reverse=True)
        return spenders[:limit]

    def _get_ttl(self, period: str) -> int:
        """
        Get TTL in seconds for a budget period.

        Args:
            period: Budget period ("daily", "weekly", "monthly")

        Returns:
            TTL in seconds
        """
        if period == "daily":
            return 86400  # 24 hours
        if period == "weekly":
            return 604800  # 7 days
        if period == "monthly":
            return 2592000  # 30 days
        raise ValueError(f"Invalid period: {period}")


class CostAlertManager:
    """
    Manager for cost alert thresholds and notifications.

    Sends alerts when users approach budget limits (80%, 90%, 95%).
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        alert_callback: Optional[Callable[..., Any]] = None,
    ):
        """
        Initialize alert manager.

        Args:
            redis_client: Redis async client
            alert_callback: Async function to call when alert is triggered
                           Signature: async def callback(user_id, utilization, period)
        """
        self.redis = redis_client
        self.alert_callback = alert_callback
        self.thresholds = [0.80, 0.90, 0.95]  # 80%, 90%, 95%

    async def check_and_alert(
        self, user_id: str, current_spend: float, budget_limit: float, period: str
    ) -> None:
        """
        Check if user has crossed alert thresholds and send alerts.

        Args:
            user_id: User identifier
            current_spend: Current spending
            budget_limit: Budget limit
            period: Budget period
        """
        if budget_limit <= 0:
            return

        utilization = current_spend / budget_limit

        for threshold in self.thresholds:
            # Check if we've crossed this threshold
            if utilization >= threshold:
                # Check if we've already alerted for this threshold
                alert_key = f"alert:{period}:{user_id}:{int(threshold * 100)}"

                # Set alert flag (expires with budget period)
                was_set = await self.redis.set(
                    alert_key, "1", nx=True, ex=self._get_period_ttl(period)
                )

                # If flag was just set (not already present), send alert
                if was_set and self.alert_callback:
                    await self.alert_callback(user_id, utilization, period)
                    logger.info(
                        "Alert sent: user=%s, utilization=%.1f%%, period=%s, threshold=%.0f%%",
                        user_id,
                        utilization * 100,
                        period,
                        threshold * 100,
                    )

    def _get_period_ttl(self, period: str) -> int:
        """Get TTL for period (same as cost tracker)"""
        if period == "daily":
            return 86400
        if period == "weekly":
            return 604800
        if period == "monthly":
            return 2592000
        return 86400


# Example usage
if __name__ == "__main__":
    import asyncio

    async def example():
        # Create Redis client
        redis_client = await redis.from_url("redis://localhost:6379")

        # Initialize tracker
        tracker = RedisCostTracker(redis_client)

        # Track some costs
        await tracker.track_cost(user_id="user123", tier=1, cost=0.000074)
        await tracker.track_cost(user_id="user123", tier=1, cost=0.000050)
        await tracker.track_cost(user_id="user456", tier=3, cost=0.005)

        # Get totals
        user_cost = await tracker.get_total_cost("user123", period="daily")
        print(f"User123 daily cost: ${user_cost:.6f}")

        tier_costs = await tracker.get_cost_by_tier(period="daily")
        print(f"Cost by tier: {tier_costs}")

        global_cost = await tracker.get_global_cost(period="daily")
        print(f"Global daily cost: ${global_cost:.6f}")

        top_spenders = await tracker.get_top_spenders(period="daily", limit=5)
        print(f"Top spenders: {top_spenders}")

        # Alert example
        async def send_alert(user_id, utilization, period):
            print(f"ALERT: User {user_id} at {utilization:.1%} of {period} budget!")

        alert_mgr = CostAlertManager(redis_client, alert_callback=send_alert)
        await alert_mgr.check_and_alert(
            user_id="user123", current_spend=8.5, budget_limit=10.0, period="daily"
        )

        await redis_client.close()

    asyncio.run(example())
