"""
Provider Analytics - TASK-039

Comprehensive analytics for LLM provider performance:
- Cost breakdown by provider and tier
- Latency percentiles (P50, P95, P99)
- Success rate tracking
- Token usage analysis
- Provider comparison
- Real-time alerts
- Trend analysis

Integrates with PostgreSQL + TimescaleDB for time-series data.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

try:
    import asyncpg
except ImportError:
    asyncpg = None


logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class ProviderMetrics:  # pylint: disable=too-many-instance-attributes
    """Aggregated provider metrics"""

    provider_name: str
    tier: str
    invocations: int
    successes: int
    failures: int
    total_cost: float
    total_tokens: int
    total_latency: float

    # Derived metrics
    success_rate: float = 0.0
    avg_cost: float = 0.0
    avg_latency: float = 0.0
    avg_tokens: int = 0

    # Percentiles
    latency_p50: Optional[float] = None
    latency_p95: Optional[float] = None
    latency_p99: Optional[float] = None

    def calculate_derived_metrics(self):
        """Calculate derived metrics"""
        if self.invocations > 0:
            self.success_rate = self.successes / self.invocations
            self.avg_cost = self.total_cost / self.invocations
            self.avg_latency = self.total_latency / self.invocations
            self.avg_tokens = self.total_tokens / self.invocations


@dataclass
class CostBreakdown:
    """Cost breakdown analysis"""

    total_cost: float
    by_provider: Dict[str, float]
    by_tier: Dict[str, float]
    by_model: Dict[str, float]
    top_spenders: List[Tuple[str, float]]  # (provider, cost)


@dataclass
class PerformanceAnalysis:
    """Performance analysis"""

    avg_latency: float
    latency_by_provider: Dict[str, float]
    latency_by_tier: Dict[str, float]
    percentiles: Dict[str, Dict[str, float]]  # {provider: {p50, p95, p99}}


@dataclass
class UsageAnalysis:
    """Token usage analysis"""

    total_tokens: int
    by_provider: Dict[str, int]
    by_tier: Dict[str, int]
    avg_tokens_per_request: float


@dataclass
class Alert:
    """Performance alert"""

    alert_id: str
    severity: AlertSeverity
    message: str
    provider: Optional[str]
    metric: str
    value: float
    threshold: float
    timestamp: datetime


class ProviderAnalyticsEngine:
    """
    Provider analytics engine.

    Usage:
        engine = ProviderAnalyticsEngine(db_pool)

        # Get cost breakdown
        breakdown = await engine.get_cost_breakdown(days=7)
        print(f"Total cost: ${breakdown.total_cost:.2f}")
        print(f"By provider: {breakdown.by_provider}")

        # Get performance metrics
        performance = await engine.get_performance_analysis(days=7)
        print(f"Avg latency: {performance.avg_latency:.2f}s")

        # Check for alerts
        alerts = await engine.check_alerts()
        for alert in alerts:
            print(f"[{alert.severity.value}] {alert.message}")
    """

    def __init__(self, db_pool: asyncpg.Pool):
        """
        Initialize analytics engine.

        Args:
            db_pool: AsyncPG connection pool to PostgreSQL/TimescaleDB
        """
        self.db = db_pool
        self.alert_thresholds = {
            "cost_per_request": 0.50,  # $0.50 per request
            "latency_p95": 5.0,  # 5 seconds
            "failure_rate": 0.10,  # 10% failure rate
            "cost_increase": 1.5,  # 50% increase from baseline
        }

    async def get_cost_breakdown(
        self, days: int = 7, provider: Optional[str] = None
    ) -> CostBreakdown:
        """
        Get cost breakdown analysis.

        Args:
            days: Number of days to analyze
            provider: Filter by provider (optional)

        Returns:
            CostBreakdown with detailed cost analysis
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        # Total cost
        query_total = """
            SELECT COALESCE(SUM(cost), 0) as total_cost
            FROM llm_invocations
            WHERE timestamp >= $1
            AND ($2::TEXT IS NULL OR provider = $2)
            AND success = true
        """

        total_row = await self.db.fetchrow(query_total, start_time, provider)
        total_cost = float(total_row["total_cost"])

        # Cost by provider
        query_by_provider = """
            SELECT provider, COALESCE(SUM(cost), 0) as cost
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY provider
            ORDER BY cost DESC
        """

        provider_rows = await self.db.fetch(query_by_provider, start_time)
        by_provider = {row["provider"]: float(row["cost"]) for row in provider_rows}

        # Cost by tier
        query_by_tier = """
            SELECT tier, COALESCE(SUM(cost), 0) as cost
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY tier
            ORDER BY cost DESC
        """

        tier_rows = await self.db.fetch(query_by_tier, start_time)
        by_tier = {row["tier"]: float(row["cost"]) for row in tier_rows}

        # Cost by model
        query_by_model = """
            SELECT model, COALESCE(SUM(cost), 0) as cost
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY model
            ORDER BY cost DESC
            LIMIT 10
        """

        model_rows = await self.db.fetch(query_by_model, start_time)
        by_model = {row["model"]: float(row["cost"]) for row in model_rows}

        # Top spenders
        top_spenders = [
            (row["provider"], float(row["cost"])) for row in provider_rows[:5]
        ]

        return CostBreakdown(
            total_cost=total_cost,
            by_provider=by_provider,
            by_tier=by_tier,
            by_model=by_model,
            top_spenders=top_spenders,
        )

    async def get_performance_analysis(
        self, days: int = 7, provider: Optional[str] = None
    ) -> PerformanceAnalysis:
        """
        Get performance analysis.

        Args:
            days: Number of days to analyze
            provider: Filter by provider (optional)

        Returns:
            PerformanceAnalysis with latency metrics
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        # Average latency
        query_avg = """
            SELECT AVG(duration) as avg_latency
            FROM llm_invocations
            WHERE timestamp >= $1
            AND ($2::TEXT IS NULL OR provider = $2)
            AND success = true
        """

        avg_row = await self.db.fetchrow(query_avg, start_time, provider)
        avg_latency = float(avg_row["avg_latency"]) if avg_row["avg_latency"] else 0.0

        # Latency by provider
        query_by_provider = """
            SELECT provider, AVG(duration) as avg_latency
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY provider
            ORDER BY avg_latency DESC
        """

        provider_rows = await self.db.fetch(query_by_provider, start_time)
        latency_by_provider = {
            row["provider"]: float(row["avg_latency"]) for row in provider_rows
        }

        # Latency by tier
        query_by_tier = """
            SELECT tier, AVG(duration) as avg_latency
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY tier
            ORDER BY avg_latency DESC
        """

        tier_rows = await self.db.fetch(query_by_tier, start_time)
        latency_by_tier = {row["tier"]: float(row["avg_latency"]) for row in tier_rows}

        # Percentiles by provider
        query_percentiles = """
            SELECT
                provider,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration) as p50,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration) as p95,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration) as p99
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY provider
        """

        percentile_rows = await self.db.fetch(query_percentiles, start_time)
        percentiles = {}

        for row in percentile_rows:
            percentiles[row["provider"]] = {
                "p50": float(row["p50"]),
                "p95": float(row["p95"]),
                "p99": float(row["p99"]),
            }

        return PerformanceAnalysis(
            avg_latency=avg_latency,
            latency_by_provider=latency_by_provider,
            latency_by_tier=latency_by_tier,
            percentiles=percentiles,
        )

    async def get_usage_analysis(
        self, days: int = 7, provider: Optional[str] = None
    ) -> UsageAnalysis:
        """
        Get token usage analysis.

        Args:
            days: Number of days to analyze
            provider: Filter by provider (optional)

        Returns:
            UsageAnalysis with token metrics
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        # Total tokens
        query_total = """
            SELECT
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COUNT(*) as invocations
            FROM llm_invocations
            WHERE timestamp >= $1
            AND ($2::TEXT IS NULL OR provider = $2)
            AND success = true
        """

        total_row = await self.db.fetchrow(query_total, start_time, provider)
        total_tokens = int(total_row["total_tokens"])
        invocations = int(total_row["invocations"])
        avg_tokens = total_tokens / invocations if invocations > 0 else 0

        # Tokens by provider
        query_by_provider = """
            SELECT provider, COALESCE(SUM(total_tokens), 0) as total_tokens
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY provider
            ORDER BY total_tokens DESC
        """

        provider_rows = await self.db.fetch(query_by_provider, start_time)
        by_provider = {
            row["provider"]: int(row["total_tokens"]) for row in provider_rows
        }

        # Tokens by tier
        query_by_tier = """
            SELECT tier, COALESCE(SUM(total_tokens), 0) as total_tokens
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY tier
            ORDER BY total_tokens DESC
        """

        tier_rows = await self.db.fetch(query_by_tier, start_time)
        by_tier = {row["tier"]: int(row["total_tokens"]) for row in tier_rows}

        return UsageAnalysis(
            total_tokens=total_tokens,
            by_provider=by_provider,
            by_tier=by_tier,
            avg_tokens_per_request=avg_tokens,
        )

    async def get_provider_metrics(
        self, provider: str, days: int = 7
    ) -> ProviderMetrics:
        """
        Get comprehensive metrics for specific provider.

        Args:
            provider: Provider name
            days: Number of days to analyze

        Returns:
            ProviderMetrics with detailed stats
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        # Aggregate metrics
        query = """
            SELECT
                provider,
                tier,
                COUNT(*) as invocations,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failures,
                COALESCE(SUM(cost), 0) as total_cost,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(duration), 0) as total_latency,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY duration) as p50,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration) as p95,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration) as p99
            FROM llm_invocations
            WHERE timestamp >= $1
            AND provider = $2
            GROUP BY provider, tier
        """

        row = await self.db.fetchrow(query, start_time, provider)

        if not row:
            return ProviderMetrics(
                provider_name=provider,
                tier="",
                invocations=0,
                successes=0,
                failures=0,
                total_cost=0.0,
                total_tokens=0,
                total_latency=0.0,
            )

        metrics = ProviderMetrics(
            provider_name=row["provider"],
            tier=row["tier"],
            invocations=row["invocations"],
            successes=row["successes"],
            failures=row["failures"],
            total_cost=float(row["total_cost"]),
            total_tokens=int(row["total_tokens"]),
            total_latency=float(row["total_latency"]),
            latency_p50=float(row["p50"]) if row["p50"] else None,
            latency_p95=float(row["p95"]) if row["p95"] else None,
            latency_p99=float(row["p99"]) if row["p99"] else None,
        )

        metrics.calculate_derived_metrics()

        return metrics

    async def check_alerts(self, days: int = 1) -> List[Alert]:
        """
        Check for performance alerts.

        Args:
            days: Number of days to check

        Returns:
            List of Alert objects
        """
        alerts = []
        start_time = datetime.utcnow() - timedelta(days=days)

        # Check cost per request
        query_cost = """
            SELECT
                provider,
                AVG(cost) as avg_cost
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY provider
        """

        cost_rows = await self.db.fetch(query_cost, start_time)

        for row in cost_rows:
            avg_cost = float(row["avg_cost"])
            if avg_cost > self.alert_thresholds["cost_per_request"]:
                alerts.append(
                    Alert(
                        alert_id=f"cost_{row['provider']}_{int(datetime.utcnow().timestamp())}",
                        severity=AlertSeverity.WARNING,
                        message=f"High cost per request for {row['provider']}: ${avg_cost:.4f}",
                        provider=row["provider"],
                        metric="cost_per_request",
                        value=avg_cost,
                        threshold=self.alert_thresholds["cost_per_request"],
                        timestamp=datetime.utcnow(),
                    )
                )

        # Check P95 latency
        query_latency = """
            SELECT
                provider,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration) as p95
            FROM llm_invocations
            WHERE timestamp >= $1
            AND success = true
            GROUP BY provider
        """

        latency_rows = await self.db.fetch(query_latency, start_time)

        for row in latency_rows:
            p95 = float(row["p95"]) if row["p95"] else 0.0
            if p95 > self.alert_thresholds["latency_p95"]:
                alerts.append(
                    Alert(
                        alert_id=f"latency_{row['provider']}_{int(datetime.utcnow().timestamp())}",
                        severity=AlertSeverity.CRITICAL,
                        message=f"High P95 latency for {row['provider']}: {p95:.2f}s",
                        provider=row["provider"],
                        metric="latency_p95",
                        value=p95,
                        threshold=self.alert_thresholds["latency_p95"],
                        timestamp=datetime.utcnow(),
                    )
                )

        # Check failure rate
        query_failures = """
            SELECT
                provider,
                COUNT(*) as total,
                SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failures
            FROM llm_invocations
            WHERE timestamp >= $1
            GROUP BY provider
        """

        failure_rows = await self.db.fetch(query_failures, start_time)

        for row in failure_rows:
            total = int(row["total"])
            failures = int(row["failures"])
            failure_rate = failures / total if total > 0 else 0.0

            if failure_rate > self.alert_thresholds["failure_rate"]:
                alerts.append(
                    Alert(
                        alert_id=f"failure_{row['provider']}_{int(datetime.utcnow().timestamp())}",
                        severity=AlertSeverity.CRITICAL,
                        message=f"High failure rate for {row['provider']}: {failure_rate:.1%}",
                        provider=row["provider"],
                        metric="failure_rate",
                        value=failure_rate,
                        threshold=self.alert_thresholds["failure_rate"],
                        timestamp=datetime.utcnow(),
                    )
                )

        return alerts

    async def get_trend_analysis(
        self, metric: str, days: int = 30, granularity: str = "1 day"
    ) -> List[Dict[str, Any]]:
        """
        Get trend analysis for a metric over time.

        Args:
            metric: Metric to analyze (cost, latency, tokens, success_rate)
            days: Number of days to analyze
            granularity: Time bucket size (e.g., "1 hour", "1 day")

        Returns:
            List of time-series data points
        """
        start_time = datetime.utcnow() - timedelta(days=days)

        if metric == "cost":
            query = f"""
                SELECT
                    time_bucket('{granularity}', timestamp) as time,
                    COALESCE(SUM(cost), 0) as value
                FROM llm_invocations
                WHERE timestamp >= $1
                AND success = true
                GROUP BY time_bucket('{granularity}', timestamp)
                ORDER BY time
            """

        elif metric == "latency":
            query = f"""
                SELECT
                    time_bucket('{granularity}', timestamp) as time,
                    AVG(duration) as value
                FROM llm_invocations
                WHERE timestamp >= $1
                AND success = true
                GROUP BY time_bucket('{granularity}', timestamp)
                ORDER BY time
            """

        elif metric == "tokens":
            query = f"""
                SELECT
                    time_bucket('{granularity}', timestamp) as time,
                    COALESCE(SUM(total_tokens), 0) as value
                FROM llm_invocations
                WHERE timestamp >= $1
                AND success = true
                GROUP BY time_bucket('{granularity}', timestamp)
                ORDER BY time
            """

        elif metric == "success_rate":
            query = f"""
                SELECT
                    time_bucket('{granularity}', timestamp) as time,
                    AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as value
                FROM llm_invocations
                WHERE timestamp >= $1
                GROUP BY time_bucket('{granularity}', timestamp)
                ORDER BY time
            """

        else:
            raise ValueError(f"Unsupported metric: {metric}")

        rows = await self.db.fetch(query, start_time)

        return [
            {"time": row["time"].isoformat(), "value": float(row["value"])}
            for row in rows
        ]

    async def compare_providers(
        self, providers: List[str], days: int = 7
    ) -> Dict[str, ProviderMetrics]:
        """
        Compare multiple providers side-by-side.

        Args:
            providers: List of provider names
            days: Number of days to analyze

        Returns:
            Dict mapping provider name to metrics
        """
        comparison = {}

        for provider in providers:
            metrics = await self.get_provider_metrics(provider, days)
            comparison[provider] = metrics

        return comparison


# Example usage
if __name__ == "__main__":

    async def main():
        # Initialize database pool
        db_pool = await asyncpg.create_pool(
            host="localhost",
            port=5432,
            database="llm_metrics",
            user="postgres",
            password="postgres",
        )

        engine = ProviderAnalyticsEngine(db_pool)

        # Cost breakdown
        print("=== Cost Breakdown (Last 7 Days) ===")
        breakdown = await engine.get_cost_breakdown(days=7)
        print(f"Total: ${breakdown.total_cost:.2f}")
        print(f"By Provider: {breakdown.by_provider}")
        print(f"Top Spenders: {breakdown.top_spenders}")

        # Performance analysis
        print("\n=== Performance Analysis ===")
        performance = await engine.get_performance_analysis(days=7)
        print(f"Avg Latency: {performance.avg_latency:.2f}s")
        print(f"By Provider: {performance.latency_by_provider}")

        # Check alerts
        print("\n=== Active Alerts ===")
        alerts = await engine.check_alerts()
        for alert in alerts:
            print(f"[{alert.severity.value.upper()}] {alert.message}")

        # Provider comparison
        print("\n=== Provider Comparison ===")
        comparison = await engine.compare_providers(
            ["fireworks", "together", "anthropic"]
        )
        for provider, metrics in comparison.items():
            print(f"\n{provider}:")
            print(f"  Success Rate: {metrics.success_rate:.1%}")
            print(f"  Avg Cost: ${metrics.avg_cost:.4f}")
            print(f"  Avg Latency: {metrics.avg_latency:.2f}s")

        await db_pool.close()

    asyncio.run(main())
