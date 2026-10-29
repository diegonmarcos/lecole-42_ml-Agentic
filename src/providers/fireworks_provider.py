"""
Fireworks AI Provider - Tier 1 ($0.20-0.80/M tokens)

Optimized for fast, cost-effective inference with models like:
- llama-v3p1-8b-instruct ($0.20/M input, $0.20/M output)
- llama-v3p1-70b-instruct ($0.90/M input, $0.90/M output)
- mixtral-8x7b-instruct ($0.50/M input, $0.50/M output)
"""

import asyncio
from typing import Optional

from .demo import run_provider_demo
from .openai_compatible import OpenAICompatibleProvider


class FireworksProvider(OpenAICompatibleProvider):
    """
    Fireworks AI provider implementation.

    Features:
    - 2-3x faster than OpenAI for same model sizes
    - Generous rate limits (up to 16k tokens/sec)
    - Streaming support
    - Health check with /models endpoint
    """

    DISPLAY_NAME = "Fireworks"
    API_KEY_ENV = "FIREWORKS_API_KEY"

    # Pricing per 1M tokens (input, output)
    PRICING = {
        "accounts/fireworks/models/llama-v3p1-8b-instruct": (0.20, 0.20),
        "accounts/fireworks/models/llama-v3p1-70b-instruct": (0.90, 0.90),
        "accounts/fireworks/models/mixtral-8x7b-instruct": (0.50, 0.50),
        "accounts/fireworks/models/mixtral-8x22b-instruct": (1.20, 1.20),
    }
    DEFAULT_MODEL = "accounts/fireworks/models/llama-v3p1-8b-instruct"
    DEFAULT_PRICING = (0.20, 0.20)

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.fireworks.ai/inference/v1",
    ):
        """
        Initialize Fireworks provider.

        Args:
            api_key: Fireworks API key (or set FIREWORKS_API_KEY env var)
            base_url: API base URL (default: production endpoint)
        """
        super().__init__(base_url=base_url, api_key=api_key)


# Example usage
if __name__ == "__main__":
    asyncio.run(
        run_provider_demo(
            FireworksProvider(),
            "Fireworks",
            "accounts/fireworks/models/llama-v3p1-8b-instruct",
        )
    )
