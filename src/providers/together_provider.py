"""
Together AI Provider - Tier 1 ($0.20-0.80/M tokens)

Optimized for cost-effective inference with models like:
- meta-llama/Llama-3.1-8B-Instruct-Turbo ($0.18/M input, $0.18/M output)
- meta-llama/Llama-3.1-70B-Instruct-Turbo ($0.88/M input, $0.88/M output)
- mistralai/Mixtral-8x7B-Instruct-v0.1 ($0.60/M input, $0.60/M output)
"""

import asyncio
from typing import Optional

from .demo import run_provider_demo
from .openai_compatible import OpenAICompatibleProvider


class TogetherProvider(OpenAICompatibleProvider):
    """
    Together AI provider implementation.

    Features:
    - Competitive pricing (often cheapest for Llama models)
    - Fast inference with Turbo models
    - OpenAI-compatible API
    - JSON mode support
    """

    DISPLAY_NAME = "Together"
    API_KEY_ENV = "TOGETHER_API_KEY"

    # Pricing per 1M tokens (input, output)
    PRICING = {
        "meta-llama/Llama-3.1-8B-Instruct-Turbo": (0.18, 0.18),
        "meta-llama/Llama-3.1-70B-Instruct-Turbo": (0.88, 0.88),
        "meta-llama/Llama-3.1-405B-Instruct-Turbo": (3.50, 3.50),
        "mistralai/Mixtral-8x7B-Instruct-v0.1": (0.60, 0.60),
        "mistralai/Mixtral-8x22B-Instruct-v0.1": (1.20, 1.20),
        "Qwen/Qwen2.5-7B-Instruct-Turbo": (0.30, 0.30),
    }
    DEFAULT_MODEL = "meta-llama/Llama-3.1-8B-Instruct-Turbo"
    DEFAULT_PRICING = (0.18, 0.18)

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.together.xyz/v1",
    ):
        """
        Initialize Together provider.

        Args:
            api_key: Together API key (or set TOGETHER_API_KEY env var)
            base_url: API base URL (default: production endpoint)
        """
        super().__init__(base_url=base_url, api_key=api_key)


# Example usage
if __name__ == "__main__":
    asyncio.run(
        run_provider_demo(
            TogetherProvider(), "Together", "meta-llama/Llama-3.1-8B-Instruct-Turbo"
        )
    )
