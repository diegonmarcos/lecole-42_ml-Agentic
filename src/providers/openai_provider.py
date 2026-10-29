"""
OpenAI Provider - Tier 3 ($2.50-15/M tokens)

Premium models for complex tasks:
- gpt-4o ($2.50/M input, $10/M output)
- gpt-4o-mini ($0.15/M input, $0.60/M output)
- gpt-4-turbo ($10/M input, $30/M output)
"""

import asyncio
from typing import Optional

from .demo import run_provider_demo
from .openai_compatible import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    """
    OpenAI provider implementation.

    Features:
    - Industry-standard API (OpenAI-compatible)
    - Function calling and JSON mode
    - Vision capabilities (gpt-4o, gpt-4-turbo)
    - Streaming support
    """

    DISPLAY_NAME = "OpenAI"
    API_KEY_ENV = "OPENAI_API_KEY"

    # Pricing per 1M tokens (input, output)
    PRICING = {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.00, 30.00),
        "gpt-4-turbo-2024-04-09": (10.00, 30.00),
        "gpt-4": (30.00, 60.00),
        "gpt-3.5-turbo": (0.50, 1.50),
        "gpt-3.5-turbo-0125": (0.50, 1.50),
    }
    DEFAULT_MODEL = "gpt-4o"
    DEFAULT_PRICING = (2.50, 10.00)

    def __init__(
        self, api_key: Optional[str] = None, base_url: str = "https://api.openai.com/v1"
    ):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (or set OPENAI_API_KEY env var)
            base_url: API base URL (default: production endpoint)
        """
        super().__init__(base_url=base_url, api_key=api_key)


# Example usage
if __name__ == "__main__":
    asyncio.run(run_provider_demo(OpenAIProvider(), "OpenAI", "gpt-4o-mini"))
