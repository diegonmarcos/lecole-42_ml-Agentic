"""
Unit tests for LLMOps Logger

Run with: pytest tests/unit/test_llmops_logger.py -v
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llmops.logger import LLMOpsLogger, LLMOpsMetrics


@pytest.fixture
def mock_db_pool():
    """Mock asyncpg connection pool (acquire() is sync, returns an async CM)"""
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    return pool


@pytest.mark.asyncio
async def test_log_invocation_success(mock_db_pool):
    """Test successful logging of an invocation"""
    logger = LLMOpsLogger(mock_db_pool, batch_size=1)

    await logger.log_invocation(
        user_id="test_user",
        tier=1,
        model="llama-v3p1-8b",
        prompt_tokens=100,
        completion_tokens=50,
        cost=0.00001,
        latency_ms=450,
        success=True,
        task_type="test",
        provider="fireworks",
    )

    # Verify flush was called
    conn = await mock_db_pool.acquire().__aenter__()
    conn.executemany.assert_called_once()


@pytest.mark.asyncio
async def test_log_invocation_validation():
    """Test validation of invocation parameters"""
    logger = LLMOpsLogger(AsyncMock(), batch_size=100)

    # Invalid tier
    with pytest.raises(ValueError, match="Tier must be 0-4"):
        await logger.log_invocation(tier=5, model="test")

    # Negative tokens
    with pytest.raises(ValueError, match="Token counts must be non-negative"):
        await logger.log_invocation(tier=0, model="test", prompt_tokens=-1)

    # Negative cost
    with pytest.raises(ValueError, match="Cost must be non-negative"):
        await logger.log_invocation(tier=0, model="test", cost=-0.01)


@pytest.mark.asyncio
async def test_batch_flushing(mock_db_pool):
    """Test that batch is flushed when size limit is reached"""
    logger = LLMOpsLogger(mock_db_pool, batch_size=3)

    # Log 2 invocations (should not flush yet)
    await logger.log_invocation(tier=0, model="test1")
    await logger.log_invocation(tier=0, model="test2")

    conn = await mock_db_pool.acquire().__aenter__()
    assert conn.executemany.call_count == 0

    # Log 3rd invocation (should trigger flush)
    await logger.log_invocation(tier=0, model="test3")
    assert conn.executemany.call_count == 1


@pytest.mark.asyncio
async def test_trace_id_generation():
    """Test that trace_id is auto-generated if not provided"""
    logger = LLMOpsLogger(AsyncMock(), batch_size=100)

    await logger.log_invocation(tier=0, model="test")

    assert len(logger._batch) == 1
    assert logger._batch[0]["trace_id"] is not None


@pytest.mark.asyncio
async def test_metrics_cost_by_tier(mock_db_pool):
    """Test cost aggregation by tier"""
    conn = await mock_db_pool.acquire().__aenter__()
    conn.fetch.return_value = [
        {"tier": 0, "total_cost": 0.0},
        {"tier": 1, "total_cost": 12.34},
        {"tier": 3, "total_cost": 45.67},
    ]

    metrics = LLMOpsMetrics(mock_db_pool)
    result = await metrics.get_cost_by_tier(days=7)

    assert result == {0: 0.0, 1: 12.34, 3: 45.67}
    conn.fetch.assert_called_once()


@pytest.mark.asyncio
async def test_metrics_success_rate(mock_db_pool):
    """Test success rate calculation"""
    conn = await mock_db_pool.acquire().__aenter__()
    conn.fetchrow.return_value = {"success_rate": 95.5}

    metrics = LLMOpsMetrics(mock_db_pool)
    result = await metrics.get_success_rate(tier=1, days=30)

    assert result == 95.5
    conn.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_metrics_latency_percentiles(mock_db_pool):
    """Test latency percentile calculation"""
    conn = await mock_db_pool.acquire().__aenter__()
    conn.fetchrow.return_value = {"p50": 450, "p95": 1200, "p99": 2500}

    metrics = LLMOpsMetrics(mock_db_pool)
    result = await metrics.get_latency_percentiles(tier=1, days=7)

    assert result == {"p50": 450, "p95": 1200, "p99": 2500}


@pytest.mark.asyncio
async def test_optimal_tier_recommendation(mock_db_pool):
    """Test optimal tier recommendation for task type"""
    conn = await mock_db_pool.acquire().__aenter__()
    conn.fetchrow.return_value = {
        "tier": 1,
        "success_rate": 95.5,
        "avg_cost": 0.000074,
        "avg_latency_ms": 450,
        "sample_size": 1000,
    }

    metrics = LLMOpsMetrics(mock_db_pool)
    result = await metrics.get_optimal_tier_for_task("code_generation")

    assert result["tier"] == 1
    assert result["success_rate"] == 95.5
    assert result["sample_size"] == 1000
    assert "reasoning" in result


@pytest.mark.asyncio
async def test_flush_and_close(mock_db_pool):
    """Test graceful shutdown with flush"""
    logger = LLMOpsLogger(mock_db_pool, batch_size=100)

    # Add entries to batch
    await logger.log_invocation(tier=0, model="test1")
    await logger.log_invocation(tier=0, model="test2")

    assert len(logger._batch) == 2

    # Flush and close
    await logger.flush_and_close()

    assert len(logger._batch) == 0
    conn = await mock_db_pool.acquire().__aenter__()
    conn.executemany.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
