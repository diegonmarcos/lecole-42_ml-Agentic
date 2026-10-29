"""
Performance Metrics Aggregation - TASK-040

Aggregates LLM metrics for real-time analytics:
- Redis for real-time counters and aggregations
- TimescaleDB continuous aggregates for time-series data
- Materialized views for fast queries
- Automatic rollup from 1-minute to 1-hour to 1-day buckets
- HyperLogLog for cardinality estimation
- Percentile approximation with t-digest
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    import asyncpg
    import redis.asyncio as redis
except ImportError:
    asyncpg = None  # type: ignore[assignment]
    redis = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class AggregationPeriod(Enum):
    """Aggregation time periods"""

    ONE_MINUTE = "1 minute"
    FIVE_MINUTES = "5 minutes"
    ONE_HOUR = "1 hour"
    ONE_DAY = "1 day"


@dataclass
class MetricSnapshot:
    """Point-in-time metric snapshot"""

    timestamp: datetime
    invocations: int
    successes: int
    failures: int
    total_cost: float
    total_tokens: int
    avg_latency: float
    p95_latency: float
    p99_latency: float
    unique_users: int


class PerformanceMetricsAggregator:
    """
    Aggregates performance metrics using Redis + TimescaleDB.

    Redis: Real-time counters, rolling windows
    TimescaleDB: Continuous aggregates, materialized views

    Usage:
        aggregator = PerformanceMetricsAggregator(redis_client, db_pool)

        # Record invocation
        await aggregator.record_invocation(
            provider="fireworks",
            tier="tier-1",
            model="llama-70b",
            success=True,
            cost=0.05,
            tokens=1500,
            latency=1.2,
            user_id="user_123"
        )

        # Get real-time metrics (last 5 minutes)
        metrics = await aggregator.get_realtime_metrics(minutes=5)

        # Get historical aggregates
        hourly = await aggregator.get_hourly_aggregates(days=7)
    """

    def __init__(self, redis_client: redis.Redis, db_pool: asyncpg.Pool):
        """
        Initialize metrics aggregator.

        Args:
            redis_client: Redis client for real-time aggregation
            db_pool: PostgreSQL connection pool (with TimescaleDB)
        """
        self.redis = redis_client
        self.db = db_pool

    async def setup_timescaledb_aggregates(self):
        """
        Create TimescaleDB continuous aggregates.

        Must be run once during setup to create materialized views.
        """
        # 1-minute continuous aggregate
        query_1min = """
        CREATE MATERIALIZED VIEW IF NOT EXISTS llm_metrics_1min
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 minute', timestamp) AS bucket,
            provider,
            tier,
            COUNT(*) AS invocations,
            SUM(CASE WHEN success THEN 1 ELSE 0 END) AS successes,
            SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) AS failures,
            SUM(cost) AS total_cost,
            SUM(total_tokens) AS total_tokens,
            AVG(duration) AS avg_latency,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration) AS p95_latency,
            PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration) AS p99_latency
        FROM llm_invocations
        GROUP BY bucket, provider, tier
        WITH NO DATA;
        """

        # 1-hour continuous aggregate (rollup from 1-minute)
        query_1hour = """
        CREATE MATERIALIZED VIEW IF NOT EXISTS llm_metrics_1hour
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', bucket) AS bucket,
            provider,
            tier,
            SUM(invocations) AS invocations,
            SUM(successes) AS successes,
            SUM(failures) AS failures,
            SUM(total_cost) AS total_cost,
            SUM(total_tokens) AS total_tokens,
            AVG(avg_latency) AS avg_latency,
            MAX(p95_latency) AS p95_latency,
            MAX(p99_latency) AS p99_latency
        FROM llm_metrics_1min
        GROUP BY bucket, provider, tier
        WITH NO DATA;
        """

        # 1-day continuous aggregate (rollup from 1-hour)
        query_1day = """
        CREATE MATERIALIZED VIEW IF NOT EXISTS llm_metrics_1day
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 day', bucket) AS bucket,
            provider,
            tier,
            SUM(invocations) AS invocations,
            SUM(successes) AS successes,
            SUM(failures) AS failures,
            SUM(total_cost) AS total_cost,
            SUM(total_tokens) AS total_tokens,
            AVG(avg_latency) AS avg_latency,
            MAX(p95_latency) AS p95_latency,
            MAX(p99_latency) AS p99_latency
        FROM llm_metrics_1hour
        GROUP BY bucket, provider, tier
        WITH NO DATA;
        """

        # Refresh policies
        policy_1min = """
        SELECT add_continuous_aggregate_policy('llm_metrics_1min',
            start_offset => INTERVAL '1 day',
            end_offset => INTERVAL '1 minute',
            schedule_interval => INTERVAL '1 minute');
        """

        policy_1hour = """
        SELECT add_continuous_aggregate_policy('llm_metrics_1hour',
            start_offset => INTERVAL '7 days',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour');
        """

        policy_1day = """
        SELECT add_continuous_aggregate_policy('llm_metrics_1day',
            start_offset => INTERVAL '30 days',
            end_offset => INTERVAL '1 day',
            schedule_interval => INTERVAL '1 day');
        """

        try:
            await self.db.execute(query_1min)
            await self.db.execute(query_1hour)
            await self.db.execute(query_1day)

            # Add refresh policies (ignore errors if already exist)
            try:
                await self.db.execute(policy_1min)
                await self.db.execute(policy_1hour)
                await self.db.execute(policy_1day)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug("Refresh policies may already exist: %s", e)

            logger.info("TimescaleDB continuous aggregates created successfully")

        except Exception as e:
            logger.error("Failed to create continuous aggregates: %s", e)
            raise

    async def record_invocation(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        provider: str,
        tier: str,
        model: str,  # pylint: disable=unused-argument  # not aggregated per model
        success: bool,
        cost: float,
        tokens: int,
        latency: float,
        user_id: str,
        timestamp: Optional[datetime] = None,
    ):
        """
        Record LLM invocation for real-time aggregation.

        Updates Redis counters for instant metrics.
        PostgreSQL insertion is handled by provider router.

        Args:
            provider: Provider name
            tier: Tier level
            model: Model name
            success: Success/failure flag
            cost: Invocation cost
            tokens: Total tokens
            latency: Latency in seconds
            user_id: User identifier
            timestamp: Event timestamp (defaults to now)
        """
        ts = timestamp or datetime.utcnow()
        minute_bucket = ts.replace(second=0, microsecond=0)
        minute_key = f"metrics:1min:{minute_bucket.isoformat()}"

        # Use Redis pipeline for atomic updates
        async with self.redis.pipeline(transaction=True) as pipe:
            # Overall counters
            pipe.hincrby(minute_key, "invocations", 1)
            pipe.hincrby(minute_key, "successes" if success else "failures", 1)
            pipe.hincrbyfloat(minute_key, "total_cost", cost)
            pipe.hincrby(minute_key, "total_tokens", tokens)

            # Provider-specific counters
            provider_key = f"{minute_key}:provider:{provider}"
            pipe.hincrby(provider_key, "invocations", 1)
            pipe.hincrbyfloat(provider_key, "total_cost", cost)

            # Tier-specific counters
            tier_key = f"{minute_key}:tier:{tier}"
            pipe.hincrby(tier_key, "invocations", 1)
            pipe.hincrbyfloat(tier_key, "total_cost", cost)

            # Track unique users with HyperLogLog
            users_key = f"{minute_key}:users"
            pipe.pfadd(users_key, user_id)

            # Store latency for percentile calculation (use sorted set)
            latency_key = f"{minute_key}:latencies"
            pipe.zadd(latency_key, {f"{ts.timestamp()}:{latency}": latency})

            # Set expiration (keep 1 hour in Redis, rest in PostgreSQL)
            pipe.expire(minute_key, 3600)
            pipe.expire(provider_key, 3600)
            pipe.expire(tier_key, 3600)
            pipe.expire(users_key, 3600)
            pipe.expire(latency_key, 3600)

            await pipe.execute()

    async def get_realtime_metrics(  # pylint: disable=too-many-locals
        self,
        minutes: int = 5,
        provider: Optional[str] = None,
        tier: Optional[str] = None,
    ) -> MetricSnapshot:
        """
        Get real-time metrics from Redis (last N minutes).

        Args:
            minutes: Number of minutes to aggregate
            provider: Filter by provider (optional)
            tier: Filter by tier (optional)

        Returns:
            MetricSnapshot with aggregated metrics
        """
        now = datetime.utcnow()
        start = now - timedelta(minutes=minutes)

        invocations = 0
        successes = 0
        failures = 0
        total_cost = 0.0
        total_tokens = 0
        latencies = []
        unique_users_hlls = []

        # Iterate through minute buckets
        current = start.replace(second=0, microsecond=0)
        while current <= now:
            minute_key = f"metrics:1min:{current.isoformat()}"

            # Get base metrics or filtered metrics
            if provider:
                key = f"{minute_key}:provider:{provider}"
            elif tier:
                key = f"{minute_key}:tier:{tier}"
            else:
                key = minute_key

            # Fetch metrics
            metrics = await self.redis.hgetall(key)

            if metrics:
                invocations += int(metrics.get(b"invocations", 0))
                successes += int(metrics.get(b"successes", 0))
                failures += int(metrics.get(b"failures", 0))
                total_cost += float(metrics.get(b"total_cost", 0.0))
                total_tokens += int(metrics.get(b"total_tokens", 0))

            # Get latencies for percentile calculation
            latency_key = f"{minute_key}:latencies"
            minute_latencies = await self.redis.zrange(
                latency_key, 0, -1, withscores=True
            )
            latencies.extend([float(score) for _, score in minute_latencies])

            # Get unique users HLL
            users_key = f"{minute_key}:users"
            if await self.redis.exists(users_key):
                unique_users_hlls.append(users_key)

            current += timedelta(minutes=1)

        # Calculate derived metrics
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0

        # Calculate percentiles
        if latencies:
            latencies.sort()
            p95_idx = int(len(latencies) * 0.95)
            p99_idx = int(len(latencies) * 0.99)
            p95_latency = (
                latencies[p95_idx] if p95_idx < len(latencies) else latencies[-1]
            )
            p99_latency = (
                latencies[p99_idx] if p99_idx < len(latencies) else latencies[-1]
            )
        else:
            p95_latency = 0.0
            p99_latency = 0.0

        # Merge HyperLogLogs for unique user count
        if unique_users_hlls:
            merged_key = f"temp:users:{now.timestamp()}"
            await self.redis.pfmerge(merged_key, *unique_users_hlls)
            unique_users = await self.redis.pfcount(merged_key)
            await self.redis.delete(merged_key)
        else:
            unique_users = 0

        return MetricSnapshot(
            timestamp=now,
            invocations=invocations,
            successes=successes,
            failures=failures,
            total_cost=total_cost,
            total_tokens=total_tokens,
            avg_latency=avg_latency,
            p95_latency=p95_latency,
            p99_latency=p99_latency,
            unique_users=unique_users,
        )

    async def get_hourly_aggregates(
        self, days: int = 7, provider: Optional[str] = None, tier: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get hourly aggregates from TimescaleDB materialized view.

        Args:
            days: Number of days to query
            provider: Filter by provider (optional)
            tier: Filter by tier (optional)

        Returns:
            List of hourly aggregate records
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        query = """
        SELECT
            bucket,
            provider,
            tier,
            invocations,
            successes,
            failures,
            total_cost,
            total_tokens,
            avg_latency,
            p95_latency,
            p99_latency
        FROM llm_metrics_1hour
        WHERE bucket >= $1
        """

        params: List[Any] = [start_time]

        if provider:
            query += " AND provider = $2"
            params.append(provider)

        if tier:
            query += f" AND tier = ${len(params) + 1}"
            params.append(tier)

        query += " ORDER BY bucket DESC"

        rows = await self.db.fetch(query, *params)

        return [
            {
                "timestamp": row["bucket"].isoformat(),
                "provider": row["provider"],
                "tier": row["tier"],
                "invocations": row["invocations"],
                "successes": row["successes"],
                "failures": row["failures"],
                "success_rate": row["successes"] / row["invocations"]
                if row["invocations"] > 0
                else 0.0,
                "total_cost": float(row["total_cost"]),
                "total_tokens": row["total_tokens"],
                "avg_latency": float(row["avg_latency"]),
                "p95_latency": float(row["p95_latency"]),
                "p99_latency": float(row["p99_latency"]),
            }
            for row in rows
        ]

    async def get_daily_aggregates(
        self, days: int = 30, provider: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get daily aggregates from TimescaleDB materialized view.

        Args:
            days: Number of days to query
            provider: Filter by provider (optional)

        Returns:
            List of daily aggregate records
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        query = """
        SELECT
            bucket,
            provider,
            tier,
            invocations,
            successes,
            failures,
            total_cost,
            total_tokens,
            avg_latency,
            p95_latency,
            p99_latency
        FROM llm_metrics_1day
        WHERE bucket >= $1
        """

        params: List[Any] = [start_time]

        if provider:
            query += " AND provider = $2"
            params.append(provider)

        query += " ORDER BY bucket DESC"

        rows = await self.db.fetch(query, *params)

        return [
            {
                "date": row["bucket"].date().isoformat(),
                "provider": row["provider"],
                "tier": row["tier"],
                "invocations": row["invocations"],
                "successes": row["successes"],
                "failures": row["failures"],
                "success_rate": row["successes"] / row["invocations"]
                if row["invocations"] > 0
                else 0.0,
                "total_cost": float(row["total_cost"]),
                "total_tokens": row["total_tokens"],
                "avg_latency": float(row["avg_latency"]),
                "p95_latency": float(row["p95_latency"]),
                "p99_latency": float(row["p99_latency"]),
            }
            for row in rows
        ]

    async def get_top_spenders(
        self, period: AggregationPeriod = AggregationPeriod.ONE_DAY, limit: int = 10
    ) -> List[Tuple[str, float]]:
        """
        Get top spending providers for a period.

        Args:
            period: Aggregation period
            limit: Number of results

        Returns:
            List of (provider, cost) tuples
        """
        if period == AggregationPeriod.ONE_DAY:
            table = "llm_metrics_1day"
            cutoff = datetime.utcnow() - timedelta(days=1)
        elif period == AggregationPeriod.ONE_HOUR:
            table = "llm_metrics_1hour"
            cutoff = datetime.utcnow() - timedelta(hours=1)
        else:
            # Default to 1-minute for real-time
            return await self._get_top_spenders_realtime(limit)

        query = f"""
        SELECT
            provider,
            SUM(total_cost) as total_cost
        FROM {table}
        WHERE bucket >= $1
        GROUP BY provider
        ORDER BY total_cost DESC
        LIMIT $2
        """

        rows = await self.db.fetch(query, cutoff, limit)

        return [(row["provider"], float(row["total_cost"])) for row in rows]

    async def _get_top_spenders_realtime(self, limit: int) -> List[Tuple[str, float]]:
        """Get top spenders from Redis (last 5 minutes)"""
        now = datetime.utcnow()
        start = now - timedelta(minutes=5)

        provider_costs: Dict[str, float] = {}

        current = start.replace(second=0, microsecond=0)
        while current <= now:
            minute_key = f"metrics:1min:{current.isoformat()}"

            # Scan for provider keys
            pattern = f"{minute_key}:provider:*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)

                for key in keys:
                    if isinstance(key, bytes):
                        key = key.decode()

                    provider = key.split(":")[-1]
                    cost = await self.redis.hget(key, "total_cost")

                    if cost:
                        provider_costs[provider] = provider_costs.get(
                            provider, 0.0
                        ) + float(cost)

                if cursor == 0:
                    break

            current += timedelta(minutes=1)

        # Sort and limit
        sorted_providers = sorted(
            provider_costs.items(), key=lambda x: x[1], reverse=True
        )

        return sorted_providers[:limit]

    async def refresh_materialized_views(self):
        """Manually refresh all materialized views (for testing/admin)"""
        await self.db.execute(
            "CALL refresh_continuous_aggregate('llm_metrics_1min', NULL, NULL)"
        )
        await self.db.execute(
            "CALL refresh_continuous_aggregate('llm_metrics_1hour', NULL, NULL)"
        )
        await self.db.execute(
            "CALL refresh_continuous_aggregate('llm_metrics_1day', NULL, NULL)"
        )

        logger.info("Materialized views refreshed")


# Example usage
if __name__ == "__main__":

    async def main():
        # Initialize
        redis_client = redis.from_url("redis://localhost:6379")
        db_pool = await asyncpg.create_pool(
            host="localhost",
            port=5432,
            database="llm_metrics",
            user="postgres",
            password="postgres",
        )

        aggregator = PerformanceMetricsAggregator(redis_client, db_pool)

        # Setup TimescaleDB (run once)
        await aggregator.setup_timescaledb_aggregates()

        # Record invocations
        for i in range(100):
            await aggregator.record_invocation(
                provider="fireworks",
                tier="tier-1",
                model="llama-70b",
                success=True,
                cost=0.05,
                tokens=1500,
                latency=1.2,
                user_id=f"user_{i % 10}",
            )

        # Get real-time metrics (last 5 minutes)
        realtime = await aggregator.get_realtime_metrics(minutes=5)
        print("\nReal-time metrics (last 5 min):")
        print(f"  Invocations: {realtime.invocations}")
        print(f"  Success rate: {realtime.successes / realtime.invocations:.1%}")
        print(f"  Total cost: ${realtime.total_cost:.2f}")
        print(f"  Avg latency: {realtime.avg_latency:.2f}s")
        print(f"  P95 latency: {realtime.p95_latency:.2f}s")
        print(f"  Unique users: {realtime.unique_users}")

        # Get hourly aggregates
        hourly = await aggregator.get_hourly_aggregates(days=7)
        print(f"\nHourly aggregates (last 7 days): {len(hourly)} records")

        # Get top spenders
        top_spenders = await aggregator.get_top_spenders(
            period=AggregationPeriod.ONE_DAY
        )
        print("\nTop spenders (last 24h):")
        for provider, cost in top_spenders:
            print(f"  {provider}: ${cost:.2f}")

        # Cleanup
        redis_client.close()
        await redis_client.wait_closed()
        await db_pool.close()

    asyncio.run(main())
