"""
Health Check Endpoints - TASK-044

Comprehensive health checks for all system components:
- Redis connectivity and performance
- PostgreSQL connectivity and performance
- Qdrant connectivity
- LLM providers (Ollama, Jan, cloud providers)
- MCP servers
- System resources (CPU, memory, disk)
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import psutil
from fastapi import APIRouter, Response, status

try:
    import asyncpg
    import redis.asyncio as redis
except ImportError:
    redis = None  # type: ignore[assignment]
    asyncpg = None  # type: ignore[assignment]

import aiohttp

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enum"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a component"""

    name: str
    status: HealthStatus
    latency_ms: float = 0.0
    message: str = ""
    details: Optional[Dict[str, Any]] = None


router = APIRouter(prefix="/health", tags=["health"])


def _as_health(
    name: str, result: Union[ComponentHealth, BaseException]
) -> ComponentHealth:
    """Turn an exception returned by asyncio.gather into an unhealthy component."""
    if isinstance(result, BaseException):
        return ComponentHealth(
            name=name, status=HealthStatus.UNHEALTHY, message=f"Check failed: {result}"
        )
    return result


class HealthChecker:
    """Comprehensive health checker for all system components"""

    def __init__(self):
        self.redis_host = "localhost"
        self.redis_port = 6379
        self.pg_host = "localhost"
        self.pg_port = 5432
        self.qdrant_url = "http://localhost:6333"
        self.ollama_url = "http://localhost:11434"
        self.jan_url = "http://localhost:1337"

    async def check_redis(self) -> ComponentHealth:
        """Check Redis health"""
        start = time.time()
        try:
            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                socket_connect_timeout=2,
                decode_responses=True,
            )

            # Ping
            await client.ping()

            # Test set/get
            test_key = f"health:test:{int(time.time())}"
            await client.set(test_key, "test", ex=10)
            value = await client.get(test_key)

            if value != "test":
                raise RuntimeError("Redis read/write test failed")

            # Get info
            info = await client.info("stats")

            latency = (time.time() - start) * 1000

            await client.close()

            return ComponentHealth(
                name="Redis",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Operational",
                details={
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory_human", "N/A"),
                },
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Redis health check failed: %s", e)
            return ComponentHealth(
                name="Redis",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message=f"Error: {str(e)}",
            )

    async def check_postgres(self) -> ComponentHealth:
        """Check PostgreSQL health"""
        start = time.time()
        try:
            conn = await asyncpg.connect(
                host=self.pg_host,
                port=self.pg_port,
                user="postgres",
                password="postgres",
                database="postgres",
                timeout=2,
            )

            # Test query
            result = await conn.fetchval("SELECT 1")

            if result != 1:
                raise RuntimeError("PostgreSQL test query failed")

            # Get stats
            stats = await conn.fetchrow(
                """
                SELECT
                    count(*) as active_connections,
                    pg_database_size('postgres') as db_size
                FROM pg_stat_activity
                WHERE state = 'active'
            """
            )

            latency = (time.time() - start) * 1000

            await conn.close()

            return ComponentHealth(
                name="PostgreSQL",
                status=HealthStatus.HEALTHY,
                latency_ms=latency,
                message="Operational",
                details={
                    "active_connections": stats["active_connections"],
                    "database_size_mb": stats["db_size"] // (1024 * 1024),
                },
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("PostgreSQL health check failed: %s", e)
            return ComponentHealth(
                name="PostgreSQL",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message=f"Error: {str(e)}",
            )

    async def check_qdrant(self) -> ComponentHealth:
        """Check Qdrant health"""
        start = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.qdrant_url}/health", timeout=aiohttp.ClientTimeout(total=2)
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"HTTP {response.status}")

                    data = await response.json()

                    latency = (time.time() - start) * 1000

                    return ComponentHealth(
                        name="Qdrant",
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency,
                        message="Operational",
                        details=data,
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Qdrant health check failed: %s", e)
            return ComponentHealth(
                name="Qdrant",
                status=HealthStatus.UNHEALTHY,
                latency_ms=(time.time() - start) * 1000,
                message=f"Error: {str(e)}",
            )

    async def check_ollama(self) -> ComponentHealth:
        """Check Ollama health"""
        start = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.ollama_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"HTTP {response.status}")

                    data = await response.json()

                    latency = (time.time() - start) * 1000

                    return ComponentHealth(
                        name="Ollama",
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency,
                        message="Operational",
                        details={"models_count": len(data.get("models", []))},
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Ollama is optional
            return ComponentHealth(
                name="Ollama",
                status=HealthStatus.DEGRADED,
                latency_ms=(time.time() - start) * 1000,
                message=f"Not available (optional): {str(e)}",
            )

    async def check_jan(self) -> ComponentHealth:
        """Check Jan health"""
        start = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.jan_url}/health", timeout=aiohttp.ClientTimeout(total=2)
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"HTTP {response.status}")

                    latency = (time.time() - start) * 1000

                    return ComponentHealth(
                        name="Jan",
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency,
                        message="Operational",
                    )

        except Exception as e:  # pylint: disable=broad-exception-caught
            # Jan is optional
            return ComponentHealth(
                name="Jan",
                status=HealthStatus.DEGRADED,
                latency_ms=(time.time() - start) * 1000,
                message=f"Not available (optional): {str(e)}",
            )

    async def check_mcp_servers(self) -> List[ComponentHealth]:
        """Check MCP servers health"""
        mcp_servers = [
            ("MCP Filesystem", "http://localhost:3001/health"),
            ("MCP Git", "http://localhost:3002/health"),
            ("MCP Memory", "http://localhost:3003/health"),
        ]

        results = []

        for name, url in mcp_servers:
            start = time.time()
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=2)
                    ) as response:
                        if response.status != 200:
                            raise RuntimeError(f"HTTP {response.status}")

                        latency = (time.time() - start) * 1000

                        results.append(
                            ComponentHealth(
                                name=name,
                                status=HealthStatus.HEALTHY,
                                latency_ms=latency,
                                message="Operational",
                            )
                        )

            except Exception as e:  # pylint: disable=broad-exception-caught
                # MCP servers are optional
                results.append(
                    ComponentHealth(
                        name=name,
                        status=HealthStatus.DEGRADED,
                        latency_ms=(time.time() - start) * 1000,
                        message=f"Not available (optional): {str(e)}",
                    )
                )

        return results

    async def check_system_resources(self) -> ComponentHealth:
        """Check system resources"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=0.1)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent

            # Determine status
            overall = HealthStatus.HEALTHY

            if cpu_percent > 80 or memory_percent > 80 or disk_percent > 80:
                overall = HealthStatus.DEGRADED

            if cpu_percent > 95 or memory_percent > 95 or disk_percent > 95:
                overall = HealthStatus.UNHEALTHY

            return ComponentHealth(
                name="System Resources",
                status=overall,
                message="Operational",
                details={
                    "cpu_percent": round(cpu_percent, 2),
                    "memory_percent": round(memory_percent, 2),
                    "disk_percent": round(disk_percent, 2),
                    "memory_available_mb": round(memory.available / 1024 / 1024, 2),
                },
            )

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("System resources check failed: %s", e)
            return ComponentHealth(
                name="System Resources",
                status=HealthStatus.DEGRADED,
                message=f"Error: {str(e)}",
            )

    async def check_all(self) -> Dict[str, Any]:
        """Run all health checks in parallel"""
        # Run all checks concurrently
        results: List[Any] = await asyncio.gather(
            self.check_redis(),
            self.check_postgres(),
            self.check_qdrant(),
            self.check_ollama(),
            self.check_jan(),
            self.check_mcp_servers(),
            self.check_system_resources(),
            return_exceptions=True,
        )

        # Flatten MCP servers list
        redis_health = _as_health("redis", results[0])
        pg_health = _as_health("postgres", results[1])
        qdrant_health = _as_health("qdrant", results[2])
        ollama_health = _as_health("ollama", results[3])
        jan_health = _as_health("jan", results[4])
        mcp_result = results[5]
        mcp_healths: List[ComponentHealth] = (
            [_as_health("mcp", mcp_result)]
            if isinstance(mcp_result, BaseException)
            else mcp_result
        )
        system_health = _as_health("system", results[6])

        # Combine all components
        components = [
            redis_health,
            pg_health,
            qdrant_health,
            ollama_health,
            jan_health,
            *mcp_healths,
            system_health,
        ]

        # Determine overall status
        unhealthy_count = sum(
            1 for c in components if c.status == HealthStatus.UNHEALTHY
        )
        degraded_count = sum(1 for c in components if c.status == HealthStatus.DEGRADED)

        if unhealthy_count > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_count > 2:  # More than 2 degraded components
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return {
            "status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "4.2.0",
            "components": {
                c.name: {
                    "status": c.status.value,
                    "latency_ms": round(c.latency_ms, 2),
                    "message": c.message,
                    **({"details": c.details} if c.details else {}),
                }
                for c in components
            },
            "summary": {
                "total_components": len(components),
                "healthy": sum(
                    1 for c in components if c.status == HealthStatus.HEALTHY
                ),
                "degraded": degraded_count,
                "unhealthy": unhealthy_count,
            },
        }


# Global health checker instance
health_checker = HealthChecker()


@router.get("")
async def health_check(response: Response):
    """
    Comprehensive health check for all system components.

    Returns detailed health status of:
    - Redis
    - PostgreSQL
    - Qdrant
    - Ollama (optional)
    - Jan (optional)
    - MCP servers (optional)
    - System resources
    """
    health_data = await health_checker.check_all()

    # Set HTTP status code based on health
    if health_data["status"] == "unhealthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif health_data["status"] == "degraded":
        response.status_code = status.HTTP_200_OK  # Still operational
    else:
        response.status_code = status.HTTP_200_OK

    return health_data


@router.get("/live")
async def liveness_probe():
    """
    Kubernetes liveness probe.

    Simple check that the API is running.
    """
    return {"status": "alive", "timestamp": datetime.utcnow().isoformat()}


@router.get("/ready")
async def readiness_probe(response: Response):
    """
    Kubernetes readiness probe.

    Checks if the API is ready to serve traffic.
    Verifies critical dependencies (Redis, PostgreSQL).
    """
    # Check only critical components
    redis_result, pg_result = await asyncio.gather(
        health_checker.check_redis(),
        health_checker.check_postgres(),
        return_exceptions=True,
    )
    redis_health = _as_health("redis", redis_result)
    pg_health = _as_health("postgres", pg_result)

    ready = (
        redis_health.status == HealthStatus.HEALTHY
        and pg_health.status == HealthStatus.HEALTHY
    )

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if ready else "not_ready",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "redis": redis_health.status.value,
            "postgres": pg_health.status.value,
        },
    }


@router.get("/startup")
async def startup_probe(_response: Response):
    """
    Kubernetes startup probe.

    Checks if the application has started successfully.
    """
    # Simple startup check
    return {
        "status": "started",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "4.2.0",
    }
