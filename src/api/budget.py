"""
Budget API Endpoints - FastAPI routes for budget management

Provides REST API for:
- Setting user budget limits
- Querying current spend
- Budget utilization reports
- Top spenders analytics
- Alert management
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.budget.enforcer import BudgetEnforcer
from src.cost.redis_tracker import RedisCostTracker

# API Router
router = APIRouter(prefix="/api/v1/budget", tags=["budget"])


# Pydantic Models
class BudgetLimit(BaseModel):
    """Budget limit configuration"""

    user_id: str = Field(..., description="User identifier")
    period: str = Field(
        ..., pattern="^(daily|weekly|monthly)$", description="Budget period"
    )
    limit: float = Field(..., gt=0, description="Budget limit in USD")


class BudgetResponse(BaseModel):
    """Budget status response"""

    user_id: str
    period: str
    limit: float
    current_spend: float
    utilization: float = Field(..., ge=0, le=1, description="Budget utilization (0-1)")
    remaining: float
    status: str = Field(..., description="ok, warning, critical, exceeded")


class CostEntry(BaseModel):
    """Cost tracking entry"""

    user_id: str
    tier: int = Field(..., ge=0, le=4)
    cost: float = Field(..., gt=0)
    period: str = Field(default="daily", pattern="^(daily|weekly|monthly)$")


class TopSpender(BaseModel):
    """Top spender entry"""

    user_id: str
    cost: float
    limit: Optional[float]
    utilization: Optional[float]


class UtilizationReport(BaseModel):
    """Budget utilization summary"""

    period: str
    total_users: int
    total_spend: float
    users_over_80: int
    users_over_90: int
    users_over_95: int
    users_exceeded: int
    timestamp: datetime


# Dependency: Redis connection
async def get_redis():
    """Get Redis connection"""
    redis_client = redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        yield redis_client
    finally:
        await redis_client.close()


# Dependency: Budget components
async def get_cost_tracker(redis_client: redis.Redis = Depends(get_redis)):
    """Get cost tracker instance"""
    return RedisCostTracker(redis_client)


async def get_budget_enforcer(redis_client: redis.Redis = Depends(get_redis)):
    """Get budget enforcer instance"""
    return BudgetEnforcer(redis_client)


# ============================================================================
# Budget Limit Management
# ============================================================================


@router.post("/limit", response_model=BudgetResponse, status_code=201)
async def set_budget_limit(
    budget: BudgetLimit, redis_client: redis.Redis = Depends(get_redis)
):
    """
    Set budget limit for user.

    Example:
        POST /api/v1/budget/limit
        {
            "user_id": "user_123",
            "period": "daily",
            "limit": 10.00
        }
    """
    limit_key = f"budget:{budget.user_id}:{budget.period}:limit"

    # Set limit
    await redis_client.set(limit_key, budget.limit)

    # Get current spend
    cost_key = f"cost:{budget.period}:user:{budget.user_id}"
    current_spend = float(await redis_client.get(cost_key) or 0)

    # Calculate utilization
    utilization = current_spend / budget.limit if budget.limit > 0 else 0

    # Determine status
    if utilization >= 1.0:
        status = "exceeded"
    elif utilization >= 0.95:
        status = "critical"
    elif utilization >= 0.80:
        status = "warning"
    else:
        status = "ok"

    return BudgetResponse(
        user_id=budget.user_id,
        period=budget.period,
        limit=budget.limit,
        current_spend=current_spend,
        utilization=utilization,
        remaining=max(0, budget.limit - current_spend),
        status=status,
    )


@router.get("/limit/{user_id}", response_model=List[BudgetResponse])
async def get_budget_limits(
    user_id: str,
    periods: Optional[List[str]] = Query(default=["daily", "weekly", "monthly"]),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Get budget limits and status for user.

    Example:
        GET /api/v1/budget/limit/user_123?periods=daily&periods=weekly
    """
    responses = []

    for period in periods or []:
        limit_key = f"budget:{user_id}:{period}:limit"
        cost_key = f"cost:{period}:user:{user_id}"

        # Get limit and spend
        limit = float(await redis_client.get(limit_key) or 0)
        current_spend = float(await redis_client.get(cost_key) or 0)

        if limit == 0:
            continue  # Skip if no limit set

        # Calculate utilization
        utilization = current_spend / limit

        # Determine status
        if utilization >= 1.0:
            status = "exceeded"
        elif utilization >= 0.95:
            status = "critical"
        elif utilization >= 0.80:
            status = "warning"
        else:
            status = "ok"

        responses.append(
            BudgetResponse(
                user_id=user_id,
                period=period,
                limit=limit,
                current_spend=current_spend,
                utilization=utilization,
                remaining=max(0, limit - current_spend),
                status=status,
            )
        )

    return responses


