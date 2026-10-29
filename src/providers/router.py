"""
Provider Router - Intelligent LLM routing with health checks and failover

Features:
- Tier-based routing (0: Ollama/Jan, 1: Fireworks/Together, 3: Anthropic/OpenAI)
- Automatic failover on provider failures
- Circuit breaker pattern (3 failures → open, 30s retry)
- Health check caching (5-min TTL)
- Cost tracking integration
- Privacy mode support
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import AsyncIterator, Callable, Dict, List, Optional

from .anthropic_provider import AnthropicProvider
from .base import LLMProvider, LLMResponse
from .fireworks_provider import FireworksProvider
from .ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


class Tier(IntEnum):
    """LLM tier classification"""

    LOCAL_FREE = 0  # Ollama, Jan (free)
    CLOUD_CHEAP = 1  # Fireworks, Together ($0.18-0.90/M)
    VISION = 2  # Ollama vision models (free, GPU required)
    PREMIUM = 3  # Anthropic, OpenAI ($1-75/M)
    BATCH = 4  # RunPod, Salad (batch processing)


@dataclass
class ProviderConfig:
    """Configuration for a provider"""

    provider: LLMProvider
    tier: Tier
    priority: int  # Lower = higher priority within tier
    models: List[str]  # Supported models
    privacy_compatible: bool = False
    health_check_interval: int = 300  # 5 minutes
    circuit_breaker_threshold: int = 3
    circuit_breaker_timeout: int = 30


@dataclass
class CircuitBreakerState:
    """Circuit breaker state for a provider"""

    failure_count: int = 0
    last_failure_time: float = 0
    is_open: bool = False
    last_health_check: float = 0
    is_healthy: bool = True


class ProviderRouter:
    """
    Intelligent router for LLM providers with failover and health checks.

    Usage:
        router = ProviderRouter()
        router.register(ollama_provider, tier=Tier.LOCAL_FREE, models=["llama-3.1-8b"])
        router.register(
            fireworks_provider, tier=Tier.CLOUD_CHEAP, models=["llama-v3p1-8b-instruct"]
        )

        response = await router.chat_completion(
            tier=Tier.LOCAL_FREE,
            model="llama-3.1-8b",
            messages=[...]
        )
    """

    def __init__(self, on_failover: Optional[Callable] = None):
        """
        Initialize provider router.

        Args:
            on_failover: Callback function(old_provider, new_provider, error) on failover
        """
        self.providers: Dict[str, ProviderConfig] = {}
        self.circuit_breakers: Dict[str, CircuitBreakerState] = {}
        self.on_failover = on_failover
        self._lock = asyncio.Lock()

    def register(
        self,
        name: str,
        provider: LLMProvider,
        tier: Tier,
        models: List[str],
        priority: int = 0,
        privacy_compatible: bool = False,
    ):
        """
        Register a provider with the router.

        Args:
            name: Unique provider name (e.g., "ollama", "fireworks")
            provider: LLMProvider instance
            tier: Tier classification
            models: List of supported model names
            priority: Priority within tier (lower = higher priority)
            privacy_compatible: Whether provider is privacy-compatible
        """
        config = ProviderConfig(
            provider=provider,
            tier=tier,
            priority=priority,
            models=models,
            privacy_compatible=privacy_compatible,
        )

        self.providers[name] = config
        self.circuit_breakers[name] = CircuitBreakerState()

        logger.info(
            "Registered provider: %s (Tier %s, %s models)", name, tier, len(models)
        )

    def _get_candidates(
        self, tier: Tier, model: Optional[str] = None, privacy_mode: bool = False
    ) -> List[str]:
        """
        Get candidate providers for a tier and model.

        Args:
            tier: Requested tier
            model: Model name (if None, use first available)
            privacy_mode: Whether to require privacy-compatible providers

        Returns:
            List of provider names sorted by priority
        """
        candidates = []

        for name, config in self.providers.items():
            # Filter by tier
            if config.tier != tier:
                continue

            # Filter by model support
            if model and model not in config.models:
                continue

            # Filter by privacy mode
            if privacy_mode and not config.privacy_compatible:
                continue

            # Check circuit breaker
            breaker = self.circuit_breakers[name]
            if breaker.is_open:
                # Check if timeout expired
                if (
                    time.time() - breaker.last_failure_time
                    >= config.circuit_breaker_timeout
                ):
                    breaker.is_open = False
                    breaker.failure_count = 0
                    logger.info("Circuit breaker closed for %s", name)
                else:
                    logger.debug("Skipping %s (circuit breaker open)", name)
                    continue

            candidates.append((name, config.priority))

        # Sort by priority (lower = higher priority)
        candidates.sort(key=lambda x: x[1])
        return [name for name, _ in candidates]

    async def _check_health(self, name: str) -> bool:
        """
        Check provider health with caching.

        Args:
            name: Provider name

        Returns:
            True if provider is healthy
        """
        config = self.providers[name]
        breaker = self.circuit_breakers[name]

        # Use cached result if fresh
        if time.time() - breaker.last_health_check < config.health_check_interval:
            return breaker.is_healthy

        # Perform health check
        try:
            is_healthy = await asyncio.wait_for(
                config.provider.health_check(), timeout=10.0
            )

            breaker.is_healthy = is_healthy
            breaker.last_health_check = time.time()

            if not is_healthy:
                logger.warning("Health check failed for %s", name)

            return is_healthy

        except asyncio.TimeoutError:
            logger.warning("Health check timeout for %s", name)
            breaker.is_healthy = False
            return False

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Health check error for %s: %s", name, e)
            breaker.is_healthy = False
            return False

    async def _record_failure(self, name: str):
        """
        Record provider failure and update circuit breaker.

        Args:
            name: Provider name
        """
        async with self._lock:
            config = self.providers[name]
            breaker = self.circuit_breakers[name]

            breaker.failure_count += 1
            breaker.last_failure_time = time.time()

            if breaker.failure_count >= config.circuit_breaker_threshold:
                breaker.is_open = True
                logger.warning(
                    "Circuit breaker opened for %s (%s failures)",
                    name,
                    breaker.failure_count,
                )

    async def _record_success(self, name: str):
        """
        Record provider success and reset circuit breaker.

        Args:
            name: Provider name
        """
        async with self._lock:
            breaker = self.circuit_breakers[name]
            breaker.failure_count = 0

    async def chat_completion(
        self,
        tier: Tier,
        model: Optional[str],
        messages: List[Dict[str, str]],
        privacy_mode: bool = False,
        enable_failover: bool = True,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate chat completion with automatic failover.

        Args:
            tier: Requested tier
            model: Model name
            messages: List of message dicts
            privacy_mode: Whether to use privacy-compatible providers only
            enable_failover: Whether to enable tier failover
            **kwargs: Additional parameters for provider

        Returns:
            LLMResponse from provider

        Raises:
            ValueError: If no providers available for tier
            Exception: If all providers fail
        """
        # Build fallback chain
        tiers_to_try = [tier]

        if enable_failover:
            # Fallback: Tier N → Tier N+1 → Tier 3 (premium)
            if tier < Tier.PREMIUM:
                tiers_to_try.append(Tier(tier + 1))
            if Tier.PREMIUM not in tiers_to_try:
                tiers_to_try.append(Tier.PREMIUM)

        last_error = None

        for current_tier in tiers_to_try:
            candidates = self._get_candidates(current_tier, model, privacy_mode)

            if not candidates:
                logger.warning("No candidates for tier %s", current_tier)
                continue

            for name in candidates:
                config = self.providers[name]

                # Health check
                if not await self._check_health(name):
                    logger.warning("Skipping unhealthy provider: %s", name)
                    continue

                # Attempt completion
                try:
                    logger.debug("Trying provider: %s (tier %s)", name, current_tier)

                    resolved_model = model or (
                        config.models[0] if config.models else ""
                    )
                    response = await config.provider.chat_completion(
                        model=resolved_model, messages=messages, **kwargs
                    )

                    # Success!
                    await self._record_success(name)

                    # Emit failover alert if we're not on the requested tier
                    if current_tier != tier and self.on_failover:
                        self.on_failover(tier, current_tier, name, last_error)

                    return response

                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error("Provider %s failed: %s", name, e)
                    await self._record_failure(name)
                    last_error = e
                    continue

        # All providers failed
        raise RuntimeError(
            f"All providers failed for tier {tier}. Last error: {last_error}"
        )

    async def stream_completion(
        self,
        tier: Tier,
        model: Optional[str],
        messages: List[Dict[str, str]],
        privacy_mode: bool = False,
        **kwargs,
    ) -> AsyncIterator[str]:
        """
        Stream completion with automatic failover.

        Args:
            tier: Requested tier
            model: Model name
            messages: List of message dicts
            privacy_mode: Whether to use privacy-compatible providers only
            **kwargs: Additional parameters for provider

        Yields:
            Content chunks from provider
        """
        candidates = self._get_candidates(tier, model, privacy_mode)

        if not candidates:
            raise ValueError(f"No providers available for tier {tier}")

        for name in candidates:
            config = self.providers[name]

            # Health check
            if not await self._check_health(name):
                continue

            # Attempt streaming
            try:
                resolved_model = model or (config.models[0] if config.models else "")
                async for chunk in config.provider.stream_completion(
                    model=resolved_model, messages=messages, **kwargs
                ):
                    yield chunk

                # Success!
                await self._record_success(name)
                return

            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Provider %s streaming failed: %s", name, e)
                await self._record_failure(name)
                continue

        raise RuntimeError(f"All providers failed for streaming on tier {tier}")

    def get_provider_status(self) -> Dict[str, Dict]:
        """
        Get status of all registered providers.

        Returns:
            Dict mapping provider name to status dict
        """
        status = {}

        for name, config in self.providers.items():
            breaker = self.circuit_breakers[name]

            status[name] = {
                "tier": config.tier.name,
                "models": config.models,
                "privacy_compatible": config.privacy_compatible,
                "is_healthy": breaker.is_healthy,
                "circuit_breaker_open": breaker.is_open,
                "failure_count": breaker.failure_count,
                "last_health_check": breaker.last_health_check,
            }

        return status


