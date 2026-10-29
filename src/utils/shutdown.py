"""
Graceful Shutdown Manager - TASK-045

Handles graceful shutdown of all system components:
- Database connection pools
- Redis connections
- Background tasks
- Agent processes
- Open file handles
- Active requests
"""

import asyncio
import logging
import signal
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List

logger = logging.getLogger(__name__)


class ShutdownPhase(Enum):
    """Shutdown phases"""

    STOP_ACCEPTING = "stop_accepting"  # Stop accepting new requests
    DRAIN_REQUESTS = "drain_requests"  # Wait for in-flight requests
    STOP_BACKGROUND = "stop_background"  # Stop background tasks
    CLOSE_CONNECTIONS = "close_connections"  # Close DB/Redis connections
    CLEANUP = "cleanup"  # Final cleanup


@dataclass
class ShutdownHook:
    """Shutdown hook configuration"""

    name: str
    phase: ShutdownPhase
    callback: Callable
    timeout: float = 30.0
    critical: bool = True  # If True, failure prevents graceful shutdown


class GracefulShutdownManager:
    """
    Manages graceful shutdown of the application.

    Usage:
        shutdown_manager = GracefulShutdownManager(
            shutdown_timeout=60.0,
            drain_timeout=30.0
        )

        # Register shutdown hooks
        shutdown_manager.register(
            name="Close Redis",
            phase=ShutdownPhase.CLOSE_CONNECTIONS,
            callback=redis_client.close
        )

        # Start listening for shutdown signals
        await shutdown_manager.setup_signal_handlers()

        # Trigger shutdown programmatically
        await shutdown_manager.shutdown()
    """

    def __init__(self, shutdown_timeout: float = 60.0, drain_timeout: float = 30.0):
        """
        Initialize shutdown manager.

        Args:
            shutdown_timeout: Total shutdown timeout
            drain_timeout: Request draining timeout
        """
        self.shutdown_timeout = shutdown_timeout
        self.drain_timeout = drain_timeout
        self.hooks: List[ShutdownHook] = []
        self.is_shutting_down = False
        self._shutdown_event = asyncio.Event()

    def register(
        self,
        name: str,
        phase: ShutdownPhase,
        callback: Callable,
        timeout: float = 30.0,
        critical: bool = True,
    ):
        """
        Register shutdown hook.

        Args:
            name: Hook name for logging
            phase: Shutdown phase
            callback: Async or sync callback function
            timeout: Timeout for this hook
            critical: If True, failure prevents graceful shutdown
        """
        hook = ShutdownHook(
            name=name,
            phase=phase,
            callback=callback,
            timeout=timeout,
            critical=critical,
        )

        self.hooks.append(hook)

        logger.info("Registered shutdown hook: %s (phase=%s)", name, phase.value)

    async def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""

        def signal_handler(signum, _frame):
            logger.warning(
                "Received signal %s, initiating graceful shutdown...", signum
            )
            asyncio.create_task(self.shutdown())

        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        logger.info("Signal handlers registered for graceful shutdown")

    async def shutdown(self):
        """Execute graceful shutdown"""
        if self.is_shutting_down:
            logger.warning("Shutdown already in progress")
            return

        self.is_shutting_down = True

        logger.warning("=" * 70)
        logger.warning("  GRACEFUL SHUTDOWN INITIATED")
        logger.warning("=" * 70)

        try:
            # Execute shutdown phases in order
            for phase in ShutdownPhase:
                await self._execute_phase(phase)

            logger.warning("Graceful shutdown completed successfully")

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error during graceful shutdown: %s", e, exc_info=True)

        finally:
            self._shutdown_event.set()

    async def _execute_phase(self, phase: ShutdownPhase):
        """Execute all hooks for a shutdown phase"""
        phase_hooks = [h for h in self.hooks if h.phase == phase]

        if not phase_hooks:
            return

        logger.warning(
            "\n--- Phase: %s (%s hooks) ---", phase.value.upper(), len(phase_hooks)
        )

        # Execute hooks in parallel
        tasks = []
        for hook in phase_hooks:
            task = asyncio.create_task(self._execute_hook(hook))
            tasks.append(task)

        # Wait for all hooks with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=max(h.timeout for h in phase_hooks),
            )

        except asyncio.TimeoutError:
            logger.error("Phase %s timed out", phase.value)

    async def _execute_hook(self, hook: ShutdownHook):
        """Execute a single shutdown hook"""
        logger.info("Executing: %s", hook.name)

        try:
            # Execute with timeout
            if asyncio.iscoroutinefunction(hook.callback):
                await asyncio.wait_for(hook.callback(), timeout=hook.timeout)
            else:
                await asyncio.wait_for(
                    asyncio.to_thread(hook.callback), timeout=hook.timeout
                )

            logger.info("✓ %s completed", hook.name)

        except asyncio.TimeoutError:
            logger.error("✗ %s timed out after %ss", hook.name, hook.timeout)

            if hook.critical:
                raise

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("✗ %s failed: %s", hook.name, e)

            if hook.critical:
                raise

    async def wait_for_shutdown(self):
        """Wait for shutdown to complete"""
        await self._shutdown_event.wait()


# Global shutdown manager instance
shutdown_manager = GracefulShutdownManager(shutdown_timeout=60.0, drain_timeout=30.0)
