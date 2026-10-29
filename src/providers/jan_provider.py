"""
Jan Provider - Privacy Mode (Tier 0, $0 cost)

100% local inference with privacy-first design:
- Runs entirely on-device (CPU or GPU)
- No telemetry or analytics
- OpenAI-compatible API
- Supports GGUF models from HuggingFace

Models supported:
- llama-3.1-8b-instruct
- mistral-7b-instruct
- phi-3-mini-4k-instruct
- Any GGUF model from HuggingFace
"""

import asyncio
from typing import Dict, List, Optional

from .demo import run_provider_demo
from .openai_compatible import OpenAICompatibleProvider


class JanProvider(OpenAICompatibleProvider):
    """
    Jan.ai provider implementation for privacy-first local inference.

    Features:
    - 100% local execution (no API calls)
    - Zero cost (runs on your hardware)
    - Privacy-compatible (GDPR/HIPAA friendly)
    - OpenAI-compatible API
    - GPU acceleration support
    """

    DISPLAY_NAME = "Jan"
    API_PREFIX = "/v1"
    EXTRA_COMPLETION_FIELDS = {"stream": False}

    def __init__(self, base_url: str = "http://localhost:1337"):
        """
        Initialize Jan provider.

        Args:
            base_url: Jan API base URL (default: http://localhost:1337)

        Note:
            Jan must be running locally. Start with: `jan serve`
        """
        super().__init__(base_url=base_url)

    def get_cost(  # pylint: disable=unused-argument  # Jan is free
        self, input_tokens: int, output_tokens: int, model: Optional[str] = None
    ) -> float:
        """
        Calculate cost in USD for token usage.

        Jan is always free (local inference).

        Returns:
            Cost in USD (always 0.0)
        """
        return 0.0

    async def list_models(self) -> List[Dict[str, str]]:
        """
        List available models in Jan.

        Returns:
            List of model dicts with 'id', 'name', 'size' keys
        """
        session = await self._get_session()

        async with session.get(self._url("/models")) as resp:
            resp.raise_for_status()
            data = await resp.json()

        return [
            {
                "id": model["id"],
                "name": model.get("name", model["id"]),
                "size": model.get("size", "unknown"),
            }
            for model in data.get("data", [])
        ]

    async def download_model(self, model_id: str) -> bool:
        """
        Download a model to Jan.

        Args:
            model_id: HuggingFace model ID (e.g., "TheBloke/Llama-2-7B-Chat-GGUF")

        Returns:
            True if download started successfully
        """
        session = await self._get_session()

        async with session.post(
            self._url("/models/download"), json={"model": model_id}
        ) as resp:
            return resp.status == 200


async def _demo() -> None:
    provider = JanProvider()

    if not await provider.health_check():
        print("Jan is not running. Start it with: jan serve")
        return

    # List models
    models = await provider.list_models()
    print(f"\nAvailable models: {len(models)}")
    for model in models[:3]:
        print(f"  - {model['id']} ({model['size']})")

    if models:
        await run_provider_demo(provider, "Jan", models[0]["id"])
    else:
        await provider.close()


# Example usage
if __name__ == "__main__":
    asyncio.run(_demo())
