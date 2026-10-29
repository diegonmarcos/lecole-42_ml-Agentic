"""
Rate Limiting Middleware - TASK-049

Redis-based rate limiting for FastAPI endpoints:
- Per-endpoint rate limits
- Per-user rate limits
- Token bucket algorithm
- Sliding window counter
- Custom rate limit rules
- Rate limit headers (X-RateLimit-*)
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware

try:
    import redis.asyncio as redis
except ImportError:
    redis = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


class RateLimitStrategy(Enum):
    """Rate limiting strategies"""

    FIXED_WINDOW = "fixed_window"  # Simple counter per time window
    SLIDING_WINDOW = "sliding_window"  # Sliding window counter
    TOKEN_BUCKET = "token_bucket"  # Token bucket algorithm


@dataclass
class RateLimitRule:
    """Rate limit rule configuration"""

    requests: int  # Number of requests allowed
    window: int  # Time window in seconds
    strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW
    key_func: Optional[Callable] = None  # Custom key function


class RateLimiter:
    """
    Redis-based rate limiter.

    Strategies:
    1. Fixed Window: Simple counter that resets every window
    2. Sliding Window: Precise rate limiting using sorted sets
    3. Token Bucket: Smooth rate limiting with burst support

    Usage:
        limiter = RateLimiter(redis_client)

        # Check rate limit
        allowed, retry_after = await limiter.check_rate_limit(
            key="user:123",
            max_requests=100,
            window=60,  # 60 seconds
            strategy=RateLimitStrategy.SLIDING_WINDOW
        )
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize rate limiter.

        Args:
            redis_client: Redis client for storing counters
        """
        self.redis = redis_client

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window: int,
        strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW,
    ) -> tuple[bool, int]:
        """
        Check if request is within rate limit.

        Args:
            key: Rate limit key (e.g., "user:123" or "endpoint:/api/search")
            max_requests: Maximum requests allowed
            window: Time window in seconds
            strategy: Rate limiting strategy

        Returns:
            (allowed, retry_after) tuple
            - allowed: True if request is allowed
            - retry_after: Seconds to wait before retry (0 if allowed)
        """
        if strategy == RateLimitStrategy.FIXED_WINDOW:
            return await self._check_fixed_window(key, max_requests, window)
        if strategy == RateLimitStrategy.SLIDING_WINDOW:
            return await self._check_sliding_window(key, max_requests, window)
        if strategy == RateLimitStrategy.TOKEN_BUCKET:
            return await self._check_token_bucket(key, max_requests, window)
        raise ValueError(f"Unknown strategy: {strategy}")

    async def _check_fixed_window(
        self, key: str, max_requests: int, window: int
    ) -> tuple[bool, int]:
        """Fixed window counter"""
        now = int(time.time())
        window_key = f"ratelimit:fixed:{key}:{now // window}"

        # Increment counter
        count = await self.redis.incr(window_key)

        # Set expiration on first request
        if count == 1:
            await self.redis.expire(window_key, window)

        # Check limit
        if count <= max_requests:
            return True, 0
        # Calculate retry_after
        window_start = (now // window) * window
        retry_after = window_start + window - now
        return False, retry_after

    async def _check_sliding_window(
        self, key: str, max_requests: int, window: int
    ) -> tuple[bool, int]:
        """Sliding window using sorted set"""
        now = time.time()
        window_key = f"ratelimit:sliding:{key}"

        # Use pipeline for atomic operations
        async with self.redis.pipeline(transaction=True) as pipe:
            # Remove old entries
            pipe.zremrangebyscore(window_key, 0, now - window)

            # Count requests in window
            pipe.zcard(window_key)

            # Add current request with score = timestamp
            pipe.zadd(window_key, {f"{now}": now})

            # Set expiration
            pipe.expire(window_key, window)

            results = await pipe.execute()

        count = results[1]  # zcard result

        if count < max_requests:
            return True, 0
        # Get oldest request timestamp
        oldest = await self.redis.zrange(window_key, 0, 0, withscores=True)
        if oldest:
            oldest_time = oldest[0][1]
            retry_after = int(oldest_time + window - now)
            return False, max(1, retry_after)
        return False, window

    async def _check_token_bucket(
        self, key: str, capacity: int, refill_rate: float
    ) -> tuple[bool, int]:
        """Token bucket algorithm"""
        bucket_key = f"ratelimit:bucket:{key}"
        now = time.time()

        # Get bucket state
        bucket_data = await self.redis.hgetall(bucket_key)

        if not bucket_data:
            # Initialize bucket
            tokens = float(capacity - 1)  # Consume one token
            last_refill = now

            await self.redis.hset(
                bucket_key, mapping={"tokens": tokens, "last_refill": last_refill}
            )
            await self.redis.expire(bucket_key, int(capacity / refill_rate) + 60)

            return True, 0

        # Get current state
        tokens = float(bucket_data.get(b"tokens", 0))
        last_refill = float(bucket_data.get(b"last_refill", now))

        # Refill tokens based on time passed
        time_passed = now - last_refill
        new_tokens = min(capacity, tokens + (time_passed * refill_rate))

        # Check if we can consume a token
        if new_tokens >= 1:
            new_tokens -= 1

            await self.redis.hset(
                bucket_key, mapping={"tokens": new_tokens, "last_refill": now}
            )

            return True, 0
        # Calculate retry_after
        tokens_needed = 1 - new_tokens
        retry_after = int(tokens_needed / refill_rate) + 1

        return False, retry_after

    async def get_remaining(
        self,
        key: str,
        max_requests: int,
        window: int,
        strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW,
    ) -> int:
        """Get remaining requests in current window"""
        if strategy == RateLimitStrategy.SLIDING_WINDOW:
            window_key = f"ratelimit:sliding:{key}"
            now = time.time()

            # Remove old entries and count
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(window_key, 0, now - window)
                pipe.zcard(window_key)
                results = await pipe.execute()

            count = results[1]
            return max(0, max_requests - count)

        if strategy == RateLimitStrategy.FIXED_WINDOW:
            now = int(time.time())
            window_key = f"ratelimit:fixed:{key}:{now // window}"
            count = await self.redis.get(window_key)
            count = int(count) if count else 0
            return max(0, max_requests - count)

        return 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.

    Usage:
        app.add_middleware(
            RateLimitMiddleware,
            redis_client=redis_client,
            default_limits={
                "requests": 100,
                "window": 60
            },
            endpoint_limits={
                "/api/search": {"requests": 10, "window": 60},
                "/api/chat": {"requests": 5, "window": 60}
            }
        )
    """

    def __init__(
        self,
        app,
        redis_client: redis.Redis,
        default_limits: Optional[Dict[str, int]] = None,
        endpoint_limits: Optional[Dict[str, Dict[str, int]]] = None,
        strategy: RateLimitStrategy = RateLimitStrategy.SLIDING_WINDOW,
        key_func: Optional[Callable] = None,
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: FastAPI app
            redis_client: Redis client
            default_limits: Default rate limits {"requests": 100, "window": 60}
            endpoint_limits: Per-endpoint limits {"/api/search": {"requests": 10, "window": 60}}
            strategy: Rate limiting strategy
            key_func: Custom key function (request -> key)
        """
        super().__init__(app)
        self.limiter = RateLimiter(redis_client)
        self.default_limits = default_limits or {"requests": 1000, "window": 60}
        self.endpoint_limits = endpoint_limits or {}
        self.strategy = strategy
        self.key_func = key_func or self._default_key_func

    def _default_key_func(self, request: Request) -> str:
        """Default key function: IP address"""
        # Try to get real IP from X-Forwarded-For header
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return f"ip:{forwarded.split(',')[0].strip()}"

        host = request.client.host if request.client else "unknown"
        return f"ip:{host}"

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting"""
        # Skip rate limiting for health checks
        if request.url.path.startswith("/health"):
            return await call_next(request)

        # Get rate limit configuration
        endpoint = request.url.path
        limits = self.endpoint_limits.get(endpoint, self.default_limits)

        max_requests = limits.get("requests", self.default_limits["requests"])
        window = limits.get("window", self.default_limits["window"])

        # Generate rate limit key
        key = self.key_func(request)
        rate_limit_key = f"{endpoint}:{key}"

        # Check rate limit
        try:
            allowed, retry_after = await self.limiter.check_rate_limit(
                key=rate_limit_key,
                max_requests=max_requests,
                window=window,
                strategy=self.strategy,
            )

            # Get remaining requests
            remaining = await self.limiter.get_remaining(
                key=rate_limit_key,
                max_requests=max_requests,
                window=window,
                strategy=self.strategy,
            )

            if not allowed:
                # Rate limit exceeded
                logger.warning("Rate limit exceeded: %s", rate_limit_key)

                return Response(
                    content='{"error": "Rate limit exceeded", "retry_after": '
                    + str(retry_after)
                    + "}",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    media_type="application/json",
                    headers={
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                        "X-RateLimit-Reset": str(int(time.time()) + retry_after),
                        "Retry-After": str(retry_after),
                    },
                )

            # Process request
            response = await call_next(request)

            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(max_requests)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Reset"] = str(int(time.time()) + window)

            return response

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Rate limiting error: %s", e)
            # On error, allow request (fail open)
            return await call_next(request)


# Example usage
if __name__ == "__main__":
    import asyncio

    async def test_rate_limiter():
        """Test rate limiter"""
        redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
        limiter = RateLimiter(redis_client)

        print("Testing Fixed Window:")
        for i in range(12):
            allowed, retry_after = await limiter.check_rate_limit(
                key="test:fixed",
                max_requests=10,
                window=60,
                strategy=RateLimitStrategy.FIXED_WINDOW,
            )
            outcome = (
                "✓ Allowed" if allowed else f"✗ Denied (retry after {retry_after}s)"
            )
            print(f"Request {i+1}: {outcome}")

        print("\nTesting Sliding Window:")
        for i in range(12):
            allowed, retry_after = await limiter.check_rate_limit(
                key="test:sliding",
                max_requests=10,
                window=10,
                strategy=RateLimitStrategy.SLIDING_WINDOW,
            )
            remaining = await limiter.get_remaining("test:sliding", 10, 10)
            outcome = (
                "✓ Allowed" if allowed else f"✗ Denied (retry after {retry_after}s)"
            )
            print(f"Request {i+1}: {outcome} (remaining: {remaining})")

            await asyncio.sleep(0.5)

        await redis_client.close()

    asyncio.run(test_rate_limiter())