@router.delete("/limit/{user_id}/{period}", status_code=204)
async def delete_budget_limit(
    user_id: str, period: str, redis_client: redis.Redis = Depends(get_redis)
):
    """
    Delete budget limit for user.

    Example:
        DELETE /api/v1/budget/limit/user_123/daily
    """
    if period not in ["daily", "weekly", "monthly"]:
        raise HTTPException(status_code=400, detail="Invalid period")

    limit_key = f"budget:{user_id}:{period}:limit"
    await redis_client.delete(limit_key)


# ============================================================================
# Cost Tracking
# ============================================================================


@router.post("/track", status_code=202)
async def track_cost(
    cost_entry: CostEntry, tracker: RedisCostTracker = Depends(get_cost_tracker)
):
    """
    Track cost for user and tier.

    Example:
        POST /api/v1/budget/track
        {
            "user_id": "user_123",
            "tier": 1,
            "cost": 0.0015,
            "period": "daily"
        }
    """
    try:
        new_total = await tracker.track_cost(
            user_id=cost_entry.user_id,
            tier=cost_entry.tier,
            cost=cost_entry.cost,
            period=cost_entry.period,
        )

        return {
            "status": "tracked",
            "new_total": new_total,
            "user_id": cost_entry.user_id,
            "period": cost_entry.period,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/spend/{user_id}", response_model=Dict[str, float])
async def get_user_spend(
    user_id: str,
    periods: Optional[List[str]] = Query(default=["daily", "weekly", "monthly"]),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Get current spend for user across periods.

    Example:
        GET /api/v1/budget/spend/user_123?periods=daily&periods=monthly

    Returns:
        {
            "daily": 0.0234,
            "weekly": 0.1567,
            "monthly": 0.8923
        }
    """
    spend = {}

    for period in periods or []:
        cost_key = f"cost:{period}:user:{user_id}"
        spend[period] = float(await redis_client.get(cost_key) or 0)

    return spend


@router.delete("/spend/{user_id}/{period}", status_code=204)
async def reset_user_spend(
    user_id: str, period: str, redis_client: redis.Redis = Depends(get_redis)
):
    """
    Reset spend for user (admin operation).

    Example:
        DELETE /api/v1/budget/spend/user_123/daily
    """
    if period not in ["daily", "weekly", "monthly"]:
        raise HTTPException(status_code=400, detail="Invalid period")

    cost_key = f"cost:{period}:user:{user_id}"
    alert_keys = [
        f"alert:{period}:{user_id}:80",
        f"alert:{period}:{user_id}:90",
        f"alert:{period}:{user_id}:95",
    ]

    # Delete cost and alerts
    await redis_client.delete(cost_key, *alert_keys)


# ============================================================================
# Analytics
# ============================================================================


@router.get("/top-spenders/{period}", response_model=List[TopSpender])
async def get_top_spenders(
    period: str,
    limit: int = Query(default=10, ge=1, le=100),
    redis_client: redis.Redis = Depends(get_redis),
):
    """
    Get top spenders for period.

    Example:
        GET /api/v1/budget/top-spenders/daily?limit=20
    """
    if period not in ["daily", "weekly", "monthly"]:
        raise HTTPException(status_code=400, detail="Invalid period")

    spenders = []
    cursor = 0

    # Scan all user cost keys
    while True:
        cursor, keys = await redis_client.scan(
            cursor, match=f"cost:{period}:user:*", count=100
        )

        for key in keys:
            user_id = key.split(":")[-1]
            cost = float(await redis_client.get(key) or 0)

            # Get limit if set
            limit_key = f"budget:{user_id}:{period}:limit"
            user_limit = float(await redis_client.get(limit_key) or 0)

            utilization = cost / user_limit if user_limit > 0 else None

            spenders.append(
                TopSpender(
                    user_id=user_id,
                    cost=cost,
                    limit=user_limit if user_limit > 0 else None,
                    utilization=utilization,
                )
            )

        if cursor == 0:
            break

    # Sort by cost descending
    spenders.sort(key=lambda x: x.cost, reverse=True)

    return spenders[:limit]


@router.get("/utilization/{period}", response_model=UtilizationReport)
async def get_utilization_report(
    period: str, redis_client: redis.Redis = Depends(get_redis)
):
    """
    Get budget utilization report for period.

    Example:
        GET /api/v1/budget/utilization/daily

    Returns summary of how many users are at different utilization thresholds.
    """
    if period not in ["daily", "weekly", "monthly"]:
        raise HTTPException(status_code=400, detail="Invalid period")

    report: Dict[str, Any] = {
        "total_users": 0,
        "total_spend": 0.0,
        "users_over_80": 0,
        "users_over_90": 0,
        "users_over_95": 0,
        "users_exceeded": 0,
    }

    cursor = 0

    while True:
        cursor, keys = await redis_client.scan(
            cursor, match=f"cost:{period}:user:*", count=100
        )

        for key in keys:
            user_id = key.split(":")[-1]
            cost = float(await redis_client.get(key) or 0)

            # Get limit
            limit_key = f"budget:{user_id}:{period}:limit"
            user_limit = float(await redis_client.get(limit_key) or 0)

            if user_limit == 0:
                continue  # Skip users without limits

            report["total_users"] += 1
            report["total_spend"] += cost

            utilization = cost / user_limit

            if utilization >= 1.0:
                report["users_exceeded"] += 1
            elif utilization >= 0.95:
                report["users_over_95"] += 1
            elif utilization >= 0.90:
                report["users_over_90"] += 1
            elif utilization >= 0.80:
                report["users_over_80"] += 1

        if cursor == 0:
            break

    return UtilizationReport(period=period, timestamp=datetime.utcnow(), **report)


@router.get("/tier-costs/{period}", response_model=Dict[int, float])
async def get_tier_costs(period: str, redis_client: redis.Redis = Depends(get_redis)):
    """
    Get total costs by tier for period.

    Example:
        GET /api/v1/budget/tier-costs/daily

    Returns:
        {
            "0": 0.0,
            "1": 12.34,
            "3": 45.67
        }
    """
    if period not in ["daily", "weekly", "monthly"]:
        raise HTTPException(status_code=400, detail="Invalid period")

    tier_costs = {}

    for tier in range(5):  # Tiers 0-4
        cost_key = f"cost:{period}:tier:{tier}"
        cost = float(await redis_client.get(cost_key) or 0)
        if cost > 0:
            tier_costs[tier] = cost

    return tier_costs


# ============================================================================
# Health Check
# ============================================================================


@router.get("/health")
async def health_check(redis_client: redis.Redis = Depends(get_redis)):
    """
    Health check for budget API.
    """
    try:
        # Ping Redis
        await redis_client.ping()

        return {
            "status": "healthy",
            "redis": "connected",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=503, detail=f"Budget API unhealthy: {str(e)}"
        ) from e