def build_local_router() -> ProviderRouter:
    """Build a router with a single local Ollama provider (used by demos)."""
    router = ProviderRouter()
    router.register(
        "ollama",
        OllamaProvider(),
        tier=Tier.LOCAL_FREE,
        models=["llama3.1:8b"],
        privacy_compatible=True,
    )
    return router


# Example usage
if __name__ == "__main__":

    async def main():
        # Create router
        router = ProviderRouter(
            on_failover=lambda old, new, name, err: print(
                f"FAILOVER: {old} → {new} (using {name}) due to: {err}"
            )
        )

        # Register providers
        router.register(
            "ollama",
            OllamaProvider(),
            tier=Tier.LOCAL_FREE,
            models=["llama3.1:8b", "mistral:7b"],
            privacy_compatible=True,
            priority=0,
        )

        router.register(
            "fireworks",
            FireworksProvider(),
            tier=Tier.CLOUD_CHEAP,
            models=["accounts/fireworks/models/llama-v3p1-8b-instruct"],
            priority=0,
        )

        router.register(
            "anthropic",
            AnthropicProvider(),
            tier=Tier.PREMIUM,
            models=["claude-3-5-sonnet-20241022"],
            priority=0,
        )

        # Test completion with failover
        try:
            response = await router.chat_completion(
                tier=Tier.LOCAL_FREE,
                model="llama3.1:8b",
                messages=[
                    {"role": "user", "content": "What is the capital of France?"}
                ],
                enable_failover=True,
            )

            print(f"Response: {response.content}")
            print(f"Model: {response.model}")

        except Exception as e:  # pylint: disable=broad-exception-caught
            print(f"Error: {e}")

        # Check provider status
        status = router.get_provider_status()
        print("\nProvider Status:")
        for name, info in status.items():
            print(f"  {name}: {info['tier']} - Healthy: {info['is_healthy']}")

    asyncio.run(main())
