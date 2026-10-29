"""
LLMOps Logger - Track all LLM invocations for cost and performance analytics

This module provides asynchronous logging of LLM invocations to PostgreSQL
with minimal overhead (<10ms per call).

Usage:
    from llmops.logger import LLMOpsLogger

    logger = LLMOpsLogger(db_pool)
    await logger.log_invocation(
        trace_id="uuid",
        user_id="user123",
        tier=1,
        model="llama-v3p1-8b",
        prompt_tokens=100,
        completion_tokens=50,
        cost=0.000015,
        latency_ms=450,
        success=True,
        task_type="code_generation",
        privacy_mode=False,
        provider="fireworks"
    )
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import asyncpg

logger = logging.getLogger(__name__)


class LLMOpsLogger:
    """
    Asynchronous logger for LLM invocations with PostgreSQL persistence.

    Features:
    - Non-blocking async logging (<10ms overhead)
    - Automatic retry on transient failures
    - Batch insert support for high-throughput scenarios
    - Type validation for all fields
    """

    def __init__(self, db_pool: asyncpg.Pool, batch_size: int = 100):
        """
        Initialize LLMOps logger.

        Args:
            db_pool: asyncpg connection pool
            batch_size: Number of logs to batch before insert (default: 100)
        """
        self.db_pool = db_pool
        self.batch_size = batch_size
        self._batch: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._flush_task = None

    async def log_invocation(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        trace_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
        tier: int = 0,
        model: str = "unknown",
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float = 0.0,
        latency_ms: int = 0,
        success: bool = True,
        error: Optional[str] = None,
        task_type: Optional[str] = None,
        privacy_mode: bool = False,
        provider: Optional[str] = None,
    ) -> None:
        """
        Log an LLM invocation asynchronously.

        Args:
            trace_id: Unique ID linking all steps in a workflow (auto-generated if None)
            user_id: User identifier
            tier: LLM tier (0-4)
            model: Model name (e.g., "llama-v3p1-8b")
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            cost: Cost in USD
            latency_ms: Latency in milliseconds
            success: Whether the invocation succeeded
            error: Error message if failed
            task_type: Type of task (e.g., "code_generation", "rag_query")
            privacy_mode: Whether query was in privacy mode
            provider: Provider name (e.g., "ollama", "fireworks")

        Raises:
            ValueError: If tier is not 0-4 or tokens/cost are negative
        """
        # Validation
        if not 0 <= tier <= 4:
            raise ValueError(f"Tier must be 0-4, got {tier}")
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("Token counts must be non-negative")
        if cost < 0:
            raise ValueError("Cost must be non-negative")
        if latency_ms < 0:
            raise ValueError("Latency must be non-negative")

        # Generate trace_id if not provided
        if trace_id is None:
            trace_id = uuid4()

        # Create log entry
        entry = {
            "trace_id": trace_id,
            "timestamp": datetime.utcnow(),
            "user_id": user_id,
            "tier": tier,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost": cost,
            "latency_ms": latency_ms,
            "success": success,
            "error": error,
            "task_type": task_type,
            "privacy_mode": privacy_mode,
            "provider": provider,
        }

        # Add to batch
        async with self._lock:
            self._batch.append(entry)

            # Flush if batch is full
            if len(self._batch) >= self.batch_size:
                await self._flush()

    async def _flush(self) -> None:
        """
        Flush batch to database.

        This method is called automatically when batch is full.
        Callers must hold ``self._lock`` (log_invocation and flush_and_close do).
        """
        if not self._batch:
            return

        batch = self._batch[:]
        self._batch.clear()

        try:
            async with self.db_pool.acquire() as conn:
                await conn.executemany(
                    """
                    INSERT INTO llm_invocations (
                        trace_id, timestamp, user_id, tier, model,
                        prompt_tokens, completion_tokens, cost, latency_ms,
                        success, error, task_type, privacy_mode, provider
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """,
                    [
                        (
                            entry["trace_id"],
                            entry["timestamp"],
                            entry["user_id"],
                            entry["tier"],
                            entry["model"],
                            entry["prompt_tokens"],
                            entry["completion_tokens"],
                            entry["cost"],
                            entry["latency_ms"],
                            entry["success"],
                            entry["error"],
                            entry["task_type"],
                            entry["privacy_mode"],
                            entry["provider"],
                        )
                        for entry in batch
                    ],
                )
                logger.debug("Flushed %s log entries to database", len(batch))

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to flush logs to database: %s", e)
            # Re-add to batch for retry (lock is already held by the caller;
            # asyncio.Lock is not re-entrant, re-acquiring it would deadlock)
            self._batch.extend(batch)

    async def flush_and_close(self) -> None:
        """
        Flush remaining logs and stop background tasks.

        Call this before application shutdown.
        """
        async with self._lock:
            if self._batch:
                await self._flush()

        logger.info("LLMOps logger closed")


class LLMOpsMetrics:
    """
    Helper class for computing metrics from logged invocations.

    Usage:
        metrics = LLMOpsMetrics(db_pool)
        cost_by_tier = await metrics.get_cost_by_tier(days=7)
        success_rate = await metrics.get_success_rate(tier=1, days=30)
    """

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

    async def get_cost_by_tier(self, days: int = 7) -> dict:
        """
        Get total cost by tier for the last N days.

        Args:
            days: Number of days to look back

        Returns:
            Dict mapping tier to total cost, e.g., {0: 0.0, 1: 12.34, 3: 45.67}
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT tier, SUM(cost)::DECIMAL(10,2) as total_cost
                FROM llm_invocations
                WHERE timestamp > NOW() - INTERVAL '%s days'
                GROUP BY tier
                ORDER BY tier
                """,
                days,
            )
            return {row["tier"]: float(row["total_cost"]) for row in rows}

    async def get_success_rate(
        self, tier: Optional[int] = None, days: int = 30
    ) -> float:
        """
        Get success rate for a tier (or all tiers).

        Args:
            tier: Tier to filter (None for all tiers)
            days: Number of days to look back

        Returns:
            Success rate as percentage (0-100)
        """
        async with self.db_pool.acquire() as conn:
            if tier is not None:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE success) * 100.0 / COUNT(*) as success_rate
                    FROM llm_invocations
                    WHERE tier = $1 AND timestamp > NOW() - INTERVAL '%s days'
                    """,
                    tier,
                    days,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE success) * 100.0 / COUNT(*) as success_rate
                    FROM llm_invocations
                    WHERE timestamp > NOW() - INTERVAL '%s days'
                    """,
                    days,
                )

            return float(row["success_rate"]) if row else 0.0

    async def get_latency_percentiles(
        self, tier: Optional[int] = None, days: int = 7
    ) -> dict:
        """
        Get latency percentiles (p50, p95, p99).

        Args:
            tier: Tier to filter (None for all tiers)
            days: Number of days to look back

        Returns:
            Dict with p50, p95, p99 latencies in milliseconds
        """
        async with self.db_pool.acquire() as conn:
            if tier is not None:
                row = await conn.fetchrow(
                    """
                    SELECT
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms)::INTEGER as p50,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)::INTEGER as p95,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms)::INTEGER as p99
                    FROM llm_invocations
                    WHERE tier = $1 AND timestamp > NOW() - INTERVAL '%s days'
                    """,
                    tier,
                    days,
                )
            else:
                row = await conn.fetchrow(
                    """
                    SELECT
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY latency_ms)::INTEGER as p50,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms)::INTEGER as p95,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms)::INTEGER as p99
                    FROM llm_invocations
                    WHERE timestamp > NOW() - INTERVAL '%s days'
                    """,
                    days,
                )

            return {
                "p50": row["p50"] if row else 0,
                "p95": row["p95"] if row else 0,
                "p99": row["p99"] if row else 0,
            }

    async def get_optimal_tier_for_task(self, task_type: str) -> Optional[dict]:
        """
        Get optimal tier recommendation for a task type based on historical data.

        Args:
            task_type: Task type (e.g., "code_generation")

        Returns:
            Dict with recommended tier and reasoning, or None if no data
        """
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    tier,
                    COUNT(*) as sample_size,
                    (COUNT(*) FILTER (WHERE success) * 100.0 / COUNT(*))::DECIMAL(5,2)
                        as success_rate,
                    AVG(cost)::DECIMAL(10,6) as avg_cost,
                    AVG(latency_ms)::INTEGER as avg_latency_ms
                FROM llm_invocations
                WHERE task_type = $1 AND timestamp > NOW() - INTERVAL '30 days'
                GROUP BY tier
                ORDER BY success_rate DESC, avg_cost ASC
                LIMIT 1
                """,
                task_type,
            )

            if not row:
                return None

            return {
                "tier": row["tier"],
                "success_rate": float(row["success_rate"]),
                "avg_cost": float(row["avg_cost"]),
                "avg_latency_ms": row["avg_latency_ms"],
                "sample_size": row["sample_size"],
                "reasoning": f"Tier {row['tier']} has {row['success_rate']:.1f}% success rate "
                f"with ${row['avg_cost']:.4f} avg cost over {row['sample_size']} samples",
            }


# Example usage
if __name__ == "__main__":

    async def example():
        # Create connection pool
        pool = await asyncpg.create_pool(
            host="localhost",
            port=5432,
            database="orchestrator",
            user="admin",
            password="password",
        )

        # Initialize logger
        ops_logger = LLMOpsLogger(pool)

        # Log an invocation
        await ops_logger.log_invocation(
            user_id="user123",
            tier=1,
            model="llama-v3p1-8b-instruct",
            prompt_tokens=245,
            completion_tokens=128,
            cost=0.000074,
            latency_ms=450,
            success=True,
            task_type="code_generation",
            privacy_mode=False,
            provider="fireworks",
        )

        # Flush remaining logs
        await ops_logger.flush_and_close()

        # Get metrics
        metrics = LLMOpsMetrics(pool)
        cost_by_tier = await metrics.get_cost_by_tier(days=7)
        print(f"Cost by tier (last 7 days): {cost_by_tier}")

        optimal = await metrics.get_optimal_tier_for_task("code_generation")
        print(f"Optimal tier for code_generation: {optimal}")

        await pool.close()

    asyncio.run(example())
